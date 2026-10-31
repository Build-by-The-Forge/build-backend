# Assessment lifecycle plan

**Status: proposed, for reviewer approval before implementation.** It implements the merged mobile contract (#52). Nothing here is built yet.

**Summary:** the backend can make finalization, attempt limits, release and feedback rules transactional and durable. Learning-memory delivery is different: **today's AI service would count a repeated delivery twice, so exactly-once processing isn't available.** The plan fixes that with an idempotency key in the AI service, in its own PR.

## Decisions for the reviewer

| # | Decision | Recommendation |
|---|---|---|
| 1 | Policy for assessments that already exist | Practice defaults, which match today's behaviour: `kind: practice`, no limit, retakes on, immediate results and feedback, `best` |
| 2 | Can a policy change after publication? | No. It locks at publish, so nobody's attempts are judged by rules changed midway |
| 3 | Where does best, latest or first show up? | On the staff results route as a `stands` flag. The student contract has no outcome route, and adding one is a contract change |
| 4 | Learning-memory delivery | A transactional outbox, plus idempotency in the AI service |
| 5 | Which clock decides the deadline? | **PostgreSQL's**, for every deadline decision, as the reviewer prefers. This changes #54, and removes the clock-difference limit. See [Deadline clock](#deadline-clock) |
| 6 | Learning-memory production gate | Memory reads and writes both stay off in production until the gate below is met, enforced in `MemoryService`. Approve the architecture independently of the final retention period |

## The three kinds of guarantee

| Kind | Meaning | Applies to |
|---|---|---|
| **Contract** | What #52 promises a client | Policy semantics, result and feedback precedence, no correct answers |
| **Implementation** | What one PostgreSQL transaction can enforce | One terminal outcome, one result row, one reporting obligation, one release, attempt limits |
| **Distributed** | Depends on workers, the AI service or external delivery | When finalization runs, when memory is delivered, whether a repeat is deduplicated |

Anything in the third row is described by its delivery semantics, and never as exactly-once unless both sides prove it.

## Interim limitations and their tests

These two are accepted today and listed as open gaps. Each closes only with its named test.

| Gap | Limitation today | Closing test |
|---|---|---|
| G-36 | `is_correct` and `awarded_marks` are returned as soon as an attempt is submitted | `test_feedback_stays_null_until_its_stage` |
| G-37 | An expired attempt waits for the student to submit | `test_the_worker_finalizes_an_expired_attempt_with_no_client` |

**The score limitation is permanent, not interim.** A score can reveal withheld correctness, particularly on short assessments. `test_a_score_can_reveal_withheld_feedback_on_one_question` asserts this on purpose, so no one later reads the feedback rules as a guarantee of concealment.

## Contract mapping

| Operation (#52) | Today | Change |
|---|---|---|
| `listAssessments`, `getAssessment` | Published only, no policy | Add `attempt_policy`, `attempts_used` |
| `startAttempt` | Returns the active attempt or starts another, with no limit | Finalize an expired active attempt, then apply the policy. `ATTEMPT_LIMIT_REACHED` |
| `getAttempt`, `listAttempts` | Has `expires_at` | Finalize first if expired |
| `getAttemptQuestions` | Refused once submitted | Finalize first if expired, so they're then refused |
| `saveAnswer`, `deleteAnswer` | Refused after the deadline | Unchanged |
| `submitAttempt` | Safe to repeat | Shares the one finalization path |
| `getAttemptResult` | Always returns everything | `RESULT_NOT_RELEASED`, and nulls until the feedback stage |

Staff routes also change, outside the student contract: create and update accept a policy, and a new route records the release.

The work uses today's error conventions. M3-A standardizes them afterwards without changing these semantics.

## State transitions

An attempt has two states. `submitted` is terminal and immutable, and it covers student submission and automatic finalization, with `finalized_by` recording which.

| From | Event | To | Rule |
|---|---|---|---|
| none | Start | `in_progress` | Published, within policy, and no other attempt in progress |
| `in_progress` | Save or delete an answer | `in_progress` | Before `expires_at` only |
| `in_progress` | Student submits | `submitted` | Allowed before or after the deadline |
| `in_progress` | Worker or read finds it expired | `submitted` | From `expires_at` onwards |
| `submitted` | Submit again | `submitted` | Returns the stored attempt, with no grading |

Invalid, and refused or impossible:

- `submitted` to anything else
- Changing answers or a result after `submitted`
- A second result for an attempt, which the `uq_attempt_result_tenant_attempt` constraint already refuses
- Starting a new attempt while one is in progress, which `uq_assessment_attempts_active` already refuses

## Required decisions

### Finalization

**One function makes an attempt final, and every path calls it.** In one transaction it locks the attempt row, returns at once if already `submitted`, grades the saved answers, inserts the result, sets `submitted`, and inserts the memory event. Whoever gets the row lock first owns finalization.

- Student submit, the worker and read-time fallback all use it.
- Saves take the same lock and check the deadline inside it, so an answer is either committed before grading or refused.
- The exact deadline instant stays late, as in #54.
- **Unanswered questions score zero.** Not a setting.

### Attempt limits

A start runs in one transaction, in this order:

1. **Take a transaction-scoped advisory lock** on the tenant, assessment and student.
2. Finalize any expired active attempt.
3. Count this student's attempts for the assessment, and check the policy.
4. Insert with `INSERT ... ON CONFLICT DO NOTHING` on the `uq_assessment_attempts_active` partial index. If no row comes back, read the active attempt with a fresh query.

**The lock is what protects the limit, and the unique index alone wouldn't.** Without it, a slow request can count attempts, then wait while a faster one starts and submits. Nothing is in progress any more, so the slow one's insert succeeds on its stale count, and the student exceeds the limit.

`ON CONFLICT` stays as a defence, because a uniqueness violation would leave the PostgreSQL transaction failed, and nothing further could run in it. It also covers any path that inserts without the lock.

SQLite has no advisory locks and no real concurrency, so the lock applies only on PostgreSQL, and only the PostgreSQL gate can prove this.

A retake needs all earlier attempts finalized and `attempts_used` below `max_attempts`. Abandoned attempts count, since starting consumes an attempt. Nothing about a failed or incomplete attempt reduces the count.

The rules that rule out contradictory policies are also enforced in the domain, not only in the OpenAPI schema.

### Scoring

`best` is the highest `total_score`, then the earliest finalized. `latest` is the latest finalized. `first` is the earliest started. Each ends in the attempt's ID, so the choice is deterministic. Each attempt's own result never changes.

### Result release

A new insert-only table, `assessment_result_releases`, with one row per assessment: tenant, assessment, who released it, and when. The primary key on the assessment makes it single, and having no update or delete path makes it monotonic. Staff with `assessment.publish` call it, and a repeat returns the existing row. It also emits a domain event for audit.

### Feedback

One pure function decides, with no database access:

```text
result_visible   = attempt finalized AND (immediate OR released)
feedback_reached = attempt finalized AND stage reached for feedback_timing
feedback_shown   = result_visible AND feedback_reached
```

- Not `result_visible`: `RESULT_NOT_RELEASED`, with no score or feedback.
- `result_visible` only: the score, with `is_correct` and `awarded_marks` null.
- The correct answer is never returned. `correct_option_index` stays internal to grading.
- Staff keep their existing separately permissioned view.

### Learning memory

The two questions have different answers.

**Can the backend guarantee one logical reporting obligation per finalized attempt? Yes.** A new table, `assessment_memory_events`, gets its row inside the finalization transaction, keyed uniquely on the attempt. If finalization commits, so does the obligation.

**Can the AI service guarantee one logical update per delivery? Not today.** `MemoryService.record` increments `attempts`, and `/v1/ai/memory/upsert` takes no event ID. A repeat counts twice. So:

| Step | Who | Guarantee |
|---|---|---|
| Create the event | Backend, in one transaction | Exactly one per finalized attempt |
| Deliver it | Backend worker, with retries | At-least-once attempts, while the service is reachable |
| Apply it | AI service, after its PR | One update per event ID: the ID and the memory change commit in one transaction, and a repeat returns success with no change |
| Lost acknowledgement | Both | The backend retries, and the AI service recognises the ID |

**Until the AI PR is merged, this is at-least-once with possible duplicates, and must be described that way.** The existing best-effort background task stays until then, so nothing is lost or newly duplicated in the meantime.

**Context retained:** the event holds only tenant, user, attempt ID, membership ID and generation, and delivery state. It holds no role, answers, prompts, documents or request data. Observations are computed from the stored result at delivery, as they are today.

**A stored event is not an authorization.** The AI service trusts the backend's signed context, so it can't catch a stale one. The backend must decide afresh on every delivery attempt, including every retry:

1. Load the user and the membership, by tenant and user, from the database.
2. Deliver only if **all** of these hold:
   - The event isn't cancelled.
   - The account can authenticate.
   - The membership is active.
   - **The membership's generation equals the one on the event.**
   - The current role still holds the permission. The signed call uses that current role.
3. Otherwise, **cancel the event**: a terminal state, with a reason and no content. It's never retried.

Checking only that a membership is active today can't see that it was revoked in between. So revocation leaves two durable marks:

- **A generation.** `memberships.generation` goes up each time a membership is revoked, inside the domain's revoke method, so every path gets it. Reinstating doesn't change it. The event records the generation when it's created.
- **Cancellation in the same transaction.** Revoking a membership also cancels that membership's pending events, so nothing waits to be noticed. The generation is the backstop for anything this misses.

**An event created while the membership isn't active is created already cancelled.** Otherwise it would record the post-revocation generation, and reinstating would make it match.

| Situation | Result |
|---|---|
| Membership revoked before delivery | Cancelled, not delivered. Retrying can't bypass this |
| Revoked after a failed delivery, before the retry | Cancelled at the retry |
| Role changed | Delivered with the current role, if it still holds the permission. Otherwise cancelled |
| Account deleted | Attempts and their events are removed by the existing cascade. If an event remains, it's cancelled |
| Account made ineligible | Cancelled at the next delivery. No route suspends and restores an account today. If one is added, it needs the same generation treatment, and L4 records this |
| Revoked, then reinstated before the dispatcher runs | Cancelled in the revoking transaction. No request reaches the AI service |
| Reinstated after cancellation | The event stays cancelled. Reinstating doesn't send old activity |
| Finalized after revocation | The attempt is still graded, since the result is the authoritative record. The event is created already cancelled, so a later reinstatement can't deliver it |

**Accepted limit:** one request already in flight can't be recalled, so a revocation committed between the check and the send can let that single delivery through. Holding a lock across an HTTP call isn't worth closing that. No retry follows it, because every retry checks again.

Memory already delivered before a revocation stays under the memory retention policy, which isn't changed by this.

### Deadline clock

Every deadline decision uses **one** source: PostgreSQL. Worker time, request-server time and database time are never mixed.

- Starting sets `started_at` and `expires_at` from the database.
- Saves, deletes, finalization and the worker's query compare against the database time **read after taking the row lock**, using `clock_timestamp()`. `now()` is wrong here: it's the transaction's start, so a request that waited on the lock would see a time before the wait, and could pass a deadline that had already gone by.
- The domain's `is_expired(now)` already takes the time as an argument, so the rule itself doesn't change, and the exact instant stays late.

This is a change to #54, made in L3. SQLite tests supply the time from Python, so **only the PostgreSQL gate proves the database clock is used**.

### Recovery

| Failure | Result |
|---|---|
| Worker dies mid-finalization | The transaction rolls back. The attempt stays eligible and is finalized next pass, or on the next read |
| Worker dies after commit | Done. A later pass doesn't see it, because it's no longer `in_progress` |
| Two workers | `FOR UPDATE SKIP LOCKED`, as the ingestion loops do |
| Student and worker at once | The row lock decides. The loser sees `submitted` and returns it |
| AI service unavailable | The event stays pending, with bounded backoff. Finalization isn't affected |
| Acknowledgement lost | Delivered again, and deduplicated once the AI PR is in |
| Membership revoked while pending | Cancelled at the next delivery attempt, as above |

**The database is the source of truth.** The worker loop only triggers a query for `in_progress` attempts past `expires_at`, using a new partial index. It uses the existing worker process and shutdown behaviour.

### Privacy

Three kinds of record have three separate lifetimes. Deleting one never deletes another.

| Record | Purpose | Proposed retention |
|---|---|---|
| Outbox event (backend) | Delivery and reconciliation | Deleted 30 days after delivery. Holds no academic content |
| Deduplication record (AI service) | Stops a late retry applying twice | Longer than the backend's longest retry and reconciliation window, so it must outlive any retry. The value is set in AI-1 |
| Learning memory (AI service) | Personalization | **Proposed default: expires after 12 months without meaningful activity**, by deletion or de-identification, subject to institutional policy and student controls. Kept only while its purpose and authorization stay valid. A background read doesn't reset the clock; only student activity or an authorized update does |

### Learning-memory production gate

**No student data goes to the learning-memory service in production until all of these are implemented and verified:**

1. A formally approved retention policy.
2. Expiry enforced by the AI service, not just documented.
3. Deletion and revocation propagation, including on account deletion.
4. Student controls to inspect, correct and delete their memories.
5. Idempotency by event ID, verified.
6. Purpose limitation: memory serves that student's personalization, and isn't used to train a model.
7. Tenant isolation on every read and change of memory.
8. A memory failure can't affect an authoritative assessment result. That already holds, and stays tested.

**The gate covers both directions, as separate capabilities.** Not writing new memories and not disclosing existing ones are different things.

| Capability | While the gate is closed |
|---|---|
| Reporting | No assessment submission creates or dispatches a student-memory event |
| Retrieval | No stored memory is read into a chat context, returned, or sent to a model provider |

**Today's code honours neither.** Nothing is deployed, so nothing has been sent in production, but a policy alone wouldn't hold:

| Direction | Path today | Service |
|---|---|---|
| Write | `submit_attempt`, through `LearningMemoryReporter`, to `/v1/ai/memory/upsert` | Backend, then AI |
| Read | `AIOrchestrator.chat` puts memory in the prompt and returns it as `memory_used` | AI |
| Read | `AdaptiveEngine` | AI |
| Read | `/v1/ai/memory/query`, reached from the backend's `GET /ai/memory` | AI |

**A backend switch alone wouldn't close this**, since chat reads memory inside the AI service. Every path goes through `MemoryService`, so that is the enforcement point.

### L0: the default-deny boundary

**L0-A, ai-service, first.** `MemoryService` refuses every read and write while the gate is closed. Chat then runs with no memory in its prompt, and the memory routes answer 503.

**L0-B, backend.** The reporter creates and sends nothing while the gate is closed, and `GET /ai/memory` answers 503.

**How the gate is opened:**

- A setting, off by default, in each service. A malformed value fails startup.
- **A constant in the source records the gate as closed.** Opening it takes a reviewed code change, once the gate's conditions are met.
- **A marker baked into the production image.** The Dockerfile's `production` stage writes it at build time, so no runtime configuration can remove it.

The rule, where `requested` is the setting:

```text
allowed = requested AND (gate constant open
                         OR (no production marker AND APP_ENVIRONMENT in development, testing))
```

If `requested` is on and `allowed` is false, startup fails. No runtime endpoint can change any of this.

`APP_ENVIRONMENT` is an ordinary variable, so it can't be the only thing separating test from production: **a production image misconfigured as `development` still refuses**, because of the marker. Tests and local runs have no marker, so they can exercise the enabled behaviour.

**What this doesn't do:** it's a release control, not a replacement for deployment access. Someone who deploys an image built from a non-production stage, or runs the source directly, has no marker. The first deployment must use the `production` stage, and the release record names the image.

Inside chat, a closed gate is an expected condition with its own handling, not a generic exception, so it can't fail the chat request.

Acceptance:

1. Production starts with both capabilities off.
2. A test sets the setting on in production mode with the gate closed, and startup fails. In both services.
   **Also run against the built production image with `APP_ENVIRONMENT=development` and the setting on: it must refuse to start.** This belongs in the production-image gate, since only a real image has the marker.
3. Chat retrieval is blocked independently of reporting: a test with stored memories asserts they're absent from the prompt sent to the model and from `memory_used`.
4. Stored memories stay unreachable on every path in the table, and on `MemoryService` directly.
5. Missing or malformed configuration fails closed.
6. Non-production settings can't establish production authorization, and no runtime endpoint can override the gate.
7. A one-time startup log line and a counter show the gate's state. Tests assert no memory content reaches logs.
8. Assessment submission still succeeds and is graded with the gate closed.

The boundary gate needs updating, since it exercises memory today. Where it builds the `production` stage, the marker now refuses memory. L0-A must therefore give its memory checks a stage without the marker, without lowering what the rest of the gate tests on the production image. If that can't be done cleanly, L0-A reports it before changing the gate.

**The current memory shape can't meet this gate.** `learning_memory` holds one aggregated row per tenant, user and topic: a running `mastery_score`, `attempts`, and `last_interaction`, stored as a string.

- **No provenance.** A running average can't have one source's contribution removed. Provenance-aware invalidation needs a per-event record that the aggregate can be recomputed from, so deleting one source doesn't wipe a student's whole memory. AI-1's event table is the natural place, holding only IDs, topic and outcome, with no answers or documents. Its source reference is generic (a kind and an ID), so document sources can be added later without a redesign. None are built now.
- **Required tests for AI-1:** deleting one contribution leaves the others, recomputing is deterministic, and reprocessing or correcting never creates a duplicate contribution. A processed event can still be revised later.
- **No expiry and no delete path exist** in the memory service.
- **Student controls aren't in the #52 contract**, which left `/ai/memory` out of scope. They need their own contract decision, as three separate capabilities:
  - **Inspect:** the student's own memory, with topics and update information.
  - **Correct:** changes the derived learning representation only. It never rewrites an assessment result or the historical source event.
  - **Delete:** invalidates the contribution or memory, with authorization and audit.

Assessment-derived memory traces back to attempts and topics rather than documents, so document revocation mainly matters once memory draws on documents. Attempt and account deletion matter from the start.

## Delivery

Each is its own PR with its own gates. The first three depend on each other in this order.

| PR | Contents | Migration |
|---|---|---|
| L0-A | ai-service: `MemoryService` default-deny, startup refusal | No |
| L0-B | Backend: reporter and `GET /ai/memory` default-deny, startup refusal | No |
| L1 | `attempt_policy`, domain invariants, policy lock, staff routes, attempt limits and retakes | Yes |
| L2 | Release table and route, feedback function, `getAttemptResult`, `stands` flag | Yes |
| L3 | One finalization path, worker loop, read-time fallback | Index |
| AI-1 | ai-service: idempotent memory upsert with a per-event record | ai-service |
| L4 | Memory outbox and dispatcher, removing the background task | Yes |

Then M3-A. L0-A and L0-B merge and are verified before any memory integration is enabled. The rest of the memory gate (expiry, deletion, student controls) is separate reviewed work, which doesn't block L1 to L4 because both capabilities stay off until it's done.

## Test plan

| Requirement | Tests | Where |
|---|---|---|
| Attempt creation, submission, retakes, exhaustion | Each row of the transitions table, and each valid policy combination | HTTP |
| Finalization | Before, at and after the deadline; zero for unanswered | Domain, HTTP |
| Scoring | `best`, `latest` and `first` across attempts, with ties | Domain, HTTP |
| Result and feedback | Every combination of `result_visibility` and `feedback_timing`, before and after release, against the precedence table | HTTP |
| Authorization and isolation | Another student, another tenant, and staff separately | HTTP |
| Duplicates and retries | Repeat submit, repeat release, repeat delivery | HTTP, AI service |
| Concurrency | Submit against finalize, save against finalize, two workers. Simultaneous starts get the same attempt, with one row. **A slow start against a fast start-and-submit can't exceed the limit** | **PostgreSQL gate** |
| Stale authorization | Revocation between event creation and delivery, and between a failed delivery and its retry; role change; account deletion. **Event created, membership revoked, reinstated, dispatcher runs: the event stays cancelled and no AI-service request is sent.** The same with the cancellation step removed, so the generation is proven on its own. An attempt finalized during revocation, then reinstated: never delivered | PostgreSQL gate |
| Deadline clock | Every deadline path uses the database time, read after the lock | **PostgreSQL gate** |
| Limits can't be bypassed | Abandoned, expired and failed attempts all count | HTTP |
| No unauthorized fields | Every student assessment route, at every stage, has no correct answer or explanation | HTTP, drift gate |
| Recovery | Crash before commit and after commit; AI service down; lost acknowledgement | PostgreSQL gate, boundary gate |
| Migrations | Backfilling real rows, which #54's gate didn't exercise | PostgreSQL gate |

SQLite can't exercise locks, so concurrency evidence comes only from PostgreSQL. Each PR moves its gaps to `closed` in `contracts/mobile/gaps.yaml` with the test that proves them: G-29 in L1, G-16 and G-36 in L2, G-37 in L3.

**Every important lock-based guarantee needs a test shown to fail without its lock.** #54's race test wasn't, and that gap shouldn't repeat. L3 also closes it for #54's submit lock.

## Recorded limits

- **In-flight delivery:** a revocation can't recall a memory delivery already being sent, as above.
- **Worker delay:** an expired attempt is finalized when the worker reaches it or someone reads it, not at the instant it expires. Its answers are already frozen at the deadline.
- **Result timing:** a worker outage delays results, but can't change them.
- **Score leakage**, as above.
