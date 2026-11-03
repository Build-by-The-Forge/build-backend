# M3-E design: the assessment contract

**Status: proposed, for the reviewer. Nothing here is implemented.** Written against backend `a16db6d`. M3-E runs alongside M3-D and owns `/assessment` in `openapi.yaml`.

**Summary:** M3-E closes G-10's assessment and attempt findings and the rest of G-39. Most of that is mechanical. Two things aren't: the same staff-visibility defect M3-C found in the catalogue exists here, and assessments can outlive their course. Everything L1 to L3 guarantee must still hold afterwards, and the existing PostgreSQL race tests are how that's shown.

## Decisions for the reviewer

| # | Decision | Recommendation |
|---|---|---|
| 1 | Staff see drafts in `listAssessments`, though the contract says drafts never appear | Default to published for everyone, as M3-C did for archived courses. Staff pass `include_drafts=true`, documented as a staff extension outside the mobile contract |
| 2 | Staff get every question in list and detail responses, though the contract says questions are only available through an attempt | The mobile routes never return questions, to anyone. Staff read them through a staff route outside the mobile contract |
| 3 | An assessment of a course that's archived, or that sits under an archived department or faculty | Hidden from students, the same as the course, and no new attempt can start |
| 4 | An attempt already in progress when its course is archived | It can still be answered and submitted, and finalization still runs, so no student loses work they started. Only new attempts are refused |
| 5 | `attempts_used` on the list | Computed for the page's assessments only, in the same query or one more, not for every assessment the student ever took |

## What M3-E closes

| Gap | Findings | Change |
|---|---|---|
| G-10 | `limit` and `offset` on `GET /assessment/assessments` and `GET /assessment/attempts` | The shared `Page` parameters from M3-C, paged and counted in SQL, with `meta.pagination` |
| G-39 | `tenant_id` and `user_id` in twelve responses: list and get assessment, list and get attempt, the result, start and submit | Removed from student responses. The contract's schemas are the allowlist, as for documents |

**Order:** both lists are newest first, then by id, per the contract: `created_at DESC, id DESC`. Today neither query orders at all.

## Visibility

The same rule as M3-C, so a student can't reach an assessment through a course they can't see:

| Assessment | Student | Staff, default | Staff, `include_drafts=true` |
|---|---|---|---|
| Published, course visible | Listed and opened | Listed | Listed |
| Draft | 404 | Not listed, can open | Listed |
| Published, course archived or hidden by its department or faculty | 404 | Not listed, can open | Listed |
| Another tenant's | 404 | 404 | 404 |

- **The course filter** follows M3-C's rules: an unknown or hidden `course_id` gives an empty page, not everything. A NUL or an offset past the maximum is refused with 422.
- **Starting an attempt** checks the same visibility inside the transaction that L1 already uses for the attempt limit. L1's advisory lock doesn't cover the course, so that transaction also reads the course, department and faculty `FOR SHARE`. An archive then waits for it, and an attempt starts either before the archive commits, continuing as decision 4 says, or not at all.
- **An attempt in progress** isn't affected by its course being archived (decision 4). L3's finalization worker doesn't look at visibility, and must not start to.
- `listAttempts` shows a student's own attempts whatever their course's state: it's their history, and hiding it would look like lost work.

## What must not change

L1 to L3 are merged and their guarantees are in the register. M3-E reads them and doesn't touch their logic:

- **L1, attempt limits:** `pg_smoke/test_attempt_policy_race.py`.
- **L2, result release and feedback:** release precedence and correct answers never in a student response.
- **L3, one finalization path:** `pg_smoke/test_attempt_finalization_race.py` and `test_attempt_submit_race.py`.

Each M3-E PR runs those on migrated PostgreSQL, and the PR states that it did.

**Removing fields** is the only change near them. `user_id` leaves the response, not the authorization: every attempt route still checks that the attempt belongs to the caller, and a test proves another student's attempt gives the same 404 after the change as before.

## Delivery

| # | PR | Closes |
|---|---|---|
| 0 | This design | |
| 1 | Visibility: published by default, `include_drafts`, no questions on mobile routes, hidden courses | Decisions 1 to 4 |
| 2 | Pagination and order on both lists, in SQL, with `attempts_used` for the page | G-10's remaining findings |
| 3 | Fields removed from the twelve responses, and the gap entries closed | G-39 |
| 4 | PostgreSQL tests: visibility under a concurrent archive, paging past the generic-plan threshold, the L1 to L3 suites | |

G-10 and G-39 close in the PRs that remove their findings, with the drift gate in the same commit, so no intermediate commit fails it.

## Acceptance tests

| Requirement | Test must show |
|---|---|
| Pagination | Pages cover everything once, in contract order, with the true total. Boundaries as in M3-C: limit 0, 101, a negative or huge offset, NUL |
| Drafts | No student or default staff list contains one; `include_drafts` needs staff; a student asking is refused |
| Questions | No mobile route returns questions to anyone |
| Hidden course | Its assessments are unlisted and unopenable for students, and starting an attempt is refused, including when the archive races the start |
| Work in progress | An attempt started before its course was archived can be answered, submitted and finalized |
| Fields | No response on a mobile route contains `tenant_id` or `user_id`, checked by the drift gate |
| Ownership | Another student's attempt is a 404 before and after the change |
| L1 to L3 | Their PostgreSQL race tests pass unchanged |

## Coordination

- `/assessment` in `openapi.yaml` and G-10 and G-39 in `gaps.yaml` are M3-E's. M3-D and M3-F don't edit them.
- M3-E adds no migration unless an index is needed for the ordered page, which the PR measures first. If it does, it takes the next Alembic number after whichever of M3-D's 0030 and L4's outbox merges first.
- M3-E's PRs and M3-D's will both change `contract_sha256`. Whichever merges second rebases the hash.
