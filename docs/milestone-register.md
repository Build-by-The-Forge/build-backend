# Milestone register

The one living record of where the programme stands, from here to M7. Update it in the PR that changes a milestone's status.

**A merged PR doesn't complete a milestone.** A milestone is done when its acceptance criteria hold and its evidence exists. "Approved" means an explicit "APPROVED — merge eligible" on an exact commit.

There are two tracks, and neither one's progress counts for the other:

- **M-track:** mobile integration, M0 to M7. This is the path to release.
- **L-track:** assessment lifecycle and learning memory. Its M-track dependency is noted where one exists.

## M-track

| Milestone | Scope | Depends on | Acceptance | Required tests | Status | Approved SHA |
|---|---|---|---|---|---|---|
| M0 | Conventions, inventory, boundary decisions | None | Reviewer approval of the three documents | Link check | **Merged** | `615ee48` (merge) |
| M1 | Intended mobile API contract | M0 | The contract describes what the system should guarantee | `tests/test_mobile_contract.py` | **Merged** | `31faad4` |
| M2 | Drift gate against the contract | M1 | Every known gap is listed, and a closed gap stays closed | `test_mobile_contract_drift.py` | **Merged** | `16a5227` (merge) |
| M3-A | One error shape and stable codes | M2 | G-20, G-22, G-08 closed | HTTP, drift gate | **Complete:** all three gaps closed, drift gate enforcing them | #72 `1c6cb7f`, #73 `0826bc8` (merges) |
| M3-B | Typed identity bodies, device handling | M3-A | G-14 closed; G-39 with M3-E | HTTP, drift gate | **Complete:** G-14 closed; registration's durable, non-enumerating 202; G-39's membership finding closed, the rest with M3-E | #75 `4faca25`, #76 `604f8b1` (merges) |
| M3-C | Academic structure reads, pagination | M3-A | G-09 closed; G-10 with M3-E | HTTP, drift gate | **Complete:** G-09 closed; G-10's catalogue findings closed, its assessment and attempt findings wait for M3-E | #77 `418fbd5` (merge) |
| M3-D | Student uploads, content rights | M3-A | G-01, G-02, G-11, G-12, G-13, G-25, G-30, G-32, G-38, G-07, G-23 closed; G-31 with M4 | HTTP, object storage, PostgreSQL, boundary | **Design approved**. Its first PR, the AI scope filter, is in review as a pair: ai-service #43 with backend #86. No student route opens until PRs 1, 4 and 6 are deployed | #79 `fef4cfa` (design) |
| M3-E | Assessment contract | M3-A, L1 to L3 | The rest of G-10 and G-39 closed; M3-C and M3-B closed their other parts. Lifecycle gaps are already closed | HTTP, drift gate | **Design approved**, implementation not started. Partly done by L1 to L3 | #80 `f4ce131` (design) |
| M3-F | Conversations, cited chat | M3-A | G-17, G-18 closed; G-04 with M4 | HTTP, boundary | **Design approved**, implementation not started. No conversation reaches students until retention is decided | #81 `e0057ad` (design), #83 `bcbbde8` (provenance amendment) |
| M4 | Retrieval eligibility and citation authorization | M3-D, M3-F | G-05 closed; G-04 and G-31 closed; the boundary doc's measurements taken | Boundary, both repositories | **Specified** in `mobile-m0-boundary.md` | |
| M5 | Typed client, auth and session, error handling | M3-A, M3-B | Generated client passes contract-drift checks; secure token storage | Client against the contract | **Not started** | |
| M6 | Student workflows and screens | M5, M3-C to M3-F | Screens use the generated client only; G-26 closed; device tests | Device, end to end | **Not started** | |
| M7 | Pinned, release-blocking integration gate | M4, M5, M6 | The evidence list in `mobile-m0-boundary.md` passes on pinned SHAs | Real stack with the generated client | **Not started**. Test design can start early | |

### M3 position

M3 is **not close to done**. The fixes merged so far closed security and lifecycle gaps early, ahead of their slices. M3-A, M3-B and M3-C are the only slices whose gaps are closed, and G-10 stays open for M3-E. M3-D to M3-F haven't started, apart from the lifecycle work in M3-E. All three designs are approved, which is permission to implement them in order, not evidence that any of their gaps are closed.

| | Count | IDs |
|---|---|---|
| Closed | 16 | G-03, G-06, G-08, G-09, G-14, G-15, G-16, G-20, G-21, G-22, G-24, G-27, G-29, G-35, G-36, G-37 |
| Open | 23 | 7 contract, 16 implementation, listed in `contracts/mobile/gaps.yaml` |
| Open and blocking | 2 | G-01, G-02: students can't upload or start ingestion |

`contracts/mobile/gaps.yaml` stays the source of truth for individual gaps. This table is a snapshot of it. Don't reopen a closed gap without new evidence.

## L-track

| Milestone | Scope | Depends on | Acceptance | Required tests | Status | Approved SHA |
|---|---|---|---|---|---|---|
| L0-A | ai-service default-deny memory gate | Plan | Reads and writes refused; production image refuses | Unit, PostgreSQL, real image | **Merged** | `2e9307d` |
| L0-B | Backend sends nothing while closed | L0-A | No request leaves; submission unaffected | Integration, real image, boundary | **Merged** | `5ea38a4` |
| L1 | Attempt policy, limits, retakes | Plan | G-29 closed | HTTP, PostgreSQL races | **Merged** | `899e52a` |
| L2 | Result release, feedback, standing attempt | L1 | G-16, G-36 closed | HTTP, PostgreSQL | **Merged** | `31d7d6a` |
| L3 | One finalization path, worker, database clock | L2 | G-37 closed | HTTP, PostgreSQL races, boundary | **Merged** | `bc9bee8` |
| AI-1 | Idempotent upsert, contributions, recompute | L0-A | The plan's AI-1 tests | PostgreSQL, forced-order lock test | **Merged** (ai-service #42) | `0553f35` (merge) |
| L4 | Memory outbox and dispatcher, `memberships.generation`, shared membership lock, removing the background task | AI-1 | The six conditions on #59, sending `event_id`, removing #65's older table set | PostgreSQL forced-order and lock-removal races | **Specified** in `assessment-lifecycle-plan.md`, approved on #59 | |
| Memory activation | The production gate's conditions | L4, and everything in that gate | Each condition implemented and verified | Own safety review | **Not started**. `GATE_OPEN` stays `False` | |

**L4 is the plan's final L-track PR.** The plan defines no L5, L6 or L7, so this register doesn't list any.

## M3 exit checklist

Set by the reviewer on #76. M3 is done when all of these hold, each with evidence:

- M3-A: G-08, G-20 and G-22 closed.
- M3-B: G-14, and registration's durable, non-enumerating 202, closed.
- M3-C: G-09, and catalogue pagination and trailing-slash requirements, closed.
- M3-D: all upload, ingestion, rights, ownership, deduplication, retry and deletion requirements closed.
- M3-E: assessment pagination and the remaining G-39 findings closed, with the L1 to L3 guarantees preserved.
- M3-F: conversation persistence, cited responses and grounding behaviour closed.
- The contract-drift tests pass with no unapproved gaps.
- PostgreSQL, authorization and boundary tests pass.
- The mobile contract and backend implementation agree.
- This register is updated with exact merged SHAs and acceptance evidence.

**M3-D is larger than its route gaps.** Closing every listed gap isn't enough. These are also acceptance criteria:

- My Shelf and Public views, with 100 to 500 level filters and course filtering.
- Uploads private by default, with explicit consent to publish.
- Form-like shelf submission, prefilled only when classification is confident enough.
- Chat uploads and shelf uploads entering the same backend-owned ingestion pipeline.
- Exact duplicate detection that never reveals another student's private record.
- Reuse of eligible stored content without needless reprocessing.
- Authorized opening, reading and downloading of public resources.
- Processing states and retry visible to the student.
- Rights, provenance, trust class and audience restrictions preserved through processing.
- **Deduplicating a physical file must not merge ownership, publication consent or access permissions.** M3-D must prove this separation.

M4 is a security boundary, not a search improvement: being indexed doesn't mean every student may retrieve a document.

## Approved order

Decided by the reviewer on #66. M3-A goes before L4, which changes the plan's scheduling, not L4's architecture or its existence. Two conditions hold:

- L4 completes before any memory reporting is enabled or any production memory event is dispatched.
- L4 removes #65's temporary table allowance.

A faster order doesn't weaken any acceptance criteria. M3-D isn't done because uploads return success, and M7 isn't done because a workflow passes.

**Immediate work**

1. AI-1: merged (ai-service #42).
2. This register: merged (#67).
3. The boundary gate: fixes merged (#68, #69), and the acceptance bar below is met.
4. M3-A: complete (#72, #73).

**Boundary gate acceptance bar, before M3-A: met**

- 40 consecutive full gate runs against the same pinned commits, after both fixes.
- Every first-attempt result is recorded. A rerun never erases a failure.
- No skipped required tests, and no hidden retries that turn failures green.
- A failure is preserved and diagnosed. After a corrective change, the count restarts from zero on new pinned commits.

Forty clean runs are a practical confidence check, not proof of reliability. They sit alongside the root-cause fixes and regression tests.

The 40-run boundary-gate requirement is met. All 40 full executions passed on their first attempt against the same pinned merge commits (`backend: 9dd8de6`, `ai-service: 0553f35`). Executions were independently isolated and dispatched in sequence, with up to eight running concurrently. No retries, skipped tests or count variations occurred. This establishes 40 consecutive clean executions by campaign dispatch order, but does not constitute a strictly sequential or long-duration soak test.

Ledger of all 40 runs: [#70](https://github.com/Build-by-The-Forge/build-backend/pull/70#issuecomment-6561912352). Accepted by the reviewer on 2026-11-01.

Passing this gate allows M3-A to proceed. It doesn't bypass any remaining milestone, and `GATE_OPEN` stays `False`.

**M-track**

5. M3-B: complete (#75, #76).
6. M3-C: complete (#77).
7. M3-D, now, the largest slice, which holds the two blockers. Its design is approved (#79), and implementation follows the order in `m3-d-design.md`, starting with the AI scope filter. The catalogue work is not evidence that document ingestion is solved.
8. M3-E, which can run alongside M3-D.
9. M3-F, its design approved (#81, amended in #83), behind M3-D's provenance and contract work, and tested against the completed authorization rules.
10. M4.
11. M5. Its scaffolding can start: M3-A's error shape is merged.
12. M6, against the generated client. Screen design can start earlier.
13. M7 on pinned SHAs. Its test design can start at any time.

**L-track, independently:** AI-1 and M3-A are merged, so L4 can start, then memory activation under its own approval once every gate condition is implemented and verified.

## Product direction for this sprint

Given by the reviewer on #79 at `06b433a`. It changes what's built first, not any security, authorization or deployment gate.

| Area | Decision |
|---|---|
| Users | Students. The first release is the Student Adoption Release, and a normal login is a student's |
| Other roles | Lecturer, HOD, faculty and university workflows are paused. They stay in the architecture |
| Student Shelf | The central academic document library |
| Upload privacy | Private by default |
| Student publication | Opt-in. During this sprint, a student's own work with tenant sharing publishes on their request, without staff approval. Any other rights basis stays private until the moderated workflow exists. This is a deliberate sprint exception, not the removal of governance |
| "Public" | Discoverable by authorized students of the same tenant, never the open internet |
| AI knowledge eligibility | Separate from publication |
| Provider eligibility | Separate from publication and from retrieval |
| AI capabilities | BUILD implements the complete AI capability set, including Offline AI: chat and contextual help, document understanding and OCR, grounded retrieval, explanations, summaries and question generation, learning support, and offline execution with synchronization. Offline isn't reduced to a basic chatbot. Capabilities may use different models and reach different quality offline, so the goal is the capability, with local execution and fallbacks designed per capability |
| Classifying existing material | During the sprint, by an audited operator command, approved on `fe7742e` under seven conditions in `m3-d-design.md`: tenant authorization, evidence per document, institutional only, the same service as the staff route, a full audit record, dry runs and bounded idempotent batches, and no retrieval before the AI service acknowledges |
| Reports on shelf documents | Three distinct, authorized students hide a document temporarily until the takedown contact restores it or takes it down. Approved on `fe7742e` with safeguards. Hiding changes no rights or AI eligibility |
| Revoked sources | A document revoked while an answer is generated withholds the whole answer, cited or not, on every path. Ruled on `fe7742e` as release-blocking |
| Offline authorization | A device holds what its user was authorized for at its last sync, under a signed lease that starts at 72 hours. The lease runs on monotonic elapsed time and boot identity: a reboot ends it, missing or inconsistent trusted time fails closed, and the wall clock can only shorten it. It doesn't hold on a rooted or jailbroken device. Offline answers stay provisional until reconnect validation passes. Approved with M3-D's design at `ab09d2c` |

**Not permitted by these decisions:** exposing a route before its own gates pass. A design approval isn't permission to expose a route, and `GATE_OPEN` stays `False`.

## M3-D implementation rulings

Given by the reviewer on the first implementation pair (ai-service #43 and backend #86), before review. They bind later PRs, not just this pair.

| Topic | Ruling | Binds |
|---|---|---|
| Scope on the ingestion dispatch | Deferred to PR 7. An ingested document stays `unknown`, and out of retrieval, until a signed assignment | PR 7 adds the requirement without any window in which unclassified documents become accessible |
| `denied_assets` limit | 1,000 entries, a **shared contract limit**. The AI service refuses a longer list, and the backend never sends one: it refuses the tenant's retrieving calls instead of truncating. Published in the AI OpenAPI contract and in the boundary design's A.6 | Any change moves in both repositories and is tested together. Neither side configures its own |
| `sources_used` against the read policy | Deferred to PR 4. Until then the backend verifies the signature, the exact request, the unconsumed nonce, and the structure of `sources_used`, and withholds anything else | A signature doesn't prove the AI service retrieved only authorized sources: PR 4's provenance check closes that |
| Merging the pair | Coordinated: neither merges alone, and each needs its own exact-SHA verdict. The AI PR merges first, then the backend's `boundary-gate` is re-run on its unchanged head | Every later pair that changes the AI request contract |

## Open incidents

| Incident | Status | Closes when |
|---|---|---|
| Commit `067d980` (closed PR #66) was pushed to a public branch with an internal audit file | **Open.** GitHub Support purge request outstanding; treat the file as publicly accessible | GitHub confirms the purge |

## Deferred risks

**From M3-C's audit, accepted by the reviewer as non-blocking on `2c5c0cd`, not yet scheduled:**

- About 20 `"... repository is required"` errors in the assessment, content and curriculum services are marked as written for clients, though they're wiring faults. They should be `RuntimeError`, as the catalogue's now is.
- M3-C refused input PostgreSQL can't hold (a NUL in text or an ID, an integer past its column) on catalogue routes only. Other routes haven't been audited for the same 500. M3-E's lists get the shared `offset` maximum when they adopt it.
- A write route would answer 422 for the internal parent-ID checks in `add_topic`, `add_reference` and `add_learning_outcome`. The handlers build each child from its parent, so an ordinary request can't reach them.
- `be8165c` and `07ef8e0` fail the drift gate on their own; `506025c` turns it green. The history was kept rather than rewritten, so bisecting across them can stop on that gate.

| Risk | Accepted on | Closes in |
|---|---|---|
| Release is permanent, so the staff interface must make that unmistakable, and the action must be auditable | #63 | M6 and any staff interface |
| `stands` reads every result per request; benchmark at realistic sizes | #63 | Before large-scale deployment |
| The staff role list in `get_attempt_result` should be permission-based | #63 | Separate authorization work |
| A worker finalization publishes no domain event | #64 | Event-delivery design, L4 for memory |
| Reads can write; monitor latency and transaction duration | #64 | First deployment |
| Worker interval and batch aren't capacity-tested | #64 | Deployment readiness |
| Migration `0028` assumes L1 wasn't deployed first | #64 | When applying it |
| Start-triggered finalization reports no memory | #62 | L4 |
| Marker is a release control: record image digests, use `production` stages, verify memory is off at startup | #41, #61 | First deployment |
| A closed-gate scenario on the two-service stack | #61 | Later improvement |
| 22 existing `mypy app` errors in the backend, not a CI check | #61 | Unscheduled |
| Model-provider data handling (G-33), and reviewing the 7 public OCR documents (G-34) | M0 | Before any production provider or shared retrieval |
| Retention lifecycle for memory events and contributions | #42 | Memory activation |
| The event fingerprint is an unkeyed SHA-256 of low-entropy data, so someone with database access could test guesses. It must be covered by retention and account deletion | #42 | Memory activation |
| Fingerprint immutability is application-level; consider a database trigger or equivalent | #42 | Before memory activation |
| The fault-arming idle check is a harness synchronization, not a guarantee against work enqueued after it; it relies on no unrelated jobs starting during arming | #69 | Keep true in the gate's phases |
| Accepted registrations wait in `pending_registrations`, with their password hash, until `backend-registration-worker` runs. A row is dropped after 5 failed attempts, but there's no age limit, so a stopped worker leaves hashes in place, and nothing reports the backlog yet | M3-B registration | First deployment: run the worker, and alert on backlog |
| The worker and requests share the database, so in principle its writes could slow a request. Six seeds showed no consistent difference through the database, within a noise floor of about 14 ms on one machine. An attacker with a quieter database might do better | M3-B registration | Re-measure in the deployed environment |
| New devices hold `platform: unknown`, and `last_seen` isn't updated on later sign-ins | #75 | When devices are used |
| The gateway's uncertain-timeout unit tests need reviewing | #74 | Before release |
| No HSTS or CSP headers | Security review, 2026-11-01 | Unscheduled |
| The AI service's report text stays in the logs, minus what redaction catches, so log access needs protecting | #72 | First deployment |
| `tests/integration/content/test_real_ai_dispatch.py` runs in no workflow. Its behaviours are covered by the boundary gate, by name | #72 | Before release, confirm line by line or retire the file |
| `/content/jobs` and other staff content routes keep their older response shapes, as the conventions allow | #72 | When staff clients are built |
