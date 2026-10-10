# Phase 1 — Milestone 5: AI Intelligence Contracts

**Status:** Rulings accepted 2026-10-10; implemented in M5.
**Builds on:** `docs/phase1-m3-boundary-design.md` (signature, context, permissions); `ai-service/docs/phase1-m4-completion-report.md` (domain boundary).

## 1. Rulings

| # | Question | Ruling |
|---|---|---|
| R1 | Namespace | **Keep `/v1/ai/*`.** New operations go under the same signed prefix. The plan's `/internal/v1/...` paths were examples. |
| R2 | Generated questions | **Structured, not persisted.** AI-service returns questions in the backend's question shape. The backend validates them against its own question rules and returns them to the lecturer to review. Nothing is saved. |
| R3 | Learning memory | **Backend-driven upsert.** The backend reports graded outcomes to AI-service; AI-service owns the memory store; both expose a scoped query. |

## 2. Contract rules (all operations)

- **Transport and identity:** BUILD Service Signature v1. The user context names tenant and user. Each route declares one permission and refuses a context without it (403). Bodies forbid unknown fields and never carry identity (422).
- **Response envelope:** `{"success": true, "data": <typed>, "message": str}`. `data` has a declared Pydantic model on every route, so the OpenAPI document is the machine-readable contract.
- **Backend side:** it re-validates every AI response (it never trusts AI output shape) and maps it to its own response. An unusable answer is 502 without detail; AI-service unreachable is 503.

## 3. Operations

| AI-service route | Permission | Request | `data` |
|---|---|---|---|
| `POST /v1/ai/chat` | `ai.use` | `message` (1–4000) | `answer: str`, `context_used: [{text}]`, `memory_used: str` |
| `POST /v1/ai/explain` | `ai.use` | `subject` (1–4000) | `explanation: str` |
| `POST /v1/ai/generate-questions` | `ai.questions.generate` | `topic` (1–4000), `count` (1–50, default 5), `difficulty` (`easy`/`medium`/`hard`, default `medium`), `question_type` (`mcq`/`true_false`, default `mcq`) | `questions: [GeneratedQuestion]`, `discarded: int` |
| `POST /v1/ai/memory/query` | `ai.use` | `topics` (optional, ≤ 50, each 1–255) | `items: [{topic, mastery_score, attempts}]` |
| `POST /v1/ai/memory/upsert` | `assessment.attempt.submit` | `observations: [{topic (1–255), correct: bool}]` (1–200) | `items: [{topic, mastery_score, attempts}]` (the touched topics) |
| `POST /v1/ai/retrieve`, `/v1/ai/tree/generate`, `/v1/ai/read/start` | `ai.use` | unchanged from M3 | unchanged; **not proxied** by the backend in Phase 1 (retrieval has no real index, plan §13) |

**GeneratedQuestion** follows the backend's `CreateQuestionRequest`, without the course placement the lecturer chooses later:

```text
question_type: "mcq" | "true_false"
prompt: str (non-empty)
options: [{text: str (non-empty), is_correct: bool}]
         mcq: 2–6 options; true_false: exactly "True" and "False"
         exactly one is_correct
explanation: str | null
difficulty: "easy" | "medium" | "hard"
```

The model is asked for JSON. AI-service drops any item that breaks these rules and reports how many in `discarded`. It never repairs or invents an item.

**Memory semantics.**
- Rows are keyed by (context tenant, context user, topic). Mastery starts at 0.5.
- Each observation moves it +0.1 if correct and −0.05 if not, clamped to [0, 1]. `attempts` counts observations.
- Query and upsert read and write only the signed user's rows in the signed tenant (C29 style).

## 4. Backend endpoints

| Endpoint | Permission | Forwards to |
|---|---|---|
| `POST /ai/chat`, `/ai/explain` | `ai.use` | unchanged (M3-11) |
| `POST /ai/generate-questions` | `ai.questions.generate` | `difficulty` and `question_type` added; `data = {questions: [...], discarded}`. Each item is re-checked against the backend's question rules; failures count as discarded. |
| `GET /ai/memory` | `ai.use` | `/v1/ai/memory/query`: the member's own mastery in the current tenant |
| *(no endpoint)* attempt submission | `assessment.attempt.submit` (already checked) | After a graded attempt commits, the backend sends one observation per answered question, using the question's topic title (or its id when there is no title), to `/v1/ai/memory/upsert`. This is **best effort**: a failure is logged and never fails the submission, because memory is derived data the backend can resend. |

The same per-user AI rate limit applies to every AI endpoint. Memory upserts from submissions are bounded by attempts, so they are not rate limited.

## 5. Out of scope for M5

- **Question persistence (R2):** the lecturer saves a reviewed question through the existing assessment API.
- **Retrieval, tree and read through the backend:** they need a real index (Phase 2).
- **Consolidating `services/ai` and `core/models`** model stacks. It is not needed for these contracts; recorded as a follow-up.

## 6. Acceptance

| # | Check | Where |
|---|---|---|
| M5-1 | Every `/v1/ai/*` route has a typed request and `data` model in OpenAPI | AI contract test |
| M5-2 | Generated questions satisfy the GeneratedQuestion rules; invalid model output is discarded and counted, never repaired | AI unit; backend unit |
| M5-3 | Backend `/ai/generate-questions` returns structured questions end to end | **real** (boundary) |
| M5-4 | A submitted attempt updates the student's memory; `GET /ai/memory` shows it; another user or tenant sees none of it | **real** (boundary) |
| M5-5 | The memory routes refuse identity in the body (422) and a missing permission (403) | **real** (boundary) |
| M5-6 | No regressions: both suites, postgres-gate, boundary gate | local |
