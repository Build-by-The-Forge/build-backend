# Student journey contracts: design for S-03, S-07 to S-10, S-13 and S-14

**Status:** design for review. Nothing here is implemented. Written against backend `6e216ca`.

This carries out the blueprint's "needed first" item (section 5): the student journey contract, so the mobile app builds only against operations the backend guarantees and never invents its own. S-02, the academic profile, has its own design (#110) and implementation (#111).

**What the screens need** comes from the frontend PRD (Build-UI `docs/BUILD_FRONTEND_MASTER_PRD.md`). **What the backend guarantees** is this document.

**Summary:**
- **New routes** for four capabilities:
  - a reading position per document (S-07);
  - practice sets (S-10);
  - a progress summary over official results (S-13);
  - account preferences (S-14).
- **No aggregate endpoint for the dashboard (S-03):** it is composed from existing routes, plus one new filter.
- **Study planning (S-09)** stays on the device in this release.
- **Knowledge trees (S-08)** get their contract now. They are implemented once the AI service builds them from authorised course material. A shared tree uses only material every eligible student can read, and every read re-checks each citation for the reader (D3, revised after review).

## Rules for every operation here

These are the same as S-02, including the review findings on #111.

| Rule | How |
|---|---|
| Student memberships only | Enforced where data is read and written, not only by the route. The membership row is held `FOR SHARE` for the whole transaction, reads included (#111) |
| Identity | Taken only from the authenticated principal. No user or membership ID appears in a path or a body |
| Tenant | Tenant-scoped (`X-Tenant-Slug`), and every foreign key carries `tenant_id` |
| Envelope and errors | `docs/mobile-api-conventions.md`. Submitted values are never echoed, and no internal field appears (G-39) |
| No fabricated data | Every figure has a documented definition and source (PRD sections 151 and 152). Nothing is called "mastery" |

## Decisions for the reviewer

| # | Capability | Question | Recommendation |
|---|---|---|---|
| D1 | S-03 dashboard | One aggregate endpoint, or composed from existing routes? | **Composed.** The PRD wants sections that load and fail independently (section 75). An aggregate would couple their failures and duplicate each list's authorization. The contract documents which route feeds each section. "Suggested next actions" waits for recommendations (PRD section 153), which depend on learning memory's gate |
| D2 | S-07 reading | What is stored? | **The last page per document only**: `{page, updated_at}`, per student and document. The app derives a percentage from the page count. Highlights and notes need their own retention decision and aren't in this slice. A new version of the document starts again at page 1 |
| D3 | S-08 trees | When, and who may see a shared tree? | **The contract now; implementation after AI-07 builds trees from authorised course material** (blueprint AI order, step 5). Generation is a backend job (202 with a status), never synchronous. **Revised after review:** a tree shared by a course's students is built **only from material every eligible student can read**. Every read **re-checks each cited source for that reader**, so a citation can never reveal material the reader can't access. See the S-08 section |
| D4 | S-09 planning | Backend or device? | **Device only in this release.** The calendar already works locally, and nothing else needs the data yet. The contract says so, and the app labels plans as stored on this device (PRD section 188). Goals stay unstored (S-02 decision 6) |
| D5 | S-10 practice | What is a practice set? | Generated from authorised material by the AI service, through the backend. **Stored per student.** Never an official attempt, score or result (blueprint decision 2). Answers come with the set: practice reveals them by learning mode, and every question is labelled generated. Unsupported questions are dropped and counted (AI-06's checks). A daily cap per student applies until entitlements exist |
| D6 | S-10 practice | Which permission does the backend sign? | **A new `ai.practice.generate`**, granted to students, which the AI service accepts on `/v1/ai/generate-questions` (a paired change). `ai.questions.generate` stays staff-only: it is for question banks, and students don't hold it |
| D7 | S-13 progress | Which metrics? | **Official CBT only in this slice**, each with a definition (below). Practice never enters official figures. **Correctness counts only where the result's release policy already discloses it** (L2), so the summary can't reveal what the result screen withholds |
| D8 | S-14 preferences | Which, and where? | **A closed set:** theme, text size and reduce motion. They belong to the **account**, not a tenant (`/identity/preferences`). Notification toggles arrive with notifications. Account deletion is its own design (NDPR), not a preference |

## S-03 dashboard: the composition (D1)

| Section | Route | State |
|---|---|---|
| Academic context, current courses | `GET /academic/profile` | #111 |
| Recent materials, and what is processing | `GET /content/my-documents?limit=5` and **a new `ingestion_status` filter** | Contract #87 without the filter; not implemented (G-01) |
| Recent AI sessions | `GET /ai/conversations?limit=5` | Contract #90; not implemented (G-17) |
| Available examinations | `GET /assessment/assessments` | Implemented |
| Recent results | `GET /assessment/attempts?limit=5` | Implemented, newest first |
| Learning progress | `GET /progress/summary` | S-13, below |

The only contract change is the `ingestion_status` filter on `listMyDocuments` (`processing` covers `uploaded`, `quarantined`, `queued` and `processing`). Each section is one request the app can retry on its own.

## S-07 reading position (D2)

| Route | Behaviour |
|---|---|
| `GET /reading/positions/{asset_id}` | `{asset_id, asset_version, page, updated_at}`. Before the first save it is 200 with `page` and `updated_at` null, like S-02 decision 8 |
| `PUT /reading/positions/{asset_id}` | `{page}`: stored and returned. Last write wins |

- **Readable documents only:** the content read policy decides (`may_read`, M3-D PR 4). An unknown or unreadable document gets the same 404, so existence never leaks.
- `page` is from 1 to the version's page count, taken from its ingestion metrics. Anything else is 422.
- **Data:** `reading_positions (tenant_id, user_id, asset_id, asset_version, page, updated_at)`.
  - The primary key is `(tenant_id, user_id, asset_id)`.
  - Composite tenant keys point to the membership and the asset.
  - Rows are deleted with the membership and with the asset.

## S-08 knowledge trees: contract only (D3)

| Route | Behaviour |
|---|---|
| `GET /courses/{course_id}/knowledge-tree` | `{status, version, generated_at, nodes: [{id, parent_id, title, kind, sources: [{asset_id, page}]}]}`. `status` is `not_generated`, `generating`, `ready`, `stale` (a source changed since generation; a regeneration is queued) or `failed`. A course the student can't read is 404 (the M3-C rule) |
| `POST /courses/{course_id}/knowledge-tree/generation` | **202**, with the job's status. One job runs per course: a second request while one runs returns it |

### Who may see a shared tree (revised after review)

A tree is the course's, shared by the students who can read the course. Two rules keep sharing from becoming a way around authorization.

**1. Generation uses only uniformly authorized material.** The AI service is given only material that **every** student who can read the course can read:
- the course's institutional-scope material (scope acknowledged by the AI service);
- with a tenant-wide audience under the content read policy (`may_read`, M3-D PR 4);
- not in `denied_assets` and not pending a lowering.

**Excluded:**
- a student's own documents;
- material limited to a narrower audience;
- anything unclassified.

So no student's access shapes what the others see. The generation call carries `denied_assets`, and the provenance check runs on the answer as for chat.

**2. Every read re-checks the citations for the reader.** `GET` runs `may_read` for the caller on each node's sources:
- A source the caller can't read now is removed from that node's citations: no asset ID, page or title.
- A node left with no readable source is omitted, and its children move up to the nearest remaining ancestor.
- If any source was lowered, revoked or denied since generation, the tree reads as `stale` and a regeneration is queued.

Material can change after generation, so rule 1 alone isn't enough; rule 2 makes the citations safe for each reader regardless.

**Further:**
- **Every node cites at least one source** at generation, and a node without one is dropped.
- A citation is an asset ID and a page only. The passage's text is read through the reading routes, which apply `may_read` themselves.
- Trees from a student's own documents are per student and come later. **Partitioning** shared trees by authorization scope (the review's alternative) is the route if narrower audiences become student-visible; until then, one uniformly authorized tree per course is enough.

## S-09 planning (D4)

**No routes.** The contract records that study plans and calendar events are device-only in this release, and the app shows that.

## S-10 practice sets (D5, D6)

| Route | Behaviour |
|---|---|
| `POST /practice/sets` | `{topic, course_id?, asset_ids?, question_type, count (1 to 20), difficulty}`. The answer is **201** with the stored set. Other answers: **503** `AI_SERVICE_UNAVAILABLE` when the model can't answer; a `grounded: false` set (no questions) when no authorised material covers the topic, never questions from the model's own knowledge; **429** `PRACTICE_LIMIT_REACHED` past the daily cap |
| `GET /practice/sets` | The student's sets, paged, newest first |
| `GET /practice/sets/{set_id}`, `DELETE /practice/sets/{set_id}` | The student's own only. Any other set is 404 |

- **What a set holds:** `{id, created_at, topic, course, question_type, difficulty, requested, grounded, discarded, questions: [{id, prompt, options: [{text, is_correct}], explanation, sources: [{asset_id, page}]}]}`.
- **The material it may use:** the student's own readable documents and the tenant's institutional material. That means `asset_ids`, checked by `may_read`, or the course's material otherwise. Every call carries `denied_assets`, and the provenance check runs on the answer.
- **Citations are re-checked on every read**, as for trees (D3, rule 2), and in line with chat's provenance check (#100). A stored set can outlive the reader's access to a source: a rights takedown, a revocation or a lowering.
  - A source the student can no longer read is removed from a question's citations.
  - A question with no readable source left is **withheld** (`withheld: true`, with no prompt, options or explanation), because its text was built from that material.
  - The set's counts show how many are withheld.
- **Separate from CBT:** `practice_sets` and `practice_questions` are separate tables. Nothing is written to the assessment tables, so practice can't reach official results.
- **The daily cap** is a setting, with a conservative default, enforced by the backend.

## S-13 progress summary (D7)

`GET /progress/summary` returns `{as_of, definitions_version, official: {...}}`. Each figure below is all-time within the tenant, computed when read, and counts only the student's own attempts.

| Figure | Meaning | Source | Limitation |
|---|---|---|---|
| `assessments_attempted` | Distinct assessments with at least one started attempt | Attempts | — |
| `attempts_submitted` | Submitted or finalized attempts | Attempts | — |
| `results_released` | Attempts whose result the student may see now | The release policy (L2) | Unreleased results aren't counted |
| `mean_percentage` | Mean score percentage over released results | Results | Null when there are none |
| `by_course` | The same, per course | Results and assessments | Readable courses only |
| `by_topic` | Correct answers over answered questions, per topic | Answers, `questions.topic_id` | **Only attempts whose feedback timing already discloses correctness**, and only topics the student can read now (active, in a readable course: the M3-C rule), so an archived topic's title isn't shown |
| `last_activity_at` | The latest attempt start or submission | Attempts | — |

Practice figures, if they are ever shown, are a separate, labelled section, never in `official`.

## S-14 preferences (D8)

| Route | Behaviour |
|---|---|
| `GET /identity/preferences` | `{theme, text_size, reduce_motion, updated_at}`. The defaults are `system`, `default`, `false` and null |
| `PUT /identity/preferences` | The whole set. An unknown key or value is 422 |

- Values:
  - `theme`: `system`, `light` or `dark`;
  - `text_size`: `small`, `default`, `large` or `larger`;
  - `reduce_motion`: a boolean.
- They belong to the account, so they aren't tenant-scoped: a student in two tenants has one set. Any authenticated, verified user may read and write their own.

## Delivery

1. **This design**, for review only.
2. **The contract:** the operations approved here, and the `ingestion_status` filter. New implementation gaps, numbered after G-43, each get `missing_route` findings, so the drift gate tracks them until they're built.
3. **Implementation, one PR each, smallest first:**
   - S-14 preferences;
   - S-07 reading positions;
   - S-13 progress;
   - S-10 practice, paired with the AI service for `ai.practice.generate`;
   - S-08 after AI-07.

   Each closes its gaps with proof, and each has PostgreSQL tests wherever it writes.

## Acceptance tests

| Test | Capability |
|---|---|
| Each dashboard section's route answers on its own; one failing doesn't affect the others | S-03 |
| A position is saved and read back. An unreadable or unknown document gets the same 404. A page outside the document is 422. A new version starts at page 1 | S-07 |
| Generation receives only uniformly authorized material: no personal, narrow-audience, unclassified, denied or lowering-pending asset. Every node cites a source. A second generation request while one runs returns the running job | S-08 |
| A source lowered or revoked after generation disappears from a reader's citations on the next read. A node left without a readable source is omitted. The tree reads as `stale`. A reader who can't read a source never receives its asset ID | S-08 |
| A set's questions come from authorised material, with sources. Topics without material give `grounded: false` and no questions. Nothing is written to the assessment tables. The cap is 429. Another student's set is 404 | S-10 |
| After a source is revoked or lowered, a stored set's next read drops that citation. A question left with no readable source is withheld, with none of its text | S-10 |
| Every figure matches its definition on seeded attempts. An unreleased result, or correctness not yet disclosed, never changes a figure | S-13 |
| Preferences round-trip. Unknown keys or values are 422. They are the same from any tenant | S-14 |
| Staff memberships are refused at the data-access boundary, and the membership is held for each read and write (PostgreSQL forced-order tests) | S-07, S-10, S-13 |
