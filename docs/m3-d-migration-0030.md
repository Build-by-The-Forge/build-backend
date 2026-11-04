# M3-D migration 0030: the schema, for review before it's written

**Status: proposed.** This is M3-D PR 3, from the design approved at `ab09d2c` (#79) and the contract merged in #87. It's written against `main` at `63b4e93`, Alembic head `0029`. Once this document is approved, the migration and its PostgreSQL tests follow it exactly in one PR.

**It changes no route behaviour.** It adds columns, tables and indexes, and backfills nothing beyond defaults. Every existing row keeps working as today. The read policy that uses these columns is PR 4.

## Scope

| In 0030 | Later, in its own migration |
|---|---|
| Ownership class and owner on documents and sources | The operator's tenant authorization records (PR 5) |
| Classification decisions | The scope-assignment outbox (PR 5) |
| Blobs | The deletion outbox and `content.document.deleted` (PR 11) |
| Scans | The tenant's `shelf_publication` mode, reports, takedown and the blocklist (PR 15) |
| Rights assertions | `indexed_from_asset_id` for reuse (PR 17) |
| Publication consent | |
| Upload and retry quotas | |
| The shelf form's columns (contract #87) | |
| One active job per asset | |

Splitting it this way keeps 0030 to what PRs 4, 6, 8, 12 and 14 need first. Each later table arrives with the PR that writes it.

## Conventions

These follow the existing content tables:
- **IDs** are `varchar(36)` UUIDs.
- **Statuses** are `varchar` with a `CHECK` constraint, not database enums.
- **Timestamps** are `timestamptz`.
- **Tenancy:** every new table has `tenant_id` referencing `tenants.id ON DELETE CASCADE`, and every read filters on it first.
- **Append-only tables** have a trigger that refuses `UPDATE` and `DELETE`. A tenant's cascade is exempt, because a cascaded delete fires the trigger with `pg_trigger_depth() > 1`.

## 1. `content_assets`: new columns

| Column | Type | Rule |
|---|---|---|
| `ownership_class` | `varchar(20) NOT NULL DEFAULT 'unclassified'` | `CHECK IN ('institutional', 'personal', 'unclassified')`. **Every existing row becomes `unclassified` through the default: nothing is assumed** (ruling D) |
| `owner_user_id` | `varchar(36) NULL`, references `users.id ON DELETE RESTRICT` | `CHECK ((ownership_class = 'personal') = (owner_user_id IS NOT NULL))`. RESTRICT, because a document's owner isn't deleted from under it; account deletion is the open retention question |
| `blob_id` | `varchar(36) NULL`, references `content_blobs.id ON DELETE RESTRICT` | Null for existing rows, which keep their per-asset object and `storage_uri` |
| `trust_class` | `varchar(20) NULL` | `CHECK IN ('user_provided', 'staff_provided')`. Null for existing rows. Set only by the backend |
| `course_id` | `varchar(36) NULL`, references `courses.id ON DELETE SET NULL` | The shelf form |
| `level` | `smallint NULL` | `CHECK IN (100, 200, 300, 400, 500, 600)`. Whether 600 is allowed is the tenant's to decide, enforced by the application (ruling on #87) |
| `semester` | `smallint NULL` | `CHECK BETWEEN 1 AND 3`. Checked against the selected course by the application (ruling on #87) |
| `document_type` | `varchar(30) NULL` | `CHECK IN ('lecture_notes', 'summary', 'assignment', 'project_report', 'slides', 'other')` |

`status` gains the value `deleted`, and `ingestion_status` gains `quarantined` and `rejected`. Neither column has a `CHECK` today, so this needs no DDL. The application's enums change in the PRs that write them.

**Uniqueness.** `uq_content_assets_tenant_hash` is dropped and replaced by two partial unique indexes:
- `ux_content_assets_shared_hash` on `(tenant_id, content_sha256) WHERE ownership_class <> 'personal'`
- `ux_content_assets_personal_hash` on `(tenant_id, owner_user_id, content_sha256) WHERE ownership_class = 'personal' AND status <> 'deleted'`

Every existing row is `unclassified`, so the first index enforces exactly what the old constraint did, and staff behaviour doesn't change. The indexes are created before the old constraint is dropped, in the same transaction, so there's no moment without the rule.

Also: `ix_content_assets_owner` on `(tenant_id, owner_user_id) WHERE owner_user_id IS NOT NULL`, for My Shelf.

## 2. `content_sources`: the personal source

| Column | Type | Rule |
|---|---|---|
| `owner_user_id` | `varchar(36) NULL`, references `users.id ON DELETE RESTRICT` | `CHECK ((visibility = 'private') = (owner_user_id IS NOT NULL))` |

Plus `ux_content_sources_personal` on `(tenant_id, owner_user_id) WHERE owner_user_id IS NOT NULL`: one personal source per student per tenant, safe under a race. No existing row is `private`, so the check holds for all of them. `VisibilityScope` gains `private` in PR 8.

## 3. `content_ownership_classifications` (new, append-only)

One row per recorded decision. The document's `ownership_class` is the latest one.

| Column | Type |
|---|---|
| `id` | `varchar(36)` PK |
| `tenant_id` | references `tenants` |
| `asset_id` | references `content_assets ON DELETE CASCADE` |
| `previous_class`, `new_class` | `varchar(20)`, each with the same `CHECK` as `ownership_class` |
| `decided_by` | references `users ON DELETE RESTRICT`: the operator or staff member |
| `decided_via` | `CHECK IN ('operator_command', 'staff_route')` |
| `evidence_reference` | `text NOT NULL`, `CHECK (length(evidence_reference) > 0)` |
| `run_id` | `varchar(36) NULL`: the operator command's run |
| `decided_at` | `timestamptz NOT NULL DEFAULT now()` |

Index: `(tenant_id, asset_id, decided_at DESC)`. This is the audit record that operator condition 5 requires, written in the same transaction as the class change.

## 4. `content_blobs` (new)

| Column | Type | Rule |
|---|---|---|
| `id` | PK | |
| `tenant_id` | references `tenants` | |
| `content_sha256` | `char(64)` | `CHECK (content_sha256 ~ '^[0-9a-f]{64}$')` |
| `size_bytes` | `bigint` | `CHECK > 0` |
| `mime_type` | `varchar(100)` | |
| `generation` | `varchar(36)`: random per row | |
| `object_key` | `varchar(1024)` | `tenants/{tenant}/blobs/{sha256}/{generation}`, unique |
| `state` | `varchar(10)` | `CHECK IN ('pending', 'active', 'deleting')` |
| `claimed_until` | `timestamptz NULL` | The sweeper's grace |
| `created_at`, `updated_at` | `timestamptz` | |

Indexes:
- `ux_content_blobs_live_hash` on `(tenant_id, content_sha256) WHERE state <> 'deleting'`: at most one live row per bytes (ruling C).
- `ix_content_blobs_sweep` on `(state, claimed_until)`.

## 5. `content_scans` (new)

One row per document, never shared across identical bytes (ruling 7).

| Column | Type | Rule |
|---|---|---|
| `asset_id` | PK, references `content_assets ON DELETE CASCADE` | |
| `tenant_id` | references `tenants` | |
| `verdict` | `varchar(10)` | `CHECK IN ('pending', 'accepted', 'rejected')` |
| `fence` | `bigint NOT NULL DEFAULT 0` | Each attempt increments it and presents it with its verdict, which is accepted only `WHERE fence = :token AND verdict = 'pending'` |
| `attempts` | `integer NOT NULL DEFAULT 0` | |
| `lease_until`, `next_attempt_at` | `timestamptz NULL` | |
| `scanner`, `signature_version` | `varchar(100) NULL` | |
| `scanned_at` | `timestamptz NULL` | |

Indexes:
- `ix_content_scans_due` on `(next_attempt_at) WHERE verdict = 'pending'`
- `ix_content_scans_rescan` on `(signature_version) WHERE verdict = 'accepted'`, for publication's rescan

## 6. `content_rights_assertions` (new, append-only)

Its columns follow the design's [Rights and provenance](m3-d-design.md#rights-and-provenance) table:

| Column | Rule |
|---|---|
| `id`, `tenant_id`, `asset_id` (cascade) | |
| `asserted_by` | references `users` |
| `kind` | `CHECK IN ('owner_declaration', 'staff_review', 'copied_source_default')` |
| `rights_basis` | `CHECK IN ('own_work', 'lecturer_provided', 'institution_licensed', 'publisher_licensed', 'public_domain', 'unknown')` |
| `audience` | `CHECK IN ('owner', 'tenant', 'faculty', 'department', 'programme', 'course')` |
| `redistribution` | `CHECK IN ('none', 'tenant_only', 'permitted')` |
| `ai_use` | `CHECK IN ('not_permitted', 'permitted')` |
| `declaration_version` | Required for an owner's declaration: `CHECK (kind <> 'owner_declaration' OR declaration_version IS NOT NULL)` |
| `outcome`, `reason` | Required for a staff review: `CHECK (kind <> 'staff_review' OR outcome IN ('accepted', 'rejected'))` |
| `asserted_at` | |

Index: `(tenant_id, asset_id, asserted_at DESC)`. **Effective rights** are the latest staff review, otherwise the latest owner declaration. That's read by the application, not stored, so no row ever changes.

## 7. `content_publications` (new)

One row per request. The consent fields never change; only its end can be recorded, once.

| Column | Rule |
|---|---|
| `id`, `tenant_id`, `asset_id` (cascade) | |
| `requested_by` | references `users` |
| `consent_version` | `NOT NULL` |
| `declaration_id` | references `content_rights_assertions`: the declaration made with it |
| `state` | `CHECK IN ('requested', 'published', 'withdrawn', 'taken_down', 'closed')` |
| `requested_at`, `published_at` | |
| `hidden_at` | Set by three distinct eligible reports (PR 15) |
| `ended_at`, `ended_by`, `end_reason` | |

- **Index:** `ux_content_publications_live` on `(asset_id) WHERE state IN ('requested', 'published')`. That allows one live publication per document, and two requests racing can't both create one.
- **Trigger:** an `UPDATE` may only move `requested` to `published`, `closed` or `withdrawn`, move `published` to `withdrawn` or `taken_down`, or set or clear `hidden_at`. Anything else, including any change to the consent fields, is refused.
- **Mapping to the contract:** `Document.publication.status` maps `closed` to `private` and `hidden_at` to `hidden`.

## 8. Quotas (new)

`content_upload_usage`, primary key `(tenant_id, owner_user_id)`:
- `usage_day date`
- `uploads_on_day integer`
- `stored_bytes bigint`
- `CHECK`s that both counts are `>= 0`

An upload charges it with one conditional `UPDATE ... WHERE` within the limits, in the transaction that references the blob, so two uploads at the limit can't both pass (ruling 6). A deletion returns the bytes at its commit.

`content_retry_usage`, primary key `(asset_id, usage_day)`, with `retries integer CHECK >= 0`, charged in the transaction that creates the retry job.

The limits themselves are settings, not columns.

## 9. One active job per asset

`ux_content_ingestion_jobs_active_asset` on `content_ingestion_jobs (asset_id) WHERE status NOT IN ('ready', 'failed')`.

**The migration doesn't silently resolve existing violations** (design, "the migration reports existing violations"). Before creating the index, it selects any asset with more than one active job. If there are any, it stops with a message listing the asset and job IDs, and changes nothing. The index can't be created over duplicates, and choosing which job to fail is an operator's decision. `scripts/report_active_job_conflicts.py` runs the same query read-only before a deployment.

## 10. The classification report

`scripts/report_unclassified_assets.py` is read-only. Per tenant, it lists:
- the unclassified documents
- the source each came from
- whether that source is a staff source (evidence, never a default)

It's the operator's starting list for PR 5.

## Tests, on migrated PostgreSQL

Statements repeat past five runs where a partial index or a plan could differ, with literal predicates on every partial-index conflict target.

| Requirement | Test |
|---|---|
| Upgrade from `0029` with data, then downgrade, then upgrade again | Every existing asset is `unclassified` with no owner. Staff upload and duplicate detection behave exactly as before. Downgrade restores `uq_content_assets_tenant_hash` |
| The ownership checks | A personal document without an owner, or an owner on a non-personal one, is refused. The same for private sources |
| The two hash indexes | Two students can each hold the same bytes; one student can't hold them twice, except after deleting. Shared material stays unique per tenant |
| One personal source per student | Two concurrent creations end with one row |
| One live blob per bytes | A second live row is refused; a `deleting` row doesn't block a new one |
| The scan fence | A stale token's verdict changes nothing, past five runs |
| Append-only | `UPDATE` and `DELETE` on classifications and rights assertions are refused, and a tenant's cascade still removes them |
| Publication | One live publication per document under a race. Disallowed transitions and consent edits are refused |
| Quotas | Uploads racing at the limit: exactly the allowed number pass |
| Active jobs | With two active jobs on one asset, the migration stops and names them, and the schema is unchanged. Without them, a second active job is refused |
| Roles | The runtime role can use every new table; the owner role created them |

## Coordination

- **Alembic head:** 0030 is the next revision, and no other migration PR is open. If L4's outbox migration is written first, whichever merges second renumbers.
- **The contract:** no change. The columns serve #87's fields.
- **The AI service:** no change.

## Questions for the reviewer

1. **The split:** the tenant authorization, outbox, deletion, reports and reuse tables come with their own PRs rather than all in 0030. This keeps each migration to what its PR uses.
2. **`ON DELETE RESTRICT` on owners:** a user who owns documents can't be hard-deleted until the retention and account-deletion policy exists. That's the design's open question, made explicit.
3. **Active-job conflicts stop the migration** rather than being resolved by it, as the design says. A deployment runs the report script first.
