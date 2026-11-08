# S-02 design: the student's academic profile

**Status: design for review. Nothing here is implemented.** Written against backend `a8f4b4d`. It carries out decision 1 of the master execution blueprint (#107): a backend-owned academic profile (programme, level, enrolled courses), validated against the academic catalogue, closing G-28. This design comes first; its migration follows 0031.

**Summary:** today onboarding keeps the student's school, department, level and courses only on the device, so no other device, no dashboard and no AI capability can use them. This adds one profile per membership, set and read by the student through two routes. Every reference in it is checked against the tenant's active catalogue, and it's replaced as a whole, so a profile is never half-written.

## Decisions for the reviewer

| # | Decision | Recommendation |
|---|---|---|
| 1 | Mobile onboarding asks for a department; the profile needs a programme | **Programme is required.** The student picks from the department's active programmes, and the app preselects it when there's only one. Department and faculty aren't stored: they're read from the programme, so they can't disagree with it |
| 2 | Which levels are allowed | **Any active level of the tenant** (`levels.code`). Not capped by the programme's `duration_years`, because spill-over students study beyond it |
| 3 | Which courses can be enrolled | **Any course a student can read** (active, under an active department and faculty: the M3-C rule), in any department or level. Carry-overs, electives and general courses cross departments. No programme-to-course mapping exists to check against (`curriculum_versions` is unmigrated), and this design doesn't invent one |
| 4 | A course or programme archived after it was saved | The stored row stays, so restoring it brings it back. Reads leave out an enrolled course the student can no longer read. An unavailable programme reads as `null` with `complete: false`, so the app asks again. A **new** save that names anything unavailable is refused |
| 5 | Course history across sessions | **Not in this slice.** The profile holds the current set only, with no session reference. History arrives only with a later decision, when results or progress need it |
| 6 | Goals and learning styles (onboarding steps three and four) | **Not stored.** They feed personalisation, which depends on learning memory, and its production gate stays closed. The app keeps them on the device until that decision is made |
| 7 | Who can have a profile | **Student memberships only.** The product has only student logins. A staff membership calling either route gets 403 `PERMISSION_DENIED` |
| 8 | Before the first save | `GET` answers 200 with every field `null`, no courses and `complete: false`, not 404. Onboarding is a normal state, not an error |
| 9 | Two devices saving at once | **Last write wins, whole.** Each save locks the profile row and replaces the course set in one transaction, so the result is exactly one save's content, never a mix. There's no `If-Match`: a profile has one owner, and the cost of a lost edit is re-picking a course |

## Routes

Both routes are tenant-scoped (`X-Tenant-Slug`, membership checked on every request, as for every mobile route). The S-02 rows go into the student journey contract PR.

| Route | Behaviour |
|---|---|
| `GET /academic/profile` | The caller's profile in the selected tenant |
| `PUT /academic/profile` | Replaces it: `{programme_id, level, course_ids}`. All three are required, and `course_ids` can be empty. Answers 200 with the stored profile |

**Response `data`:**

```text
AcademicProfile {
  programme: { id, name, code } | null
  department: { id, name } | null      # from the programme
  faculty: { id, name } | null         # from the programme
  level: integer | null                # a levels.code, e.g. 300
  courses: [ { id, code, title, level, semester, credit_units } ]   # ordered by code, then id
  complete: boolean                    # a readable programme and a level are set
  updated_at: date-time | null
}
```

No `tenant_id`, `user_id` or `membership_id` appears, following G-39's rule that the contract's schema is the allowlist.

**Validation (`PUT`):**

| Input | Answer |
|---|---|
| Unknown fields, wrong types, more than 30 `course_ids`, or duplicates | 422 `VALIDATION_FAILED`. Submitted values are never echoed |
| A programme, level or course that doesn't exist, belongs to another tenant, or can't be read by a student | 422 `VALIDATION_FAILED`, with the field that's wrong. The same answer for all three cases, so it never reveals whether an ID exists in another tenant |
| A staff membership | 403 `PERMISSION_DENIED` |

**Readable** means what a student's catalogue reads already return:
- a programme `listProgrammes` would list: active, its department active, and that department in the programme's own faculty;
- a level that's active;
- a course `getCourse` would answer for a student: active, under an active department and faculty.

The save reuses those queries' conditions rather than restating them.

The 30-course cap bounds the row count and the response size. A full FUTA semester load is well under it.

## Data (migration 0032)

```text
academic_profiles
  id               varchar(36) primary key
  tenant_id        varchar(36) not null
  user_id          varchar(36) not null
  programme_id     varchar(36) not null
  level_code       integer     not null
  created_at, updated_at  timestamptz not null
  unique (tenant_id, user_id)
  foreign key (tenant_id, user_id)      references memberships (tenant_id, user_id) on delete cascade
  foreign key (tenant_id, programme_id) references programmes (tenant_id, id)       on delete restrict
  foreign key (tenant_id, level_code)   references levels (tenant_id, code)         on delete restrict

academic_profile_courses
  profile_id  varchar(36) not null references academic_profiles (id) on delete cascade
  tenant_id   varchar(36) not null
  course_id   varchar(36) not null
  primary key (profile_id, course_id)
  foreign key (tenant_id, course_id) references courses (tenant_id, id) on delete cascade
  index (tenant_id, course_id)
```

- **Tenant-consistent references.** Every foreign key carries `tenant_id`, as 0030 did for courses, so a row can't point into another tenant even if a code path is wrong.
  - `uq_programmes_tenant_id_id` is added as the programme FK's target.
  - `uq_levels_tenant_code` and `uq_courses_tenant_id_id` already exist.
- **Deleting.** No route hard-deletes catalogue rows, so `restrict` is never hit in normal use; it stops a manual deletion from silently emptying profiles. A course deletion cascades, because an enrolment in a course that no longer exists means nothing.
- **Membership.** Removing a membership deletes its profile, so a student who leaves a tenant leaves no academic record behind there.
- **A profile row exists only after the first save.** `GET` before then is decision 8's empty answer, with no row written.

## Transaction (`PUT`)

1. Read the programme, the level and every course, one query each, filtered by tenant and by the readability rule above. Any miss is the 422, and nothing is written.
2. Upsert the profile row: `INSERT ... ON CONFLICT (tenant_id, user_id) DO UPDATE SET programme_id, level_code, updated_at ... RETURNING id`. This takes the row lock.
   - The first save inserts the row. Two concurrent first saves can't both insert: the second becomes the update.
   - A concurrent save waits here until the first commits.
3. Delete the profile's course rows, insert the new ones, then commit.

**Concurrent saves serialise at step 2.** The waiting save's step 3 runs after the first one has committed. Under READ COMMITTED, its delete therefore sees and removes the first save's courses, so the stored set is exactly the second save's.

**An archival that commits between steps 1 and 3 isn't blocked.** The save still stores the course, and reads hide it afterwards (decision 4). This is the same outcome as saving just before the archival, so no `FOR SHARE` is needed on catalogue rows.

## What must not change

- The catalogue routes, their visibility rule and their staff behaviour are untouched.
- No profile data is sent to the AI service or any provider in this slice. Using enrolled courses as a retrieval or dashboard input is Stage 2's work, under its own review. G-33 still governs any provider.
- Request and response bodies are never logged.
- The `GATE_OPEN` gate and learning memory are untouched (decision 6).

## Delivery

1. **This design.** Review only.
2. **The contract.** Part of the student journey contract PR: two operations, the `AcademicProfile` schema, and the S-02 row. G-28 moves from `contract_gaps` to `implementation_gaps` with two `missing_route` findings, so the drift gate tracks it.
3. **Migration 0032 and the routes**, in separate commits:
   - the migration with its round trip;
   - the repository and the transaction;
   - the routes;
   - the PostgreSQL tests.
   This closes G-28 with its proof.
4. **Mobile.** Onboarding's steps one, two and five read and write the profile through the typed client, adding the programme pick from decision 1.

## Acceptance tests

| Test | Where |
|---|---|
| Save, then read: the same programme, level and courses, with department and faculty taken from the programme | Integration |
| Each validation row above, including a programme, level and course of another tenant, all answered identically | Integration |
| A course archived after saving disappears from reads and comes back when restored; an archived programme reads `null` and `complete: false` | Integration |
| A staff membership gets 403 on both routes; a revoked membership gets the tenant guard's refusal | Integration |
| Two concurrent saves with different course sets: the stored set is exactly one of them, 40 runs out of 40 | `pg_smoke` |
| Two concurrent first saves: one profile row | `pg_smoke` |
| Removing the membership deletes the profile and its courses | `pg_smoke` |
| The reads and the save's lookups repeated past five executions, so the generic plan is exercised | `pg_smoke` |
| Migration 0032 round trip and schema drift | Migration gate |
| G-28 closed with its proof; the drift gate is green | Drift gate |
