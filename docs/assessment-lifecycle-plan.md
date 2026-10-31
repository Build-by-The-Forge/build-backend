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
| 5 | Which clock decides the deadline? | The application server's, as #54 does. Clock differences between servers are a recorded limit |

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

In one transaction, a start finalizes any expired active attempt, counts this student's attempts for the assessment, and checks the policy. Two simultaneous starts can't exceed a limit, because at most one attempt can be in progress: the loser hits `uq_assessment_attempts_active`, and gets the winner's attempt back.

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

**Context retained:** the event holds only tenant, user, membership, role, attempt ID and delivery state. It holds no answers, prompts, documents or request data. Observations are computed from the stored result at delivery, as they are today. The worker makes the signed call with the retained membership and role, since it has no student request.

### Recovery

| Failure | Result |
|---|---|
| Worker dies mid-finalization | The transaction rolls back. The attempt stays eligible and is finalized next pass, or on the next read |
| Worker dies after commit | Done. A later pass doesn't see it, because it's no longer `in_progress` |
| Two workers | `FOR UPDATE SKIP LOCKED`, as the ingestion loops do |
| Student and worker at once | The row lock decides. The loser sees `submitted` and returns it |
| AI service unavailable | The event stays pending, with bounded backoff. Finalization isn't affected |
| Acknowledgement lost | Delivered again, and deduplicated once the AI PR is in |

**The database is the source of truth.** The worker loop only triggers a query for `in_progress` attempts past `expires_at`, using a new partial index. It uses the existing worker process and shutdown behaviour.

### Privacy

- Delivered events are deleted after 30 days. They hold no academic content, so this limits retention without losing anything useful.
- **Open product question: how long learning memory itself is kept in the AI service.** No policy exists today, and the conversation retention decision doesn't cover it.

## Delivery

Each is its own PR with its own gates. The first three depend on each other in this order.

| PR | Contents | Migration |
|---|---|---|
| L1 | `attempt_policy`, domain invariants, policy lock, staff routes, attempt limits and retakes | Yes |
| L2 | Release table and route, feedback function, `getAttemptResult`, `stands` flag | Yes |
| L3 | One finalization path, worker loop, read-time fallback | Index |
| AI-1 | ai-service: idempotent memory upsert | ai-service |
| L4 | Memory outbox and dispatcher, removing the background task | Yes |

Then M3-A.

## Test plan

| Requirement | Tests | Where |
|---|---|---|
| Attempt creation, submission, retakes, exhaustion | Each row of the transitions table, and each valid policy combination | HTTP |
| Finalization | Before, at and after the deadline; zero for unanswered | Domain, HTTP |
| Scoring | `best`, `latest` and `first` across attempts, with ties | Domain, HTTP |
| Result and feedback | Every combination of `result_visibility` and `feedback_timing`, before and after release, against the precedence table | HTTP |
| Authorization and isolation | Another student, another tenant, and staff separately | HTTP |
| Duplicates and retries | Repeat submit, repeat release, repeat delivery | HTTP, AI service |
| Concurrency | Submit against finalize, simultaneous starts at a limit, save against finalize, two workers | **PostgreSQL gate** |
| Limits can't be bypassed | Abandoned, expired and failed attempts all count | HTTP |
| No unauthorized fields | Every student assessment route, at every stage, has no correct answer or explanation | HTTP, drift gate |
| Recovery | Crash before commit and after commit; AI service down; lost acknowledgement | PostgreSQL gate, boundary gate |
| Migrations | Backfilling real rows, which #54's gate didn't exercise | PostgreSQL gate |

SQLite can't exercise locks, so concurrency evidence comes only from PostgreSQL. Each PR moves its gaps to `closed` in `contracts/mobile/gaps.yaml` with the test that proves them: G-29 in L1, G-16 and G-36 in L2, G-37 in L3.

**Concurrency tests must be shown to fail without their lock.** #54's race test wasn't, and that gap shouldn't repeat.

## Recorded limits

- **Server clocks:** deadlines use application server time, so differences between servers shift them slightly.
- **Worker delay:** an expired attempt is finalized when the worker reaches it or someone reads it, not at the instant it expires. Its answers are already frozen at the deadline.
- **Result timing:** a worker outage delays results, but can't change them.
- **Score leakage**, as above.
