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
| M3-A | One error shape and stable codes | M2 | G-20, G-22, G-08 closed | HTTP, drift gate | **Not started** | |
| M3-B | Typed identity bodies, device handling | M3-A | G-14 closed; G-39 with M3-E | HTTP, drift gate | **Not started** | |
| M3-C | Academic structure reads, pagination | M3-A | G-09 closed; G-10 with M3-E | HTTP, drift gate | **Not started** | |
| M3-D | Student uploads, content rights | M3-A | G-01, G-02, G-11, G-12, G-13, G-25, G-30, G-32, G-38, G-07, G-23 closed; G-31 with M4 | HTTP, object storage, PostgreSQL, boundary | **Not started** | |
| M3-E | Assessment contract | M3-A, L1 to L3 | G-10 and G-39 with their partners. Lifecycle gaps are already closed | HTTP, drift gate | **Partly done** by L1 to L3 | |
| M3-F | Conversations, cited chat | M3-A | G-17, G-18 closed; G-04 with M4 | HTTP, boundary | **Not started** | |
| M4 | Retrieval eligibility and citation authorization | M3-D, M3-F | G-05 closed; G-04 and G-31 closed; the boundary doc's measurements taken | Boundary, both repositories | **Specified** in `mobile-m0-boundary.md` | |
| M5 | Typed client, auth and session, error handling | M3-A, M3-B | Generated client passes contract-drift checks; secure token storage | Client against the contract | **Not started** | |
| M6 | Student workflows and screens | M5, M3-C to M3-F | Screens use the generated client only; G-26 closed; device tests | Device, end to end | **Not started** | |
| M7 | Pinned, release-blocking integration gate | M4, M5, M6 | The evidence list in `mobile-m0-boundary.md` passes on pinned SHAs | Real stack with the generated client | **Not started**. Test design can start early | |

### M3 position

M3 is **not close to done**. The fixes merged so far closed security and lifecycle gaps early, ahead of their slices. No M3 slice is complete.

| | Count | IDs |
|---|---|---|
| Closed | 11 | G-03, G-06, G-15, G-16, G-21, G-24, G-27, G-29, G-35, G-36, G-37 |
| Open | 28 | 10 contract, 18 implementation, listed in `contracts/mobile/gaps.yaml` |
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
| AI-1 | Idempotent upsert, contributions, recompute | L0-A | The plan's AI-1 tests | PostgreSQL, forced-order lock test | **In review** (ai-service #42) | |
| L4 | Memory outbox and dispatcher, `memberships.generation`, shared membership lock, removing the background task | AI-1 | The six conditions on #59, sending `event_id`, removing #65's older table set | PostgreSQL forced-order and lock-removal races | **Specified** in `assessment-lifecycle-plan.md`, approved on #59 | |
| Memory activation | The production gate's conditions | L4, and everything in that gate | Each condition implemented and verified | Own safety review | **Not started**. `GATE_OPEN` stays `False` | |

**L4 is the plan's final L-track PR.** The plan defines no L5, L6 or L7, so this register doesn't list any.

## Proposed order

This changes one approved decision: the plan puts L4 before M3-A. **Proposal:** M3-A goes next, and L4 follows when the memory track needs it.

- **Why it's safe:** with the gate closed, nothing uses the outbox, and L0-B already stops the background task from sending anything.
- **What it risks:** none of this affects students until memory is activated, but L4's membership changes stay undone in the meantime.
- **Status:** awaiting the reviewer's decision.

1. AI-1 review, then merge.
2. M3-A, because every later slice and M5's error handling depend on it.
3. M3-B and M3-C, then M3-D and M3-F. M3-D holds the two blockers.
4. M4, with its boundary tests, alongside M3-D and M3-F where the interfaces are agreed.
5. M5 scaffolding once M3-A's error shape is merged. It can run alongside M3-B to M3-F.
6. M6 against the generated client. Screen design can start earlier.
7. M7 on pinned SHAs. Its test design can start at any time.

L4 runs whenever the reviewer places it, and doesn't block this list.

## Deferred risks

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
