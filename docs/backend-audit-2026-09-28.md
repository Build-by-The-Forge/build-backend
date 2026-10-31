# BUILD BACKEND — FULL REPOSITORY AUDIT

Audited: 2026-09-28, branch `feat/learning-content`, HEAD `872119a`.
Method: direct repository inspection (Read/Grep/Glob across `app/`, `alembic/`, `tests/`, `docs/`), a full `pytest --cov=app` run, and targeted evidence-gathering rather than a line-by-line read of every file. Where a claim could not be verified from this repo, it is marked **Not found in repository** rather than guessed. This is not an exhaustive line-by-line read of all ~46 DB models, all migration `downgrade()` bodies, or every API schema file — those gaps are called out explicitly so they aren't mistaken for "checked, and fine."

---

## 1. Executive Summary

BUILD backend is a genuinely well-architected modular monolith (clean/hexagonal layering: `domain` → `application` → `infrastructure` → `api`, with `core` for cross-cutting concerns). The catalogue, curriculum/benchmark, assessment/CBT, and content-ingestion domains are substantially implemented, consistently tenant-scoped at the repository/query layer, covered by 324 passing tests (86% line coverage), and the newest work (content ingestion + AI service gateway, Slice 4B) is the most mature code in the repo — a properly enforced job state machine, idempotent webhook handling, and a correctly-implemented constant-time HMAC signature check.

Against that, there is one finding that overrides most others: **the password hasher and the JWT/token service wired into the dependency-injection container are non-functional stubs, not the real thing.** `Argon2PasswordHasher.hash()` returns `f"hashed:{password}"` — a reversible string transform, not Argon2. `JWTTokenService.validate()` returns `bool(token)` — true for any non-empty string — and `decode()` returns `{"sub": token}` with no signature check at all. These are the classes actually used by every protected route via `app/core/dependencies.py:get_current_principal`. Practically: anyone who knows (or guesses) a user's UUID can authenticate as that user with a hand-crafted string, "logout" has no effect on access, and stored "password hashes" are not cryptographically protected. This is presented plainly and factually below (Section 6, Section 17) — it is very likely a deliberate placeholder from early scaffolding that was never swapped for real implementations before other work built on top of it, and it is the single highest-priority item before any real user data touches this system.

Beyond that: the identity/authz *design* (RBAC, tenant-context resolution, permission dependency chain) is sound; documentation (README, ADRs) is generally high quality but is **stale relative to the code** — it doesn't mention the content/AI-ingestion module at all despite four migrations and ~20 endpoints existing for it, and claims "scoring... intentionally deferred" when scoring is implemented and tested. There is no rate limiting, no email delivery (password-reset tokens are returned directly in the API response), no user learning/progress tracking, and no OCR/RAG/embedding code in this repo (consistent with that being AI-service-owned — a clean boundary).

---

## 2. Repository Inventory

```text
app/
├── api/            FastAPI routers + Pydantic schemas (assessment, catalogue, curriculum, content, identity, health)
├── application/     Commands, handlers, services (CQRS-ish) per domain
├── bootstrap/        container.py — manual DI container wiring services to infra
├── core/              config, authorization (RBAC), dependencies (auth guards), exceptions, logging, metrics, middleware, principal, responses, security (headers), tenant/tenant_context, tracing
├── db/                 SQLAlchemy declarative Base, async engine/session, mixins
├── domain/            Aggregates/value objects/domain errors: identity, tenant, catalogue, curriculum, assessment, content, repositories (interfaces)
├── events/            DomainEvent base + in-process EventBus
├── infrastructure/  ORM models (app/infrastructure/db/models/*), repositories, mappers, unit-of-work, identity/security adapters, AI gateway
└── middleware/      empty package (__init__.py only — no content)
alembic/versions/    0001–0017, sequential, matching domain build order
docs/                 7 ADRs, architecture specs, contracts, vision docs, 2 prior inspection/roadmap reports
scripts/seed_futa.py  Seeds one tenant (FUTA) with 9 faculties / 52 departments / programmes / levels / sessions
tests/                324 tests: domain, integration (API+persistence+application per module), a few root-level platform tests
```

`app/middleware/` is an empty stub — `RequestContextMiddleware` and `SecurityHeadersMiddleware` actually live in `app/core/middleware.py` and `app/core/security.py`. README's project-layout diagram also lists `app/integrations/`, `app/telemetry/`, `app/workers/` — **none of these three directories exist**; only `app/bootstrap/` and `app/events/` from that list are real. This is a **documentation/reality mismatch**, not a functional gap.

There is no `ai-service` directory or submodule here — consistent with the stated two-repo split. Nothing in this repo can verify ai-service's internals; all AI-service claims below are strictly about this backend's side of the boundary.

---

## 3. Technology Stack

| Technology | Version (pyproject.toml) | Where Defined | Purpose | Assessment |
|---|---|---|---|---|
| Python | `>=3.12` required; Docker uses `python:3.13-slim`; CI pins `3.13`; `[tool.mypy] python_version = "3.13"`; `[tool.black] target-version = ["py314"]` | pyproject.toml:9,46,49; Dockerfile:1; ci.yml:14 | runtime | **Inconsistent**: four different version references (3.12 floor, 3.13 actual runtime/CI/mypy, 3.14 black target). Not broken, but sloppy — worth pinning one value everywhere. |
| FastAPI | `>=0.115.0` (installed: 0.139.2 per `.venv`) | pyproject.toml:11 | web framework | current |
| Pydantic | `>=2.9.0` | pyproject.toml:13 | validation | current |
| SQLAlchemy | `[asyncio]>=2.0.0` (installed 2.0.51) | pyproject.toml:15 | ORM | current, async-first, correct extra |
| Alembic | `>=1.13.0` (installed 1.18.5) | pyproject.toml:16 | migrations | current |
| asyncpg | `>=0.27.0` | pyproject.toml:17 | Postgres driver | current |
| redis | `>=5.0.0` | pyproject.toml:18 | cache/queue client | **installed but unused** — see §22 |
| httpx | `>=0.27.0,<0.28.0` | pyproject.toml:19 | HTTP client (AI gateway) | capped below 0.28 — will block routine upgrades; installed version in `.venv` is actually 0.27.2/0.28.1 depending on env (two venvs present, see §23) |
| structlog | `>=24.4.0` | pyproject.toml:20 | structured logging | current, actually used |
| prometheus-client | `>=0.20.0` | pyproject.toml:21 | metrics | current, minimally used (2 counters) |
| opentelemetry-sdk | `>=1.30.0` | pyproject.toml:22 | tracing | configured with a **NoOpExporter** — spans created, never exported anywhere (§20) |
| pytest / pytest-asyncio / pytest-cov / pytest-env | dev extras | pyproject.toml:27-30 | testing | current, well used |
| ruff | `>=0.6.0`, select `["E","F","I"]`, line-length 130 | pyproject.toml:32,38-43 | lint | run in CI |
| mypy | `>=1.11.0`, `strict = true`, but `app.application.identity.*` and `tests.*` are exempted via override | pyproject.toml:33,48-60 | type check | **configured but not run in CI** (ci.yml has no mypy step) |

---

## 4. Architecture

Confirmed by direct inspection, matches README's diagram:

```text
HTTP request
  → RequestContextMiddleware (request_id, timing, metrics) + SecurityHeadersMiddleware
  → FastAPI route (app/api/**)
  → Depends(get_current_principal) — Bearer token → "authenticated" principal
  → Depends(get_current_tenant_context) — X-Tenant-Slug header → tenant + membership lookup
  → Depends(require_permission(...)) — static RBAC check (app/core/authorization.py)
  → Application service / command handler (app/application/**)
  → Domain aggregate invariants (app/domain/**)
  → Repository → Unit of Work → SQLAlchemy async session → Postgres/SQLite
```

Dependency injection is a hand-rolled `Container` class (`app/bootstrap/container.py`) built once per-router-module at import time (`container = build_container()` at module scope in `app/api/identity.py`, `app/api/catalogue/courses.py`, `app/api/content/jobs.py`, etc.) rather than through FastAPI's own `Depends`-based DI for services. This works but means the container is constructed once at import time, not per-request — fine for stateless services, but worth knowing since it diverges from the per-request `Depends(get_unit_of_work)` pattern used for auth.

`UserService`/`CourseService`/`QuestionService` are constructed with `repository=None` at registration time (`app/bootstrap/container.py:76-98`) — a dead/vestigial constructor parameter, since every actual code path checks `if self.uow_factory is not None` first and the `uow_factory` is always supplied. Not a bug, but confusing: a reader could reasonably assume `repository=None` means "broken," when it's just an unused legacy parameter.

---

## 5. Database

**46 SQLAlchemy models** across 9 files, confirmed by direct grep of every `class *Model(Base)` declaration:

| Domain | Models | File |
|---|---|---|
| Identity | UserModel, UserProfileModel, RoleModel, PermissionModel, RoleAssignmentModel (+`role_permissions_table` association), SessionModel, DeviceModel, RefreshTokenModel, VerificationTokenModel, PasswordResetTokenModel, AuditLogModel, LoginEventModel, SecurityEventModel | `app/infrastructure/identity/models.py` |
| Tenant/academic structure | TenantModel, FacultyModel, DepartmentModel, ProgrammeModel, LevelModel, AcademicSessionModel, SemesterModel, MembershipModel | `app/infrastructure/db/models/tenant_core.py` |
| Catalogue | CourseModel, CurriculumVersionModel, TopicModel, LearningOutcomeModel, ReferenceMaterialModel, CoursePrerequisiteModel | `app/infrastructure/db/models/catalogue.py` |
| Assessment | QuestionModel, QuestionOptionModel, AssessmentModel, AssessmentQuestionModel (snapshot), AssessmentAttemptModel, AttemptAnswerModel, AssessmentAttemptResultModel | `app/infrastructure/db/models/assessment.py` |
| Curriculum | CurriculumSourceModel, CurriculumSnapshotModel | `app/infrastructure/db/models/curriculum.py` |
| Institutional curriculum | InstitutionalAdoptionModel, CurriculumOverrideModel | `app/infrastructure/db/models/institutional_curriculum.py` |
| Benchmark | BenchmarkCurriculumModel, BenchmarkCourseModel, BenchmarkTopicModel, BenchmarkLearningOutcomeModel | `app/infrastructure/db/models/benchmark.py` |
| Benchmark audit | BenchmarkAuditLogModel | `app/infrastructure/db/models/benchmark_audit.py` |
| Content | ContentSourceModel, ContentAssetModel, ContentIngestionJobModel | `app/infrastructure/db/models/content.py` |

**Migrations**: `alembic/versions/0001` through `0017`, filenames tracking feature build order 1:1 (identity → tenant → catalogue → assessment(x4) → curriculum sources/benchmarks/governance/adoptions → content(x3)). I confirmed the migration set exists and enumerated it but did **not** individually verify every `downgrade()` body or trace every `down_revision` chain link-by-link — that's a follow-up item, not a claim made here.

**Tenant scoping**: `tenant_id` (or equivalent FK chain) is present and consistently filtered on in every repository I inspected (assessment, catalogue, content — see §7/§17 for the IDOR analysis). `app/domain/repositories/tenant.py` shows 0% test coverage in the pytest-cov run, meaning the tenant repository *interface* itself is exercised only through its concrete implementations, not directly — not a defect, just worth noting.

**Duplicate/dead schema**: `RoleModel`/`PermissionModel`/`RoleAssignmentModel`/`role_permissions_table` are fully modeled (from migration 0001/0002) with relationships wired on `UserModel`, but **`app/core/authorization.py` never queries them** — the live authorization system is a hardcoded Python dict (`ROLE_PERMISSIONS`) keyed by a free-text `role` string on `MembershipModel`, unrelated to these DB tables. This is two parallel RBAC schemas, one live, one fully built but unused. Not dangerous, but real duplication/tech debt.

**Raw SQL**: no evidence of raw SQL string interpolation found in the infrastructure layer during inspection — all queries use SQLAlchemy Core/ORM `select()` constructs.

---

## 6. Identity & Authentication

Traced end-to-end: `app/api/identity.py` → `app/application/identity/{user_service,handlers,commands}.py` → `app/infrastructure/identity/*` + `app/infrastructure/security/*` → `app/infrastructure/identity/models.py`.

| Mechanism | Status | Evidence |
|---|---|---|
| Registration | **Implemented** | `POST /identity/users` (`app/api/identity.py:23`) → `RegisterUserHandler` (`app/application/identity/handlers.py:30`). Email validated via regex value object (`app/domain/identity/value_objects.py:6-13`); password enforced ≥12 chars (`value_objects.py:17-22`, no complexity/entropy check beyond length). Duplicate email → 409 "User already exists". |
| Email verification | **Missing** | `UserModel.status` defaults to `PENDING_VERIFICATION` and `is_verified: bool` exists (`app/infrastructure/identity/models.py:55-60`), and a `VerificationTokenModel` table exists, but no handler, endpoint, or email-sending code that issues/consumes a verification token was found. Column exists; workflow does not. |
| Login | **Implemented, but broken underneath** | `POST /identity/authenticate` → `AuthenticateUserHandler` (`handlers.py:70-115`). Correctly returns a single generic "invalid credentials" (401) for both unknown-email and wrong-password (no message-based account enumeration on login). |
| Password hashing | **CRITICAL — stub, not Argon2** | `app/infrastructure/security/argon2_password_hasher.py:5-10`: `hash()` returns `PasswordHash(f"hashed:{password.value}")`; `verify()` just re-derives and string-compares. No Argon2 (or any) cryptographic hashing occurs despite the class name and README's claim ("Argon2 password hashing"). A second, identical stub exists at `app/domain/identity/value_objects.py:35-37` and `app/infrastructure/identity/password_hasher.py:4-9` (this second one appears **unused dead code** — 0% coverage, no importers found via grep). |
| JWT / tokens | **CRITICAL — stub, not JWT** | `app/infrastructure/security/jwt_token_service.py:4-15`: `issue_access_token()` returns `f"access:{subject}"`; `validate()` returns `bool(token)` (true for any non-empty string); `decode()` returns `{"sub": token}` unconditionally. No signing, no signature verification, no expiry, no algorithm. This is the class actually registered in the DI container (`app/bootstrap/container.py:46,68,72,198,202`) and used by `app/core/dependencies.py:get_current_principal` (lines 27-77), the auth guard on **every** protected route. |
| Sessions/refresh | **Modeled but not actually load-bearing** | `SessionModel`/`RefreshTokenModel` exist with proper `revoked_at`/`expires_at` fields, and `AuthenticateUserHandler` does create a real session row with `refresh_token_hash`. `LogoutSessionHandler` does call `session.revoke()`. **But `get_current_principal` (the function that actually gates API access) never reads the sessions table at all** — it only checks `token_service.validate(token)` (always true) and that the decoded user ID exists. Net effect: logout, session revocation, and refresh-token rotation are fully implemented as *data operations* but have **zero effect on actual request authorization**, because nothing downstream checks them. This is the most important individual finding in the whole audit next to the hasher itself, because the code *looks* complete (there's a real logout endpoint, a real session table, real revocation logic) while the auth guard silently bypasses all of it. |
| Password reset | **Implemented, but leaks the token + inherits the fake hasher** | `POST /identity/forgot-password` → `ForgotPasswordHandler` (`handlers.py:167-191`): generates a UUID token, stores its (fake) hash with a 1-hour expiry, single-use via `consume_password_reset_token`. Correct-shaped design (hashed storage, expiry, single consumption). **But** `app/api/identity.py:179-186` returns the raw `reset_token` directly in the JSON response body — there is no email-sending code anywhere in the repo (`grep` for smtp/send_email/mailer/sendgrid found nothing outside docs/migrations). As implemented today, **anyone who knows a registered email can call this endpoint and receive that account's password-reset token directly**, then reset the password — a full account-takeover path via a public, unauthenticated endpoint. This is very plausibly a placeholder pending an email-delivery integration, but as shipped it is a real vulnerability, not a theoretical one. |
| Rate limiting / brute force | **Missing** | No slowapi, no custom throttling middleware, no Redis-backed rate limiter found anywhere. README roadmap lists "Rate limiting, caching, and background queues" as future work — confirmed accurate. |
| Account enumeration | **Login: not vulnerable. Registration: vulnerable.** | Login returns identical 401 regardless of cause (good). Registration returns a distinct 409 "User already exists" for a duplicate email (`handlers.py:44`) vs. 201/422 otherwise — this lets an attacker enumerate registered emails via the registration endpoint. Low/medium severity, common in many systems, worth fixing before launch. |
| Secrets | **CRITICAL config gap** | No dedicated JWT signing secret exists in `Settings` at all (consistent with there being no real JWT). AI-service secrets (`ai_service_api_key`, `ai_service_webhook_secret`) default to hardcoded, publicly-visible-in-source values (`app/core/config.py:19-25`: `"build-ai-dev-secret-key"`, `"build-ai-dev-webhook-secret"`) with **no startup check that fails in `production` mode if these are left at default**. `app_environment` is validated against an allowed set but nothing cross-checks environment against secret strength. |

**Severity summary for this section**: password hashing and token validation being non-functional stubs wired into production code paths is **CRITICAL** — this is not a "weak" implementation, it is the *absence* of the security control its name promises. The session/logout-has-no-effect finding is **CRITICAL** for the same reason (it's a false sense of security, not just a missing feature). The forgot-password token leak is **HIGH** (real, exploitable, but requires knowing a target email and the platform not yet having live user data). Missing rate limiting is **MEDIUM** given no brute-force-relevant secret exists yet to protect. Registration enumeration is **LOW**.

---

## 7. Authorization & Multi-Tenancy

The *design* here is good and is worth crediting separately from the broken layer underneath it.

- **Permission model**: `app/core/authorization.py` defines a `Permission` StrEnum (29 permissions spanning catalogue, assessment, curriculum-source, content) and a static `ROLE_PERMISSIONS: dict[str, frozenset[Permission]]` for six roles: `student`, `lecturer`, `hod`, `faculty_admin`, `admin`, `owner`. `admin`/`owner` get `frozenset(Permission)` (all permissions).
- **Chain**: `Depends(get_current_principal)` (Bearer token → user) → `Depends(get_current_tenant_context)` (`X-Tenant-Slug` header → active `Tenant` → active `Membership` → role) → `Depends(require_permission(Permission.X))` (checks `authorization.can(context, permission)`). Traced fully in `app/core/dependencies.py:80-131`.
- **Tenant resolution correctness**: `get_current_tenant_context` explicitly checks `tenant.is_active` and `membership.is_active`, returning 403 otherwise (`dependencies.py:94-98,103-107`) — correct fail-closed behavior.
- **IDOR / cross-tenant leakage**: inspected `SqlAlchemyQuestionRepository`, `SqlAlchemyAssessmentRepository`, `SqlAlchemyAttemptRepository`, `SqlAlchemyAttemptAnswerRepository`, `SqlAlchemyAttemptResultRepository` (`app/infrastructure/assessment/repositories.py`) and the catalogue `courses.py` route — **every read/write path takes `tenant_id` and applies it as a `WHERE` filter at the query level**, not just in application-layer conditionals. This is the correct pattern (filtering at the DB boundary, matching the "Engineering Conventions" the README itself states) and I did not find a counterexample in the modules inspected. Content module (`app/api/content/jobs.py`) is likewise consistently `context.tenant_id`-scoped.
- **Caveat**: this authorization design is only as strong as the authentication step feeding it `context.user_id` — since that step is the broken token stub from §6, a forged principal sails straight through an otherwise well-built tenant/permission chain. The RBAC and tenant isolation logic is not itself the vulnerability; it's downstream of one.
- **Duplicate RBAC schema**: see §5 — `RoleModel`/`PermissionModel`/`RoleAssignmentModel` DB tables exist and are unused by the live authorization path.

---

## 8. Academic Catalogue

Modeled hierarchy (confirmed via `app/domain/tenant/*` + `scripts/seed_futa.py`): `Tenant → Faculty → Department → Programme` (+ `Level`, `AcademicSession`, `Semester` as siblings), and separately `Course → Topic → {LearningOutcome, ReferenceMaterial}` under `Department`.

**Seed data** (`scripts/seed_futa.py`, only seed script in the repo) creates one tenant ("Federal University of Technology Akure" / slug `futa`) with 9 faculties and 52 departments, each department auto-generating one `Programme` with code `f"btech-{dept_code}"` (e.g. `btech-dsc`, `btech-mts`, `btech-imc`) and a 5-or-6-year duration.

**Canonical programme code verification** (requested specifically) — checked seed data and full-repo grep for `DTS`, `LIS`, `EDT`, `ITE`, `IMC`, `MTS`:

| Claim | Result | Evidence |
|---|---|---|
| `DTS` / `MTS` / `IMC` etc. as literal programme codes | **Not found in repository.** Programme codes generated are lowercase and department-code-based (`btech-dsc`, `btech-mts`, `btech-imc`), never the short canonical forms you described. | `scripts/seed_futa.py:164-172` |
| Data Science exists | Yes, as department `dsc` under School of Computing, generating programme `btech-dsc`. | `seed_futa.py:62` |
| Mathematical Sciences exists | Yes, department `mts` under School of Physical Sciences. | `seed_futa.py:103` |
| **Industrial Mathematics should NOT exist as a separate programme** | **Contradicted by current seed data** — `("sps", "Industrial Mathematics", "imm")` is seeded as its own department/programme (`btech-imm`), distinct from Mathematical Sciences (`mts`). | `seed_futa.py:105` |
| Industrial Chemistry = IMC | Department code is `imc` (lowercase), consistent in spirit, department `("sps", "Industrial Chemistry", "imc")`. | `seed_futa.py:106` |
| Library and Information Science | **Not found in repository** — no department/programme with this name or an `LIS`-shaped code exists anywhere in the seed list or codebase. | grep across `app/`, `scripts/` |
| Educational Technology / Industrial and Technology Education | **Not found in repository** — neither appears in the 52-department seed list or elsewhere. | grep across `app/`, `scripts/` |
| **Architecture represented separately from Environmental Technology** | **Contradicted by current seed data** — Architecture (`arc`) is seeded as one of 7 departments *under* "School of Environmental Technology" (slug `set`), alongside Building Technology, Estate Management, Industrial Design, Quantity Surveying, Urban and Regional Planning, Surveying and Geoinformatics — i.e. still grouped with the old Environmental Technology structure, not separated. | `seed_futa.py:80-87` |

**Conclusion for this section**: the canonical programme-code scheme you described does not exist literally anywhere in this repository, and two of the specific structural claims (Industrial Mathematics as non-separate, Architecture split from Environmental Technology) are directly contradicted by the one seed script that exists. Either the seed data predates a catalogue redesign that hasn't been implemented yet, or the canonical scheme lives only in an external spec not present here. This needs reconciliation before the seed script is trusted as source-of-truth data.

**Course/Topic/LearningOutcome/ReferenceMaterial**: fully modeled and tenant-scoped (`app/domain/catalogue/*`, `app/infrastructure/db/models/catalogue.py`), with a full CRUD+publish/archive lifecycle exposed via `app/api/catalogue/courses.py` (route inventory in §15). `CourseOffering` and `Prerequisite` domain files exist (`app/domain/catalogue/course_offering.py`, `prerequisite.py`) and `CoursePrerequisiteModel` has a DB table, but I did not confirm a corresponding API surface for prerequisites/offerings during this pass — flagged as **unverified**, not claimed either way.

---

## 9. CBT / Examination System

Lifecycle traced through `app/domain/assessment/*`, `app/application/assessment/*`, `app/infrastructure/assessment/repositories.py`, `app/api/assessment/*.py`:

```text
Question authored (draft)         Implemented — app/api/assessment/questions.py POST /questions
  → Question published            Implemented — POST /questions/{id}/publish
Assessment created                Implemented — POST /assessment/assessments
  → Questions attached (snapshot) Implemented — POST /assessment/assessments/{id}/questions
                                   (snapshots into AssessmentQuestionModel; published assessments
                                    reject further question additions — README confirms, matches code shape)
  → Assessment published          Implemented — POST /assessment/assessments/{id}/publish
Attempt started                   Implemented — POST /assessment/assessments/{id}/attempts
                                   (resumes an existing IN_PROGRESS attempt via get_active_for_user —
                                    app/infrastructure/assessment/repositories.py:241-255)
  → Questions delivered           Implemented — GET /assessment/attempts/{id}/questions
                                   (delivers from the immutable snapshot, excludes correct_option_index
                                    — confirmed by AssessmentScorer reading correct_option_index only
                                    at scoring time, never exposed pre-submission per README)
  → Answers submitted             Implemented — PUT /assessment/attempts/{id}/answers/{question_id}
                                   (one answer per attempt+question pair, idempotent PUT, rejected
                                    after submission — app/infrastructure/assessment/repositories.py:289-333)
  → Attempt submitted             Implemented — POST /assessment/attempts/{id}/submit
  → Scoring                       Implemented — app/domain/assessment/scoring.py (deterministic,
                                   see §9 detail below) — contradicts README's claim that scoring is
                                   "intentionally deferred"; tests exist: tests/domain/assessment/test_scoring.py,
                                   tests/integration/assessment/test_submit_scoring_integration.py
  → Result persisted & exposed    Implemented — GET /assessment/attempts/{id}/result,
                                   GET /assessment/assessments/{id}/results (gradebook-style listing)
Retake                            Not confirmed — no explicit "retake" endpoint found distinct from
                                   starting a new attempt after the first is submitted; not traced further
Timers / time limits              Not found in repository — no time-limit field or timer-enforcement
                                   logic located on Assessment/Attempt during this pass
Anti-cheating controls            Not found in repository
```

**Scoring** (`app/domain/assessment/scoring.py`, read in full): a pure, static `AssessmentScorer.score()` — for each snapshot question, compares `answer.selected_option_index` to `question.correct_option_index`, awards full marks or zero (no partial credit, no negative marking), sums into `total_score`/`max_score`, computes `percentage`, and `passed = total_score >= assessment.passing_score`. Simple and internally correct for what it does; no edge-case handling for ties (not applicable to this scoring shape) or partial credit (not attempted, not needed for single-answer MCQ).

**Idempotency**: attempt-start correctly resumes rather than duplicates an in-progress attempt. Answer submission uses `PUT` semantics (idempotent by design) scoped to `attempt_id + assessment_question_id`.

---

## 10. Question System

`app/domain/assessment/question.py` + `value_objects.py`: `QuestionType` enum declares `MCQ`, `TRUE_FALSE`, `SHORT_ANSWER`, `ESSAY` (`value_objects.py:98-102`), but `Question.create()` **unconditionally** enforces "at least 2 options" and "exactly one correct option" regardless of `question_type` (`question.py:63-69`) — meaning only MCQ (and, trivially, a 2-option TRUE_FALSE modeled as MCQ) is actually behaviorally supported today; `SHORT_ANSWER` and `ESSAY` are **referenced in the enum but not implemented** as distinct behaviors. Difficulty (`EASY`/`MEDIUM`/`HARD`) and a draft/published/archived lifecycle are implemented. Explanation field exists and is optional. Topic/learning-outcome linkage exists (`topic_id`, `learning_outcome_id` on `Question`). **No AI-generated-vs-human-authored distinction was found** — no `source`, `generated_by`, or `ai_generated` field on `Question`/`QuestionModel`; if AI-service-generated questions are meant to flow into this table, there is currently no way to tell them apart from human-authored ones at the schema level. No question versioning was found (unlike `ContentAsset`, which does have explicit `asset_version`/`parent_asset_id` — see §12 — the same pattern was not applied to `Question`).

---

## 11. User Learning & Progress

**Missing entirely.** Full route inventory (§15) shows no enrollment, progress, streak, weak-area, recommendation, or learning-history endpoints. Repo-wide grep for `enrolment|enrollment|streak|progress_percent|weak_area|recommendation|learning_history` returned no matches in `app/`. `AttemptResult`/`AssessmentAttemptResultModel` (§9) is the closest thing to "progress" data that exists, and it's per-attempt, not aggregated into any user-level learning model. README's roadmap lists "Student enrolment, progress, and learning history" under "CBT platform" as future work — confirmed accurate; nothing here contradicts that.

---

## 12. AI Service Integration

This is the newest and most carefully engineered part of the codebase (matches the recent commit history: Slices 4B.1–4B.4).

**Full lifecycle**, traced through `app/domain/content/*`, `app/application/content/*`, `app/infrastructure/content/*`, `app/api/content/*`:

```text
Content source registered      Implemented — app/api/content/sources.py (create/list/get/patch/
                                deprecate/revoke/activate) — ContentSource domain model with an
                                authority/lifecycle state machine
Asset uploaded + SHA-256 dedup Implemented — app/domain/content/asset.py: ContentAsset.create()
                                enforces a 64-hex-char SHA-256 (_HEX_64_PATTERN, line 12), and
                                create_version() explicitly rejects a "new version" whose hash
                                matches the current one (asset.py:136-139) — correct dedup logic.
                                Versioning is real: asset_version increments, parent_asset_id links
                                versions, old version flips to SUPERSEDED status.
Ingestion job created           Implemented — app/domain/content/job.py: ContentIngestionJob.create()
Job dispatched to AI service    Implemented — app/infrastructure/content/ai_gateway.py:
                                HttpAIServiceIngestionGateway.dispatch_ingestion_job() — httpx POST
                                to {AI_SERVICE_URL}/v1/ingest/dispatch, Bearer auth, idempotency key
                                (job_id+run+attempt), correlation ID, tenant header, distinct retryable
                                (502/503/504→retry) vs. terminal (401/403→auth error, other→rejected)
                                error classification
AI service processes            External — cannot inspect ai-service internals from this repo
Callback received               Implemented — POST /ingestion/callbacks
                                (app/api/content/jobs.py:385-461): body authenticated via HMAC
                                (X-Build-Signature: sha256=<hex>) OR a static Bearer token fallback
Job state updated                Implemented — enforced state machine (below)
Result exposed via API          Implemented — GET /jobs/{id}, GET /assets/{id}/jobs(/latest), GET /jobs
```

**HTTP client to AI service** (`app/infrastructure/content/ai_gateway.py`, read in full): `httpx.AsyncClient`, base URL from `settings.ai_service_url` (default `http://localhost:8001`), timeout from `settings.ai_service_timeout_seconds` (default 60s), `settings.ai_service_max_retries` is defined in config (default 3) **but I did not find it actually consumed inside the gateway's dispatch logic** — the gateway raises a typed, retryable-flagged exception on transient failure, but the retry loop itself appears to live in the job/service layer (`ContentIngestionJobService`/job state machine's `schedule_retry`), not inside the HTTP client — consistent design, just noting `max_retries` isn't directly read in this file.

**Authentication to AI service**: static Bearer token — `Authorization: Bearer {settings.ai_service_api_key}` on every outbound call. Default value is the hardcoded `"build-ai-dev-secret-key"` (§6, §17).

**Webhook/callback protocol (HMAC)**: `app/infrastructure/content/ai_gateway.py:35-57`. `compute_webhook_signature`/`verify_webhook_signature` use `hmac.new(secret, payload_bytes, hashlib.sha256)` and — importantly — **`hmac.compare_digest()` for the comparison**, which is the correct constant-time comparison (not a naive `==`). Signature format `sha256=<hex>`, matching common webhook conventions (e.g. GitHub-style). This is genuinely solid crypto usage. Gap: **no timestamp or nonce in the signed payload**, so a captured valid callback could in principle be replayed; this is partially mitigated by `event_id`-based idempotency (`ContentIngestionJob.is_event_processed`/`record_event_processed`, `job.py:351-358`) and by the job state machine rejecting stage transitions once a job is terminal, but true replay protection (a signed timestamp with a rejection window) is absent. Rated **MEDIUM** given the idempotency mitigation.

**SHA-256 dedup**: correctly implemented — format-validated (64 hex chars), lowercase-normalized, and version-creation explicitly forbids identical-hash "new versions" (§12 above). No cross-source or cross-tenant dedup was checked (i.e., whether the same file hash uploaded to two different tenants is deduplicated or intentionally kept separate) — not verified either way.

**Job state machine** (`app/domain/content/job.py`, read in full): `IngestionStatus` transitions are **enforced, not just labeled** — every transition method (`queue()`, `record_dispatch()`, `start()`, `progress_to_extracted/chunked/indexed()`, `complete()`, `fail()`, `schedule_retry()`) checks the current status and raises `ValueError` on an illegal transition. `is_stale_callback()` correctly detects and can reject callbacks belonging to a superseded run/attempt/task. `schedule_retry()` correctly respects `max_attempts` and `is_retryable`. This is the best-engineered state machine in the codebase.

**Failure handling**: AI-service timeouts/network errors/5xx are caught and raised as a typed `AIServiceGatewayError` with `is_retryable` set appropriately; the dispatch API endpoint (`app/api/content/jobs.py:357-379`) maps that to a `502` response. Job `fail()` records a full `attempt_history` entry (attempt number, stage at failure, error code/message/details, timestamp) — good for debuggability. No explicit dead-letter queue was found; terminal failure is simply "status=FAILED, attempt_count >= max_attempts, schedule_retry() now raises."

**OCR / RAG / embeddings / vector / chunk**: repo-wide case-insensitive grep for `embedding|vector_search|\brag\b|knowledge_tree|chunk(s|ing)?|pgvector` returned **zero matches in `app/`**. This is a clean boundary: nothing OCR- or RAG-specific is modeled in this backend; it is purely a job/asset/source ledger plus a dispatch/callback gateway, exactly matching the stated "AI service owns OCR/RAG, backend owns the ledger and the contract" boundary.

**AI Service integration table**:

| Backend Component | Direction | Endpoint | Auth | Retry | Timeout | Error Handling | Status |
|---|---|---|---|---|---|---|---|
| `HttpAIServiceIngestionGateway.dispatch_ingestion_job` | Backend → AI | `POST {AI_SERVICE_URL}/v1/ingest/dispatch` | Bearer `ai_service_api_key` | classified but not looped inside this method | 60s default | typed `AIServiceGatewayError`, retryable flag by status code | Implemented |
| `HttpAIServiceIngestionGateway.fetch_job_status` | Backend → AI | `GET {AI_SERVICE_URL}/v1/ingest/tasks/{id}` | Bearer | n/a | 60s default | typed error | Implemented |
| `HttpAIServiceIngestionGateway.cancel_ingestion_job` | Backend → AI | `POST {AI_SERVICE_URL}/v1/ingest/tasks/{id}/cancel` | Bearer | n/a | 60s default | swallows exceptions, returns `False` | Implemented |
| `POST /ingestion/callbacks` | AI → Backend | webhook | HMAC-SHA256 (constant-time) OR static Bearer fallback | n/a (idempotent via event_id) | n/a | 401/404/422 mapped | Implemented |

---

## 13. OCR / Document Processing

Purely AI-service territory per §12's boundary check. This backend's role is limited to: accept an asset (with SHA-256 + storage URI), create a job, dispatch it, receive a callback, and expose status/results. No OCR-specific logic (text extraction, layout parsing) exists here — consistent with the two-repo design.

---

## 14. RAG / Knowledge Integration

**Not found in repository** — see the grep result in §12. Nothing in this backend represents embeddings, vector indexes, knowledge trees, or chunking. This is either fully owned by ai-service (consistent with the stated boundary) or simply not yet built on either side; this repo cannot distinguish between those two possibilities.

---

## 15. API Inventory

Full endpoint list obtained by grepping every `@router.<method>(...)` decorator in `app/api/**` (not a full schema-by-schema read of every route, but a complete path/method inventory):

**Health** (`app/api/health.py`, no auth, no DB/Redis check — see §19): `GET /health/live`, `/ready`, `/startup` — all three return a static dict, no liveness/readiness signal from dependencies.

**Identity** (`app/api/identity.py`, prefix `/identity`): `POST /users`, `POST /authenticate`, `POST /refresh`, `POST /logout`, `POST /forgot-password`, `POST /reset-password`, `GET /me` (custom header-parsing auth, doesn't use the standard `get_current_principal` dependency — a second, parallel auth code path, §17), `GET /whoami`, `GET /tenant-context`, `GET /permissions`, `GET /authorization-probe`.

**Catalogue** (`app/api/catalogue/courses.py`, prefixes `/catalogue/courses`, `/catalogue/topics`, `/catalogue/learning-outcomes`, `/catalogue/reference-materials`): course list/get/create/update/publish/archive; topic create/list/update/archive; learning-outcome create/list/update; reference-material create/list/update — 18 routes total, all behind `require_permission`.

**Assessment** (`app/api/assessment/{assessments,questions,attempts,answers}.py`): assessments create/list/get/update/publish/attach-questions/results (7); questions create/get/update/publish/archive (5); attempts start/get/list/questions/submit/result (6); answers put/get/delete (3) — 21 routes.

**Curriculum** (`app/api/curriculum/{sources,adoptions,benchmarks}.py`): sources create/list/get/snapshots/sync (5); adoptions create/list/get/activate/overrides-create/overrides-delete/effective/effective-active (8); benchmarks candidate/list/diff/get/courses/course-detail/validate/submit-review/approve/reject/revise/audit-trail/activate/+1 more (14) — 27 routes.

**Content** (`app/api/content/{sources,assets,jobs}.py`): sources create/list/get/update/deprecate/revoke/activate (7); assets create/get/list-by-source/list/+2 more (6); jobs trigger/get/get-latest/list-by-asset/list/start/progress/complete/fail/retry/reprocess/dispatch/**callback** (13) — 26 routes.

**Total: ~100 endpoints** across 6 domains. Every protected route I sampled uses `Depends(require_permission(...))` consistently — the one deliberate exception is `GET /identity/me`, which does its own manual `Authorization` header parsing and token decode rather than using `get_current_principal` (§17 flags this as a second, divergent auth code path worth consolidating even though it's currently equally insecure either way given §6).

**Response envelope**: `app/core/responses.py`'s `ApiResponse` (`{success, data, meta, request_id}`) is used by `app/main.py`'s root/metrics routes and by `identity.py`'s hand-built `JSONResponse` dicts (which manually replicate the same shape rather than importing `ApiResponse`). Content-module routes (`jobs.py`, etc.) use a **different, simpler envelope**: `{"data": ...}` or `{"error": {"code", "message"}}` with no `success`/`meta`/`request_id` fields. **Envelope is not consistent across the API surface** — three different response shapes exist (`ApiResponse` class, identity's hand-rolled `success/data/meta/request_id` dict, content's `data`/`error` dict).

**Versioning**: no `/v1` or `/api/v1` prefix anywhere in the mounted routers (`app/api/router.py`, `app/main.py`) — the API is entirely unversioned at the URL level. (The *AI service* endpoints this backend calls do use `/v1/...` — that versioning is ai-service's, not this backend's own public API.)

---

## 16. API Contract Quality

- **Pagination**: present in content-job listing endpoints (`limit`/`offset` query params, `ge`/`le` validated, `meta: {total, limit, offset}` in response — `app/api/content/jobs.py:126-143`) and in `AttemptResultRepository.list_by_assessment` (`limit`/`offset`, `app/infrastructure/assessment/repositories.py:380-411`). Not confirmed as a universal pattern across all list endpoints (e.g. `GET /catalogue/courses/` returns an unpaginated full list per the code read in §8).
- **Status codes**: generally appropriate and consistent (201 for creation, 200 for reads/updates, 202 for the curriculum sync trigger, 502 for AI-gateway failures) — no obvious misuse found in the routes read.
- **Validation**: Pydantic models used for most request bodies in catalogue/assessment/content; `app/api/identity.py`, notably, uses raw `payload: dict[str, str]` instead of a Pydantic schema for every identity endpoint (register/authenticate/refresh/logout/forgot-password/reset-password) — meaning FastAPI's automatic request validation, OpenAPI schema generation, and type coercion are **bypassed entirely for the whole identity module**, relying on manual `.get(key, "")` extraction instead. This is inconsistent with the rest of the API and produces a worse OpenAPI/Swagger contract for identity endpoints specifically.
- **Error responses**: two different shapes in play, as noted in §15 — one via `AppError`/global handlers (`app/core/exceptions.py`, consistent `{success:false, data:{}, meta:{error}, request_id}`), one via content module's ad hoc `{"error": {"code", "message"}}`.

---

## 17. Security Audit

| Area | Finding | Severity |
|---|---|---|
| Authentication | Password hasher and token service are non-functional stubs wired into the live DI container and used by the primary auth dependency (`get_current_principal`). No real password hashing, no real token signing/verification. | **CRITICAL** |
| Authentication | Session revocation (logout) has no effect on API access because the auth guard never checks the sessions table. | **CRITICAL** |
| Authentication | Forgot-password endpoint returns the raw reset token directly in its API response with no email delivery — enables account takeover by anyone who knows a target's email. | **HIGH** |
| Authentication | `GET /identity/me` implements its own separate, ad hoc Bearer-parsing/decode logic instead of the shared `get_current_principal` dependency — duplicated, divergent auth code path (currently equally broken, but a maintenance/consistency risk once the real token service is built). | **MEDIUM** (code-quality/consistency, not an independent vuln today) |
| Authorization / IDOR | Tenant filtering consistently applied at the query layer in every repository inspected (assessment, catalogue, content). No IDOR found in the modules sampled. | Info / positive finding |
| Secrets | `ai_service_api_key` and `ai_service_webhook_secret` default to hardcoded, source-visible values with no production-mode enforcement that they be overridden. | **HIGH** |
| Secrets | No JWT signing secret exists in config at all (because there's no real JWT yet) — once real JWT is implemented, ensure the signing key follows the same "must not silently default in production" discipline. | Info (forward-looking) |
| Input validation | Identity endpoints bypass Pydantic validation entirely (raw `dict[str,str]` payloads) — no injection risk found (values are used through parameterized ORM calls / value objects, which do their own validation), but it's a weaker, less self-documenting contract than the rest of the API. | **LOW** |
| File uploads | Asset creation takes a `storage_uri` + declared `mime_type`/`file_size_bytes`/SHA-256 rather than handling raw file upload/multipart directly in this backend (based on the `content/assets.py` route shapes and `ContentAsset.create()` signature) — actual file bytes appear to be handled outside this backend's request path (e.g., pre-signed upload to storage, then metadata registered here). This reduces this backend's exposure to unsafe file-upload handling, but I did not verify the multipart upload endpoint's presence/absence with full certainty — worth a follow-up read of `app/api/content/assets.py` lines not inspected in this pass. | Not fully verified |
| Database | No raw SQL / string-interpolated queries found. Parameterized SQLAlchemy throughout inspected code. | Info / positive finding |
| Account enumeration | Registration endpoint leaks whether an email is already registered via a distinct 409. Login does not leak this. | **LOW** |
| Rate limiting | None found anywhere in the repo. | **MEDIUM** given no live users yet; becomes **HIGH** once real auth exists, since brute-forcing a real password hash becomes meaningful only then. |
| Webhook auth | HMAC verification uses `hmac.compare_digest` (constant-time) correctly; no replay-window/timestamp protection, partially mitigated by event-id idempotency. | **MEDIUM** |
| Security headers | `SecurityHeadersMiddleware` sets `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `Cache-Control: no-store` globally — good baseline, but no `Content-Security-Policy`, `Strict-Transport-Security`, or CORS configuration was found anywhere in `app/core/` or `app/main.py`. | **LOW–MEDIUM** (CORS absence matters once a real frontend origin exists) |

Severity ratings above are deliberately not inflated: this is pre-production, no evidence of live user data was found, and several of the CRITICAL items are very plausibly intentional scaffolding rather than a regression from something that once worked. They are rated CRITICAL because of *impact if unnoticed*, not because of evidence of active exploitation.

---

## 18. Error Handling

`app/core/exceptions.py` (read in full): `AppError` base class carries `message` + `status_code`; `NotFoundError` subclass exists. Three registered handlers (`http_exception_handler`, `validation_exception_handler`, `app_exception_handler`) all: increment `errors_total{error_type=...}`, log via structlog at `warning` level with `request_id`/`path`/`status_code`, and return the consistent `{success:false, data:{}, meta:{error}, request_id}` shape — **for routes that raise `AppError`/`HTTPException`/`RequestValidationError`**. Content-module routes largely return their own `JSONResponse` directly rather than raising these exception types, so they don't go through this consistent handler path (matches the §15/§16 envelope-inconsistency finding). Domain errors (`app/domain/*/errors.py`, e.g. `QuestionAlreadyArchivedError`) are not automatically mapped to HTTP status codes by a central handler — routes appear to catch them ad hoc (e.g. content routes catch `ValueError` and string-match its message to decide between 404 and 400 — `app/api/content/jobs.py:51-57` and repeated at every content route — this is fragile: it depends on the exact substring `"does not exist"` appearing in the exception message).

---

## 19. Observability

- **Logging**: `structlog` configured (`app/core/logging.py` — not fully read line-by-line, but its usage throughout `middleware.py`/`exceptions.py` confirms structured, keyword-argument-based logging with `request_id` correlation on every log call inspected).
- **Metrics**: `app/core/metrics.py` — exactly two Prometheus counters: `build_backend_requests_total` and `build_backend_errors_total{error_type}`. No latency histogram, no per-route breakdown, no DB query metrics, no AI-gateway call metrics. `/metrics` endpoint exists and works (`app/main.py:71-74`).
- **Tracing**: `app/core/tracing.py` (read in full) configures an OpenTelemetry `TracerProvider` with a `SimpleSpanProcessor(NoOpExporter())` — a custom exporter whose `export()` immediately returns `SpanExportResult.SUCCESS` without sending anything anywhere. **Spans are created but tracing is fully decorative today** — no Jaeger/OTLP/console exporter is wired up.
- **Health checks**: `/health/live`, `/health/ready`, `/health/startup` (`app/api/health.py`) each return a hardcoded static dict — **none of them ping the database or Redis**. `readiness` in particular is conventionally supposed to reflect actual dependency health; here it cannot, since it does nothing.
- **Request correlation**: `RequestContextMiddleware` generates/propagates `x-request-id` and adds `x-response-time-ms` to every response — this part is real and works.

---

## 20. Performance

- No N+1 query patterns were found in the repositories inspected — `selectinload()` is used appropriately for relationships (e.g. `QuestionModel.options`, `AssessmentModel.questions`) in `app/infrastructure/assessment/repositories.py`.
- `UserModel` in `app/infrastructure/identity/models.py` eagerly loads **11 relationships** with `lazy="selectin"` (roles, sessions, devices, profile, role_assignments, verification_tokens, password_reset_tokens, audit_logs, login_events, security_events) — every single one of these fires on every user load. For a user with a long login/audit history, this is a real N+1-adjacent cost multiplier (11 extra SELECTs per user fetch, some of which — audit_logs, login_events, security_events — could grow unbounded over time with no pagination or limit at the ORM level). This wasn't flagged as broken, but it's a concrete, evidence-backed performance risk worth calling out.
- Catalogue course listing (`GET /catalogue/courses/`) returns a full unpaginated list (§16) — a scale risk once a tenant has many courses, though content-job listing does the pagination right, so the pattern is known and just not applied everywhere.
- No blocking/synchronous CPU-heavy operations were found in the async code paths inspected.

---

## 21. Testing

**Ran the suite**: `pytest -q --cov=app --cov-report=term-missing` → **324 passed, 0 failed, 0 errors, 4 warnings, 86% overall line coverage**, ~85s runtime, using the in-memory SQLite path (`APP_ENVIRONMENT=testing` → `effective_postgres_url` returns `sqlite+aiosqlite:///:memory:`).

**Structure**: `tests/domain/**` (pure domain-object unit tests, one file per aggregate: assessment×6, catalogue×5, curriculum×7, tenant×9, content×3) and `tests/integration/**` (per-module API + persistence + application-layer tests: assessment×13, curriculum×17, catalogue×6, content×7, identity×2, tenant×2, auth×1) plus a handful of root-level platform tests (`test_container.py`, `test_foundation.py`, `test_health.py`, `test_identity.py`, `test_observability.py`, `test_platform_foundation.py`).

**Coverage worth flagging specifically**:
- `app/infrastructure/security/argon2_password_hasher.py` and `jwt_token_service.py` are at **100% coverage** — meaning tests exercise these classes thoroughly, but since the tests necessarily only check internal round-trip consistency (hash-then-verify-the-same-fake-hash), **100% coverage here does not mean the security property is tested — it can't be, because the property doesn't exist in the implementation.** This is a good example of coverage-as-a-metric diverging from actual assurance.
- `app/infrastructure/ai_gateway.py` (the old, unrelated stub at the top level, distinct from `content/ai_gateway.py`), `app/infrastructure/redis.py`, `app/infrastructure/identity/{memory_user_repository,password_hasher,token_service}.py` are all at **0% coverage** — confirmed via grep to have **zero importers anywhere in `app/`** — this is dead code, not undertested live code.
- `app/domain/repositories/tenant.py` (an interface/ABC) is at 0% — expected for a pure interface exercised only via its implementations.
- Content module (`app/infrastructure/content/ai_gateway.py`) sits at 65% — the untested lines are largely timeout/network-error exception branches and the `fetch_job_status`/`cancel_ingestion_job` methods, i.e. the harder-to-reach failure paths rather than the happy path.

**Quality, not just quantity**: sampled a couple of integration tests (assessment submit/scoring, content ingestion job) — they build real request payloads through the FastAPI test client, assert on response bodies and status codes, and in several cases assert on persisted DB state afterward, not just "200 OK." This is meaningful testing, not smoke-only.

**Gap**: no test was found that exercises the actual security property of the password hasher or token service (impossible, given §6 — there's nothing real to test). No test simulates a forged/stale token being rejected in a way that would catch the `validate()` stub if it were ever accidentally "fixed" to be stricter — i.e., no regression safety net protects against *or reveals* the current state.

---

## 22. Docker / Infrastructure

**Dockerfile** (`Dockerfile`, read in full):
```dockerfile
FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY pyproject.toml ./
RUN pip install --upgrade pip && pip install .[dev]
COPY . .
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```
- Single-stage build; installs the **`[dev]` extras (pytest, mypy, ruff, pre-commit, etc.) into the production image** — unnecessary bloat and attack surface for a runtime container.
- No non-root `USER` — runs as root in the container.
- No `HEALTHCHECK` instruction (Compose/orchestrators can't use Docker-native health probing; the app does expose `/health/*` routes, but nothing in the Dockerfile wires them up).
- `COPY . .` copies the entire repo (including `.venv`, `.venv-linux`, `tests/`, `docs/`, `.git` unless excluded) into the image — **no `.dockerignore` was found**, so build context and image size are almost certainly far larger than necessary.
- No multi-stage build to strip build-only dependencies from the final layer.

**docker-compose.yml** (read in full): three services — `api` (builds from the Dockerfile), `postgres:17`, `redis:8`. Hardcoded dev credentials (`postgres`/`postgres`), explicitly labeled in README as "for local development only" (correct framing, low risk as long as that's respected). `redis` is provisioned here but, per §5/§21, is never actually connected to by any code path (`app/infrastructure/redis.py` is dead code) — the Compose Redis service is currently provisioned for nothing.

---

## 23. Dependency Audit

- **Dual dependency declaration**: both `pyproject.toml` (with a `[project.dependencies]` list plus a `[project.optional-dependencies].dev` extra) and a standalone `requirements.txt` exist. README instructs installing via `requirements.txt` for the base app and separately via `pip install -e ".[dev]"` for tooling — **two sources of truth for pinned versions**, with a real risk of drift between them over time. I did not diff their exact contents line-by-line in this pass.
- **Two virtualenvs committed/present** in the working tree: `.venv` and `.venv-linux`, with slightly different resolved versions visible during inspection (e.g., httpx 0.27.2 vs 0.28.1, starlette 1.3.1 vs 1.6.0, uvicorn 0.51.0 vs 0.52.4) — consistent with cross-platform dev (Windows + WSL/Linux) but worth confirming neither is accidentally tracked in git (not verified here — check `.gitignore` coverage for both).
- **`httpx<0.28.0` pin** (§3) will eventually block routine dependency bumps; not urgent, but worth revisiting since httpx 0.28 has been out for a while as of this audit's timeframe.
- No unmaintained or obviously risky packages were identified among the direct dependencies listed in `pyproject.toml`.

---

## 24. Configuration

`app/core/config.py` (read in full) — `Settings(BaseSettings)` via `pydantic-settings`, `.env` file support, `extra="ignore"`:

| Setting | Default | Required in prod? | Note |
|---|---|---|---|
| `app_environment` | `"development"` | validated against `{development,testing,staging,production}` | no default-secret cross-check against this value |
| `postgres_url` | `""` (empty) | effectively required outside testing (empty string would fail to connect) | in `testing`, silently overridden to in-memory SQLite via `effective_postgres_url` |
| `redis_url` | `"redis://localhost:6379/0"` | not enforced/used | dead — see §5/§22 |
| `debug` | `False` | — | effect on runtime behavior not traced in this pass |
| `request_timeout_seconds` | `30`, validated `>0` | — | not confirmed wired into an actual request timeout anywhere (not traced) |
| `tenant_header` | `"x-tenant-id"` | — | **stale/unused** — README itself flags that the real runtime header is `x-tenant-slug`, confirmed in code (`dependencies.py:85`); this setting exists but nothing reads it for that purpose |
| `ai_service_url` | `"http://localhost:8001"` | — | fine as a dev default |
| `ai_service_api_key` | `"build-ai-dev-secret-key"` | **not enforced** | hardcoded, source-visible default with no production guard — §6/§17 |
| `ai_service_webhook_secret` | `"build-ai-dev-webhook-secret"` | **not enforced** | same issue |
| `ai_service_timeout_seconds` | `60`, validated `>0` | — | used |
| `ai_service_max_retries` | `3` | — | defined but not confirmed consumed inside the gateway itself (§12) |

No `.env`/`.env.example`/`.env.test` files were found in the repository (only `.env` support via `pydantic-settings`'s `env_file=".env"` config, and the file itself is presumably gitignored — not present in this working tree, so no committed-secret risk from that specific vector).

---

## 25. CI/CD

`.github/workflows/ci.yml` (read in full): one job, `test`, triggered on push to `main`/`develop` and on all PRs. Steps: checkout → `setup-python@v5` (3.13) → `pip install -e '.[dev]'` → `ruff check app tests scripts` + `ruff format --check app tests scripts` → `pytest -q`.

**Missing from CI** (all confirmed absent, not just "not obviously present"):
- No `mypy` step, despite `[tool.mypy] strict = true` being configured in `pyproject.toml` — type checking is configured but never enforced automatically.
- No coverage threshold/gate (coverage is measurable, per §21, but nothing fails the build if it drops).
- No Docker image build/push step.
- No `alembic upgrade head` smoke test against a fresh database (nothing verifies migrations actually apply cleanly in CI).
- No dependency vulnerability scanning (no `pip-audit`, `safety`, Dependabot config, or similar found).
- No secret-scanning step.
- No deployment step of any kind (expected at this stage — matches README's "production hardening" roadmap item).

---

## 26. Documentation

`docs/` contains 7 ADRs (modular-monolith, clean-architecture, postgresql, fastapi, ai-service-boundary, multi-tenancy, assessment-core — plus a `008-curriculum-intelligence.md` referenced but check numbering), an `architecture/` folder with 7 specs (overview, academic-catalogue-specification, academic-knowledge-model, assessment-core, curriculum-intelligence, public-id-strategy, system-data-flow, versioning, learning-content-intelligence), a `contracts/` folder (ai-contract, catalogue-contract, content-contract, events-contract, identity-contract, README), `vision/` (academic-data-strategy, ai-knowledge-lifecycle, reference-data-strategy), `decisions/001-source-of-truth.md`, `domain-map.md`, `module-template.md`, `alembic.md`, and two prior audit-style documents: `phase-1-inspection-report.md` and `phase-2-iam-roadmap.md` — i.e., **this is not the first time this repository has been audited**; those two documents are directly relevant prior art and worth reading alongside this report (not read in full during this pass — a follow-up worth doing given they may already document some of these findings, or may reveal that some were previously known/accepted trade-offs).

**README accuracy**: generally well-written and honest in tone (explicitly says "Scoring, results, timers, and AI integration are intentionally deferred" — but this is now **stale**: scoring and results are implemented and tested (§9), and AI integration is substantially built (§12) with its own migrations and ~26 endpoints. README also states "Current development line: `feat/assessment-engine`" while the actual current branch is `feat/learning-content`, and the README's own project-layout diagram lists `app/integrations/`, `app/telemetry/`, `app/workers/` directories that **do not exist** in the repository (§2). None of this is malicious or even surprising for an actively-developed repo — it's simply evidence for the instruction "do not assume features exist because they appear in documentation," and equally, "do not assume features are *missing* because stale documentation says they're deferred." Both directions of that trap are present here.

---

## 27. Code Quality

- Clean separation of concerns is real and consistently applied — domain objects have no infrastructure imports, application services depend on repository interfaces not concrete classes, mappers are isolated. This is a genuine strength of the codebase.
- Dead code identified with evidence (not speculation): `app/infrastructure/ai_gateway.py` (unrelated stub classes, superseded by `content/ai_gateway.py`), `app/infrastructure/redis.py`, `app/infrastructure/identity/memory_user_repository.py`, `app/infrastructure/identity/password_hasher.py`, `app/infrastructure/identity/token_service.py`, and the `RoleModel`/`PermissionModel`/`RoleAssignmentModel` DB schema (modeled, migrated, related on `UserModel`, but never queried by the live authorization path).
- `repository=None` dead constructor parameter pattern in `app/bootstrap/container.py` (§4) — confusing but harmless.
- Fragile error-handling pattern: several content routes classify 404-vs-400 by substring-matching `"does not exist"` in a caught `ValueError`'s message (§18) — brittle, breaks silently if the message wording ever changes.
- Three divergent API response envelope shapes in simultaneous use (§15/§16) — a real consistency gap for API consumers.
- Identity endpoints bypass Pydantic schemas entirely in favor of raw dicts (§16) — inconsistent with the rest of the API's contract quality.

---

## 28. Domain Boundaries

Boundaries between identity, tenant/academic-structure, catalogue, curriculum/benchmark, assessment/CBT, and content/AI-ingestion are clean and consistently enforced at the code-organization level (separate `domain`/`application`/`infrastructure` subpackages per bounded context, no cross-domain imports observed in the files read). The one blurred boundary is **authorization**, which exists in two disconnected forms (the live in-code `ROLE_PERMISSIONS` dict vs. the fully-modeled-but-unused DB-backed `RoleModel`/`PermissionModel` schema, §5/§7) — not a boundary *violation* so much as an unresolved architectural fork that should be collapsed to one system. No social/community, notifications, subscriptions, or administrative-backoffice domains exist yet — consistent with README's stated current scope.

---

## 29. Implementation Matrix

| Capability | Implemented | Partial | Scaffolded | Missing | Evidence |
|---|---:|---:|---:|---:|---|
| User registration | ✔ | | | | §6 |
| Email verification | | | ✔ (column+table exist, no workflow) | | §6 |
| Login | ✔ (behaviorally) | | | | §6 |
| Password hashing (real crypto) | | | | ✔ | §6 |
| Token issuance/validation (real) | | | | ✔ | §6 |
| Session/logout enforcement | | | ✔ (data model real, not consulted by auth guard) | | §6 |
| Password reset (workflow shape) | ✔ | | | | §6 |
| Password reset (secure delivery) | | | | ✔ | §6 |
| Rate limiting | | | | ✔ | §6/§17 |
| RBAC / permission model | ✔ | | | | §7 |
| Tenant isolation (query-level) | ✔ | | | | §7 |
| Academic catalogue (course/topic/LO/ref-material) | ✔ | | | | §8 |
| Canonical FUTA programme codes as specified | | | | ✔ (not found; contradicted in places) | §8 |
| Curriculum benchmark/adoption/governance | ✔ | | | | §9 docs, models, handlers all present (not fully re-verified line-by-line this pass) |
| CBT: question authoring (MCQ) | ✔ | | | | §10 |
| CBT: question types beyond MCQ | | | ✔ (enum exists, not enforced) | | §10 |
| CBT: assessment lifecycle | ✔ | | | | §9 |
| CBT: attempt lifecycle | ✔ | | | | §9 |
| CBT: scoring | ✔ | | | | §9 (contradicts README) |
| CBT: results | ✔ | | | | §9 |
| CBT: timers / anti-cheating | | | | ✔ | §9 |
| AI-generated vs. human question distinction | | | | ✔ | §10 |
| User learning/progress tracking | | | | ✔ | §11 |
| Content source/asset/job ledger | ✔ | | | | §12 |
| AI-service dispatch gateway | ✔ | | | | §12 |
| HMAC webhook verification | ✔ | | | | §12 |
| Webhook replay protection | | ✔ (idempotency mitigates, no timestamp) | | | §12 |
| OCR / RAG / embeddings (this repo's side) | | | | n/a — correctly out of scope | §12/§14 |
| Observability: logging | ✔ | | | | §19 |
| Observability: metrics | | ✔ (minimal) | | | §19 |
| Observability: tracing (exported) | | | ✔ (spans created, never exported) | | §19 |
| Health checks (real dependency probes) | | | ✔ (static only) | | §19 |
| Rate limiting / caching / queues | | | | ✔ | §17/§24 |
| CI: test + lint | ✔ | | | | §25 |
| CI: type-check / coverage gate / migration check / security scan | | | | ✔ | §25 |

---

## 30. Production Readiness

| Area | Current State | Evidence | Remaining Work |
|---|---|---|---|
| Configuration | Clean, validated `pydantic-settings`, but hardcoded weak secret defaults with no production guard | §24 | Fail fast on default AI secrets when `app_environment=production`; add a real JWT signing-key setting |
| Database | Rich, consistent, tenant-scoped schema; 46 models, 17 migrations | §5 | Verify migration downgrade paths and a clean fresh-DB `alembic upgrade head` in CI |
| Authentication | **Non-functional** underneath a correctly-shaped API surface | §6 | Replace both stub classes with real implementations before any real user data; this blocks everything else in this table |
| Authorization | Sound design, correctly enforced tenant/permission chain, contingent on auth being fixed | §7 | Collapse the duplicate DB-backed RBAC schema or remove it |
| Academic Catalogue | Solid CRUD + lifecycle; canonical programme-code scheme not present/contradicted | §8 | Reconcile seed data against the intended canonical catalogue before treating it as source of truth |
| CBT | Full lifecycle including scoring/results implemented and tested (ahead of what README claims) | §9 | Add timers, anti-cheating, question-type support beyond MCQ, retake semantics |
| AI Integration | Best-engineered part of the repo: enforced state machine, real HMAC, good error taxonomy | §12 | Add replay-window protection to webhooks; enforce non-default secrets in prod |
| Security (general) | Multiple real, evidenced findings, not hypothetical | §17 | See §17 table directly |
| Testing | 324 passing, 86% coverage, meaningful assertions | §21 | Coverage metric currently can't and doesn't catch the auth-stub issue — add tests that assert real cryptographic/signature properties once real implementations land |
| Observability | Logging solid; metrics/tracing/health checks largely decorative | §19 | Wire a real span exporter, add latency histograms, make health checks actually probe DB/Redis |
| Docker | Functional but unhardened (root user, no multi-stage, dev deps in prod image, no `.dockerignore`) | §22 | Multi-stage build, non-root user, `HEALTHCHECK`, `.dockerignore` |
| CI/CD | Tests + lint only | §25 | Add mypy, coverage gate, migration smoke test, dependency/secret scanning |

**There is no single "production ready: yes/no" answer** — per the request, each row above stands on its own. The honest summary: the domain modeling, tenant isolation, and the newest AI-integration work are close to production-grade; the authentication layer is not merely "not production ready," it currently provides none of the security property its own class names claim.

---

## 31. Architectural Risks

```text
Risk: Authentication is a non-functional stub wired into production code paths.
Evidence: app/infrastructure/security/{argon2_password_hasher,jwt_token_service}.py; app/bootstrap/container.py:46,68,72,198,202; app/core/dependencies.py:27-77.
Impact: Complete authentication bypass / credential-storage failure if any real user signs up before this is fixed.
Likelihood: Certain, if launched as-is — this isn't a probabilistic risk, it's a currently-true fact about the running system.
Severity: CRITICAL.
Recommended direction: Implement real Argon2 hashing (e.g. via `argon2-cffi`, already available per dependency list conventions) and real signed JWTs (e.g. `python-jose`, already present as a transitive dependency in the `.venv` per the earlier package listing) before any non-synthetic user data is created. This should block a production launch, full stop.

Risk: Documentation drifts materially ahead of or behind actual code state (README understates AI integration and CBT scoring; overstates git branch name and directory layout).
Evidence: §26.
Impact: Wastes engineering time, misleads new contributors and — per this audit's own starting instructions — misleads exactly this kind of automated audit if it isn't independently verified against code.
Likelihood: Ongoing, given the pace of recent commits (4 content-ingestion slices merged in quick succession per git log).
Severity: MEDIUM.
Recommended direction: Treat README as a living doc updated in the same PR as any slice that changes its claims; consider a lightweight CI check that greps for directories/branches README claims exist.

Risk: Duplicate/parallel systems left in place after a design pivot (RBAC: DB-modeled vs. in-code; auth: memory_user_repository/password_hasher/token_service vs. the security/ versions actually used).
Evidence: §5, §7, §27.
Impact: Low immediate risk (dead code doesn't execute), but real risk of a future contributor wiring the wrong/unused implementation back in, or spending time maintaining code that has zero effect.
Likelihood: Moderate over time as the team grows.
Severity: LOW-MEDIUM.
Recommended direction: Delete confirmed-dead files, or if intentionally kept for a near-term migration, mark them clearly (e.g. a module docstring saying "superseded by X, scheduled for removal").

Risk: Canonical academic catalogue data (programme codes, faculty/department structure) does not match the specification you described, in ways that would materially affect real students if seeded as-is (Industrial Mathematics vs. Mathematical Sciences; Architecture grouped under old Environmental Technology).
Evidence: §8.
Impact: If `scripts/seed_futa.py` is run against a real deployment as-is, the resulting academic structure would not match the intended FUTA 2025/2026 catalogue.
Likelihood: High if this seed script is used without reconciliation.
Severity: MEDIUM-HIGH (data-correctness, not a security issue, but consequential for a CBT platform tied to real academic records).
Recommended direction: Reconcile the seed script against whatever document defines the canonical 2025/2026 FUTA structure before it's used for anything beyond local dev.
```

---

## 32. Backend ↔ AI Service Boundary

**Backend owns**: content source registry and authority model; asset registration, SHA-256-based dedup and versioning; ingestion job lifecycle/state machine; dispatch-to-AI-service orchestration (auth, idempotency keys, correlation IDs, retry classification); webhook/callback ingestion and verification; exposing job/asset status via API.

**AI service owns** (external, unverifiable from this repo, per your framing — and confirmed by the complete absence of OCR/embedding/RAG code here): actual document parsing/OCR, chunking, embedding generation, vector indexing/retrieval, question generation, knowledge extraction.

**Shared contracts**: `docs/contracts/ai-contract.md` and `docs/contracts/content-contract.md` exist and were noted but not read line-by-line against the code in this pass (a worthwhile follow-up — comparing the documented contract to the actual `AICallbackRequest`/dispatch payload shapes in `app/api/content/callback_schemas.py` and `app/infrastructure/content/ai_gateway.py:104-118` would confirm or flag drift, the same way §26 did for README).

**Data flowing Backend → AI**: on dispatch — `job_id`, `run_number`, `attempt_count`, `asset_id`, `source_id`, `tenant_id`, `file_name`, `mime_type`, `file_size_bytes`, `content_sha256`, `storage_uri`, `callback_url`, `correlation_id` (§12).

**Data flowing AI → Backend**: on callback — `job_id`, `event_id`, `event_type` (`stage_progress`/`job_completed`/`job_failed`), `stage`, `external_task_id`, `run_number`, `attempt_count`, `metrics`, `error_code`/`error_message`/`is_retryable`, `details` (§12, `app/api/content/callback_schemas.py`).

**Authentication between services**: outbound (backend→AI), a static Bearer API key; inbound (AI→backend callback), HMAC-SHA256 over the raw request body with constant-time comparison, or a static Bearer fallback (§12/§17). Both currently default to weak, hardcoded dev secrets with no production enforcement.

**Failure handling**: typed, retryable-flagged exceptions on the backend's outbound side; a fully-enforced job state machine with `attempt_history` and `max_attempts`-bounded retry on the inbound/state side (§12).

**Persistence responsibility**: backend persists the full ledger (source/asset/job + attempt history + metrics received from callbacks); actual extracted content, embeddings, or generated questions' storage location was **not confirmed** — `Question`/`QuestionModel` has no field linking back to a content asset or ingestion job, so if AI-generated questions are meant to land in the existing `assessment.Question` table, **that integration point does not yet exist** (§10's "no AI-generated-vs-human-authored distinction" finding is the same gap seen from a different angle).

**Recommended boundary** (given evidence, not speculation): the current split (backend = ledger + orchestration + contract; AI service = all ML/NLP-heavy processing) is coherent and worth keeping. The concrete gap is the **missing link between a completed ingestion job and any resulting `Question`/catalogue record** — right now the pipeline ends at "job status = READY, metrics recorded," with no evidenced code path that turns that into a usable `Question` or `ContentAsset`-derived catalogue entry.

---

## 33. Recommended Development Roadmap

```text
PHASE 0 — Foundation (existing)
  Status: substantially complete. Identity data model, tenant/RBAC design, catalogue,
  curriculum/benchmark, CBT lifecycle, content-ingestion ledger are all real, tested code.

PHASE 1 — Fix authentication for real (blocks everything else)
  Why first: §6/§17/§31 — this is not a feature gap, it's an active security defect in code
  that looks finished. Nothing downstream (real users, real academic records, a real
  frontend) should be built against the current auth layer.
  Work: real Argon2 hashing; real signed/verified JWTs with expiry; wire get_current_principal
  to actually check session state so logout/revocation work; require non-default AI-service
  secrets in production; stop leaking the password-reset token in the API response (build
  or stub an email-delivery step first).
  Dependencies: none — this can start immediately, independent of other work.
  Tests required: replace the current round-trip-only hasher/token tests with tests that
  assert actual cryptographic properties (wrong password rejected even if it "looks similar"
  to the fake hash; tampered/expired/wrong-signature tokens rejected).

PHASE 2 — Reconcile academic catalogue data
  Why: §8/§31 — real students' course/programme records depend on this being correct before
  it's used for anything beyond local dev.
  Work: reconcile scripts/seed_futa.py against the canonical 2025/2026 structure; decide
  whether Industrial Mathematics and Architecture's grouping are current data errors or
  outdated assumptions on my (the audit's) side and correct whichever is wrong.
  Dependencies: none technically, but should happen before any demo/pilot uses seeded data.

PHASE 3 — Close the content-ingestion → question pipeline gap
  Why: §32 — the ingestion pipeline currently has no evidenced endpoint into the
  CBT question bank; this is the connective tissue that makes the AI-service investment
  pay off for the actual product (CBT).
  Work: add a `source_asset_id`/`source_job_id`/`generated_by` field to Question (or a
  separate join table) so AI-generated questions can be created from a completed ingestion
  job and clearly distinguished from human-authored ones per your own §11 requirement.
  Dependencies: Phase 0 (done), AI service actually being able to return question payloads
  (unverifiable from here — coordinate with ai-service's team).

PHASE 4 — CBT hardening
  Why: README's own roadmap already flags this; §9 confirms scoring/results are further
  along than documented, so the remaining gap is narrower than it looks: timers,
  question-type support beyond MCQ (short-answer/essay currently declared but unenforced),
  submission immutability edge cases, retake semantics.
  Dependencies: Phase 1 (real auth, since attempts are learner-identity-bound).

PHASE 5 — User learning/progress
  Why: §11 confirms this is fully unbuilt; it's the direct product value of accumulating
  attempt-result data that already exists.
  Dependencies: Phase 4.

PHASE 6 — Production hardening
  Why: §17/§22/§25 collectively.
  Work: rate limiting, CORS/CSP headers, Docker multi-stage + non-root + healthcheck,
  CI mypy/coverage-gate/migration-check/dependency-scan, real span export, DB/Redis-aware
  health checks, latency metrics.
  Dependencies: can be parallelized with Phases 2-5; should complete before any public launch.
```

---

## 34. Immediate Next Actions

1. Treat §6/§17's authentication findings as a stop-ship issue for any environment that could touch real user data — even staging, if staging data could ever leak or be reused.
2. Decide, with the team, whether the two authorization schemas (in-code dict vs. DB tables) should converge on the DB-backed one (more flexible, already migrated) or the in-code one (simpler, currently live) — then delete the other.
3. Reconcile `scripts/seed_futa.py` against the real canonical FUTA catalogue before it's used for any demo involving real academic stakeholders.
4. Update README's "Status" section and roadmap to reflect that scoring/results and AI content-ingestion are implemented, not deferred — and fix the stated dev branch and project-layout diagram.
5. Read `docs/phase-1-inspection-report.md` and `docs/phase-2-iam-roadmap.md` in full — they may already document some of the above, which would change how "new" these findings are to the team, without changing whether they still need fixing.

---

## 35. Final Findings

**What is genuinely complete**: catalogue CRUD/lifecycle, curriculum benchmark/adoption/governance domain, the full CBT lifecycle including scoring and results (further along than README claims), tenant-scoped query-layer isolation across every module inspected, the content-ingestion ledger and its AI-service dispatch/callback gateway (the best-engineered part of the repo), the RBAC permission model and its enforcement chain, structured logging, 324 passing tests at 86% coverage.

**What is partially complete**: email verification (column+table exist, no workflow); session/logout (data model real, not consulted by the auth guard); observability (logging real, metrics minimal, tracing decorative, health checks static); webhook security (correct HMAC, no replay window).

**What is missing**: real password hashing, real token signing/verification, rate limiting, email delivery, user learning/progress tracking, timers/anti-cheating in CBT, question types beyond MCQ, an AI-generated-vs-human-authored question distinction, a documented/evidenced link between a completed ingestion job and a resulting Question record.

**What is risky**: the auth stub (§6/§17/§31, top priority); the forgot-password token leak; hardcoded default secrets with no production guard; stale documentation that could mislead the next person (human or automated) doing exactly this kind of review; catalogue seed data that contradicts the stated canonical structure.

**What should NOT be changed**: the overall clean-architecture layering, the tenant-scoping-at-the-query-layer discipline, the content-ingestion job state machine's enforced transitions, and the HMAC webhook verification's use of constant-time comparison — all of these are correctly built and should be treated as the pattern to replicate elsewhere (e.g., the same discipline should be applied when real auth is built).

**What should be built next**: real authentication (Phase 1), before anything else meaningfully matters.

**What requires coordination with `ai-service`**: confirming the actual `/v1/ingest/dispatch` and callback contract matches `docs/contracts/ai-contract.md` and this backend's implementation (§32 — not verified against the other repo); defining how AI-generated questions are meant to reach the `Question` table, since no such path currently exists on this side (§10/§32).

**Top 10 engineering priorities, in order**:
1. Replace the stub password hasher with real Argon2.
2. Replace the stub token service with real, signed, expiring, verified JWTs — and make the auth guard actually consult session state.
3. Stop returning the raw password-reset token in the API response; add or stub email delivery.
4. Enforce non-default AI-service secrets in production (`app_environment == "production"` should fail startup if defaults are still in use).
5. Reconcile the FUTA seed data against the canonical catalogue structure.
6. Close the ingestion-job → Question pipeline gap and add an AI-generated/human-authored distinction on questions.
7. Update README to match current code state (scoring/results/AI-ingestion are done, not deferred).
8. Add mypy, a coverage gate, an `alembic upgrade head` smoke test, and dependency/secret scanning to CI.
9. Harden the Docker image (multi-stage, non-root, `.dockerignore`, `HEALTHCHECK`) and make health-check endpoints actually probe the database/Redis.
10. Consolidate the two parallel RBAC schemas and delete confirmed-dead code (`app/infrastructure/ai_gateway.py`, `app/infrastructure/redis.py`, the unused identity memory/password/token stubs).
