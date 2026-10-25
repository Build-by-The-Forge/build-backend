# P3-1 PR 3 — asset registration and identity: design (proposed)

Status: **proposed, for review.** No code changes until the decisions in section 7 are settled.

PR 2 added `POST /content/sources/{id}/assets/upload`. It is server-generated identity over verified bytes, with an explicit duplicate-content rule (`docs/p3-1-pr2-upload-design.md`). PR 3 makes every other way of creating or changing an asset obey the same trust boundary and identity policy, so that no older path can bypass them.

PR 3 strengthens the trust boundary. It does not complete ingestion: the AI-service fetching verified bytes is PR 4, extraction to indexing is P3-2 to P3-5, and orphan reconciliation is P3-6.

## 1. What exists today

Inspected on main `ea65510`. Behaviour was confirmed with throwaway probe tests through the real app (SQLite schema); the probes were not committed.

### Routes that create or change assets

| Route | Permission | What it trusts from the client |
|---|---|---|
| `POST /content/sources/{id}/assets` (register) | `CONTENT_ASSET_UPLOAD` | `storage_uri`, `content_sha256`, `file_size_bytes`, `mime_type`, `file_name`, `metadata` |
| `POST /content/assets/{id}/version` | `CONTENT_ASSET_UPLOAD` | the same fields, for the new version |
| `POST /content/assets/{id}/revoke` | `CONTENT_ASSET_UPLOAD` | the reason only |
| `POST /content/sources/{id}/assets/upload` (PR 2) | `CONTENT_ASSET_UPLOAD` | the bytes; every fact is derived from them |
| `POST /content/sources` (with `visibility=platform`) | `CONTENT_SOURCE_MANAGE` | the platform scope itself |

`CONTENT_ASSET_UPLOAD` and `CONTENT_SOURCE_MANAGE` are held by `lecturer`, `hod`, `faculty_admin`, `admin` and `owner` (`app/core/authorization.py`). Every role that can upload can also read assets.

### Probe results

| Probe | Result |
|---|---|
| Register with `storage_uri: "s3://anything/at/all"` and `file_size_bytes: 999999` for a 16-byte payload's hash | **201**; both stored as given |
| Tenant B calls `POST /content/assets/{tenant A asset}/version` | **201**; tenant A's asset becomes `superseded`, and a new version owned by tenant A points at `s3://evil/x` |
| Tenant B revokes tenant A's asset | 403 `Permission denied: asset belongs to another tenant` (no write, but it confirms the asset exists) |
| Register bytes whose earlier asset in the tenant is revoked | **500**: unhandled `IntegrityError` on `uq_content_assets_tenant_hash` |
| A tenant lecturer creates a source with `visibility=platform, authority_level=regulatory` | **201**, `tenant_id` null: a platform-wide source |
| The same lecturer registers an asset into it | **201**, `tenant_id` null: platform content visible to every tenant |

### The identity invariant (migration 0016)

- `content_assets` has `UNIQUE (tenant_id, content_sha256)` (`uq_content_assets_tenant_hash`, `alembic/versions/0016_add_content_assets.py`). PR 2 kept it (Option A).
- It is a plain unique constraint, so PostgreSQL treats NULLs as distinct. **Platform assets (`tenant_id` NULL) have no database-level deduplication**, only the application's select-then-insert check.
- The constraint covers every status. A revoked or superseded row still holds its hash.

### The register handler (`RegisterContentAssetHandler`)

- It deduplicates by selecting `get_asset_by_hash(sha, tenant)`. It returns the existing asset only when that asset is `ACTIVE`, **from any source in the tenant**, with its `storage_uri`. It does not check `CONTENT_ASSET_READ`.
- If the existing row is not active (revoked or superseded), it falls through to an insert, which the constraint refuses: the 500 above.
- It persists through `save_asset`, which selects then updates (upsert). A concurrent winner can be overwritten, and an `IntegrityError` from a lost race is not handled.
- Errors are mapped by substring (`"does not exist"` gives 404).

### Callers

| Caller | Uses |
|---|---|
| `boundary/conftest.py:301` (cross-repo boundary gate) | **register**, with `storage_uri: s3://build-assets/{slug}/boundary.pdf` and a random hash, then creates and dispatches a job |
| `app/infrastructure/content/ai_gateway.py:109` | sends `asset.storage_uri` to the AI-service on dispatch. ai-service `IngestRequest.storage_uri` accepts any non-empty string (`app/schemas/ingest.py:35`) |
| Backend tests | `tests/integration/content/test_content_asset_api.py`, `test_content_job_api.py`, `test_signed_callbacks.py`, `test_content_ai_gateway_api.py`, `tests/application/content/test_asset_handlers.py`, `tests/domain/content/test_asset.py` |
| mobile-app | none: it calls no content routes |

There is no external client of register or version. The only cross-repository dependency is the boundary fixture, and the m3 compose stack already runs SeaweedFS for the backend (`deploy/compose.m3.yml`). So the fixture can upload real bytes instead.

## 2. Findings

| # | Finding | Severity |
|---|---|---|
| F1 | **Cross-tenant write through versioning.** The version route never passes the caller's tenant, and the handler does not check it. Any tenant's uploader can supersede another tenant's asset and attach a client-chosen `storage_uri` to it. | High |
| F2 | **Tenant members write platform content.** A lecturer can create a platform (regulatory) source and register or version assets in it. The result is visible to every tenant. The comment in `sources.py:28` says this needs a platform admin; nothing enforces it. | High |
| F3 | **Client-controlled storage references are trusted.** Register and version store `storage_uri`, size, MIME type and hash as given. The backend later sends that URI to the AI-service as the document to process. | High |
| F4 | **Deduplication without authorization, and a 500.** Register returns another source's asset, `storage_uri` included, without checking `CONTENT_ASSET_READ`. A hash held by a revoked or superseded row gives a 500. | Medium |
| F5 | **No race handling on register or version.** Select-then-upsert can overwrite a concurrent winner. A lost race is a 500. | Medium |
| F6 | **Revoke scope.** Platform assets can be revoked by any tenant's uploader (the check is skipped when the asset's `tenant_id` is NULL). Another tenant's asset gives 403 instead of 404, which reveals that it exists. | Medium |
| F7 | **No database deduplication for platform assets** (NULLs are distinct). This is latent while no legitimate platform writer exists (F2). | Low now |
| F8 | Errors are classified by message substring. | Low |

## 3. Decisions proposed

### Q1. Who can create or change an asset?

- **Tenant sources.** Only callers whose verified `TenantContext.tenant_id` equals the source's tenant. A source or asset in another tenant is **404**, indistinguishable from missing, on every route: register, upload, version and revoke. No client-supplied tenant identifier is read anywhere.
- **Platform sources and assets.** No tenant-scoped caller may create them, register into them, version them or revoke them. That is 403 `PLATFORM_CONTENT_NOT_WRITABLE` for an existing platform source or asset. Creating a source with `visibility=platform` from a tenant context is 403 `PLATFORM_SOURCE_NOT_ALLOWED`.
- Platform content needs a platform-administrator path and a role that does not exist today. That is a separate, reviewed piece of work. It must add `UNIQUE (content_sha256) WHERE tenant_id IS NULL` through a reviewed migration before any platform writer exists (F7).
- Existing platform rows are left as they are (no data migration). PR 3 records how many exist in each environment, so that their review can be planned.

### Q2. What does `storage_uri` mean?

`storage_uri` is **always server-generated**. It is `s3://{object_storage_bucket}/tenants/{tenant}/assets/{asset_id}/{sha256}`, written only by the upload service after a verified `put`. The client never supplies one.

- **Register** stops accepting client storage references. **Recommended: retire it.** `POST /content/sources/{id}/assets` returns **410** `ASSET_REGISTRATION_RETIRED`, naming the upload route, and touches nothing. The upload route is now the only way to create an asset. That is what makes "both paths obey the same identity policy" true by construction.
  - The alternative is to keep register as "adopt an object already in BUILD storage", validating the namespace and running `head` with size and SHA-256 checks. It has no legitimate caller today: the only writer to that namespace is the upload service, which already creates the row. It would be a second creation path to secure, for no current use. Rejected unless a caller appears.
- **Version** stops accepting client storage references in the same way. It is replaced by **version by upload**: `POST /content/assets/{id}/versions/upload`. The raw body, `Idempotency-Key`, limits and verification are the same as PR 2. The new version's identity, storage and duplicate rules are the upload service's own. The parent is superseded in the same transaction that inserts the new version, and only if the parent is still `ACTIVE`. A conditional update guards against two concurrent versions of one parent: the loser gets 409 `ASSET_VERSION_CONFLICT`. The old version route returns 410 `ASSET_VERSION_RETIRED`.
- **Existing rows** may hold client-supplied URIs, from before PR 3. A row is **managed** only if its `storage_uri` is exactly the server form for that row. That means the configured bucket, the row's own tenant, its own id and its own SHA-256. A pure function, `managed_storage_key(asset)`, decides this. **Job creation and dispatch refuse unmanaged assets** with 409 `ASSET_NOT_IN_MANAGED_STORAGE`, so an unverified location is never sent to the AI-service. No rows are rewritten.

### Q3. What is the identity rule?

- `UNIQUE (tenant_id, content_sha256)` stays exactly as migration 0016 defines it. PR 3 adds no migration.
- One policy, already implemented by the upload service, now governs every creation path, uploads and versions alike:
  - same `Idempotency-Key` and same bytes: the original asset (200);
  - same key with other bytes: 409 `IDEMPOTENCY_KEY_REUSED`;
  - bytes the tenant already holds, under any status and any source: 409 `DUPLICATE_CONTENT`.
- `existing_asset_id` appears **only if the caller holds `CONTENT_ASSET_READ`**, and only after the source authorization above has passed. So a caller learns nothing about another tenant, and nothing about this tenant unless they may read it.
- A version whose bytes equal any asset in the tenant (its parent included) is `DUPLICATE_CONTENT`. This replaces the domain's "SHA-256 identical to current version" check with the stronger tenant-wide rule the database enforces anyway.
- **The database decides races.** Inserts only. Lost races are classified from the committed rows (by id: key collision; by hash: content collision), exactly as in PR 2. The supersede step is a conditional `UPDATE … WHERE status = 'active'`.

### Q4. When metadata disagrees with the object

With registration retired, a client can no longer declare metadata that disagrees with an object. Every remaining case fails closed:

| Case | Where it is caught | Result |
|---|---|---|
| Declared vs actual size, type or hash | Not possible: the upload derives all three from the bytes | — |
| Bytes changed in transit to storage | `put` with `x-amz-checksum-sha256` (PR 1, PR 2) | 500 `UPLOAD_INTEGRITY`; no row |
| Object missing at replay | `head` on replay heals it from the identical bytes (PR 2) | 200 |
| Unmanaged `storage_uri` (legacy row) | Job creation and dispatch (`managed_storage_key`) | 409 `ASSET_NOT_IN_MANAGED_STORAGE`; never dispatched |
| Tenant or source mismatch in the key | `managed_storage_key` requires the row's own tenant, id and hash | Unmanaged, as above |
| Object missing, or wrong bytes, when the AI-service fetches | **PR 4**: fetch by key with `get(expected_sha256, max_bytes)`, so a mismatch or absence fails the job | Job fails with a typed error (PR 4) |

### Q5. Can a legacy path bypass the protections?

Not once register and version are retired, because no route other than upload and version-by-upload can create an asset row. The tests prove it instead of assuming it (section 5), including concurrent attempts across the routes.

## 4. Error contract (changes only)

| Route | Status | Code |
|---|---|---|
| `POST /content/sources/{id}/assets` | 410 | `ASSET_REGISTRATION_RETIRED` (message names the upload route) |
| `POST /content/assets/{id}/version` | 410 | `ASSET_VERSION_RETIRED` (names the version-upload route) |
| `POST /content/assets/{id}/versions/upload` | 201 / 200 / 400 / 403 / 404 / 408 / 409 / 413 / 415 / 503 | As upload, plus 409 `ASSET_VERSION_CONFLICT` (parent no longer active) and 409 `ASSET_NOT_VERSIONABLE` (revoked parent) |
| `POST /content/assets/{id}/revoke` | 404 | another tenant's asset (was 403) |
| `POST /content/assets/{id}/revoke` and version upload | 403 | `PLATFORM_CONTENT_NOT_WRITABLE` |
| `POST /content/sources` | 403 | `PLATFORM_SOURCE_NOT_ALLOWED` for `visibility=platform` from a tenant context |
| `POST /content/assets/{id}/jobs`, dispatch | 409 | `ASSET_NOT_IN_MANAGED_STORAGE` |

Errors are typed exceptions mapped by class, not by message substring (F8), for the routes PR 3 touches.

The retired routes stay registered for one release to answer 410, so a stale client gets a clear answer instead of a 404 or 405. Their removal is a later change.

## 5. Tests

**Negative tests (API, real app):**
- Cross-tenant: version-upload and revoke of another tenant's asset give 404, and nothing changes. The F1 and F6 probes become regression tests.
- Platform: a lecturer creating a platform source gets 403; a tenant writing to an existing platform source or asset gets 403 (seeded directly); nothing is created.
- Register and old version with any payload give 410, with no row and no storage call. That includes a payload that "matches" an existing upload's hash and key.
- Duplicate content through version-upload: 409, with `existing_asset_id` only when `CONTENT_ASSET_READ` is held.
- Revoked parent: 409 `ASSET_NOT_VERSIONABLE`.
- Unmanaged legacy row: job creation and dispatch give 409. The AI gateway is never called (fake gateway asserts zero calls). Rows are seeded with a foreign bucket, another tenant's prefix, another id and another hash.
- `managed_storage_key`: unit tests for each mismatch, and for path tricks (`..`, a doubled `/`, a trailing slash, case changes, percent-encoding).

**Races (PostgreSQL, `pg_smoke`, barrier inside `put` as in PR 2):**
- upload vs version-upload with identical bytes: one asset, the loser gets `DUPLICATE_CONTENT`, no orphan;
- two version-uploads of one parent: one new version, one 409 `ASSET_VERSION_CONFLICT`, the parent superseded once, no orphan;
- version-upload vs revoke of the parent: either the version wins and the revoke then applies to a superseded row, or the revoke wins and the version gets 409. Never an active child of a revoked parent.

**Real storage (storage gate, required):** version-upload stores and reads back by SHA-256; a failed commit deletes the object.

**Compatibility:**
- The boundary fixture moves to the upload endpoint with real bytes, so the boundary gate dispatches a managed asset. The full backend suite, `pg_smoke`, the storage gate and the boundary gate stay green.
- Backend tests that use register or version to set up data move to upload or to direct repository seeding. No test is deleted or weakened. Tests that asserted the old register behaviour are rewritten to assert 410.

## 6. Acceptance criteria (mapped)

| Criterion | Where |
|---|---|
| No arbitrary client-controlled object locations are accepted as trusted references | Q2: register and version retired; unmanaged rows never dispatched |
| Authorization before revealing an existing asset | Q1 and Q3: source authorization, then `CONTENT_ASSET_READ` for `existing_asset_id`; another tenant is 404 |
| The database is the final arbiter of concurrent duplicates | Q3: inserts only, constraint-classified races, conditional supersede; `pg_smoke` races |
| Registration and upload obey one identity policy | Q2 and Q3: upload and version-upload are the only creators, through one service |
| Invalid or missing objects cannot be registered as ingested content | Q4: bytes-derived metadata, verified `put`, managed-key gate at dispatch; PR 4 verifies on fetch |
| Compatibility checked before tightening | Section 1 callers; section 5 compatibility; 410 instead of silent removal |
| Full suite, storage gate, boundary gate pass | Section 5 |

## 7. Decisions for the owner and reviewer

1. **Fix F1 and F2 now, ahead of the rest?** Recommended. They are live cross-tenant writes, independent of the identity design. A small PR "3a" would:
   - pass and check the caller's tenant in version and revoke (404 across tenants);
   - refuse platform writes from tenant contexts (source creation, register, version, revoke);
   - add regression tests from the probes.
   It changes no contract except turning those writes into 404 or 403.
2. **Retire register (410), or keep it restricted as "adopt a managed object"?** Recommended: retire. There is no legitimate caller, and one creation path is easier to keep correct than two.
3. **Version-by-upload in PR 3, or a separate PR?** Recommended: in PR 3. Retiring the old version route without a replacement removes a capability.
4. **Existing platform rows, and the future platform-admin path:** out of scope here. Recorded as a follow-up, with the partial unique index (F7) as its precondition.

Proposed order once settled:
- **PR 3a** (F1, F2, F6 authorization fixes).
- **PR 3b**: `managed_storage_key` and the dispatch gate; version-by-upload; register and old version answer 410; the boundary fixture moves to upload; typed errors.
- Each PR merges only when its own gates and the boundary gate pass.
