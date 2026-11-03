# M3-D design: student uploads and content rights

**Status: proposed, for the reviewer. Nothing here is implemented.** Written against backend `a16db6d` and ai-service `0553f35`.

**Summary:** today, a student's upload would be searchable by every student in the tenant. M3-D therefore starts by closing that in the AI service, then separates who owns a document from where its bytes live. Only after that does it open uploads, then rights, then the public shelf.

## Decisions for the reviewer

| # | Decision | Recommendation |
|---|---|---|
| 1 | Personal chunks are searchable by the whole tenant until M4 | Before any student upload exists, make retrieval exclude them by default, in the AI service. See [the sequencing blocker](#the-sequencing-blocker) |
| 2 | Decision B says uploads stay private in the first release, and that sharing needs moderation that doesn't exist. The M3 exit checklist requires a Public view | Treat the checklist as superseding Decision B only once these exist: a per-tenant switch, off by default, a staff takedown and a student report route. See [Decision B and the Public view](#decision-b-and-the-public-view) |
| 3 | Is a published document subject to staff approval first? | No approval queue in this release. Publishing is the owner's declared consent, staff can take it down, and the tenant switch stays off until a tenant accepts that |
| 4 | Does publishing a document make it usable in other students' answers? | No. Publication covers opening and reading. Its `knowledge_scope` stays `personal` until staff verify its rights, which is separate |
| 5 | Reusing processed content | Only from content the student could already see: their own, or published. Never from another student's private document, because a fast `ready` would reveal it exists |
| 6 | Student quotas | Set limits on documents and stored bytes per student per tenant. Values are proposed in [Abuse limits](#abuse-limits) |
| 7 | Malware scanning | Required before a document can be published, not before private upload. A provider isn't chosen, so publication stays off until one is |
| 8 | What happens to a published document when its owner leaves the tenant | It's unpublished, and stays private for 30 days pending their return, then is deleted. Needs the reviewer's view on retention |
| 9 | Excerpts already stored in past chat answers when the source is deleted | M3-D makes the document impossible to newly cite. Old excerpts are M3-F's to define, and that dependency is recorded here so it isn't lost |

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

The approved order puts M3-D before M4, and M4 is what limits retrieval to what a user may read. If M3-D ships as ordered, a student's private document reaches `ready` and is then returned in every other student's chat in that tenant. Being `private` in the backend wouldn't stop it, since the AI service never asks.

**Recommendation:** the first PR of this milestone is in the AI service, and no student route opens until it's merged.

- `document_chunks` gets `knowledge_scope`, `NOT NULL`, with existing rows backfilled as `institutional`.
- A signed ingestion dispatch must state the scope. A missing or unknown value is refused.
- Every retrieval path returns `institutional` chunks only. That covers `retriever.evidence`, which serves chat, explain and question generation, and also `/v1/ai/retrieve`.
- Each path has a test on real PostgreSQL proving a `personal` chunk can't come back.

This fails closed: personal documents can reach `ready` and be opened by their owner, while no answer can use them, including their owner's. M4 then opens them to their owner through its allow-list. **Until M4, the app must say that a personal document can't yet be used in answers.** That is a product limit the reviewer should accept knowingly.

It doesn't replace M4. Tenant-wide retrieval of `institutional` chunks that aren't `ready` stays open as G-05, for M4.

## The ownership model

The rule from the register: **deduplicating a physical file must not merge ownership, publication consent or access permissions.** So these become separate records.

| Record | Holds | Doesn't hold |
|---|---|---|
| `content_blobs` (new) | Tenant, SHA-256, size, detected type, object key | Any person, consent or permission |
| `content_assets` | The document: owner, display name, status, ingestion state, its blob | Bytes |
| `content_sources` | Personal source per student, or a staff source; rights fields | |
| `content_publications` (new) | Append-only consent: asset, who, what they declared, which declaration version, when, and any withdrawal | |

### Schema changes (migration 0030, reviewed on its own)

- `content_assets.owner_user_id`: null for staff material, set for a student's.
- `content_assets.blob_id`: null for existing rows, which keep their per-asset object.
- Drop `uq_content_assets_tenant_hash`. It's replaced by two partial unique indexes, so staff behaviour doesn't change:
  - `(tenant_id, content_sha256)` where `owner_user_id IS NULL`.
  - `(tenant_id, owner_user_id, content_sha256)` where `owner_user_id IS NOT NULL AND status <> 'deleted'`.
- `content_blobs`: unique `(tenant_id, content_sha256)`.
- `content_sources.owner_user_id`, unique per `(tenant_id, owner_user_id)`. New `VisibilityScope.PRIVATE`, and a check that private and an owner go together.
- New `AssetStatus.DELETED`.
- A partial unique index on `content_ingestion_jobs (asset_id)` for active states, so that one asset can't have two active jobs. The migration has to report existing violations rather than silently alter them.
- Rights columns: see [Rights](#rights-and-provenance).

### Duplicate detection without disclosure (G-25)

Three ways a student could learn about a classmate's file, and how each closes:

| Channel | Today | Designed |
|---|---|---|
| The response | 409 naming the existing asset | `DUPLICATE_CONTENT` only compares within the caller's own documents, so `existing_asset_id` only ever names their own |
| Upload time | Would differ if the store were skipped for a known hash | The object is **always written**, to a key derived only from the content, so the work is the same whether or not the blob exists |
| Processing time | A reused result is ready at once | Processed content is reused only from what the student can already see (decision 5). Otherwise the document is processed normally |

**Physical key:** `tenants/{t}/blobs/{sha256}`. A write can't corrupt another student's copy: the key is the hash of bytes verified on arrival. The AI service's `storage_reference.py` and `managed_storage_key` must both accept this form as well as the existing one, and the row's own tenant and hash still have to match.

**Timing evidence:** the same six-seed measurement method as registration (`scripts/measure_registration_timing.py`), comparing a known and an unknown hash from another owner. It reports its noise floor rather than claiming equality.

## Upload (G-01, G-02, G-38)

`POST /content/my-documents` as the contract states it:

1. Stream, hash and validate as today. The type comes from the bytes.
2. Find or create the student's personal source, safe under a race by the unique index.
3. Write the object to the blob key.
4. **In one transaction:** get or create the blob row, insert the asset, insert its `queued` job. Success means all three committed, so nothing can be left unqueued.
5. A failure before the commit leaves no document. The object may stay. The orphan sweeper, which only parses the per-asset key form today, is extended to remove a blob object no row references, after its grace period.

The worker's existing due-job loop then picks the job up, so durable queuing reuses what P3-6 built.

- **Idempotency:** the asset ID derives from the personal source and the key, so two students' keys can't collide. A replayed key whose document was since deleted answers `IDEMPOTENCY_KEY_REUSED`: it must not bring a deleted document back.
- **Chat uploads:** there's no second pipeline. A chat upload calls this same route, and a message then refers to the resulting `asset_id`. M3-F owns the reference and M3-D owns everything before it.
- **Staff routes** stay as they are, except G-07 below.

### G-11: the read timeout

Decision D sets this by measurement, so no value is proposed here. Measured on a throttled connection against the real app: 1, 2, 3.5 and 10 Mbit/s, with 1, 10 and 50 concurrent uploads, recording timeout rates, memory, disk spool and worker capacity. The result and its reasoning go in the PR that sets the value. The maximum of 600 seconds isn't a reason to choose it.

### G-07 and G-23

- `max_attempts` and `correlation_id` are removed from the job-creation request. The backend sets both.
- Asset ordering becomes `created_at DESC, id DESC`, the contract's order.

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
