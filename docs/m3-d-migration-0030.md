# M3-D migration 0030: the schema, for review before it's written

**Status: revised after the reviews of `166bbd1` and `df9278f` (changes requested).** This is M3-D PR 3, from the design approved at `ab09d2c` (#79) and the contract merged in #87. It's written against Alembic head `0029`. Once this document is approved, the migration and its PostgreSQL tests follow it exactly in one PR, and no other migration PR is open meanwhile.

**It changes no route behaviour.** It adds columns, tables, constraints and indexes, and backfills nothing beyond defaults. Every existing row keeps working as today. The read policy that uses these columns is PR 4.

## Rulings on `166bbd1`

1. **The split is accepted.** The scope-assignment outbox (PR 5), the deletion outbox and its event (PR 11), reports with takedown and the blocklist (PR 15), and reuse (PR 17) each bring their own migration.
2. **`ON DELETE RESTRICT` on owners is accepted** until the retention and account-deletion policy exists. **Every actor reference in an append-only or audit record is `RESTRICT` too**, so deleting an account can't cascade away evidence.
3. **Duplicate active jobs stop the migration.** It detects every conflict, names all of them, and aborts before any change, leaving the data and schema as they were.

## Conventions

- **IDs** are `varchar(36)` UUIDs. **Statuses** are `varchar` with a `CHECK`, not database enums. **Timestamps** are `timestamptz`.
- **Every column states its nullability.** Every status, state, class, ownership, rights and lifecycle column is `NOT NULL`, because a `CHECK` alone admits `NULL`.
- **Every `CHECK` is written so that `NULL` can't satisfy it.** PostgreSQL accepts a check that evaluates to `NULL`, so a conditional check names `IS NOT NULL` explicitly wherever a value is required.
- **Tenant consistency is enforced by the database.** Every new table has `tenant_id NOT NULL` referencing `tenants.id ON DELETE CASCADE`. **Every reference to another tenant-owned row is a composite foreign key that includes `tenant_id`**, so a row can't point at another tenant's record. The referenced tables gain the unique keys that make this possible (section 0).
- **Actor references** to `users` are `ON DELETE RESTRICT`.
- **Append-only tables** have a `BEFORE UPDATE OR DELETE` trigger that raises. A tenant's cascade is exempt: a cascaded delete runs inside the referential action, where `pg_trigger_depth() > 1`. A test proves both.
- **One transaction.** Alembic runs the upgrade as one transaction on PostgreSQL. The active-job check (section 9) runs first, so an abort leaves nothing changed.

## 0. Keys for tenant-consistent references

| Table | New unique constraint | Why |
|---|---|---|
| `content_assets` | `uq_content_assets_tenant_id_id (tenant_id, id)` | Target of `(tenant_id, asset_id)` references |
| `content_blobs` | `uq_content_blobs_tenant_id_id (tenant_id, id)` | Target of `content_assets (tenant_id, blob_id)` |
| `content_rights_assertions` | `uq_content_rights_tenant_asset_id (tenant_id, asset_id, id)` | Target of a publication's declaration: same tenant **and** same document |
| `courses` | `uq_courses_tenant_id_id (tenant_id, id)` | Target of `content_assets (tenant_id, course_id)` |

`id` is already unique on each, so these are satisfied by every existing row and create no conflict.

## 1. `content_assets`: new columns

| Column | Type | Null | Rule |
|---|---|---|---|
| `ownership_class` | `varchar(20)` | `NOT NULL DEFAULT 'unclassified'` | `CHECK IN ('institutional', 'personal', 'unclassified')`. **Every existing row becomes `unclassified` through the default: nothing is assumed** (ruling D) |
| `owner_user_id` | `varchar(36)` | `NULL` | References `users.id ON DELETE RESTRICT`. `CHECK ((ownership_class = 'personal') = (owner_user_id IS NOT NULL))`. Both sides are never `NULL`, since `ownership_class` is `NOT NULL` and `IS NOT NULL` is boolean |
| `blob_id` | `varchar(36)` | `NULL` | Composite FK `(tenant_id, blob_id)` → `content_blobs (tenant_id, id) ON DELETE RESTRICT`. `CHECK (blob_id IS NULL OR tenant_id IS NOT NULL)`, since `content_assets.tenant_id` is nullable and a composite key with a `NULL` part isn't checked. Null for existing rows, which keep their per-asset object |
| `trust_class` | `varchar(20)` | `NULL` | `CHECK (trust_class IS NULL OR trust_class IN ('user_provided', 'staff_provided'))`. Null only for rows from before 0030; every new row is set by the backend |
| `course_id` | `varchar(36)` | `NULL` | Composite FK `(tenant_id, course_id)` → `courses (tenant_id, id) ON DELETE SET NULL (course_id)`. The column list keeps `tenant_id`. **`CHECK (course_id IS NULL OR tenant_id IS NOT NULL)`**, for the same reason as `blob_id`: a composite key with a `NULL` part isn't checked |
| `level` | `smallint` | `NULL` | `CHECK (level IS NULL OR level IN (100, 200, 300, 400, 500, 600))`. Whether 600 is allowed is the tenant's to decide, enforced by the application (ruling on #87) |
| `semester` | `smallint` | `NULL` | `CHECK (semester IS NULL OR semester BETWEEN 1 AND 3)`. Checked against the selected course by the application (ruling on #87) |
| `document_type` | `varchar(30)` | `NULL` | `CHECK (document_type IS NULL OR document_type IN ('lecture_notes', 'summary', 'assignment', 'project_report', 'slides', 'other'))` |

The shelf columns are nullable by design: a document has none of them until the student fills in the form. `status` gains `deleted`, and `ingestion_status` gains `quarantined` and `rejected`. Both columns are already `NOT NULL` with no `CHECK`, so no DDL is needed.

### Uniqueness, and deleted documents

`uq_content_assets_tenant_hash` is replaced by two partial unique indexes. They're created before it's dropped, in the same transaction:

| Index | On | Where |
|---|---|---|
| `ux_content_assets_shared_hash` | `(tenant_id, content_sha256)` | `ownership_class <> 'personal' AND status <> 'deleted'` |
| `ux_content_assets_personal_hash` | `(tenant_id, owner_user_id, content_sha256)` | `ownership_class = 'personal' AND status <> 'deleted'` |

**Both exclude `deleted`, so the two are symmetric.** This corrects the asymmetry in `166bbd1`. A deleted document holds no uniqueness: re-uploading the same bytes after a deletion creates a new document, whoever owns it.

**Existing behaviour is unchanged.** No existing row is `deleted`, and `deleted` is introduced by PR 11. `revoked`, `superseded` and `draft` rows still block a duplicate, exactly as the old constraint did.

Also `ix_content_assets_owner` on `(tenant_id, owner_user_id) WHERE owner_user_id IS NOT NULL`, for My Shelf.

## 2. `content_sources`

| Column | Type | Null | Rule |
|---|---|---|---|
| `owner_user_id` | `varchar(36)` | `NULL` | References `users.id ON DELETE RESTRICT`. `CHECK ((visibility = 'private') = (owner_user_id IS NOT NULL))`. `visibility` is already `NOT NULL` |

Plus `ux_content_sources_personal` on `(tenant_id, owner_user_id) WHERE owner_user_id IS NOT NULL`: one personal source per student per tenant, safe under a race. No existing row is `private`. `VisibilityScope` gains `private` in PR 8.

**Not changed here:** `content_assets.source_id` references `content_sources.id` alone, as it does today. Making that composite needs every existing source's tenant to match its assets'. 0030 reports any mismatch (section 10), and PR 8 makes it composite once the report is clean.

## 3. `content_ownership_classifications` (new, append-only)

| Column | Type | Null | Rule |
|---|---|---|---|
| `id` | `varchar(36)` | `NOT NULL` | PK |
| `tenant_id` | `varchar(36)` | `NOT NULL` | → `tenants ON DELETE CASCADE` |
| `asset_id` | `varchar(36)` | `NOT NULL` | `(tenant_id, asset_id)` → `content_assets (tenant_id, id) ON DELETE CASCADE` |
| `previous_class` | `varchar(20)` | `NOT NULL` | Same `CHECK` as `ownership_class` |
| `new_class` | `varchar(20)` | `NOT NULL` | Same `CHECK`, and `CHECK (new_class <> previous_class)` |
| `decided_by` | `varchar(36)` | `NOT NULL` | → `users ON DELETE RESTRICT` |
| `decided_via` | `varchar(20)` | `NOT NULL` | `CHECK IN ('operator_command', 'staff_route')` |
| `evidence_reference` | `text` | `NOT NULL` | `CHECK (length(trim(evidence_reference)) > 0)` |
| `run_id` | `varchar(36)` | `NULL` | Required for the operator: `CHECK (decided_via <> 'operator_command' OR run_id IS NOT NULL)` |
| `decided_at` | `timestamptz` | `NOT NULL DEFAULT now()` | |

Index `(tenant_id, asset_id, decided_at DESC)`. This is the audit record for operator condition 5, written in the same transaction as the class change.

## 4. `content_blobs` (new)

| Column | Type | Null | Rule |
|---|---|---|---|
| `id` | `varchar(36)` | `NOT NULL` | PK |
| `tenant_id` | `varchar(36)` | `NOT NULL` | → `tenants ON DELETE CASCADE` |
| `content_sha256` | `char(64)` | `NOT NULL` | `CHECK (content_sha256 ~ '^[0-9a-f]{64}$')` |
| `size_bytes` | `bigint` | `NOT NULL` | `CHECK (size_bytes > 0)` |
| `mime_type` | `varchar(100)` | `NOT NULL` | |
| `generation` | `varchar(36)` | `NOT NULL` | Random per row |
| `object_key` | `varchar(1024)` | `NOT NULL` | Unique. `tenants/{tenant}/blobs/{sha256}/{generation}` |
| `state` | `varchar(10)` | `NOT NULL DEFAULT 'pending'` | `CHECK IN ('pending', 'active', 'deleting')` |
| `claimed_until` | `timestamptz` | `NULL` | Required while `pending`, and null once `active`: `CHECK (state <> 'pending' OR claimed_until IS NOT NULL)` and **`CHECK (state <> 'active' OR claimed_until IS NULL)`**. A `deleting` row may keep its last claim, which the sweeper reads |
| `created_at`, `updated_at` | `timestamptz` | `NOT NULL DEFAULT now()` | |

Indexes:
- `ux_content_blobs_live_hash` on `(tenant_id, content_sha256) WHERE state <> 'deleting'`: at most one live row per bytes (ruling C).
- `ix_content_blobs_sweep` on `(state, claimed_until)`.

## 5. `content_scans` (new)

| Column | Type | Null | Rule |
|---|---|---|---|
| `asset_id` | `varchar(36)` | `NOT NULL` | PK. `(tenant_id, asset_id)` → `content_assets (tenant_id, id) ON DELETE CASCADE` |
| `tenant_id` | `varchar(36)` | `NOT NULL` | |
| `verdict` | `varchar(10)` | `NOT NULL DEFAULT 'pending'` | `CHECK IN ('pending', 'accepted', 'rejected')` |
| `fence` | `bigint` | `NOT NULL DEFAULT 0` | `CHECK (fence >= 0)`. Each attempt increments it, and presents it with its verdict, which is accepted only `WHERE fence = :token AND verdict = 'pending'` |
| `attempts` | `integer` | `NOT NULL DEFAULT 0` | `CHECK (attempts >= 0)` |
| `lease_until`, `next_attempt_at` | `timestamptz` | `NULL` | |
| `scanner`, `signature_version` | `varchar(100)` | `NULL` | Required with a verdict: `CHECK (verdict = 'pending' OR (scanner IS NOT NULL AND signature_version IS NOT NULL AND scanned_at IS NOT NULL))` |
| `scanned_at` | `timestamptz` | `NULL` | Covered by the same check |

Indexes `ix_content_scans_due (next_attempt_at) WHERE verdict = 'pending'` and `ix_content_scans_rescan (signature_version) WHERE verdict = 'accepted'`.

## 6. `content_rights_assertions` (new, append-only)

| Column | Type | Null | Rule |
|---|---|---|---|
| `id` | `varchar(36)` | `NOT NULL` | PK |
| `tenant_id` | `varchar(36)` | `NOT NULL` | |
| `asset_id` | `varchar(36)` | `NOT NULL` | `(tenant_id, asset_id)` → `content_assets (tenant_id, id) ON DELETE CASCADE` |
| `asserted_by` | `varchar(36)` | `NOT NULL` | → `users ON DELETE RESTRICT` |
| `kind` | `varchar(30)` | `NOT NULL` | `CHECK IN ('owner_declaration', 'staff_review', 'copied_source_default')` |
| `rights_basis` | `varchar(30)` | `NOT NULL` | `CHECK IN ('own_work', 'lecturer_provided', 'institution_licensed', 'publisher_licensed', 'public_domain', 'unknown')` |
| `audience` | `varchar(20)` | `NOT NULL` | `CHECK IN ('owner', 'tenant', 'faculty', 'department', 'programme', 'course')` |
| `redistribution` | `varchar(20)` | `NOT NULL` | `CHECK IN ('none', 'tenant_only', 'permitted')` |
| `ai_use` | `varchar(20)` | `NOT NULL DEFAULT 'not_permitted'` | `CHECK IN ('not_permitted', 'permitted')` |
| `declaration_version` | `varchar(64)` | `NULL` | `CHECK (kind <> 'owner_declaration' OR (declaration_version IS NOT NULL AND length(trim(declaration_version)) > 0))` |
| `outcome` | `varchar(10)` | `NULL` | **`CHECK (kind <> 'staff_review' OR (outcome IS NOT NULL AND outcome IN ('accepted', 'rejected') AND reason IS NOT NULL AND length(trim(reason)) > 0))`**, and `CHECK (kind = 'staff_review' OR outcome IS NULL)` |
| `reason` | `text` | `NULL` | Covered by the check above |
| `asserted_at` | `timestamptz` | `NOT NULL DEFAULT now()` | |

Index `(tenant_id, asset_id, asserted_at DESC)`. **Effective rights** are the latest staff review, otherwise the latest owner declaration. They're read by the application and never stored, so no row ever changes.

## 7. `content_publications` (new)

| Column | Type | Null | Rule |
|---|---|---|---|
| `id` | `varchar(36)` | `NOT NULL` | PK |
| `tenant_id` | `varchar(36)` | `NOT NULL` | |
| `asset_id` | `varchar(36)` | `NOT NULL` | `(tenant_id, asset_id)` → `content_assets (tenant_id, id) ON DELETE CASCADE` |
| `declaration_id` | `varchar(36)` | `NOT NULL` | **`(tenant_id, asset_id, declaration_id)` → `content_rights_assertions (tenant_id, asset_id, id) ON DELETE RESTRICT`**: the declaration made with this request, of the same tenant and document |
| `requested_by` | `varchar(36)` | `NOT NULL` | → `users ON DELETE RESTRICT` |
| `consent_version` | `varchar(64)` | `NOT NULL` | `CHECK (length(trim(consent_version)) > 0)` |
| `state` | `varchar(12)` | `NOT NULL DEFAULT 'requested'` | `CHECK IN ('requested', 'published', 'withdrawn', 'taken_down', 'closed')` |
| `requested_at` | `timestamptz` | `NOT NULL DEFAULT now()` | |
| `published_at` | `timestamptz` | `NULL` | Set exactly when it was ever published: `CHECK (state NOT IN ('published', 'taken_down') OR published_at IS NOT NULL)` and `CHECK (state NOT IN ('requested', 'closed') OR published_at IS NULL)`. A `withdrawn` row has it only if it had been published |
| `hidden_at` | `timestamptz` | `NULL` | Only on a published row: `CHECK (hidden_at IS NULL OR state = 'published')`. Set by three distinct eligible reports (PR 15) |
| `ended_at` | `timestamptz` | `NULL` | `CHECK ((state IN ('requested', 'published')) = (ended_at IS NULL))` |
| `ended_by` | `varchar(36)` | `NULL` | → `users ON DELETE RESTRICT`. Required with `ended_at`, except for `closed` by the system: `CHECK (ended_at IS NULL OR state = 'closed' OR ended_by IS NOT NULL)` |
| `end_reason` | `text` | `NULL` | Required for a takedown: `CHECK (state <> 'taken_down' OR (end_reason IS NOT NULL AND length(trim(end_reason)) > 0))` |

- **Index:** `ux_content_publications_live` on `(asset_id) WHERE state IN ('requested', 'published')`: one live publication per document, and two racing requests can't both create one.
- **Trigger:** an `UPDATE` may only move `requested` to `published`, `closed` or `withdrawn`, move `published` to `withdrawn` or `taken_down`, or set or clear `hidden_at`. Anything else, including any change to `tenant_id`, `asset_id`, `declaration_id`, `requested_by`, `consent_version` or `requested_at`, is refused.
- **`DELETE`** is refused except through a tenant's or a document's cascade.
- **Mapping to the contract:** `Document.publication.status` maps `closed` to `private` and `hidden_at` to `hidden`.

## 8. Quotas (new)

`content_upload_usage`, primary key `(tenant_id, owner_user_id)`:

| Column | Type | Null | Rule |
|---|---|---|---|
| `tenant_id` | `varchar(36)` | `NOT NULL` | → `tenants ON DELETE CASCADE` |
| `owner_user_id` | `varchar(36)` | `NOT NULL` | → `users ON DELETE RESTRICT` |
| `usage_day` | `date` | `NOT NULL` | |
| `uploads_on_day` | `integer` | `NOT NULL DEFAULT 0` | `CHECK (uploads_on_day >= 0)` |
| `stored_bytes` | `bigint` | `NOT NULL DEFAULT 0` | `CHECK (stored_bytes >= 0)` |

`content_retry_usage`, primary key `(tenant_id, asset_id, usage_day)`:

| Column | Type | Null | Rule |
|---|---|---|---|
| `tenant_id` | `varchar(36)` | `NOT NULL` | **Added** (finding 3). It joins the convention |
| `asset_id` | `varchar(36)` | `NOT NULL` | `(tenant_id, asset_id)` → `content_assets (tenant_id, id) ON DELETE CASCADE` |
| `usage_day` | `date` | `NOT NULL` | |
| `retries` | `integer` | `NOT NULL DEFAULT 0` | `CHECK (retries >= 0)` |

Each is charged with one conditional `UPDATE ... WHERE` within the limits, in the transaction that commits the upload or the retry, so two requests at the limit can't both pass (ruling 6). A deletion returns its bytes at its commit. The limits are settings, not columns.

## 9. One active job per asset

`ux_content_ingestion_jobs_active_asset` on `content_ingestion_jobs (asset_id) WHERE status NOT IN ('ready', 'failed')`. `status` is already `NOT NULL`.

**The migration never chooses which job to fail.** Its first statement, before any DDL, selects every asset with more than one active job.

- **If there are any:** it raises with every asset ID and every one of their active job IDs. The upgrade is one transaction, so nothing has changed and the head stays at `0029`.
- **If there are none:** the rest runs, and the index refuses any future second active job.

`scripts/report_active_job_conflicts.py` runs the same query read-only, so a deployment can check before migrating.

## 10. Reports for the operator

Both scripts are read-only:

- **`scripts/report_unclassified_assets.py`:** per tenant, the unclassified documents, the source each came from, and whether that source is a staff source (evidence, never a default). It's the operator's starting list for PR 5.
- **`scripts/report_source_tenant_mismatches.py`:** any document whose tenant differs from its source's. A clean result is a precondition for PR 8 to make `source_id` tenant-consistent.

## Tests, on migrated PostgreSQL

Statements repeat past five runs where a partial index or a plan could differ, with literal predicates on every partial-index conflict target.

| Requirement | Test |
|---|---|
| Upgrade, downgrade and upgrade again, with data | Every existing asset is `unclassified` with no owner. Staff upload and duplicate detection behave exactly as before. Downgrade restores `uq_content_assets_tenant_hash` |
| No `NULL` passes a required check | For each column above marked required, by `NOT NULL` or by a conditional `CHECK`, an insert with `NULL` is refused. That includes a staff review with no outcome, or with a blank reason |
| Tenant consistency | For each composite reference, a row pointing at another tenant's asset, blob, course or declaration is refused. So is a publication naming a declaration of another document in the same tenant. **A document with no tenant can't carry a `blob_id` or a `course_id`:** both checks refuse it, since the composite keys alone wouldn't |
| The hash indexes and deletion | Two students may hold the same bytes; one student can't hold them twice. Shared material stays unique per tenant. **After a document is `deleted`, the same bytes upload again, personal or shared.** `revoked` and `superseded` still block, as before |
| One personal source per student | Two concurrent creations end with one row |
| One live blob per bytes | A second live row is refused; a `deleting` row doesn't block a new one |
| The blob claim | A `pending` row without `claimed_until` is refused, and so is an `active` row with one. Moving a row to `active` without clearing it is refused |
| The scan fence | A stale token's verdict changes nothing, past five runs. A verdict without scanner, signature version and time is refused |
| Append-only, and audit retention | `UPDATE` and `DELETE` on classifications and rights assertions are refused. A tenant's cascade still removes them. **Deleting a user referenced by any audit or append-only row is refused** |
| Publication | One live publication per document under a race. Disallowed transitions, consent edits, and a takedown without a reason are refused |
| Quotas | Uploads and retries racing at the limit: exactly the allowed number pass |
| Active jobs | With two active jobs on one asset, the migration raises naming every one, and the schema and data are unchanged at `0029`. Without them, a second active job is refused |
| Roles | The runtime role can use every new table; the owner role created them |

## Coordination

- **Alembic head:** 0030 is the next revision, and no other migration PR is open. If L4's outbox migration is written first, whichever merges second renumbers.
- **The contract:** no change. The columns serve #87's fields.
- **The AI service:** no change.
