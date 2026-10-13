# Phase 1 — Milestone 5: Completion Report

**Milestone:** M5 — AI Intelligence Contract
**Status:** Complete (2026-10-10)
**Governing documents:** `docs/PHASE_1_PLAN.md` §22 M5; `docs/phase1-m5-ai-contracts.md` (rulings R1–R3, acceptance M5-1 … M5-6)

## 1. Verdict and evidence

Every M5 acceptance row passes. The AI operations BUILD uses now have typed, validated contracts on both sides of the signed boundary. Neither service trusts the other's output shape.

| Row | Check | Evidence |
|---|---|---|
| M5-1 | Every `/v1/ai/*` route publishes a typed request and `data` model | ai-service `tests/contracts/test_ai_contract.py`: the route set is exactly the contracted one; bodies forbid extra and identity fields; `data` is a named model |
| M5-2 | Generated questions obey the rules; invalid output is discarded, never repaired | ai-service `test_structured_questions.py` (10 invalid shapes, true_false, overflow, non-JSON); backend `test_assistant_gateway.py` re-checks each item independently |
| M5-3 | Structured questions end to end | boundary: `/ai/generate-questions` returns mcq and true_false questions in the backend's shape |
| M5-4 | A submitted attempt updates memory, for that student only | boundary: course → topic → questions → published assessment over HTTP. The student answers one right and one wrong and submits; `GET /ai/memory` shows the topic at 0.55 after 2 attempts; another user and another tenant see nothing |
| M5-5 | Memory routes refuse identity in the body and the wrong permission | boundary: 422, 403 and 401 at AI-service |
| M5-6 | No regressions | see the gates below |

| Gate | Result |
|---|---|
| Real two-service gate, fresh PostgreSQL 17 + Redis 8 | **151 passed**, then C11 with Redis stopped: **3 passed**; exit 0 |
| Backend full suite | 1081 passed, 89 skipped, 0 failed |
| ai-service full suite, fresh PostgreSQL 17 + Redis 8 (migrated through `a7c2e5d10b41`) | 801 passed, 3 skipped, 2 failed — the two pre-existing failures recorded in the M4 report |
| ai-service memory store against real PostgreSQL | 4 passed, including 10 concurrent upserts of one topic leaving one row with 10 attempts |

## 2. What M5 delivered

**ai-service**
- Structured question generation:
  - `LLMProvider.generate_json`, with OpenAI JSON mode and well-formed, labelled deterministic answers;
  - a validating `StructuredQuestionGenerator`;
  - `difficulty` and `question_type` on the request;
  - typed chat, explain and question responses (`7fdfb53`).
- `learning_memory` is unique per (tenant, user, topic). The migration refuses rather than merging duplicates (`d77e8e4`).
- Signed `/v1/ai/memory/query` (`ai.use`) and `/v1/ai/memory/upsert` (`assessment.attempt.submit`) (`eab8346`):
  - one atomic `INSERT … ON CONFLICT` per observation;
  - mastery clamped to [0, 1].
- Typed retrieve, tree and read responses, and the OpenAPI contract test (`93d93a3`).
  - **Fix:** real retrieval citations had no `text` field. With a real index, chat would have run with empty context.

**build-backend**
- Contract design with the rulings (`1b3c95e`).
- Structured generated questions, re-checked by the backend's own question rules; never persisted (`3e8c06c`).
- Memory gateway and `GET /ai/memory` (`2ea2136`).
- Submitted attempts report their outcomes to memory after commit (`d80d33b`):
  - one observation per answered question, by topic title;
  - best effort, so an AI-service failure never fails a submission.
- Real-stack M5 tests (`5c5260e`).
- **Fix found by the gate:** the combined topology's PostgreSQL healthcheck now uses TCP. A socket check can pass during the image's first-start init server, and `db-init` once failed that way (`252bea7`).

## 3. Decisions taken inside the rulings

| Item | Decision |
|---|---|
| Memory topic key | The question's topic **title** (or its id when the topic has no title). Titles read well in prompts; a renamed topic starts a new memory row. |
| Mastery model | Starts at 0.5; +0.1 correct, −0.05 incorrect (the existing `LearningReward`), clamped to [0, 1]. |
| Unanswered questions | Not reported: no evidence either way. |
| Reporting timing | FastAPI background task after the response, so after the submission has committed. |
| Retrieve, tree, read | Contracted at AI-service, **not proxied**: there is no real index in Phase 1 (plan §13). |

## 4. Not in M5

- Saving generated questions (R2). The lecturer saves reviewed ones through the assessment API.
- Consolidating the two model stacks (`services/ai` and `core/models`). These contracts don't need it.
- Re-sending memory when a report fails. Reports are idempotent per attempt only if not retried. A safe resend needs an attempt-level marker, recorded for Phase 2.

## 5. Handover to M6

The production gate (M6) runs this same stack and adds the deliberate-attack list (plan §22 M6), production configuration and the hardening items carried from M3 and M4. Among those:
- the silent in-memory idempotency fallback in ai-service;
- the unsigned-response residual risk (E.4);
- the hosted gate;
- the Redis timeouts.
