# M3-D design: student uploads and content rights

**Status: revised after the reviewer's verdict on `4340b24` (changes requested). Nothing here is implemented, and M3-D stays Not started until this design is approved.** Written against backend `a16db6d` and ai-service `0553f35`.

**Summary:** today, a student's upload would be searchable by every student in the tenant. M3-D therefore starts by closing that in the AI service. It then separates who owns a document from where its bytes live, and scans every file before anything parses it. Only after that does it open private uploads. The shelf is built behind a switch that stays off, and publishing needs staff approval.

## The reviewer's rulings

Given on `4340b24`. Each is reflected in the section named.

| # | Question | Ruling | Section |
|---|---|---|---|
| 1 | Personal chunks are searchable tenant-wide before M4 | Approved with changes: fail closed, with three scope values and no blanket `institutional` backfill | [The sequencing blocker](#the-sequencing-blocker) |
| 2 | Decision B against the Public view | Staged: private-only stays the first-release rule. The shelf is built behind a per-tenant switch, off by default, and building it doesn't enable it | [The tenant shelf](#the-tenant-shelf) |
| 3 | Staff approval before publication | Required | [Publication](#publication) |
| 4 | Publication and AI answers | Approved: publication, knowledge eligibility and provider eligibility are separate | [Three kinds of permission](#three-kinds-of-permission) |
| 5 | Reusing processed content | Approved with conditions | [Reuse without reprocessing](#reuse-without-reprocessing) |
| 6 | Student quotas | Provisionally approved: configurable, atomic, non-disclosing | [Abuse limits](#abuse-limits) |
| 7 | Malware scanning | Changed: before anything processes a file, failing closed | [Scanning](#scanning) |
| 8 | An owner leaves the tenant | Changed: revoke, unpublish and exclude at once; keep under a retention policy; no 30-day deletion | [When an owner leaves](#when-an-owner-leaves) |
| 9 | Excerpts in past chat answers | M3-F defines the behaviour; M3-D provides the deletion event and source identity | [Deletion](#deletion-g-32) |
| A | Where rights live | Per document, not per source | [Rights and provenance](#rights-and-provenance) |
| B | Staff routes | One authorization policy for every read route, staff routes included. No staff access to private documents; break-glass would be a later, audited decision | [Reading](#reading-g-13) |
| C | Physical blob writes | Safe writes and references, with the orphan and last-reference race tests kept | [Physical storage and its races](#physical-storage-and-its-races) |
| D | Legacy ownership | Classified explicitly; unknown stays restricted | [Schema changes](#schema-changes-migration-0030-reviewed-on-its-own) |

Still open, and listed in [What this design doesn't settle](#what-this-design-doesnt-settle): the retention policy, the scanner's confirmation, staffing for review, and any break-glass access.

## What exists today

| Fact | Where | Consequence |
|---|---|---|
| Retrieval filters by tenant only, and chunks are searchable once committed | `pg_index.py`, G-05 | [The sequencing blocker](#the-sequencing-blocker) |
| One asset per (tenant, SHA-256) | `uq_content_assets_tenant_hash` | G-25: it tells one student what another uploaded, and it can't hold two owners of one file |
| Upload commits an asset and creates no job | `upload.py` | G-38: an upload can be left permanently unqueued |
| `created_by` is the only link to a person, and nothing checks it on reads | `content.py`, `reader_view.py` | Ownership has to be added, not inferred from this column |
| No private visibility value | `VisibilityScope` | Decision B's owner-only value doesn't exist yet |
| Object keys are `tenants/{t}/assets/{asset}/{sha}`, enforced on both sides | `managed_storage_key`, ai-service `storage_reference.py` | Physical deduplication needs a change in both repositories |
| The storage port's `get` returns whole bytes up to a limit | `storage.py` | Opening a document needs a new streaming, ranged read |
| `delete_document` exists in the AI service, with no route to it | `pg_index.py` | Deleting derived data needs a new signed route |
| Nothing stops two active jobs on one asset, and reprocess always creates a run | `job_handlers.py` | Retry can't be idempotent until a database rule exists |
| AI classification is about format only: scanned, native text, image, mixed | ai-service `analysis.py` | **No course or level classifier exists.** Prefilled shelf forms have nothing to prefill from yet |
| Upload needs the whole body in 60 seconds, at most 25 MiB | `config.py` | G-11: that requires a sustained 3.5 Mbit/s |

## The sequencing blocker

The approved order puts M3-D before M4, and M4 is what limits retrieval to what a user may read. If M3-D shipped as ordered, a student's private document would reach `ready` and then be returned in every other student's chat in that tenant. Being `private` in the backend wouldn't stop it, since the AI service never asks.

**Ruling:** the first PR of this milestone is in the AI service. No student route opens until it's merged and deployed.

### Scope values

| Value | Meaning | Retrieved by default |
|---|---|---|
| `institutional` | The backend has verified it for tenant-wide use: ownership classified, rights and audience reviewed | Yes, tenant-wide. G-05's readiness rule still waits for M4 |
| `personal` | A student's document | No. M4's allow-list opens it to its owner |
| `unknown` | Ownership or eligibility not established | No, for anyone |

### Who decides

- **Only the backend sets scope**, on a signed call, computed from its own records: ownership classification and rights review. No student request carries a scope.
- A staff request can't set `institutional` directly either. It follows from a completed rights review that permits AI use (see [Three kinds of permission](#three-kinds-of-permission)).
- A dispatch with a missing scope, or one that isn't one of the three values, is refused.

### Existing chunks

- The AI service can't tell whose a chunk is, so its migration sets **every existing chunk to `unknown`**. It assumes nothing.
- The backend then assigns scope through a new signed, idempotent call per (tenant, asset). It does so only for assets whose [classification](#schema-changes-migration-0030-reviewed-on-its-own) and [rights review](#rights-and-provenance) make them `institutional`. Each assignment records who reviewed it and when.
- **Consequence:** existing staff material stops being used in answers from the moment the AI migration runs until staff finish those reviews. That's the cost of not assuming. A deployment can do the reviews before the migration runs; the order is in [Delivery](#delivery).

### Retrieval paths

The PR inventories every entry point **from the code**, not from this list. It includes at least `retriever.evidence`, which serves chat, explain and question generation, and `/v1/ai/retrieve`. A path found later that reads chunks gets the same filter, or the PR isn't complete.

### Tests, on real PostgreSQL

- `personal` and `unknown` chunks never come back, on each path.
- Legacy rows are `unknown` after the migration.
- A dispatch with a missing or malformed scope is refused.
- No unsigned call can set or change a scope.
- A scope assignment naming another tenant's asset is refused.

**Accepted product limitation:** until M4's allow-list, students can open their own documents, but no answer can use them, not even their own.

This doesn't replace M4. Tenant-wide retrieval of `institutional` chunks that aren't `ready` stays open as G-05.

## The ownership model

The rule from the register: **deduplicating a physical file must not merge ownership, publication consent or access permissions.** So these become separate records.

| Record | Holds | Doesn't hold |
|---|---|---|
| `content_blobs` (new) | Tenant, SHA-256, size, detected type, object key | Any person, consent or permission |
| `content_assets` | The document: ownership class, owner, display name, status, ingestion state, its blob | Bytes |
| `content_sources` | Personal source per student, or a staff source; rights fields | |
| `content_publications` (new) | Append-only consent: asset, who, what they declared, which declaration version, when, and any withdrawal | |

### Schema changes (migration 0030, reviewed on its own)

**Existing records are classified, not assumed (ruling D).**

- `content_assets.ownership_class`: `institutional`, `personal` or `unclassified`, with `owner_user_id` set only for `personal`.
- **Every existing row is backfilled as `unclassified`.** An unclassified document is readable by no student and retrieved by nobody, and staff see it only in a classification queue.
- **Classification is a recorded staff decision per asset**, in a new append-only `content_ownership_classifications`: the asset, the class, who decided, when, and the evidence they relied on. A migration report lists what needs classifying, per tenant.
- **Evidence isn't proof.** G-01 shows students never held upload permission, so every existing asset came through a staff route. That makes `institutional` likely, but roles change and accounts are shared, so it's recorded as evidence for a person to accept, not applied as a default.
- `content_assets.blob_id`: null for existing rows, which keep their per-asset object.
- Drop `uq_content_assets_tenant_hash`. It's replaced by two partial unique indexes, so staff behaviour doesn't change:
  - `(tenant_id, content_sha256)` where `ownership_class <> 'personal'`.
  - `(tenant_id, owner_user_id, content_sha256)` where `ownership_class = 'personal' AND status <> 'deleted'`.
- `content_sources.owner_user_id`, unique per `(tenant_id, owner_user_id)`. New `VisibilityScope.PRIVATE`, and a check that private and an owner go together.
- New `AssetStatus.DELETED`.
- A partial unique index on `content_ingestion_jobs (asset_id)` for active states, so that one asset can't have two active jobs. The migration reports existing violations rather than silently changing them.
- New tables for blobs, rights, publication and quotas, described in their sections.

### Duplicate detection without disclosure (G-25)

Three ways a student could learn about a classmate's file, and how each closes:

| Channel | Today | Designed |
|---|---|---|
| The response | 409 naming the existing asset | `DUPLICATE_CONTENT` only compares within the caller's own documents, so `existing_asset_id` only ever names their own |
| Upload time | Would differ if the store were skipped for a known hash | The object is **always written**, to a key derived only from the content, so the work is the same whether or not the blob exists |
| Processing time | A reused result is ready at once | Processed content is reused only from what the student can already see (decision 5). Otherwise the document is processed normally |

**Physical key:** `tenants/{t}/blobs/{sha256}/{generation}`, described in the next section. The AI service's `storage_reference.py` and `managed_storage_key` must both accept this form as well as the existing one. The row's own tenant and hash still have to match, and the AI service fetches only the key the signed dispatch names.

**Timing evidence:** the same six-seed measurement method as registration (`scripts/measure_registration_timing.py`), comparing a known and an unknown hash from another owner. It reports its noise floor rather than claiming equality.

### Physical storage and its races

**Ruling C:** concurrent uploads must never overwrite unsafely, or leave a row pointing at a missing object.

A blob row is `pending`, `active` or `deleting`. At most one row per `(tenant_id, content_sha256)` isn't `deleting`, enforced by a partial unique index. Each row has its own random `generation`, so its object key is never shared with an earlier row.

**Upload:**

1. **Claim**, in a short transaction: lock or create the blob row that isn't `deleting`, and set `claimed_until` to now plus the grace period.
2. **Write** to that row's key, always, with the store verifying the SHA-256. Writing identical verified bytes to the same key is idempotent, and a checksum mismatch fails the upload.
3. **Reference**, in a transaction: lock the blob row. If it's become `deleting`, start again from step 1, which gives a new generation and key. Otherwise insert the document and its job, and mark the blob `active`.

**Sweeper:** it locks the row and acts only if no document references it and `claimed_until` has passed. It marks the row `deleting` and commits, deletes that generation's object, then deletes the row. A crash between those steps resumes from `deleting`.

An upload can't lose its object: either it claimed first, so the sweeper skips the row, or it sees `deleting` and gets a fresh key of its own.

**Tests**, keeping the existing orphan-sweeper and last-reference races:

- Two owners upload the same bytes concurrently.
- The last reference is deleted while the same bytes upload.
- The sweeper crashes between marking and deleting.
- The store reports a checksum mismatch.
- A pending blob is abandoned and later swept.

**Timing:** the claim is a lookup or an insert either way. It's part of the G-25 timing measurement, not assumed to be equal.

## Upload (G-01, G-02, G-38)

`POST /content/my-documents` as the contract states it:

1. Stream, hash and validate as today. The type comes from the bytes.
2. Find or create the student's personal source, safe under a race by the unique index.
3. Claim the blob and write its object, as in [Physical storage](#physical-storage-and-its-races).
4. **In one transaction:** reference the blob, insert the document in `quarantined`, and insert its scan. Success means all of it committed, so nothing can be left unscanned or unqueued.
5. A failure before the commit leaves no document. The object may stay. The orphan sweeper, which only parses the per-asset key form today, is extended to the blob form.

Once the scan accepts the file, its ingestion job is queued in the same transaction, and the worker's existing due-job loop picks it up. Durable queuing reuses what P3-6 built.

- **Idempotency:** the asset ID derives from the personal source and the key, so two students' keys can't collide. A replayed key whose document was since deleted answers `IDEMPOTENCY_KEY_REUSED`: it must not bring a deleted document back.
- **Chat uploads:** there's no second pipeline. A chat upload calls this same route, and a message then refers to the resulting `asset_id`. M3-F owns the reference and M3-D owns everything before it.
- **Staff routes** stay as they are, except G-07 below.

### G-11: the read timeout

Decision D sets this by measurement, so no value is proposed here. Measured on a throttled connection against the real app: 1, 2, 3.5 and 10 Mbit/s, with 1, 10 and 50 concurrent uploads, recording timeout rates, memory, disk spool and worker capacity. The result and its reasoning go in the PR that sets the value. The maximum of 600 seconds isn't a reason to choose it.

### G-07 and G-23

- `max_attempts` and `correlation_id` are removed from the job-creation request. The backend sets both.
- Asset ordering becomes `created_at DESC, id DESC`, the contract's order.

## Scanning

**Ruling 7:** a private upload is no reason to process untrusted content unscanned. Every document is scanned before anything opens it.

```text
uploaded → quarantined → accepted → queued → processing → … → ready
                       ↘ rejected
```

- **Nothing parses an unscanned file.** No OCR, extraction, chunking, embedding or AI dispatch happens until the scan accepts it. The backend refuses to dispatch, and the AI service only fetches what a signed dispatch names.
- **It fails closed.** If the scanner is down or errors, the document stays `quarantined` and the worker retries with backoff. Nothing is accepted by default. The student sees that it's waiting for a security check.
- **Rejected files aren't served to anyone**, their owner included. The student is told only that the file couldn't be accepted, with no signature name. They can delete it. Otherwise its object is removed after the grace period, and the record keeps only metadata.
- **No one opens a document before it's accepted**, its owner included. Serving unscanned bytes to a device is the risk being closed.
- **Each document is scanned itself.** A scan result isn't reused across identical bytes: an instant acceptance would reveal that someone else already uploaded the file. Each result records the scanner, its signature version and the time.
- **Publication needs a clean scan at a current signature version.** Published documents are rescanned when signatures update, on a cadence the tenant sets.

**Scanner:** ClamAV (`clamd`) is recommended, run as its own container in the deployment, in CI and in the boundary gate, with `freshclam` updating signatures. It's self-hosted, so no third party receives student files. The backend streams the stored object to it over `INSTREAM` from the worker, never from the API process.

The implementation plan includes:

- Its container, with network isolation.
- A maximum scan size at or above the upload limit.
- Timeouts.
- An EICAR test file in CI that must be rejected.
- A test with the scanner stopped, which must show uploads staying quarantined.
- Measured worker capacity.

The reviewer confirms the choice.

**Contract:** the `Ingestion.status` enum gains `quarantined` and `rejected`, in the contract PR.

## Reading (G-13)

`GET /content/assets/{asset_id}/content`:

- Authorizes on every request, with no reusable URL. A storage address never reaches the client.
- The port gains a streaming read with a byte range, so a 25 MiB file isn't held in memory per request.
- One range per request. A multi-range request gets the whole document, and a range past the end gets `RANGE_NOT_SATISFIABLE`.
- `ETag` from the SHA-256. `X-Content-Type-Options: nosniff`, the stored type rather than anything from the client, and `Content-Disposition` with a sanitized name, so a filename can't inject a header.
- **Who may read:** the one rule, in one function, used by every read route:

| Document | Owner | Another student, same tenant | Staff with content permission | Another tenant |
|---|---|---|---|---|
| Personal, unpublished | Yes | 404 | 404 | 404 |
| Personal, published and clean | Yes | Yes | Yes | 404 |
| Shared, rights verified for students | Yes | Yes | Yes | 404 |
| Deleted, or revoked | 404 | 404 | 404 | 404 |

A document the scan hasn't accepted isn't served to anyone: `DOCUMENT_NOT_AVAILABLE` (409) for its owner, and the usual 404 for anyone else.

Staff can't read a student's private document. If support access is ever needed, it needs its own decision and audit trail, rather than a side effect of a content permission. **This differs from today's staff routes, which check only the tenant**, so those routes need the same rule or they're a bypass.

## Retry (G-12)

`POST /content/my-documents/{id}/retry`, only when `retry_available` is true. The partial unique index decides races: a repeat during a retry returns the current state and starts nothing. `INGESTION_NOT_RETRYABLE` otherwise. Failure text comes through the existing allowlist (`ai_report.py`), and a student-triggered retry has its own limit, so it can't be used to burn AI capacity.

## Deletion (G-32)

The contract's promise: once this succeeds, the document can't be listed, opened, retrieved or newly cited, and its derived data leaves active retrieval.

1. **In one transaction:** status becomes `deleted`, any publication is withdrawn, and a row goes into a new `content_deletions` outbox. Listing and opening stop at this commit.
2. A worker calls a new signed AI route, `DELETE` chunks for the (tenant, asset), retried durably.
3. **Late chunks:** a job in flight can write chunks after the delete. A callback for a deleted asset is discarded and queues the AI delete again, and the outbox row isn't finished until the job is terminal and a delete has succeeded after that. The existing ingestion fence is the mechanism to reuse.
4. When a blob has no asset left, the sweeper removes its object after the grace period. The check and delete run under a lock against a concurrent upload of the same bytes, which is tested as a race.

**Limit, stated plainly:** between steps 1 and 2 the chunks still exist. Before M4, the `personal` exclusion keeps them out of retrieval. After M4, the allow-list does. Neither depends on the delete having finished.

Memory is out of scope here: `GATE_OPEN` stays `False`, and L4 defines what memory does when a source goes away.

## Rights and provenance

G-30 needs these recorded, and they must survive processing rather than sit beside it:

| Field | On | Values |
|---|---|---|
| `rights_basis` | Source | `student_declared`, `institution_licensed`, `publisher_licensed`, `public_domain`, `unknown` |
| `audience` | Source | `owner`, `tenant`, `faculty`, `department`, `programme`, `course` |
| `redistribution` | Source | `none`, `tenant_only`, `permitted` |
| `trust_class` | Asset | Set by the backend. A student's upload is `user_provided`, and no client can raise it |
| `provenance` | Asset | Who, when, by which route, the SHA-256 at upload |

Existing rows backfill to `unknown` and `none`, so they fail closed and need staff to set them. **That makes existing shared material unavailable to students until it's reviewed**, which follows the contract's "verified for students" wording but is a real consequence to accept. `listSources` and `listSourceDocuments` show only rows with rights verified.

The principle: **access to content isn't permission to share it.** `rights_basis` and consent are declarations, and the UI must not present them as legal clearance (PRD §91).

## The shelf

### Decision B and the Public view

Decision B approved private-only for the first release, because sharing needs moderation that doesn't exist. The M3 exit checklist later requires a Public view with explicit consent to publish. These conflict, and the later instruction doesn't say it supersedes the earlier one, so **this needs the reviewer's explicit ruling**. Recommendation: build it, keep it behind the per-tenant switch, off by default, and turn it on only with a takedown and report route in place.

### Proposed contract additions

Not yet in `openapi.yaml`. They go in a contract PR of their own, once these decisions are made.

| Route | Purpose |
|---|---|
| `GET /content/my-documents?level=&course_id=` | My Shelf, with the existing list adding the two filters |
| `GET /content/shelf?level=&course_id=` | The Public view: published, clean, not deleted, this tenant only |
| `PATCH /content/my-documents/{id}` | The shelf form: title, course, level, semester, document type |
| `PUT /content/my-documents/{id}/publication` | Publish, with the declaration version the student accepted. Refused unless `ready` and scanned clean |
| `DELETE /content/my-documents/{id}/publication` | Withdraw. The public document disappears at that commit |
| `POST /content/shelf/{id}/report` | Report a public document. Staff then take it down with the existing revoke |

- `level` is 100 to 500, with 600 refused unless the tenant has it: `levels` is per tenant, so that table decides rather than a hardcoded list. `course_id` must be an active course of the tenant, the same rule M3-C gave courses.
- Public listings show the title, course and level. **They never show the uploader**, unless the reviewer decides otherwise, because consent to share a file isn't consent to be named.
- Uploads are private by default. Nothing publishes as a side effect, and no default in any request means consent.

### Prefilled forms

The acceptance criterion says prefilled only when classification is confident enough. **No classifier for course or level exists**, so this is a new AI capability, not a wiring task. Recommendation: the first release has an empty form, and `suggestions` joins the contract when a classifier exists, with a threshold set from measurement on the evaluation set. Inventing a confidence score isn't an option (PRD §90). If the reviewer treats prefill as required for M3-D, it needs its own scoped AI work.

### Reuse without reprocessing

For a document already `ready`, one from the student's own account or one published in the tenant, a new upload with the same bytes shares its chunks instead of being processed again:

- The new asset records `indexed_from_asset_id` and its own run. The M4 allow-list resolves it to the chunks' real asset, and a citation is reported against the document the caller holds.
- When the source of those chunks is deleted or withdrawn, the dependent asset goes back to `queued` and is processed on its own, so one student's deletion never takes away another's document.
- This is the last PR. It's an optimization with real edge cases, so it can slip without weakening any guarantee, except the register's "without needless reprocessing" line, which the reviewer would need to accept deferring.

## Abuse limits

Proposed starting values, each a setting, each to be confirmed by measurement: 50 uploads per student per day, 500 MiB stored per student per tenant, 10 retries per document per day. Over a limit is `RATE_LIMITED` or a new `QUOTA_EXCEEDED`. The count is per owner, so it reveals nothing about anyone else. Physical deduplication doesn't reduce a student's quota, or the quota itself would reveal that a classmate holds the file.

## Delivery

One concern per PR. Each has the required gates, and the drift gate moves with the code in the same commit.

| # | Repo | PR | Closes |
|---|---|---|---|
| 0 | Backend | This design | |
| 1 | AI | `knowledge_scope`, fail-closed retrieval on every path | Unblocks everything, part of G-31 |
| 2 | Backend | Contract PR for the additions above, after the decisions | |
| 3 | Backend | Migration 0030 and domain changes, no route behaviour changes | |
| 4 | AI, backend | The blob key form accepted, dispatch states the scope | |
| 5 | Backend | Upload and queue, list and get, read rule on every route | G-01, G-02, G-25, G-38, G-23, G-07 |
| 6 | Backend | Retry | G-12 |
| 7 | Backend | Opening a document, with ranges | G-13 |
| 8 | AI, backend | Signed delete, outbox, late chunks, blob sweep | G-32 |
| 9 | Backend | Rights, provenance and backfill | G-30 |
| 10 | Backend | Timeout measurement and value | G-11 |
| 11 | Backend | My Shelf filters and form | |
| 12 | Backend | Publication, Public view, report, tenant switch, scan gate | |
| 13 | AI, backend | Reuse without reprocessing | |

G-31 stays open until M4. **No student route is reachable in a deployment until PR 1 is deployed there**, and PR 5 refuses to dispatch to an AI service that doesn't state it supports the scope.

## Acceptance tests

Run on migrated PostgreSQL unless marked. Statements repeat past five runs where a partial index or a plan could differ.

| Requirement | Test must show |
|---|---|
| Personal chunks excluded | Chat, explain, question generation and `/v1/ai/retrieve` never return a `personal` chunk, for any user, including its owner before M4 (boundary) |
| Missing scope | A dispatch without a scope is refused (boundary) |
| Two owners, one file | Two students upload the same bytes: two documents, two owners, one blob, one object |
| Ownership isn't merged | A deletes: B still lists, opens and retries theirs, byte for byte |
| Consent isn't merged | A publishes: B's copy stays private, and B's copy doesn't appear on the shelf |
| Permissions aren't merged | A's publication doesn't let C open B's copy by ID |
| No disclosure | Identical responses for a hash another student holds and one nobody holds, by status, body and headers; timing evidence within the stated noise floor |
| Cross-student read | Every route gives the same `RESOURCE_NOT_FOUND` as a nonexistent ID, including staff routes |
| Atomic queue | A failure at each step leaves either nothing or a document with its queued job, never a document without one |
| Upload races | The same key twice, the same bytes under two keys, two students with the same bytes |
| Retry races | Two retries: one job. A retry when none is available: `INGESTION_NOT_RETRYABLE` |
| Reading | Full, ranged, past the end, multi-range, wrong owner, deleted; no storage address in any response |
| Delete | After the commit: not listed, opened or retrievable. A job in flight can't bring chunks back. The AI being down delays the cleanup, not the promise |
| Blob race | Deleting the last reference while the same bytes upload: the object survives, or the upload succeeds with its own copy, never a row without an object |
| Rights survive | Scope, rights and trust class are unchanged after every ingestion state and a reprocess |
| Trust can't be raised | No client input changes `trust_class`, `owner_user_id` or `knowledge_scope` |
| Consent | No route publishes without the declaration. Withdrawal removes it at that commit |
| Public view | Published, clean, this tenant, with filters by level and course, paginated, no uploader named |
| Bad input | The same PostgreSQL bounds M3-C added: NUL, oversized offsets, lengths past a column |

## Coordination with the other lanes

| Shared thing | Owner | Rule |
|---|---|---|
| `/content` in `openapi.yaml`, `gaps.yaml` content entries | M3-D | Other lanes don't edit them |
| `/assessment` in `openapi.yaml` | M3-E | |
| `/conversations` in `openapi.yaml` | M3-F | It refers to `asset_id` and doesn't change `Document` |
| `contract_sha256` | Whichever PR merges first | The other rebases its hash. Conflicts here are expected and mechanical |
| Alembic head | One migration PR at a time | M3-D's 0030 and L4's outbox can't both claim the next number, so whichever is second renumbers |
| The AI service's chunk schema | M3-D | M4 builds on it |

## What this design doesn't settle

- **M4's allow-list**, including whether `chunk.attempt` is reliable. M3-D only ensures nothing personal is retrievable meanwhile.
- **The legal position** on students sharing copyrighted material. A declaration is recorded, but no one has reviewed the wording. G-33 and G-34 stay open and separate.
- **Which malware scanner.** Publication stays off until one is chosen.
- **Real-world timing on a deployed stack.** The disclosure evidence is local, as registration's was, and needs repeating when a deployment exists.
