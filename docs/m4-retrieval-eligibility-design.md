# M4-A design: retrieval eligibility and citation authorisation

**Status: draft for the reviewer. Nothing here is implemented.** M4-B (implementation) starts only after this document is approved on an exact commit. Written against backend `e9067ed` and ai-service `origin/main` (read with `git show origin/main:...`). Open ai-service PRs #66 (tutor turn, `ee52569`) and #69 (dispatch scope, `c4a508f`) are used for context only; nothing here depends on their fixes.

**Summary.** Retrieval today is filtered by tenant, by a per-document *scope* (`institutional` only is retrievable) and by `denied_assets`. It is not filtered by readiness, by run or attempt, or by what this user may read. The backend's post-generation check asks only "may this caller read this asset id", with the one read policy, which ignores processing state. M4 replaces the deny-list with a backend-computed **allow-list of `(asset_id, run_number, attempt)`**, makes the AI service retrieve only chunks whose exact triple is in it, and makes the backend re-evaluate the same eligibility on exactly the triples in `sources_used` after generation, withholding the whole answer on any mismatch. It also validates every citation against the evidence actually retrieved.

Sections: [1 Properties and current state](#1-the-eight-properties-and-the-current-state) · [2 Findings from reconciling](#2-findings-from-reconciling) · [3 The design](#3-the-design) · [4 Threat analysis](#4-threat-analysis) · [5 Contract changes](#5-contract-changes) · [6 Decisions for the reviewer](#6-decisions-for-the-reviewer) · [7 M4-B plan](#7-m4-b-implementation-plan) · [8 Tests as specification](#8-tests-as-specification)

## 1. The eight properties and the current state

Legend: **exists** = enforced in merged code with a test on the production path; **partial** = enforced for some states or paths; **missing**. "Owner" is who must enforce it. Evidence paths are relative to each repository; `AI:` is ai-service `origin/main`.

| # | Property | Owner | Today | Evidence | Gap |
|---|---|---|---|---|---|
| 1 | The document belongs to the requesting tenant | AI (index filter) and backend (provenance) | **exists** | AI: `app/services/rag/pg_index.py` `query_dense`, `_SPARSE` filter `tenant_id` in SQL from the verified context, never from the body (`app/schemas/ai.py` forbids extra fields); tests `tests/integration/test_pg_chunk_index.py::test_tenant_b_never_retrieves_tenant_a`, `test_scope_filter.py::test_the_scope_is_the_documents_own_tenants`. Backend: `read_policy.may_read` returns false for another tenant; `tests/integration/ai/test_provenance_policy.py` | None for retrieval. Hardening: `raise_fence` does not check the asset is not held by another tenant (§2.4) |
| 2 | The user may read it (the one read policy) | Backend | **partial** | Post-generation only: `app/api/ai.py::readable_sources` → `ContentReadService.readable_asset_ids`; `tests/integration/ai/test_provenance_policy.py`, `tests/infrastructure/ai/test_assistant_gateway.py::test_one_unreadable_source_withholds_the_whole_answer`. **Not applied before retrieval**: the AI service retrieves everything `institutional` in the tenant regardless of who asks | Nothing narrows retrieval to what *this user* may read. Today it coincides only because personal documents are excluded by scope and institutional ones are tenant-wide. Fails as soon as audiences narrower than the tenant, or personal retrieval, are enabled |
| 3 | In an eligible READY state | Backend decides; AI enforces | **missing** | Retrieval is gated by scope only (AI `pg_index.py`). Backend `may_read` ignores `ingestion_status` except `quarantined`/`rejected` for *published personal* documents (`read_policy.py` `UNCLEAN_INGESTION`). This is G-05 | A document with chunks committed by a failed attempt, or reprocessing, or a run not yet `ready`, is retrieved and passes the provenance check if its scope is `institutional` |
| 4 | Every chunk belongs to the right document, run and attempt | AI writes; backend names the current triple | **partial** | Writes are fenced: AI `pg_index.replace_asset` locks `ingestion_fences` and writes only the fenced `(run, attempt)`, replacing the whole asset (`test_index_fence.py`: `test_a_delayed_old_attempt_cannot_overwrite_the_current_index`, `test_a_late_attempt_cannot_fill_an_empty_index`). Each chunk row stores `run_number`, `attempt`; the recorder reports them in `sources_used` (`test_durable_retrieval.py::test_sources_used_names_the_run_and_attempt_that_were_retrieved`) | Nothing at read time compares a chunk's `(run, attempt)` with the backend's current one. The chunk's attempt is written from the dispatch's `attempt_count`, which the backend sets (`app/infrastructure/content/ai_gateway.py:112-114`), so it is reliable as a key (§3.2) |
| 5 | A superseded run or version is never used | Backend (which is current), AI (enforce) | **missing** | Dispatch raises the fence to the new `(run, attempt)` **before** the new chunks exist (`AI: app/api/v1/ingest.py`), and `replace_asset` only deletes the old chunks when the new attempt writes. Until then the **old chunks stay retrievable**. After a failed reprocess they stay indefinitely | Between a reprocess dispatch and its first successful write, and after a failed one, superseded chunks are served and pass the backend check (it never compares run/attempt, §2.2). The boundary doc chooses the safe side: unavailable while reprocessing |
| 6 | Revoked, deleted or lowered-scope documents are never used, including in flight | Backend | **partial** | *Lowered scope*: outbox + `denied_assets` + provenance recheck of the denial list: `scope_assignments.py::pending_lowerings`, `assistant_gateway.py::_check_provenance`; `boundary/test_scope_boundary.py::test_m3d_a_document_is_served_only_while_institutional_and_not_denied`, gateway tests `test_a_source_denied_while_the_call_was_out_withholds_the_answer`. *Revoked asset*: `RevokeContentAssetHandler` enqueues the lowering in the same transaction, and `UNREADABLE_STATUSES` fails the provenance read. *Deleted*: status exists in the policy; no delete route or AI delete route yet (G-32, PR 11) | (a) Revoking a **source** does nothing to its assets (§2.1). (b) Denial only covers documents that were `institutional`: a deny-list cannot express "this personal document stopped being the caller's". (c) Delete has no route; the AI delete (`pg_index.delete_document`) has none either |
| 7 | Every citation is validated against evidence actually retrieved | AI (builds), backend (re-validates) | **partial** | AI builds citations only from recorded passages: `evidence.py::check_grounded` (a number not among the passages, or none cited, becomes the fixed `NOT_COVERED`), `Evidence.__post_init__` rejects an unrecorded passage; tutor turn PR #66 adds structured citations carrying `(document_id, run, attempt)` and requires them to be in `sources_used`. Backend **discards** `citations` and `grounded` today (`assistant_gateway.py::chat` reads `answer` and `context_used` only, G-04) and returns raw `context` (G-18) | No backend validation exists because no backend consumer exists. Backend-owned `source_id`/`title` lookup, `[n]`↔citation consistency and citation⊆`sources_used` are all missing |
| 8 | Authorisation rechecked after generation; unreadable source withholds the whole answer | Backend | **partial** | `_check_provenance` runs after the response is verified and its nonce consumed; any unreadable or denied source, or a check that cannot run, raises `ANSWER_WITHHELD` (503 + `Retry-After`) and nothing is returned (gateway tests lines 508-561; `app/core/exceptions.py::AnswerWithheldError`) | The recheck asks *readable by policy* and *not in denied list* only. It does not ask *eligible now at this run and attempt*. It also gives no atomicity with persisting the answer (M3-F) (§3.6) |

**Reading the table.** The machinery for 1, 4 (writes), 7 (AI half) and 8 (withhold-whole) exists and is well tested. What is missing is the **read-time identity of what is eligible**: today eligibility is a property of a *document's scope*, set by an eventually-consistent outbox, not a property of the *exact processed version*, evaluated per request.

## 2. Findings from reconciling

### 2.1 Revoking a source leaves its documents live (possible defect, reported)

`RevokeContentSourceHandler` (`app/application/content/source_handlers.py`) only calls `source.revoke(reason)`. Nothing revokes or lowers the source's assets: the read policy (`read_policy.py::may_read`, `read_policy_sql.py::readable`) never looks at the source's status, and only `RevokeContentAssetHandler` enqueues a lowering. The existing test (`tests/integration/content/test_content_source_api.py` around "15. Revoke source") asserts only that the source reads back `revoked`. After "Withdrawn by department head", its institutional documents stay readable, stay `institutional` in the AI service, and keep being retrieved and cited. Whether a source revocation should withdraw its documents is a product decision (rights are per document, M3-D ruling A), so it is raised as decision **D1** and pinned by a strict-xfail test (§8). M4's eligibility query closes it mechanically if the decision is "yes" (a revoked source's assets are not eligible).

### 2.2 The backend never compares run or attempt

`_valid_sources` checks only that `run_number` and `attempt` are integers ≥ 1; `_check_provenance` is passed `{source["asset_id"] ...}` and discards the rest. `readable_asset_ids` is a pure function of the asset row. So the superseded-run and failed-after-ready cases (property 5, 3) are invisible to the post-check. This is the known G-05 gap, stated precisely: **the information needed to close it is already in the signed response; the backend throws it away.**

### 2.3 `may_read` is not an eligibility predicate

`may_read` answers "may this caller see this document", not "may this document's text be used in an answer". Examples that differ: a *published personal* document is readable by classmates but must never be retrievable for them (publication ≠ AI use, `m3-d-design.md` "Three kinds of permission"); an *institutional* document under reprocessing is readable but not eligible; staff may read an unreviewed institutional document but it must not reach a student's answer. Eligibility must be defined as `may_read ∧ ai_use ∧ ready ∧ current`, one function, one SQL query, one set of tests.

### 2.4 Cross-tenant asset holding: where it exists on `origin/main`

I looked for the class of gap behind #69 on `origin/main`:

- Reads (`query_dense`, `_SPARSE`, `delete_document`, `count`) all filter the verified tenant in SQL. No cross-tenant read path found.
- `PgScopeStore.assign` refuses an asset held by another tenant (`_HELD_ELSEWHERE`, looks at both `ingestion_fences` and `asset_scopes`).
- `PgChunkIndex.raise_fence` (`app/services/rag/pg_index.py`) does **not** make the same check: a signed dispatch from tenant B naming an asset ID that tenant A holds creates `(B, asset)` fence and, later, `(B, asset)` chunks. Tenant A's data is not exposed (every read is tenant-filtered), but B's fence row then makes A's own later scope assignment fail `AssetHeldByAnotherTenantError` (`_HELD_ELSEWHERE` sees B's fence). Reaching it needs a validly signed backend call for B naming A's ID; asset IDs are backend-generated UUIDs, so this requires a backend bug or compromise. **Not a live defect; a hardening item** for the AI-side M4-B PR: the dispatch must refuse an asset another tenant holds, as `assign` does. The version-zero hole in #69 is in that open PR only, not in `origin/main`.

### 2.5 Other observations (not defects)

- `PgChunkIndex._to_contract` sets `document_title=row.asset_id`: the AI service never knows titles. Good: it means a model can't invent a title from retrieval, and the backend must own title and `source_id` (as the boundary doc already says).
- The boundary doc's required-tests table says "each runs on every path to retrieved text". The paths today are `chat`, `explain`, `generate-questions`, `/v1/ai/retrieve` (all `RetrievingRequest`), and the tutor turn in #66. All go through `RetrievalService`/`retriever.evidence` → `HybridRetrievalEngine.retrieve` → `PgChunkIndex`. A single filter in the engine/index covers all of them; the tests must still run per path (§8).
- The AI service has no request-body limit on its retrieving routes (backend: 1 MiB by default, `max_request_body_bytes`). §3.5 sets one.


## 3. The design

### 3.1 One definition of eligible

A document version is **eligible for this caller at this moment** when all of the following hold. The backend evaluates it in one SQL query (`eligible_sources`), used for both the allow-list before retrieval and the recheck after generation, so the two cannot drift (the same technique as `readable` / `may_read`, with the same agreement test).

| # | Condition | Source of truth |
|---|---|---|
| E1 | The asset is in the caller's tenant (`tenant_id` equals the verified context's) | `content_assets` |
| E2 | The caller may read it: `may_read` (the one policy) | `read_policy_sql.readable` |
| E3 | The asset is `active` (not `revoked`, not `deleted`) and its **source** is not `revoked` (decision D1) | `content_assets.status`, `content_sources.status` |
| E4 | **AI use is permitted for this caller**: the document is the caller's own personal document, or it is `institutional` and its latest staff rights review is accepted, has `ai_use = permitted`, and is for an audience that includes the caller. Publication alone never qualifies (`m3-d-design.md`, "Three kinds of permission"). Today `ai_use` is checked only when the classification is made, where it decides whether a scope assignment is queued (`classification.py:220`, `classification_store.py:150`), and `may_read` ignores it: a later review that withdraws AI use reaches the AI service only through a new assignment | `ownership_class`, `owner_user_id`, rights assertions (`ai_use`) |
| E5 | The scan verdict is `accepted` (not `quarantined`, not `rejected`) | scan record / `ingestion_status` |
| E6 | The asset's **latest job** (highest `run_number`) is `ready`; no newer run exists in any other state | `content_ingestion_jobs` |
| E7 | The entry's `(run_number, attempt)` is that latest ready job's `(run_number, attempt_count)` | same row |
| E8 | The AI service holds the document with a retrievable scope (applied by the AI service, never assumed by the backend) | `asset_scopes` |

E1-E7 are the backend's; E8 stays the AI service's, as defence in depth (§3.4). A missing or unreadable input to any condition means *not eligible*.

### 3.2 The allow-list entry is the exact processed version

```json
"allowed": [ {"asset_id": "...", "run_number": 3, "attempt": 1}, ... ]
```

Why the triple and not the asset: chunk rows carry `(run_number, attempt)` written by the fenced `replace_asset`; those are the dispatch's values, which the backend set from the job it tracks (`app/infrastructure/content/ai_gateway.py:112-114`). The fence is monotonic and `replace_asset` replaces the asset whole, so at most one `(run, attempt)` exists in the index per asset, and it is the fenced one. A chunk can therefore only match when it was written by the exact attempt the backend later recorded as `ready`. **`chunk.attempt` is reliable for this purpose**; it is not provenance-only. This answers the boundary doc's open question. The one caveat is that the `ready` job's `attempt_count` must be the attempt that wrote; `apply_callback`'s active-attempt rule (`app/domain/content/job.py`) guarantees only the active attempt can advance the job to ready, and the §8 tests pin it on the production path.

### 3.3 Allow-list, not deny-list, for personal documents (G-05)

Recommendation: **allow-list only.** A deny-list is correct only if the backend can enumerate everything that must *not* be retrieved, forever, and every entry is delivered; both fail open (a missing entry means "retrievable"). Personal documents are exactly the case where the unsafe set is large and growing (every other student's documents and every non-ready one) and the safe set is small and known (the caller's own ready documents plus the tenant's reviewed institutional set). `denied_assets` was the right interim tool (it covers one transition and is bounded by 1,000); it cannot express "not yours" or "not ready". With an allow-list:

- absence means not retrievable, everywhere, including when the backend forgets a state;
- a personal document is retrievable only for its owner because it is only ever put in the owner's list;
- revocation, deletion, lowering, reprocessing and new attempts all work by one mechanism: the entry disappears or changes triple at the commit;
- the list can be bounded and measured (§3.5), and a too-large list fails visibly.

`denied_assets` stays during migration and is removed once `allowed` is required and proven (D4): `allowed` minus `denied` is strictly narrower, and removal is a contract change that deserves its own step.

### 3.4 What the AI service enforces

For every retrieving call, in SQL, before ranking or any limit (where the scope filter sits today, `pg_index.py`):

```text
chunk.tenant_id = verified tenant
AND (chunk.asset_id, chunk.run_number, chunk.attempt) IN allowed      -- new
AND asset_scope.scope is retrievable for this call                    -- E8, existing
AND chunk.asset_id NOT IN denied                                      -- existing, until D4
```

- `allowed` is required. A missing field is a 422 (the schema forbids extra fields and `Field(...)` is required, as `denied_assets` is today). An **empty** list means the backend does not call (boundary doc). If the AI service nonetheless receives one it returns no passages and `sources_used: []`; it never reads empty as "no filter".
- The list is authoritative **only on a verified signed call**; the body hash is under the signature, so the list cannot be altered in flight. The tenant comes from the signed context, never from an entry.
- Scope changes meaning with the allow-list: `unknown` is never retrievable for anyone; `institutional` and `personal` are retrievable **only if in `allowed`**. A personal document therefore needs both its owner's entry and the backend's assigned `personal` scope (PR 7's dispatch scope); a bug on either side leaves it out.
- The recorder is unchanged: it records what the filtered query returned, so `sources_used` is a subset of `allowed` by construction. The AI service also asserts this before responding (a violation is a 500, never a response).

### 3.5 Large allow-lists: payload, limits, failure mode

Measured on the wire format above (compact JSON, UUID asset IDs; serialisation plus SHA-256 as the signer does, local Python):

| Eligible documents | Body bytes | gzip | Serialise + hash |
|---|---|---|---|
| 100 | 7,913 (7.7 KiB) | 2,398 | 0.3 ms |
| 1,000 | 79,013 (77 KiB) | 23,168 | 1.7 ms |
| 10,000 | 790,013 (772 KiB) | 228,597 | 12.8 ms |

Payload is not the binding constraint (the backend's default body limit is 1 MiB; the AI service sets none on these routes today, so M4-B must set one to match `MAX_ALLOWED`). The binding constraints are the **SQL cost of the membership test** and **recall under a selective filter on an approximate index**. The boundary doc requires M4 to measure both, and they cannot be settled by reading code, so they are a **gate, not a guess**: M4-B phase 0 (§7) runs them, and its numbers set the limits before any enforcement ships. This document does not claim latency or recall numbers it has not measured.

Until then:

- **Proposed limit `MAX_ALLOWED = 5,000` entries (about 395 KiB)**, a shared contract constant like `MAX_DENIED_ASSETS`, published in both contracts and tested together; neither side configures its own.
- **Failure mode: fail closed, visibly.** Over the limit the backend makes no AI call, answers `AI_UNAVAILABLE` (503), logs tenant, user and count (no content) and alerts. It **never truncates, samples or sends a partial list**: a partial list silently changes answers. The AI service refuses a longer list with 422.
- **Who is likely to hit it:** a student's list is their own documents (quota-bound at 50 uploads a day, 500 MiB) plus the tenant's reviewed institutional documents; the second set is the one that grows. If a real tenant approaches the cap the choice returns to the reviewer (D3): option (a) of the boundary doc for the institutional set only (a replicated eligibility index with an outbox, intersected with the per-request personal list), or a narrower query scope (course or document, G-19, deferred).
- **Query shape:** the membership test joins on `unnest`ed arrays or a `VALUES` list over `(asset_id, run_number, attempt)`, not an `IN (...)` of thousands of bound parameters; phase 0 compares plans. The HNSW iterative scan `query_dense` already uses (pgvector 0.8) is what keeps a selective filter from starving results; phase 0 shows recall@5 with and without the filter on the existing evaluation set (`tests/integration/test_retrieval_quality.py` in ai-service) at 100, 1,000, 5,000 and 10,000 entries, and p95 latency at the same sizes.

### 3.6 After generation: recheck and withhold whole

The check runs once the signed, nonce-consumed response has arrived, on **the triples in `sources_used`** (not assets, not only citations):

1. Every triple must be in `eligible_sources(actor, triples)` evaluated **now**, not in the request-time list. (Today: asset readable and not denied.)
2. Every citation's triple (§3.7) must be in `sources_used`, and `sources_used` must be a subset of the `allowed` this request sent.
3. Any failure, or a check that cannot run, raises `ANSWER_WITHHELD`: 503 with `Retry-After`; nothing stored, nothing partial returned. The answer is **never trimmed**: removing a citation would leave a dangling `[n]`, and a document may have shaped the text without being cited, which is why the check covers every source (M3-D ruling F).
4. A document used but not cited is covered because the recorder, not the model, produced `sources_used`.

**TOCTOU.** Two windows. (a) Between computing `allowed` and the retrieval query: milliseconds, same call, closed by the recheck. (b) Between the post-check and persisting or returning the answer: closed by doing the recheck and the answer's persistence in **one database transaction that takes `FOR SHARE` on the asset rows named in `sources_used`**, while every writer that revokes, deletes, lowers or reprocesses takes `FOR UPDATE` on the same asset row (the scope outbox's `enqueue` already does, `scope_assignments.py`). Either the revocation commits first and the recheck fails, or the answer commits first and is ordered before the revocation. An answer *stored after* a revocation is impossible; one delivered in the same instant as the revocation is ordered before it, which no design can prevent (the network follows the commit). For R1's stateless tutor nothing is stored, so the check runs after the last point at which the AI response could change; when M3-F stores messages, persistence joins that transaction (D7). The model call itself is never held inside a transaction.

### 3.7 Citations: validated against what was retrieved

Backend rules, applied before anything is returned (chat today, and the tutor turn of #66):

| Rule | Check | Failure |
|---|---|---|
| C1 | Each citation's `(document_id, run_number, attempt)` is in `sources_used` | withhold whole (`ANSWER_WITHHELD`) |
| C2 | Every `[n]` in the text has exactly one citation with `number == n`; no citation has a number absent from the text; numbers are distinct and within the passage cap (5) | `AI_UPSTREAM_ERROR` (502), nothing stored |
| C3 | `grounded == false` implies `citations == []` and the fixed not-covered text; `grounded == true` implies at least one citation | same |
| C4 | `source_id`, `title` and display name come **only** from the backend's own record of the asset; `page_start/page_end` come from the AI response, nullable, never guessed; ids and titles inside model text are never read | the field is null, or the citation fails |
| C5 | `excerpt` is the recorded passage text from the response, truncated to the contract's length limit, for cited passages only | |
| C6 | No `chunk_id`, storage path or tenant ID reaches the client | schema test |

The backend **cannot** verify that an excerpt matches the stored chunk byte for byte, because it does not hold chunks. It relies on the signed response (integrity, one response per nonce) and on the AI service's recorder discipline (`Evidence.__post_init__`, `check_grounded`). This is the same trust limit M3-D states; it is recorded here as decision D9, not closed.

### 3.8 Failure behaviour

| Situation | Behaviour | Client sees |
|---|---|---|
| Eligibility query fails or times out | No AI call | 503 `AI_UNAVAILABLE` |
| `allowed` empty | No AI call; fixed not-covered reply, `grounded: false` | 200, not covered |
| `allowed` over the limit | No AI call, alert | 503 `AI_UNAVAILABLE` |
| `allowed` missing at the AI service | Refused | 422 there; the backend sees `AI_UPSTREAM_ERROR` (502) |
| Response unsigned, wrong request or nonce, replayed, no `sources_used` | Withheld | 502 `AI_UPSTREAM_ERROR` (exists) |
| A source in `sources_used` no longer eligible, or outside the request's `allowed` | Whole answer withheld | 503 `ANSWER_WITHHELD`, `Retry-After` (existing code, wider check) |
| The recheck cannot run | Whole answer withheld | 503 `ANSWER_WITHHELD` |
| Citation not in `sources_used` | Whole answer withheld | 503 `ANSWER_WITHHELD` |
| Citation and `[n]` mismatch, or `grounded` inconsistent | Rejected | 502 `AI_UPSTREAM_ERROR` |
| AI service unreachable | Nothing stored | 503 `AI_UNAVAILABLE` (exists) |

### 3.9 State-combination matrix (self-review)

Each row is a test case in §8. "Allow-list" is whether the backend puts the triple in the caller's list; "retrieved" is the AI service's SQL result; "check passes" is the post-generation recheck. `current` means `(run, attempt)` equals the latest ready job's. **⚠ marks behaviour that is not true today** (read from code, §1-2).

| Tenant | Ownership / rights | State | Version | Revoked / deleted | In flight | Allow-list | Retrieved | Check passes |
|---|---|---|---|---|---|---|---|---|
| other | any | any | any | any | any | never (E1) | no (tenant SQL) | no |
| own | owner's own personal | ready | current | no | no | yes | yes (⚠ not until M4: scope `personal` is excluded) | yes |
| own | owner's own personal | ready | current | no | revoked mid-answer | yes at request | yes | **no**, withheld whole |
| own | another student's personal, published | ready | current | no | no | no (E4) | no | no (E4); ⚠ passes `may_read` today |
| own | another student's personal, unpublished | ready | current | no | no | no | no | no |
| own | institutional, reviewed for the tenant | ready | current | no | no | yes | yes | yes |
| own | institutional, not reviewed (student caller) | ready | current | no | no | no | ⚠ yes today when scope is `institutional` | no (E4); ⚠ staff pass `may_read` |
| own | any | quarantined / rejected | none | no | no | no (E5) | no | no |
| own | any | queued / processing, first run | none | no | no | no (E6) | no (no chunks) | no |
| own | institutional | failed after chunks were written | job not ready | no | no | no (E6) | ⚠ **yes today** | ⚠ passes today |
| own | institutional | ready, reprocess queued or processing | old triple | no | no | no (E6, deliberate) | ⚠ **yes today** (old chunks stay) | ⚠ passes today |
| own | institutional | ready, reprocess ready (run n+1) | old vs new | no | no | new triple only | new chunks only | old triple in `sources_used` is withheld |
| own | institutional | ready, retry attempt 2 after attempt 1 wrote | attempt 1 vs 2 | no | no | the ready job's attempt | ⚠ attempt 1 visible until 2 writes | ⚠ passes today |
| own | any | any | any | asset revoked | no | no (E3) | ⚠ only if the lowering was enqueued (institutional) | no |
| own | any | any | any | **source** revoked | no | no if D1 = yes | ⚠ **yes today** | ⚠ passes today |
| own | any | any | any | deleted | no | no (E3) | ⚠ until the AI delete exists (no route yet) | no |
| own | institutional | ready | current | lowered, outbox pending | request starts after commit | no | no (also in `denied_assets` today) | no |
| own | identical bytes, two owners | ready (both) | each its own | no | no | each owner's own only | own only | own only |

## 4. Threat analysis

| Threat | How it would happen | Mitigation (owner) | Residual |
|---|---|---|---|
| **Cross-tenant retrieval** | Another tenant's chunks match; a body names a foreign tenant or asset | Tenant from the signed context only; tenant predicate in SQL before ranking (AI, exists); backend evaluates E1 on its own rows; entries naming other tenants' assets match no chunk. Hardening: dispatch refuses an asset held elsewhere (§2.4, AI) | None found on `origin/main` |
| **Stale run** | Old chunks survive a failed or pending reprocess; a late attempt writes after a newer one | Fence (exists) for writes; the triple in `allowed` plus E6/E7 for reads (new) | None: the list is computed per request |
| **Revoked mid-answer** | Revocation commits after retrieval, before delivery | Recheck on `sources_used` triples with `FOR SHARE` in the persistence transaction (§3.6); covers cited and uncited sources | An answer delivered in the same instant as the commit is ordered before it |
| **Large lists** | A tenant with thousands of documents; truncated or oversized lists | Fixed limit, fail closed, never truncate, alert, measured before enforcement (§3.5) | Tenants over the cap are unavailable until D3 is decided: visible, not unsafe |
| **Replay** | A captured response replayed for another request; a captured request replayed with an older `allowed` | Response signature covers request id, nonce, body hash and window; one response per nonce (exists). Request replay is refused by the request-side replay store (exists); `allowed` is under the body hash, so an old list can't be paired with a new signature | Replaying an identical request inside the window yields an answer computed from the same list; the recheck still runs on current state |
| **Confused deputy, backend and AI service** | The AI service acts on a list it didn't derive; the backend signs a list computed for another user; a cached list is reused across users | The AI service treats `allowed` as authoritative only on a verified call and applies it with the signed tenant; the backend builds the list and the signed context from the same `AIActor` in one function; **no caching of `allowed` across requests or users**; `sources_used ⊆ allowed` asserted on both sides | A compromised AI service can lie in its response: outside what any envelope establishes (M3-D) |
| **TOCTOU, eligibility to generation** | State changes during a long model call | Per-request list, post-generation recheck on current state, row locks at persistence (§3.6). The model call is not inside a transaction | As above |
| **Duplicate documents under different owners** | Two students upload identical bytes; one's chunks surface in the other's answer, or one's delete or revoke affects the other | Eligibility is per **asset**, not per blob or hash; each owner's list holds only their asset; chunks are per asset (no reuse in R1). The reuse PR (17) must give a dependent document its own entry naming the chunk-owning asset and is blocked until M4-B supports `serves_asset_id` (D6) | None while reuse is not shipped |
| **Quarantine bypass** | An unscanned or rejected file reaches the index, or a later `rejected` rescan is ignored | The backend refuses dispatch before an accepted scan (exists, `pg_smoke/test_scanning.py`); E5 re-evaluates the verdict on every request, so a rejection after `ready` removes the entry at once; the AI side fetches only what a signed dispatch names (exists) | A rescan must set the verdict transactionally (M3-D) |
| **Publication mistaken for AI permission** | `may_read` is true for a classmate's published document, so "readable implies retrievable" would leak it | E4 separates AI use from reading (§2.3); a test pins that a published personal document is readable but never eligible for another user | |
| **Source revoked, assets live** | §2.1 | D1, E3 | Live today until decided |
| **Citation forgery** | The model writes a document id, title or page in its text | The prompt gives no ids (AI); citations come from the recorder; the backend takes `title` and `source_id` from its own rows and cross-checks citations against `sources_used` (§3.7) | Excerpt text is trusted from the signed response (D9) |
| **Oracle through errors** | `ANSWER_WITHHELD` versus not covered tells a caller about documents they can't read | `ANSWER_WITHHELD` is returned only after the caller's own request produced sources it may no longer use; the not-covered reply is one text for "no eligible document" and "nothing matched"; no document id is in any client error | |
| **Partial eligibility query** | A timeout returns part of a list | One statement in one transaction; any exception means no call | |

## 5. Contract changes

**(paired)** marks changes that need an ai-service PR with or before the backend change.

| # | Change | Where | Paired? | Compatibility |
|---|---|---|---|---|
| K1 | `RetrievingRequest.allowed: list[{asset_id, run_number, attempt}]`, required in the end state, at most `MAX_ALLOWED`; applies to chat, explain, generate-questions, retrieve and the tutor turn (#66) | AI `app/schemas/ai.py` | **paired** | Phase 2: AI accepts `allowed` **optional** and applies it when present, behaving as today when absent (the known G-05 state, no new window); phase 4: required |
| K2 | Enforcement of the triple in SQL; scope `personal` retrievable only with `allowed` | AI `pg_index.py`, `evidence.py`, `retrieval.py` | **paired** | |
| K3 | `sources_used ⊆ allowed` assertion; an empty `allowed` returns nothing | AI | **paired** | |
| K4 | The backend consumes `citations` and `grounded` (chat already returns them; the tutor turn in #66) | Backend `assistant_gateway.py` | no | Reads fields that exist; absence is a bad response |
| K5 | Dispatch refuses an asset held by another tenant | AI `raise_fence` | AI only | |
| K6 | `MAX_ALLOWED` published beside `MAX_DENIED_ASSETS` | both | **paired** | Neither side configures its own |
| K7 | Mobile contract: no new error code. `ANSWER_WITHHELD` and `AI_UNAVAILABLE` are used as defined; citations follow the boundary doc's schema when M3-F exposes them | `contracts/mobile/openapi.yaml` | no | M4 adds no student route; G-04 and G-05 close in `gaps.yaml` in the commit that closes their code |
| K8 | `denied_assets` removed once `allowed` is required and proven (D4) | both | **paired** | Own PR |
| K9 | The AI contract advertises support for `allowed`; the backend refuses to rely on it for an AI service that doesn't (as M3-D PR 8 does for scope) | both | **paired** | |

## 6. Decisions for the reviewer

| # | Decision | Recommendation |
|---|---|---|
| D1 | Does revoking a **source** withhold its documents (E3)? Today it does not (§2.1) | Yes: eligibility requires an active source, and the revoke handler enqueues a lowering per institutional asset in the same transaction. If no, record that source revocation means "stop new uploads" only |
| D2 | Allow-list alone, or allow-list intersected with scope? | Both: `unknown` is never retrievable even if listed (§3.4) |
| D3 | `MAX_ALLOWED` and the escalation path for a tenant over it | 5,000, pending phase-0 numbers; escalation to option (a) for the institutional set only |
| D4 | Keep `denied_assets` after `allowed` ships? | Remove in its own PR after proof; both are sent until then |
| D5 | Is "latest job `ready`, no newer run in another state" the right currency rule? | Yes: unavailable while reprocessing, as the boundary doc says; the "processing" note in the UI is M6's |
| D6 | May the reuse PR (17) ship before M4-B supports `serves_asset_id`? | No |
| D7 | Accept the `FOR SHARE` transaction at persistence (§3.6) on the hot path for stored answers? | Yes, once M3-F stores answers; R1's stateless tutor does the post-check only |
| D8 | Enable personal-document retrieval for the owner in R1? M3-D accepted that students can open their documents but no answer uses them until M4 | Yes, behind the allow-list: it is the point of the upload-to-tutor journey |
| D9 | Accept signed-response trust for excerpts (§3.7)? | Yes |

## 7. M4-B implementation plan

Each phase is its own PR or PRs, one concern per commit; `gaps.yaml` is updated in the commit that closes its code.

0. **Measurement (gate).** A script in `scripts/` populates PostgreSQL with pgvector at 100, 1,000, 5,000 and 10,000 eligible documents, runs the existing evaluation set with and without the membership filter, and reports payload, p50 and p95 latency and recall@5. The numbers go into §3.5 and set the limit; reviewer decision D3 here.
1. **Backend: the eligibility query.** `eligible_sources` and `eligible_allow_list` in the application layer with a SQL port covering E1-E7, plus an agreement test against a pure-Python `may_use` over every row of §3.9 (the pattern of `test_read_policy.py`). Settles D1.
2. **AI: accept and apply `allowed` (optional).** K1, K2, K3, K5, K6 in ai-service, with the matrix tests on real PostgreSQL on every retrieving path.
3. **Backend: send `allowed`, recheck on triples, consume citations.** The gateway sends the list and refuses an empty or oversize one; `_check_provenance` becomes the triple recheck; citations are validated (C1-C6). The strict-xfail tests of §8 turn to passes, with their markers removed in the same commit.
4. **AI: require `allowed`; backend: drop the compatibility path.** Then D4: remove `denied_assets`.
5. **Persistence lock** with M3-F's message store (D7).
6. **Gate:** boundary tests 6, 9, 10, 11 and 12 of `mobile-m0-boundary.md` run against the real stack; G-04, G-05 and G-31 move to `closed` in `gaps.yaml` with their proofs.

## 8. Tests as specification

Each test below is a **strict xfail** that fails today for the reason in its marker. When M4-B makes it pass, the strict marker turns the pass into a failure, so the marker is removed in the same commit as the behaviour. No existing test is changed or weakened. Tests that need a populated index run on real PostgreSQL, through the production query, never against an empty store or a stub.

The tests name the seams the design introduces. They are part of the specification: M4-B may rename a seam only by changing the test and this table in the same commit.

| Seam | Meaning |
|---|---|
| `app.application.content.eligibility.EligibilityFacts`, `may_use(facts, reader, run_number, attempt)` | The pure rule E1-E7 (§3.1). Phase 1 adds the SQL form and an agreement test over the same rows |
| `HttpAIAssistantGateway(eligible_allow_list=..., eligible_sources=...)` | The backend's two eligibility calls (§3.1, §3.6) |
| `assistant_gateway.MAX_ALLOWED` | The shared limit (§3.5) |
| `ChatAnswer.grounded`, `ChatAnswer.citations` | Validated citations returned by the gateway (§3.7) |
| ai-service `RetrievalFilter(allowed=frozenset[(asset_id, run, attempt)])`, required | The AI side's filter (§3.4) |

### Backend (`build-backend`)

`tests/infrastructure/ai/test_eligibility_spec.py` (gateway, no database):

| Test | Property |
|---|---|
| `test_the_call_carries_the_eligible_triples_sorted` | 2, 3, 4, 5 |
| `test_an_empty_allow_list_makes_no_call_and_is_the_not_covered_reply` | 3, boundary "empty set" |
| `test_an_allow_list_that_cannot_be_read_makes_no_call` | fail closed |
| `test_the_shared_allow_list_limit_is_never_exceeded_or_truncated` (5000, 5001) | large lists |
| `test_a_source_from_a_superseded_run_withholds_the_answer_though_the_asset_is_readable` | 5, 8 |
| `test_a_source_the_request_did_not_allow_withholds_the_answer_even_if_eligible_now` | 4, 8, confused deputy |
| `test_eligibility_is_evaluated_again_after_the_response_not_reused` | 6, 8, TOCTOU |
| `test_the_check_is_asked_about_exactly_the_triples_that_were_used` | 4, 8 |
| `test_an_eligibility_check_that_cannot_run_withholds_the_answer` | 8, fail closed |
| `test_a_citation_naming_a_version_that_was_not_retrieved_withholds_the_answer` | 7 (C1) |
| `test_a_marker_with_no_citation_is_a_broken_response` | 7 (C2) |
| `test_a_citation_the_text_never_uses_is_a_broken_response` | 7 (C2) |
| `test_a_not_grounded_answer_with_citations_is_a_broken_response` | 7 (C3) |
| `test_a_grounded_answer_with_no_citation_is_a_broken_response` | 7 (C3) |
| `test_the_answer_carries_validated_citations_and_never_an_internal_id` | 7 (C4, C6) |

`tests/integration/content/test_eligibility_spec.py`:

| Test | Property |
|---|---|
| `test_the_eligibility_rule_over_every_state_combination` (24 rows: current, older run, older attempt, retry, reprocess queued/processing, failed with chunks, no job, quarantined, rejected, no verdict, revoked, deleted, source revoked or unknown, another tenant, not reviewed, AI use not permitted, unclassified, unknown class, the owner's personal, quarantined personal, another student's personal unpublished and **published**) | 1-6 |
| `test_a_fact_the_rule_does_not_know_is_not_eligible` | fail closed |
| `test_a_document_whose_source_was_revoked_is_not_readable_for_a_provenance_check` | 6, **D1, runs the production `readable_sources` on a populated world** |

### ai-service (`tests/integration/test_eligibility_spec.py`, real PostgreSQL, a populated index)

| Test | Property |
|---|---|
| `test_an_allow_list_is_required_never_defaulted` | missing never means unfiltered |
| `test_an_empty_allow_list_returns_nothing_even_for_an_institutional_document` | 3 |
| `test_only_the_listed_document_is_returned` | 2, 3 |
| `test_a_listing_for_another_run_or_attempt_matches_no_chunk` (2 cases) | 4, 5 |
| `test_a_personal_document_is_returned_only_when_listed` | G-05 allow-list for personal documents |
| `test_a_listed_document_without_a_retrievable_scope_is_never_returned` (unknown, no row) | D2 |
| `test_a_listed_asset_of_another_tenant_matches_nothing` | 1 |
| `test_a_denied_document_stays_out_even_when_listed` | 6, migration period |
| `test_a_dispatch_for_an_asset_another_tenant_holds_is_refused` | 1, hardening (§2.4) |
| `test_every_retrieving_request_requires_a_bounded_allow_list` | contract K1, K6 |

### Not yet specified as tests, and why

- **Latency and recall at 100 / 1,000 / 5,000 / 10,000 entries** are measurements, not assertions (phase 0).
- **The SQL form agrees with `may_use`** needs the SQL, which does not exist; it is the first test of phase 1.
- **Persistence under `FOR SHARE`** needs the M3-F message store (D7); the race test is written with that store.
- **End-to-end boundary tests 6, 9, 10, 11, 12** (`mobile-m0-boundary.md`) need the real stack and arrive with phase 6.

### Running them

Backend, in the CI image (`pytest` on the two files plus the drift gate, which must stay green):

```text
pytest tests/infrastructure/ai/test_eligibility_spec.py tests/integration/content/test_eligibility_spec.py tests/integration/test_mobile_contract_drift.py -rx
```

ai-service, with `DATABASE_URL` pointing at pgvector PostgreSQL as in its CI: `pytest tests/integration/test_eligibility_spec.py -rx`.
