# Mobile contract

**Status: M1, proposed for reviewer approval.**

[`openapi.yaml`](openapi.yaml) is the intended student API for the first mobile release. It says what the system must guarantee, not what the backend does today, so **most of it isn't implemented yet**. M2 records each difference in a machine-readable allowlist, and M3 closes them.

`tests/test_mobile_contract.py` checks the document's structure in CI. It doesn't check the backend.

## Decisions for the reviewer

M0 left these to M1.

| Item | Decision | Why |
|---|---|---|
| G-13 reopening a document | **`GET /content/assets/{asset_id}/content`: the backend streams the bytes, with Range support** | Authorization runs on every request, a revoked document stops at once, and no reusable URL or storage address reaches the client. The cost is backend bandwidth, bounded by the upload limit |
| G-19 limiting a question to one course or document | **Not in this version** | Adding it later is additive. It depends on the M4 filter, so it's better designed after that |
| G-16 result policy | **Each assessment states an `attempt_policy`**: kind, maximum attempts, retakes, result visibility, feedback timing and scoring. Correct answers are never returned | Proposed product ruling below. Practice defaults to immediate results; formal assessments are configurable |

## Proposed product rulings

These came from the product side on 2026-10-30 as recommendations for the reviewer. They describe intent. **Neither the implementation nor the legal permissions have been verified.**

**Guiding principle: BUILD should learn from academic content without confusing access to that content with permission to share it.** Uploads feed the intelligence layer, and that doesn't weaken document authorization. Being indexed never makes a private document available to another student.

### Knowledge scopes

| Scope | Holds | Who it serves | Conditions |
|---|---|---|---|
| Personal | A student's uploads, by default | That student only | Leaves active retrieval when deleted, revoked or superseded |
| Institutional | Authorized staff material and explicitly approved student contributions | Eligible students in that institution | Needs provenance, ownership or licensing information, and academic validation |
| Platform intelligence and evaluation | Aggregated quality signals, retrieval evaluations and feedback | Improving retrieval, ranking, generation and reliability | Must not expose source documents or identifiable students across institutions |

The contract carries the first two as `Document.knowledge_scope`, separate from `ownership`, which governs the original file. The third is never student-facing, so it isn't in this API. There's no route for contributing a student document to institutional knowledge in this version.

**Using content for retrieval isn't training a model on it.** Uploads aren't to be treated as permission for model training, or for training by an external provider. This belongs in the ingestion and data-governance architecture, and M4 must carry the scope into its eligibility check.

### Other rulings

| Question | Ruling | In this contract |
|---|---|---|
| Can students retake assessments? | Yes, by assessment-specific policy. Lecturers or the institution control it for formal examinations | `Assessment.attempt_policy`, `attempts_used`, `ATTEMPT_LIMIT_REACHED`, `RESULT_NOT_RELEASED`; `is_correct` and `awarded_marks` can be null |
| How long are conversations kept? | Until the student deletes them or an institutional policy expires them, with no short arbitrary expiry. **The default period must be agreed before M3-F and student launch**, with clear disclosure | `Conversation.expires_at`, `deleteConversation`; no conversation text in analytics or ordinary logs |
| How does a student find their institution? | FUTA is configured for the first release. The app mustn't assume every student belongs to FUTA permanently | No route: the slug is app configuration, and `X-Tenant-Slug` and memberships already allow more tenants |
| Can staff-uploaded documents be shown to students? | Yes, once the institution has verified the rights. Staff uploading a document doesn't establish permission to redistribute it. Unverified material stays out of the shared corpus | `listSourceDocuments` returns verified material only |

## Where this differs from the plan

These go beyond M0's route list. Each needs the reviewer's agreement.

| Change | Instead of | Why |
|---|---|---|
| `POST /content/my-documents` stores the document and queues ingestion together | `POST /content/sources/{id}/assets/upload`, then `POST /content/assets/{id}/jobs` | Students need no source, no general upload permission and no job permission, so staff permissions aren't widened. A failure can't leave a document that nothing will process |
| Ingestion state is embedded in `Document`; poll `GET /content/my-documents/{id}` | `GET /content/jobs/{id}`, `/content/assets/{id}/jobs/latest` | Fewer routes to secure, and no job internals to filter |
| `POST /content/my-documents/{id}/retry` | Nothing (gap G-12) | "Retry available" needs a student action |
| `DELETE /content/my-documents/{id}` | Nothing | A private upload should be removable by its owner. **Whether and when the stored bytes are erased is left to M3-D** |
| `POST /ai/conversations`, then `POST .../messages` | `POST /ai/chat` | Decision A. `/ai/chat` is not part of this contract |
| `POST /identity/users` answers 202 with no body | 201 with the user | M0 says registration doesn't reveal whether an account exists. A 201 with an ID can't meet that |
| Attempts have `expires_at`, and late answers get `ATTEMPT_EXPIRED` | No deadline | See new gap G-27 |

## Corrections to M0

Two points from M0 that this work found to be wrong or redundant:

- **`GET /tenants/{slug}/join-policy` isn't available to students.** It requires `tenant.settings.manage`, so Decision C's list was wrong. It's left out of this contract. A student just tries to join.
- **The approved chat answer shape has `request_id` in `data`, and the envelope has it in `meta`.** Both are kept as approved, which is redundant.

## New gaps

These continue the [M0 inventory](../../docs/mobile-m0-inventory.md) and move into M2's allowlist.

| ID | Kind | Severity | Gap | Evidence | Closes in |
|---|---|---|---|---|---|
| G-26 | Implementation | Low | A student has no way to discover a tenant slug. Accepted for now: FUTA is app configuration in the first release, and institution selection comes later | No listing route; `tenants` routes take a known slug | M6 |
| G-27 | Implementation | **High** | **Assessment time limits appear not to be enforced.** `duration_minutes` is stored, but nothing in the attempt code reads it | `app/application/assessment/attempt*.py`, `app/domain/assessment/attempt.py` | M3-E. M2 confirms it first |
| G-28 | Contract | Low | No record of a student's programme or department, so course lists filter by a parameter rather than "my courses" | `app/api/catalogue/courses.py` | Later phase |
| G-29 | Implementation | Medium | Assessments have no attempt policy, and starting an attempt checks only for one in progress | `app/application/assessment/attempt_handlers.py` | M3-E, needs a migration |
| G-30 | Implementation | **High** | Content sources record no rights basis, intended audience or redistribution limits, so nothing can stop unverified material reaching students | `app/infrastructure/db/models/content.py` | M3-D, needs a migration |
| G-31 | Implementation | **High** | Knowledge scope isn't modelled, so retrieval can't apply it | ai-service `retrieval.py`; backend content models | M3-D, M4 |
| G-32 | Implementation | Medium | What happens to derived data on deletion isn't defined, and neither is whether stored bytes are erased | No delete route today | M3-D |
| G-33 | Implementation | **High** | Retrieved passages go to the configured model provider. Whether that provider may train on them hasn't been checked, and no provider is chosen for production | `MODEL_PROVIDER` setting; provider terms not reviewed | Before student launch |

## Still open

- **The default conversation retention period**, before M3-F and student launch.
- **The process for verifying rights on staff material**, including who confirms them. The contract requires the outcome, and doesn't establish any right.
- **How a student contribution gets approved** into institutional knowledge. No route exists in this version.

## Assessment findings, reproduced

Both priority findings are **confirmed**, by a probe at `0ef0ba8` sending HTTP requests through the real routes as a student. It ran on the integration suite's setup, with SQLite and a test client, not PostgreSQL or a deployed service. The probe isn't committed; M2 turns these into tests.

| Finding | Request | Result |
|---|---|---|
| G-03: draft exposure | `GET /assessment/assessments` | 200, including the draft, its prompt and its options |
| | `GET /assessment/assessments/{id}` by direct ID | 200, `status: draft`, with prompt and options. No `is_correct` or answer key |
| | `POST .../attempts` on the draft | 409, so attempts are correctly refused |
| G-27: time limit | `duration_minutes` of 1, attempt moved back to 2 hours ago, then read questions, save an answer and submit | All 200. The late answer was graded: 1 of 1, passed. Attempts have no deadline field |

Also seen, and settling two earlier gaps:

- **G-15:** a repeated submit answers 409. The contract requires a safe repeat, so this is a contract gap.
- **G-29:** a new attempt starts straight after submitting, with no limit.

G-03 and G-27 stay open until M3-E fixes them. Both must be fixed before the affected assessment functionality is released.
