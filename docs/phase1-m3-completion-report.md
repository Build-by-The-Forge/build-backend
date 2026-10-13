# Phase 1 — Milestone 3: Completion Report

**Milestone:** M3 — Backend → AI Security Boundary (build-backend + ai-service)
**Status:** Complete on the local real-service gate (2026-10-10). The hosted `boundary-gate` is written but has not yet run (§1, §6).
**Governing documents:** `docs/PHASE_1_PLAN.md` (Revision 1, §22), `docs/phase1-m3-boundary-design.md` (locked; Part C acceptance matrix, Part E rulings), `docs/BUILD_MASTER_PRD.md`

## 1. Verdict and evidence

Every Part C row passes. The real rows (C2–C25, C27, C29) passed against both services running together in the combined topology, with nothing mocked. Branches:

- build-backend `feat/learning-content`: `f3aacf0` … `a2fd636`, plus this report.
- ai-service `feat/m3-boundary`: `5c1edb4` … `1ee9778`.

| Gate | Result |
|---|---|
| Real two-service boundary gate: `scripts/m3_boundary_gate.sh`, fresh volumes, PostgreSQL 17.10 + Redis 8.10.2, least-privilege roles, at `a2fd636` / `1ee9778` | **130 passed**, then C11 with Redis stopped: **3 passed**; exit 0. Run twice from empty volumes, both green. |
| Backend full suite (SQLite) | 1051 passed, 89 skipped, 0 failed (the skips are the real-Redis and real-AI tests, which run in the gates). |
| Backend `postgres-gate` (local mirror of CI), fresh PostgreSQL 17 + Redis 8 | empty → head: pass; single head: pass; latest-migration round trip: pass; schema drift: none; `pg_smoke` 20 passed, 1 xfail (known `device_id` defect from M2); real Redis: counter store 7, service auth 30, signed callbacks + reconcile 52 — all passed. |
| ai-service full suite, fresh PostgreSQL 17 + Redis 8 | 785 passed, 3 skipped, **2 failed, 1 error — all pre-existing**: the same three appear on the M3-09 head `f409269` with the same environment (§7). No regression. |
| Hosted `boundary-gate` (GitHub Actions) | **Not run.** The workflow exists (`ea2875f`). It needs the `AI_SERVICE_READ_TOKEN` secret and a push. Per ruling E.5, the local gate above is the M3 exit gate until a hosted run passes. |

## 2. What the final M3 batch delivered (M3-10 → M3-16)

Earlier steps (M3-01 → M3-09) are covered by their own reviews. This batch:

**ai-service: user routes closed (M3-10)**
- A string tenant and user request scope, set only from the verified context. Memory, retrieval and intake fail closed without a scope. Retrieval's `or "default"` tenant is gone (`a1c2932`).
- Legacy user routes are off unless `LEGACY_USER_ROUTES_ENABLED`: they cover `/auth`, `/exams`, `/api/v1/exams`, the exam AI routes, fusion exam and the exam websocket. The flag is refused outside development and needs a real `JWT_SECRET` (`3ce64ff`).
- `MODEL_PROVIDER` selects the model: `openai` (default) or `deterministic`, an offline stand-in. The stand-in is refused in staging/production (`f17d5c2`).
- Signed-only POST JSON routes under `/v1/ai/`: chat, explain, generate-questions, retrieve, tree/generate and read/start (`aca1922`).
  - Each route declares one permission.
  - A user context is required, and its tenant and user become the scope.
  - Chat memory is keyed by the context user.
  - Bodies forbid identity and extra fields.
  - Inputs are bounded.
  - The old `/api/v1/ai/*` mounts are removed.
- `TenantMiddleware` and the `X-School-ID` tenant are deleted (`75e0d2b`).

**build-backend: AI endpoints (M3-11)**
- New permissions: `ai.use` for every role, and `ai.questions.generate` for lecturer and above (`1718999`).
- Per-user AI rate limits: 30/min, and 10/min for question generation, which also counts towards the 30 (`461e05b`).
- A signed `AIAssistantGateway`: the context carries only the checked permission, redirects are not followed, and AI-service error detail never reaches the client (`ca75582`).
- `POST /ai/chat`, `/ai/explain` and `/ai/generate-questions` (`819dcec`):
  - Each request runs authentication → tenant → membership → permission → input bounds → rate limit → signed call.
  - Responses are mapped to backend shapes; failures become 503 (unreachable) or 502 (anything else).
  - Nothing is persisted.

**Topology and roles (M3-12, M3-13)**
- `python -m app.worker` worker entry point in ai-service (`1ee9778`).
- `deploy/compose.m3.yml` (`9343fe5`):
  - postgres 17, redis 8, idempotent `db-init`;
  - `backend-migrate` and `ai-migrate`, each run as its owner role;
  - `backend`, published on 127.0.0.1 only;
  - `ai-service`, unpublished;
  - `ai-worker`.
- `deploy/db-init/init-roles.sql` creates `build_backend_owner/app` and `build_ai_owner/app`:
  - Default privileges and re-grants by owner.
  - PUBLIC loses CREATE on `public` and CONNECT on the database.
  - The superuser is used only by db-init.
- A backend `.dockerignore`: before it, `COPY . .` put `.env`, local databases and the virtualenv into the image.

**Real boundary suite and gates (M3-14, M3-15)**
- `boundary/` (133 tests) runs inside the topology against both real services, the worker, the real DB roles and Redis (`9dc6d33`):
  - Setup uses product paths: the provisioning CLI, then invite → register → verify → accept, with codes read from the development outbox.
  - Requests are signed by an independent implementation in the suite.
- `scripts/m3_boundary_gate.sh` is the one command. It generates random secrets, starts from fresh volumes, runs the suite, then C11 with Redis stopped, and tears down.
- `.github/workflows/boundary-gate.yml` checks out both repositories and runs the script (`ea2875f`).
- `.gitattributes` keeps shell scripts LF (`a2fd636`).

## 3. Acceptance matrix (Part C)

| # | Invariant | Evidence |
|---|---|---|
| C1 | Identical signatures | Test vector A.7 + negative vectors, unit, both repos (M3-02) |
| C2 | Backend identity authentic | boundary: every `/v1/ai/*` route and dispatch accept a valid signed request |
| C3 | Body cannot be altered | boundary: one byte changed → 401, at AI-service and at the backend callback |
| C4 | Context cannot be altered | boundary: `tenant_id`, `user_id`, `permissions` swapped after signing → 401 |
| C5 | Query cannot be altered | boundary: query added → 401; signed query changed in case → 401 |
| C6 | Sender cannot be swapped | boundary: `X-BUILD-Service: ai-service` towards AI-service → 401 |
| C7 | Directional secrets | boundary: other direction's secret → 401 at AI-service and at the backend |
| C8 | Stale requests refused | boundary: ±61 s and −1 h → 401 |
| C9 | Replays refused | boundary: second identical request → 401, at both receivers |
| C10 | Malformed headers/context refused | boundary: each header missing, non-UUIDv4 request id, bad base64url, **validly signed** non-canonical JSON and unknown field → 401 |
| C11 | Replay store fails closed | boundary (Redis stopped): AI-service 503, backend callback 503; unsigned still 401 |
| C12 | No static Bearer | boundary: Bearer (dev keys, real secrets, a JWT) → 401 on every AI route, dispatch, task status and the callback |
| C13 | AI user routes closed | boundary: no auth / end-user JWT / `X-School-ID` → 401 on all six routes; legacy and old paths 404/405 |
| C14 | Context narrows only | boundary: missing route permission → 403 (six routes + dispatch); system context on a user route → 403 |
| C15 | Tenant authoritative end to end | boundary: backend `/ai/chat` with spoofed `X-Tenant-ID`/`X-School-ID`/`X-BUILD-Context` is served for the membership's tenant (retrieval names it); a slug without membership → 403 |
| C16 | Tenant A cannot operate B's job | boundary: get/dispatch/retry/reconcile/reprocess from B → 404, job unchanged; backend integration suite |
| C17 | Users cannot fabricate AI state | boundary: start/progress/complete/fail → 404/405; backend integration suite |
| C18 | Callback destination fixed | boundary: dispatch body with `callback_url` → 422; the worker's callbacks reach the backend only through `BACKEND_CALLBACK_URL`; redirect refusal over real sockets (ai-service, M3-07) |
| C19 | Callback cannot cross tenants | boundary: context tenant ≠ job tenant → 404 |
| C20 | Callback cannot create state | boundary: unknown job → 404 |
| C21 | No regression or duplication | boundary: the worker's own callback replayed → `duplicate`; same `event_id`, other content → 409 `EVENT_CONFLICT`; other attempt/run/task → `stale`; failed → extracted/ready → 409; backend unit + integration for the full B.3 table |
| C22 | Ingestion path (re-scoped in M3-08) | boundary: backend dispatch → AI-service → worker → signed callback → job `failed`, `INGESTION_PIPELINE_UNAVAILABLE`; `ready` unreachable without stage evidence. A successful ingestion awaits the real pipeline (plan §13). |
| C23 | Status reconciliation | boundary: reconcile reaches AI-service's recorded outcome; task status for another tenant → 404 |
| C24 | AI-service cannot write backend tables | boundary as `build_ai_app`: `SELECT users`, `UPDATE memberships`, `INSERT INTO questions`, `tenants`, `content_ingestion_jobs`, `security_events`, `alembic_version`, `CREATE TABLE` → permission denied |
| C25 | AI-service can use its own tables | boundary as `build_ai_app`: read/write/delete `learning_memory`, `session_memory` |
| C26 | Secrets enforced | unit, both repos (M3-05); plus the legacy-flag and model-provider rules (M3-10) |
| C27 | User-facing AI flow | boundary: client → backend `/ai/chat`, `/ai/explain`, `/ai/generate-questions` → AI-service → mapped response, retrieval scoped to the member's tenant; student → 403 on question generation |
| C28 | No regressions | §1: backend suite, postgres-gate, ai-service suite (pre-existing failures only) |
| C29 | Body cannot override identity | boundary: `tenant_id`/`user_id` in the body → 422 on all six AI routes, dispatch and the three backend endpoints. Memory seeded in `learning_memory` for the user, the same user id in another tenant, and another user: chat returns only the signed user's row in the signed tenant. |

## 4. Deviations from the design (all deliberate, none weakening it)

1. **C18 rejects instead of ignoring.** A `callback_url` in the dispatch body is 422 (forbidden field), not silently ignored. This is stricter, and consistent with B.4's rule that bodies reject unknown fields.
2. **C22 re-scoped** (decision during M3-08): with no real pipeline in Phase 1, the full signed path is proven on the failure outcome.
3. **`MODEL_PROVIDER=deterministic`** is new. It lets C27/C29 run without a provider key. It is development/testing only and refused in staging/production. It answers with a prompt digest, never pretend tutoring.
4. **`ai-worker` service and `boundary-tests` service** were added to the B.6 topology. The design's list had no way to run the worker. The test service runs only under the `gate` profile.
5. **Tree and read routes are POST JSON** (`/v1/ai/tree/generate`, `/v1/ai/read/start`). The old read route was a GET with a body. Neither has a client path until M5 (B.4).
6. **Rate-limit values** (30/min AI, 10/min question generation) and the **502/503 mapping** were not fixed by the design; they are documented here and in the code.

## 5. Residual risks (accepted)

- **E.4 Unsigned responses** remain until M6 TLS/mTLS.
- **The backend `context` field** in `/ai/chat` returns retrieval excerpts, tenant-scoped. Their exact content contract is M5's.
- **Task records have no cross-replica lock** (one consumer per task). This is unchanged from M3-09.
- **Replay-store timeouts** stay at their defaults (backend 0.5 s, AI 1.0 s) until deployment measurements exist.

## 6. Not done in M3 (explicit)

- **Hosted `boundary-gate` run.** It needs `AI_SERVICE_READ_TOKEN` (fine-grained, contents:read on `Build-by-The-Forge/ai-service`) and a push. Until it passes, E.5's fallback applies: the documented local gate is the exit gate.
- **Legacy code deletion** (`/auth`, exams, websocket, integer `school_id`, AI `users`/`schools`/`questions` models) is M4. In M3 it is unmounted only.

## 7. Known issues (pre-existing; outside M3)

| Issue | Status |
|---|---|
| ai-service `tests/unit/test_service_stubs.py::test_image_ocr_providers_return_data` | Fails on the pre-M3 baseline too. Unchanged. |
| ai-service `test_idempotency_store.py::test_redis_idempotency_store_operation_and_duplicates` | Fails only when `REDIS_URL` points at a live Redis and the whole suite runs; passes alone. Reproduced identically on the M3-09 head. Likely cause: `app/core/redis.py` keeps one module-global asyncio client, reused across test event loops; failures fall back to an in-memory store, so the two calls disagree. **Candidate explanation for the unidentified Redis-backed failure seen in the M3-09 gate**, not yet proven. |
| ai-service `tests/integration/test_auth_exam.py` (legacy login) | Error on a fresh database: its fixture inserts a `users` row with `school_id=1` and no `schools` row (FK violation). Legacy route; M4 deletes it. |
| backend lint | Local ruff 0.16.5 reports 47 errors already present on the base; CI's ruff version differs (known since M2). New files lint clean. |
| ai-service has two model stacks | `services/ai` (`LLMProvider`, used by the orchestrator) and `core/models` (gateway, used by agents). Consolidation belongs to M5's AI contract work. |
| `learning_memory` is read but never written | Chat only reads memory; writes arrive with M5's memory contract. |

## 8. Handover

- **Pushes (user):** build-backend `feat/learning-content` (13 commits ahead of origin, from `a22f193`) and ai-service `feat/m3-boundary` (10 ahead, from `4afa71e`); both include the unpushed M3-09 commits.
- **M4 (legacy removal)** starts from a codebase where the legacy routes are unreachable by default and the paths M3 touched use a string tenant. M4 deletes the legacy routes, models and integer `school_id`. It also removes `JWT_SECRET` and `LEGACY_USER_ROUTES_ENABLED`, and fixes or deletes the legacy test above.
- **M5 (AI contracts)** formalises `/v1/ai/*` request/response schemas and memory writes, consolidates the two model stacks, and decides what retrieval/tree/read expose through the backend.
- **M6** runs the hosted boundary gate as the production gate, adds TLS/mTLS (closing E.4) and tunes the Redis timeouts from deployment measurements.
