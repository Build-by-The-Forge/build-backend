# Phase 1 — M2: Schema Drift Investigation (read-only)

**Date:** 2026-10-03 · **Scope:** backend only · **Changes made:** none (no migration, model, data or code edits)

Triggered during M2 commit 11, when `alembic check` against a freshly migrated database reported large differences between the ORM models and the migrated schema. This report establishes the blast radius and classifies each difference before any fix.

## 1. Method

1. Fresh PostgreSQL 17 container; `alembic upgrade head` (revision `0018`). Nothing calls `create_all()`: the app only does that for SQLite (`app/main.py: initialize_database`), and the probes below do not run the app lifespan.
2. `alembic.autogenerate.compare_metadata` (with `compare_type`) between `Base.metadata` (all models) and the migrated database, grouped by table.
3. Plain ORM `SELECT` per drifted model against the migrated database.
4. API smoke test through the real ASGI app (`httpx.ASGITransport`) as a verified `admin` member of a seeded tenant: every endpoint that touches a drifted table, in a realistic order (create course → topics → learning outcomes → reference materials → assessment question → archive).
5. History: `git log` of `alembic/versions/0005_add_catalogue_schema.py` and `app/infrastructure/db/models/catalogue.py`; PRD §10–§12 for the intended structure.

Limitations: server defaults are not compared (`compare_server_default` is off); domains with no reported drift (assessment tables, curriculum sources/benchmarks/adoptions, content) were not smoke-tested here.

## 2. Root cause

- Migration `0005` (commit `ab58979`, 2026-08-02) created the original catalogue design: curriculum versions per **course**, topics per **curriculum version**, `is_active`/`is_published` flags.
- Commit `e70391d` (2026-08-03) redesigned the catalogue — topics per **course**, curriculum versions per **programme** with effective/expiry **sessions**, `status`/`updated_at` on every entity, `material_type`, `prerequisite_type` — across domain, mappers, repositories and models, **without a migration**. Later commits (`2526f20`, `523434e`) touched the models and 0005 only for typing/formatting.
- The test suite builds tables from the models (`create_all` on SQLite), and CI (`.github/workflows/ci.yml`) runs only `pytest`. Nothing ever ran the application against a migrated database, so the gap was invisible.

**Which side is intended:** the models. PRD §10 defines `Course → Topic → Subtopic → Concept` (topics belong to courses) and §11.2 requires curricula "versioned by session or effective period"; the domain layer, mappers and repositories all follow the models. Migration `0005` is the stale side.

## 3. Runtime impact (migrated PostgreSQL 17)

| Endpoint | Result |
|---|---|
| `GET /identity/tenant-context` (control) | 200 |
| `GET /catalogue/courses/` with no courses | 200 |
| `POST /catalogue/courses/` | **201**, row written |
| `GET /catalogue/courses/` with one course | **500** `column topics.course_id does not exist` |
| `GET`, `PATCH`, `POST …/publish`, `POST …/archive` on a course | **500** (same) |
| `POST`/`GET /catalogue/courses/{id}/topics`, `PATCH`/`archive` topic | **500** (same) |
| learning outcomes: create, list, patch, archive | **500** (same) |
| reference materials: create, list | **500** (same) |
| `POST /assessment/questions` | **500** (same) |

Every course repository query eager-loads `topics → learning_outcomes` and `reference_materials`, so once a single course exists the whole catalogue — and question creation, which validates the topic through the course — fails. The earlier `GET /catalogue/courses/` 200 (M2 commit 8 check) only passed because the list was empty. Assessment flows that need questions (assessments, attempts, results) are therefore unusable on a migrated database.

Direct ORM `SELECT` per model, each failing on a column the migrations never created:

| Table | First missing column | Columns actually in the database |
|---|---|---|
| `topics` | `course_id` | id, curriculum_version_id, sequence, title, slug, description, created_at |
| `learning_outcomes` | `status` | id, topic_id, sequence, description, created_at |
| `reference_materials` | `material_type` | id, course_id, title, author, citation, url, is_active, created_at |
| `curriculum_versions` | `programme_id` | id, course_id, version, is_published, notes, created_at |
| `course_prerequisites` | `prerequisite_type` | id, course_id, prerequisite_course_id |

## 4. Drift inventory and classification

Buckets: **A** harmless/historical (document) · **B** model stale (fix model) · **C** migration missing (corrective migration) · **D** runtime-breaking (high priority).

| Table | Drift (model vs migrated DB) | Runtime path | Bucket |
|---|---|---|---|
| `topics` | model: `course_id` (FK courses), `level`, `status`, `updated_at`, unique `(course_id, sequence)`; DB: `curriculum_version_id` (FK curriculum_versions), unique `(curriculum_version_id, sequence)` | all catalogue endpoints, question creation | **D** (cause: C) |
| `learning_outcomes` | model adds `status`, `updated_at` | topic/learning-outcome endpoints, course eager load | **D** (cause: C) |
| `reference_materials` | model adds `material_type`, `status`, `updated_at`; DB has `is_active` | reference endpoints, course eager load | **D** (cause: C) |
| `curriculum_versions` | model: `programme_id`, `name`, `version` VARCHAR(50), `effective_session_id`, `expires_session_id`, `status`, `course_ids`, `updated_at`; DB: `course_id`, `version` INTEGER, `is_published` | none — no repository or endpoint uses the model | **C**, dormant — needs a design decision first (§5) |
| `course_prerequisites` | model adds `prerequisite_type`, `status`, `created_at`, `updated_at` | none — no repository or endpoint uses the model | **C**, dormant |
| `devices`, `login_events`, `sessions` | DB has indexes the models do not declare (`idx_devices_device_fingerprint`, `idx_login_events_created_at`, `idx_login_events_user_id`, `idx_sessions_refresh_token_hash`, `idx_sessions_user_id`) | none (indexes only help) | **A** — declare them on the models to silence the check |
| `users.status` | DB `VARCHAR(50)`, model non-native enum (`VARCHAR(20)`) | none (values ≤ 20 chars) | **A** |
| `permissions`, `roles`, `role_assignments` | DB unique constraints not on the models | none | **A** — tables are removed by M2 commit 17 (D7) |
| `memberships` (0018) | none | — | clean |

No drift was reported for tenancy, assessment, curriculum-source/benchmark/adoption or content tables.

## 5. Decisions needed before fixing

1. **Corrective migration for the D tables** (`topics`, `learning_outcomes`, `reference_materials`): bring the schema to the model. No deployed backend database exists (M2 decision D1), so no production data is at risk, but the migration should still refuse to run, as 0018 does, if old-shape rows exist rather than guess. Existing topics are convertible if ever needed: `topics.curriculum_version_id → curriculum_versions.course_id`.
2. **`curriculum_versions` / `course_prerequisites`:** the model's programme/session-scoped curriculum version overlaps the curriculum domain added later (benchmark curricula and institutional adoptions, migrations 0011–0014, PRD §11 "CCMAS + FUTA adoption = effective curriculum"). Migrating the model as-is may cement a design the curriculum domain has since superseded. Options: migrate to the model, remove the unused models, or defer until curriculum work. Neither has a runtime path today.
3. **Bucket A:** declare the existing identity indexes on the models (small, separate), leave role-table constraints to commit 17, accept `users.status` length.

## 6. Recommendation

- Fix bucket **D** before M2 continues: one corrective migration plus a PostgreSQL smoke run of the catalogue endpoints and question creation. Commit 12 (invitations) does not touch these tables, but leaving the academic core unusable on the production database type undermines every later verification.
- Make production-schema verification a standing gate (M6 at the latest, ideally sooner): a CI job on PostgreSQL 17 that runs `alembic upgrade head`, `alembic check` (zero diff, or an explicit allow-list for bucket A), and the integration suite against the migrated database without `create_all`. SQLite stays for fast unit tests. This would have caught this drift, the `device_id` FK 500 and the `seed_tenant_membership` FK ordering.
- Migration numbering: the M2 design (§4) reserves `0019` for `tenant_invitations`; a corrective catalogue migration would take `0019` and shift the later numbers.
