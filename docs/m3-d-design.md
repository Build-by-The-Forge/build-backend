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
| `content_sources` | A personal source per student, or a staff source; descriptive fields only | Rights, which are per document |
| `content_rights_assertions` (new) | Append-only: each declaration or review of one document's rights | |
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
- **Who may read**, by **ruling B**: one policy, in one function in the application layer, used by every route that lists, returns or streams a document or its job. **That includes the existing staff routes**: `/content/assets`, `/content/sources/{id}/assets`, the job routes and reprocess, which check only the tenant today.

| Document | Owner | Another student, same tenant | Staff with content permission | Another tenant |
|---|---|---|---|---|
| Personal, not accepted by the scan | 409 `DOCUMENT_NOT_AVAILABLE` | 404 | 404 | 404 |
| Personal, private | Yes | 404 | 404 | 404 |
| Personal, publication approved and discoverable | Yes | Yes | Yes | 404 |
| Shared, rights not reviewed for students | Not applicable | 404 | Yes | 404 |
| Shared, rights reviewed for students | Not applicable | Yes | Yes | 404 |
| Unclassified, from before M3-D | Not applicable | 404 | Classification queue only | 404 |
| Deleted, revoked or rejected | 404 | 404 | 404 | 404 |

- **A content permission manages shared material. It isn't access to every student's private documents.** If support access is ever needed, it's a separate later decision: its own permission, time-limited and audited, as break-glass.
- **Lists** apply the same policy as a SQL predicate. A test checks that the SQL and the per-document check agree across every row of this table, so they can't drift apart.
- **No route can skip it.** A test enumerates every route under `/content` from the running app and fails on any that doesn't go through the policy, the way the drift gate checks routes against the contract.

## Retry (G-12)

`POST /content/my-documents/{id}/retry`, only when `retry_available` is true. The partial unique index decides races: a repeat during a retry returns the current state and starts nothing. `INGESTION_NOT_RETRYABLE` otherwise. Failure text comes through the existing allowlist (`ai_report.py`), and a student-triggered retry has its own limit, so it can't be used to burn AI capacity.

## Deletion (G-32)

The contract's promise: once this succeeds, the document can't be listed, opened, retrieved or newly cited, and its derived data leaves active retrieval.

1. **In one transaction:** status becomes `deleted`, any publication is withdrawn, and a row goes into a new `content_deletions` outbox. Listing and opening stop at this commit.
2. A worker calls a new signed AI route, `DELETE` chunks for the (tenant, asset), retried durably.
3. **Late chunks:** a job in flight can write chunks after the delete. A callback for a deleted asset is discarded and queues the AI delete again, and the outbox row isn't finished until the job is terminal and a delete has succeeded after that. The existing ingestion fence is the mechanism to reuse.
4. When a blob has no asset left, the sweeper removes its object after the grace period. The check and delete run under a lock against a concurrent upload of the same bytes, which is tested as a race.

**Limit, stated plainly:** between steps 1 and 2 the chunks still exist. Before M4, the `personal` exclusion keeps them out of retrieval. After M4, the allow-list does. Neither depends on the delete having finished.

**Past chat answers (ruling 9):** deleting a document can't erase text already copied into a conversation. M3-D provides, and M3-F defines what to do with it:

- **M3-D:** an outbox event, `content.document.deleted`, carrying the tenant, the asset and source IDs, and nothing of the content. From that commit, the document can't be retrieved, newly cited or opened.
- **M3-F must define, before integrating with documents:**
  - Existing citations to a deleted document stop opening it.
  - Stored excerpts and cached retrieved passages are removed or redacted.
  - Messages that copied source material have a defined redaction.
  - Audit records keep only metadata that's needed, never the deleted text.

Memory is out of scope here: `GATE_OPEN` stays `False`, and L4 defines what memory does when a source goes away.

## When an owner leaves

**Ruling 8:** leaving a tenant isn't deleting one's content.

When a membership ends, in the same transaction:

- The former member can't reach any of the tenant's documents, their own included, since tenancy is checked on every request already.
- Their publications are withdrawn, and any pending requests close.
- Their documents can't be discovered or retrieved by anyone, and their personal chunks are already excluded.

Their private records are **kept under a retention policy that doesn't exist yet**. That policy, and an account data export and deletion process, are a product and legal decision, recorded as open below. Nothing is deleted automatically until it exists. If they rejoin, their documents are theirs again and stay unpublished.

**Coordination:** membership changes are also what L4's `memberships.generation` and shared lock concern. The withdrawal joins the transaction that ends the membership under that lock, rather than following it as a separate event. M3-D and L4 agree the hook before either merges it.

## Rights and provenance

**Ruling A:** rights belong to each document. One student can hold their own notes, a lecturer's PDF, a publisher-licensed reference and a public-domain text, and one source can't describe all four.

**`content_rights_assertions`**, append-only, one row per declaration or review of one document:

| Field | Values |
|---|---|
| `asserted_by`, `role` | The owner declaring, or staff reviewing |
| `rights_basis` | `own_work`, `lecturer_provided`, `institution_licensed`, `publisher_licensed`, `public_domain`, `unknown` |
| `audience` | `owner`, `tenant`, `faculty`, `department`, `programme`, `course` |
| `redistribution` | `none`, `tenant_only`, `permitted` |
| `ai_use` | `not_permitted`, `permitted`; see [Three kinds of permission](#three-kinds-of-permission) |
| `declaration_version` | The wording the person saw, for an owner's declaration |
| `outcome`, `reason` | For a staff review: accepted or rejected, and why |

- **Effective rights** are the latest staff review if there is one. Otherwise they're the owner's declaration, and a declaration on its own permits nothing beyond its owner.
- **Publication consent** stays its own record, per document (see [Publication](#publication)).
- **Staff sources** may carry a default, which each new document copies into its own assertion at upload, recorded as copied. A later edit to the source never silently changes an existing document.
- **On the document:** `trust_class` is set by the backend. A student's upload is `user_provided`, and no client can raise it. `provenance` records who uploaded it, when, by which route, and the SHA-256 at upload.
- **Rights survive processing.** No ingestion state or reprocess changes them, and that's tested.

**Backfill:** existing documents have no assertion, so their effective rights are `unknown` and students can't read them until staff review them. That follows the contract's "verified for students" wording, and it's a real consequence for a deployment to plan around.

The principle: **access to content isn't permission to share it.** A declaration is recorded as what someone said, and the UI must not present it as legal clearance (PRD §91).

## Three kinds of permission

**Ruling 4:** none of these implies another.

| Permission | Means | Decided by | Default |
|---|---|---|---|
| **Publication** | Other students in the tenant may discover and read the document | The owner's consent, then staff approval | No |
| **Knowledge eligibility** | BUILD may use the content in retrieval for anyone besides its owner, which is scope `institutional` | A staff rights review with `ai_use: permitted` and an audience | No |
| **Provider eligibility** | Passages may be sent to an external model provider | Governance, through G-33 | Not decided |

- **Approving a publication doesn't change scope.** A published personal document stays `personal`, used in no one else's answers.
- **Becoming `institutional` needs its own review**, and changes the AI service's scope only through the backend's signed assignment.
- **G-33 and G-34 stay separate release considerations.** Until G-33 is decided, no production provider receives content, whatever the other two say.

## The tenant shelf

**Ruling 2: private-only stays the first-release rule.** The shelf is built, but it stays off until a tenant decides to enable it, and building it is no reason to turn it on.

- **The audience is the tenant**, not the internet. The route is `/content/tenant-shelf`, every response states `audience: "tenant"`, and the UI says which institution can see a document. Nothing uses the word "public".
- **The switch** is a per-tenant setting, off by default. Turning it on is a recorded decision by the tenant's owner, with conditions checked: a reviewer role is assigned, a report route and takedown exist, and the scanner is running. A deployment or merged code never turns it on.
- **Uploads are private by default.** Nothing publishes as a side effect, and no default in any request means consent.

### Publication

**Ruling 3:** a student's declaration isn't proof of redistribution rights, so staff approve every publication.

```text
private → requested → pending_review → approved → discoverable
                                     ↘ rejected
approved or discoverable → withdrawn (by the owner) or taken_down (by staff)
```

1. The student requests publication. BUILD records the consent and a rights declaration for this document, each with the wording version they accepted.
2. The publication waits in `pending_review`.
3. Staff with a new `content.publication.review` permission review the document and its rights basis. They approve or reject, with a reason, and the decision is audited.
4. An approved publication is **discoverable only while all of these hold:** the tenant switch is on, the latest scan is clean at a current signature version, the document isn't deleted, and its owner is still a member.
5. **The owner can withdraw at any time**, and withdrawal takes effect at that commit. Staff can take down at any time, after approval included.

Approval permits discovery and reading only. **It doesn't make the document usable in anyone's answers** (see [Three kinds of permission](#three-kinds-of-permission)).

### Moderation as a workflow

The ruling is explicit that report and takedown routes don't make a moderation process. Before a tenant can enable the switch, it needs:

- **A review queue:** staff routes listing pending publications and open reports, oldest first, with each item's rights declaration and scan result.
- **Decisions:** approve, reject, take down, dismiss a report. Each has a reason and is audited, and the student is told the outcome without the reporter's identity.
- **A runbook** in this repository: who reviews, how quickly, what to check for rights and content, and how to escalate. The tenant names its reviewers when enabling the switch.
- **Reports** that reach the queue at once, with a takedown available without waiting for the review.

These staff routes aren't in the mobile contract, since the first release is student-only.

### Proposed contract additions

Not yet in `openapi.yaml`. They go in a contract PR of their own.

| Route | Purpose |
|---|---|
| `GET /content/my-documents?level=&course_id=` | My Shelf: the existing list gains the two filters |
| `GET /content/tenant-shelf?level=&course_id=` | Discoverable documents of this tenant, with `audience: "tenant"` |
| `PATCH /content/my-documents/{id}` | The shelf form: title, course, level, semester, document type |
| `POST /content/my-documents/{id}/publication-request` | Request publication, with the consent and declaration versions accepted. Refused unless `ready` |
| `DELETE /content/my-documents/{id}/publication` | Withdraw a request or a publication, at once |
| `POST /content/tenant-shelf/{id}/report` | Report a document to the tenant's reviewers |

- **Levels** are 100 to 500, with 600 refused unless the tenant has it. The tenant's `levels` table decides this, not a hardcoded list.
- **`course_id`** must be an active course of the tenant, the same rule M3-C gave courses.
- **Shelf listings never show the uploader** unless the reviewer decides otherwise, because consent to share a file isn't consent to be named.

### Prefilled forms

The acceptance criterion says prefilled only when classification is confident enough. **No classifier for course or level exists**, so this is a new AI capability, not a wiring task. The first release has an empty form. `suggestions` joins the contract when a classifier exists, with a threshold set from measurement. Inventing a confidence score isn't an option (PRD §90).

## Reuse without reprocessing

**Ruling 5:** reuse is an optimization, and the new document never inherits an authorization boundary from the one it reuses.

**When:** a new upload has the same bytes as a document that's `ready` and that the student could already see: their own, or one discoverable on the tenant shelf. It never reuses another student's private document, because a fast `ready` would reveal that document exists. The new document is still scanned itself.

**What it shares:** only the chunks. It keeps its own owner, asset ID, publication consent, audience, rights assertions, trust class and provenance, all recorded as for any upload. `indexed_from_asset_id` names the source of the chunks.

**What it doesn't keep:**

- The source must stay eligible. When it's deleted, withdrawn, taken down or loses its rights, each dependent document goes back to `queued` and is processed on its own, in the same transaction as that change.
- Until it's reprocessed, it isn't retrievable from the source's chunks. M4's allow-list includes a dependent document only while its source is eligible.
- **Deleting one student's document never deletes another student's copy**, reused or not. That's tested.

This is the last PR. It can slip without weakening any guarantee, though the register's "without needless reprocessing" line would then need the reviewer to accept deferring it.

## Abuse limits

**Ruling 6, provisional:** these are starting values, each a setting rather than a rule in code, to be revisited against real upload sizes, storage, AI cost and observed abuse.

| Setting | Starting value |
|---|---|
| `content_student_uploads_per_day` | 50 |
| `content_student_stored_bytes` | 500 MiB per student per tenant |
| `content_document_retries_per_day` | 10 |

- **Atomic:** a usage row per (tenant, owner) is checked and charged by a conditional `UPDATE` in the same transaction that references the blob. Two uploads racing at the limit can't both pass, and a refused upload leaves no document.
- **Logical bytes:** a student is charged for their own document's size, never less because someone else holds the same bytes. A smaller charge would reveal that a classmate holds the file.
- **Non-disclosing:** a refusal is `QUOTA_EXCEEDED`, decided only by the caller's own usage.
- **Released on deletion:** deleting a document returns its bytes at that commit.
- **Retries** are counted per document per day, in the transaction that creates the retry job.
- **Tested** on PostgreSQL with uploads racing at the limit, so that exactly the allowed number succeeds.

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
