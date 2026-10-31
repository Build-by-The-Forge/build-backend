# Mobile contract

**Status: M1 contract accepted and merged as #52.** The reviewer's technical re-review was satisfied at `31faad4`. That decision was relayed by the product owner; GitHub holds no recorded review, because their integration returned 403. M2 is in place.

[`openapi.yaml`](openapi.yaml) is the intended student API for the first mobile release. It says what the system must guarantee, not what the backend does today, so **most of it isn't implemented yet**. M2 records each difference in a machine-readable allowlist, and M3 closes them.

`tests/test_mobile_contract.py` checks the document's structure in CI. It doesn't check the backend.

## The drift gate (M2)

[`gaps.yaml`](gaps.yaml) lists every known difference between the contract and the backend, as `contract_gaps` and `implementation_gaps`. `tests/integration/test_mobile_contract_drift.py` runs in CI and compares it with what the running app does. It fails when:

- a new difference appears;
- a listed difference is gone but still listed, so a gap can't disappear quietly;
- a gap ID is removed, or closed without a test that exists;
- the contract changes without the allowlist being reviewed.

**To close a gap:** fix it, then move it to `closed` with the test that proves it.

**What it checks:** served routes, query parameters, headers and typed bodies, from `app.openapi()`. Then each served route over real HTTP: without a token, without a tenant header, and as a student. It looks for refusals, envelopes, internal fields and 500s.

**What it doesn't check:**

- **Gaps with only `evidence`** aren't machine-checked. They come from reading code or from a decision, and the gate only ensures they stay listed. Each one should gain a finding or a closing test as its work happens.
- **Response fields in general.** It looks for named internal fields and the envelope. It doesn't validate each response against its schema. That belongs in M3 as routes conform.
- **Content with real data.** It has no uploaded document yet, so `G-06` isn't observed. Lists come back empty.
- **The AI service, PostgreSQL, and real devices.** It uses the test suite's SQLite setup with the AI service absent. M4 and M7 cover the boundaries.

## M1 decisions

M0 left these to M1. The reviewer accepted all of them, with G-19 deferred.

| Item | Decision | Why |
|---|---|---|
| G-13 reopening a document | **`GET /content/assets/{asset_id}/content`: the backend streams the bytes, with Range support** | Authorization runs on every request, a revoked document stops at once, and no reusable URL or storage address reaches the client. The cost is backend bandwidth, bounded by the upload limit |
| G-19 limiting a question to one course or document | **Not in this version** | Adding it later is additive. It depends on the M4 filter, so it's better designed after that |
| G-16 result policy | **Each assessment states an `attempt_policy`**: kind, maximum attempts, retakes, result visibility, feedback timing and scoring. Correct answers are never returned | See [Attempt policy](#attempt-policy) |

## Product rulings

The reviewer accepted these at the design level. They describe intent. **Neither the implementation nor the legal permissions have been verified.** The OCR evaluation documents stay public and out of shared retrieval pending review.

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
| How long are conversations kept? | **Default: 12 months after last activity**, unless an approved institutional policy sets a shorter or justified alternative. Students can delete earlier. A backend process enforces expiry, and deletion covers messages, attachments and derived personal retrieval records. Disclosed clearly before release | `Conversation.expires_at`, `deleteConversation`; no conversation text in analytics or ordinary logs |
| How does a student find their institution? | FUTA is configured for the first release. The app mustn't assume every student belongs to FUTA permanently | No route: the slug is app configuration, and `X-Tenant-Slug` and memberships already allow more tenants |
| Can staff-uploaded documents be shown to students? | Yes, once an institution-designated content administrator has approved the rights basis, audience and conditions. The uploader declares provenance, and the department or course owner confirms relevance and audience. BUILD enforces the recorded decision, and never infers permission from a document's contents or the uploader's role. Until approved, a document is available only to its uploader or owner | `listSourceDocuments` returns verified material only |

### Assessment lifecycle

Three separate events, all enforced by the backend. Hiding fields in the app isn't enough.

| Event | Meaning | Governed by |
|---|---|---|
| Submission | Records and grades the attempt | The student, or automatic finalization at the deadline |
| Result availability | When the student can see their score | `result_visibility` |
| Feedback availability | When correctness indicators can be seen | `feedback_timing` |

- **Feedback is a security boundary.** On a two-option question, `is_correct` reveals the answer. It stays null until the configured stage, even once grading is done. Today's backend returns it straight after submission (gap G-36).
- **The student API never returns the correct answer in this contract version**: no correct option or value, no answer-key text, and no explanations in attempt-question payloads.
- **Unanswered questions score zero.** This is a documented invariant, not a setting, because there's no alternative to choose yet. A field can be added when a real one exists.
- **One immutable terminal outcome per attempt.** Student submission and automatic expiry can't both grade an attempt: whichever wins the database transition finalizes it. A retry returns the same stored result, and learning-memory reporting is keyed to the finalized attempt.
- **The server finalizes expired attempts,** so a result never depends on the app being open. The database decides eligibility; a queue message or schedule is only a trigger to look. A student requesting an expired attempt before the worker reaches it gets it finalized first.
- **A retake needs both** a terminal previous attempt and a policy that allows another.

This is built after this contract is approved, together with retakes.

### Attempt policy

Every combination is either defined or impossible. Staff can't store the impossible ones, and the backend refuses them with `VALIDATION_FAILED` when staff routes gain these fields.

| `retake_after_submission` | `max_attempts` | Meaning |
|---|---|---|
| `false` | `1` | One attempt |
| `true` | `2` or more | Retakes up to that limit |
| `true` | `null` | Retakes with no limit |
| `true` | `1` | **Impossible:** it promises a retake the limit forbids |
| `false` | `2` or more, or `null` | **Impossible:** it allows attempts the setting forbids |

- **Counting:** `max_attempts` and `attempts_used` count every attempt a student has started, finalized or not. Automatic finalization counts the same as submission.
- **`after_final_attempt`** is reached when `attempts_used` equals `max_attempts` and all those attempts are finalized. It needs a limit, so `max_attempts: null` with `after_final_attempt` is **impossible**. With a limit of 1, it's reached when that attempt is finalized.
- **`kind`** is a label and changes no enforcement.
- **`scoring_policy`** chooses which finalized attempt stands as the student's outcome. Each attempt's own result doesn't change.
- **`after_release`** means a staff release of the assessment's results. There's one release per assessment, shared by results and feedback. It must be a durable, auditable, monotonic event, so a release can't be undone or lost. That staff action isn't in this student contract.

### Result and feedback precedence

`result_visibility` controls whether the result can be read at all. `feedback_timing` independently controls per-question feedback. Neither overrides the other, and the server enforces both.

| Result permitted? | Feedback stage reached? | `GET .../result` |
|---|---|---|
| No | Either | 409 `RESULT_NOT_RELEASED`, with no score or feedback |
| Yes | No | Score, with `is_correct` and `awarded_marks` null |
| Yes | Yes | Score and per-question feedback |

So `result_visibility: after_release` with `feedback_timing: immediate` gives nothing until release. That result route is the only one that carries this feedback.

**Accepted product limitation:** a score can reveal feedback that's being withheld, particularly on short assessments. On a one-question assessment, the total shows whether the answer was right. Withheld feedback isn't guaranteed to be concealed. Staff guidance and assessment configuration must account for this.

### Release-blocking governance

- **G-33, model providers (hard release gate).** No production provider receives student or institutional passages until BUILD has verified and recorded: training use of prompts, passages and outputs; provider retention and its exceptions; data-processing terms, subprocessors and locations; logging and abuse-monitoring retention; and how deletion applies. **The required default is that no provider may use BUILD's content for training or model improvement.** A provider that can't meet this doesn't receive protected content. Inference isn't training, but it is still a disclosure to an external processor.
- **G-30, rights.** Unverified material stays out of shared lists and shared retrieval.

## Where this differs from the plan

These go beyond M0's route list. Each needs the reviewer's agreement.

| Change | Instead of | Why |
|---|---|---|
| `POST /content/my-documents` stores the document and queues ingestion together | `POST /content/sources/{id}/assets/upload`, then `POST /content/assets/{id}/jobs` | Students need no source, no general upload permission and no job permission, so staff permissions aren't widened. See [Durable queuing](#durable-queuing) |
| Ingestion state is embedded in `Document`; poll `GET /content/my-documents/{id}` | `GET /content/jobs/{id}`, `/content/assets/{id}/jobs/latest` | Fewer routes to secure, and no job internals to filter |
| `POST /content/my-documents/{id}/retry` | Nothing (gap G-12) | "Retry available" needs a student action |
| `DELETE /content/my-documents/{id}` | Nothing | A private upload should be removable by its owner. **Whether and when the stored bytes are erased is left to M3-D** |
| `POST /ai/conversations`, then `POST .../messages` | `POST /ai/chat` | Decision A. `/ai/chat` is not part of this contract |
| `POST /identity/users` answers a bodyless 202 | 201 with the user | M0 says registration doesn't reveal whether an account exists. A 201 with an ID can't meet that. M3-B must also keep the response time from revealing it |
| Attempts have `expires_at`, and late answers get `ATTEMPT_EXPIRED` | No deadline | See new gap G-27 |

## Durable queuing

The reviewer's condition on the combined route: a successful upload can't become permanently unqueued. Object storage and PostgreSQL share no transaction, so M3-D builds it in this order:

1. Store the bytes under the document's key.
2. In **one database transaction**, insert the document and its `queued` ingestion job. That job row is the durable enqueue: the worker already claims queued jobs from the database.
3. Answer success only after that commit.

| Failure | Result |
|---|---|
| Storing the bytes fails | No document. The client retries with the same key |
| The transaction fails, or the process dies before it commits | No document. The object is unreferenced, and the existing orphan sweeper removes it. A retry with the same key starts again |
| The process dies after the commit | The document and job exist. The worker processes it, and a retry with the same key returns it |
| The response is lost | The same as above |

M3-D tests each row, including that the sweeper covers these objects and that the worker picks up the job. Today's upload creates no job (gap G-38).

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
| G-33 | Implementation | **High, release gate** | Retrieved passages go to the configured model provider. Whether that provider may train on them hasn't been checked, and no provider is chosen for production | `MODEL_PROVIDER` setting; provider terms not reviewed | Before any production provider receives content |
| G-34 | Implementation | Medium | The OCR evaluation documents have no rights or provenance record. Their public source status is a separate decision and stays as it is. Their evaluation use continues, and they stay out of shared retrieval until each is reviewed | ai-service evaluation corpus | Before they enter shared retrieval |
| G-36 | Implementation | **High** | `is_correct` and `awarded_marks` are returned as soon as an attempt is submitted, with no feedback stage | `get_attempt_result` in `app/api/assessment/attempts.py` | With retakes, after this contract |
| G-37 | Implementation | **High** | Expired attempts wait for the student to submit, so the result depends on the app | #54 limit | With retakes, after this contract |
| G-39 | Contract | Low | Assessment, attempt, result and membership responses carry `tenant_id` and `user_id`, which the contract doesn't | Found by the M2 gate | M3-E, M3-B |
| G-38 | Implementation | **High** | Upload creates no job, so the durable queuing above doesn't exist yet | `app/application/content/upload.py` | M3-D |
| G-35 | Implementation | **High, fixed in #53** | The answer key was readable by students mid-attempt through `GET /assessment/questions/{id}` | Test got 200 before the fix | Merged |

## Still open

- **How the 12-month default is applied**, defined in M3-F, since a null `expires_at` must not mean kept forever.
- **Who the content administrator is at FUTA.** FUTA must designate the role or person; this document doesn't assume an office, or that every lecturer has redistribution authority.
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

### Status of the fixes

The product side asked for these to be fixed now, separately from this contract. M3-E still verifies final behaviour against it.

| Gap | Status |
|---|---|
| G-03 draft exposure, G-35 answer key | Fixed and merged in #53, which also removes questions from students' assessment responses |
| G-27 time limit, G-15 repeat submit | Fixed and merged in #54, with the deadline policy this contract states. #55 adds ownership and answer-key tests over HTTP |
| G-29 retakes, G-36 feedback, G-37 finalization | Not started. They need this contract approved first |
