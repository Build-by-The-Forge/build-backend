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
| G-16 result policy | **Results and per-question `is_correct` are available straight after submission, without the correct answers** | This is what happens today, with the answer key withheld. **Needs a product answer: can an assessment be retaken?** Today a new attempt looks possible after submitting, so a student could use `is_correct` to improve on a retake |

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
| G-26 | Implementation | Medium | **A student has no way to discover a tenant slug.** This contract has none either. For a FUTA-only first release the slug can be app configuration, which needs confirming | No listing route; `tenants` routes take a known slug | Product decision, then M6 |
| G-27 | Implementation | **High** | **Assessment time limits appear not to be enforced.** `duration_minutes` is stored, but nothing in the attempt code reads it | `app/application/assessment/attempt*.py`, `app/domain/assessment/attempt.py` | M3-E. M2 confirms it first |
| G-28 | Contract | Low | No record of a student's programme or department, so course lists filter by a parameter rather than "my courses" | `app/api/catalogue/courses.py` | Later phase |

## Still open

- **Conversation retention**, a product decision that must be settled before conversations reach students.
- **Licensing of shared documents.** Opening staff-uploaded material in the app distributes it to students, so shared sources need permission to do that. The contract allows it; it doesn't establish the right.
