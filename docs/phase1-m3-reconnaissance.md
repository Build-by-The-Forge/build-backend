# Phase 1 — Milestone 3: Backend ↔ AI-Service Boundary — Reconnaissance

**Date:** 2026-10-04 · **Scope:** build-backend `37c60ad`, ai-service `a2a6042` · **Changes made:** none (read-only)
**Governing:** `docs/PHASE_1_PLAN.md` §19.1–19.4, §21, M3; M1 audit (`docs/phase1-m1-identity-audit.md`) findings X-1…X-6, A-1…A-6; M2 handover (`docs/phase1-m2-completion-report.md` §8).

The question M3 must answer: *can an AI request be proven to come from the backend, unmodified and not replayed, carrying a tenant/user context AI-service cannot forge or substitute; and can AI-service results reach the backend without becoming unauthorized business state?* Today the answer is no in both directions, and several problems sit on the backend side of the boundary rather than in the protocol.

## 1. The boundary as it is

```text
                       BACKEND → AI (only one path exists)
backend  POST /content/jobs/{id}/dispatch   (tenant user, content.job.manage)
   │      job loaded by id — no tenant check
   │      callback_url taken from the request body
   ▼
HttpAIServiceIngestionGateway
   │  Authorization: Bearer <AI_SERVICE_API_KEY>      ← static, default "build-ai-dev-secret-key"
   │  X-Tenant-ID, X-Idempotency-Key (header), X-Correlation-ID
   │  body: job/asset/source ids, tenant_id, storage_uri, callback_url — no idempotency_key
   ▼
ai-service  POST /v1/ingest/dispatch   (also mounted at /api/v1/ingest/dispatch)
   │  requires X-Service-Identity / X-Timestamp / X-Service-Signature  → backend's request: 401
   │  requires idempotency_key in the body                            → backend's request: 422
   │  tenant: int(payload.tenant_id); a UUID is silently dropped → intake later refuses (fail closed)
   ▼
                       AI → BACKEND
ai-service CallbackDispatcher → POST <callback_url>   (any http/https host accepted)
   │  X-Build-Signature = HMAC(SERVICE_AUTH_SECRET, "{ts}." + canonical_json), X-Timestamp
   ▼
backend  POST /content/ingestion/callbacks
      accepts HMAC(ai_service_webhook_secret, body)  → never matches AI's signature (X-3)
      OR "Authorization: Bearer <AI_SERVICE_API_KEY>" (X-4)
      then: event_id dedupe, stale run/attempt check, state-machine transitions (good)

                       USER → AI (no backend involvement)
client → ai-service /api/v1/ai/{chat,explain,generate-questions,retrieve,tree,read}  no auth
client → ai-service /auth/login → AI JWT → /exams, /api/v1/ai/exam/*, fusion exam
client → ai-service ws /ws/exam/{id}                                                no auth
TenantMiddleware: tenant = int(X-School-ID header) for every request
```

The backend never calls a user-facing AI operation, never forwards user identity, and never forwards end-user tokens (it sends only its static API key) — so there is no end-user token leakage today, but there is also no trusted context.

## 2. M1 findings re-verified

| ID | Finding | Status now | Evidence |
|---|---|---|---|
| X-1 | Backend sends static Bearer; AI requires HMAC headers → 401 | **Unchanged** | backend `infrastructure/content/ai_gateway.py:92-97`; ai `core/service_auth.py:42-50` |
| X-2 | Backend calls `GET /v1/ingest/tasks/{id}` and `POST …/cancel`; routes do not exist → 404 | **Unchanged** | backend `ai_gateway.py:181,219`; ai `api/v1/ingest.py` (only `/dispatch`) |
| X-3 | Callback signatures can never verify (different material and secret) | **Unchanged** | ai `core/callbacks/signer.py:31-39`; backend `ai_gateway.py:42-57` |
| X-4 | Backend callback also accepts static Bearer, no timestamp/replay | **Unchanged** | backend `api/content/jobs.py:402-405` |
| X-5 | AI ingest drops UUID tenants (`int()` swallowed) | **Unchanged**, fails closed: intake raises `DocumentTenantMissingError` | ai `api/v1/ingest.py:38-42`, `core/documents/intake.py:67-69` |
| X-6 | AI uses one `SERVICE_AUTH_SECRET` both directions | **Unchanged** | ai `core/callbacks/dispatcher.py:102`, `core/service_auth.py:82` |
| A-1 | `chat`, `explain`, `generate-questions`, `retrieve`, `tree` unauthenticated | **Unchanged, plus `read/start`** | ai `api/v1/ai/*.py`, `api/v1/router.py:23-28` |
| A-2 | Tenant from raw `X-School-ID` for every request | **Unchanged** | ai `core/middleware/tenant.py:9-12` |
| A-3 | Exam WebSocket unauthenticated | **Unchanged** | ai `api/v1/ws/exam_ws.py:57` |
| A-4 | AI authenticates users itself (`/auth/*`, legacy JWT, `JWT_SECRET="dev-secret"`) | **Unchanged**; its `users`/`questions` models collide with backend tables (N-10) | ai `auth/routes.py`, `core/config.py:48`, `db/models/user.py`, `db/models/question_bank.py` |
| A-5 | Tenant is an `int` ContextVar bridged with `str()` | **Unchanged** | ai `core/tenant.py:3`, `core/documents/intake.py:67` |
| A-6 | `TokenVerifier` dead code | Not re-checked (M4 scope) | — |

## 3. New findings

| ID | Severity | Finding | Evidence |
|---|---|---|---|
| N-1 | **High** | **Cross-tenant job control.** Every ingestion-job mutation (`dispatch`, `start`, `progress`, `complete`, `fail`, `retry`, `reprocess`) loads the job/asset by id and never compares its tenant with the caller's tenant context. A `content.job.manage` holder in tenant A can drive tenant B's jobs. | backend `api/content/jobs.py:172-382`; `application/content/job_handlers.py:263-274` |
| N-2 | **High** | **Caller-chosen callback URL → SSRF / exfiltration.** `dispatch` passes `callback_url` from the request body to AI-service, which validates only scheme and host and POSTs signed job events there (any host, including internal ones). | backend `jobs.py:362`, `job_handlers.py:276`; ai `core/callbacks/dispatcher.py:109-116` |
| N-3 | High | **Users can fabricate AI pipeline results.** `start`/`progress`/`complete`/`fail` let a tenant user move a job through extracted/chunked/indexed/completed — states that only AI-service processing should produce — so content can be marked indexed without any processing. | backend `jobs.py:172-287` |
| N-4 | High | **Dispatch contract mismatch.** AI requires `idempotency_key` in the body; the backend sends it only as a header → 422 even with valid auth. | ai `schemas/ingest.py:47`; backend `ai_gateway.py:94,104-118` |
| N-5 | High | **Default service secrets in every environment.** Backend: `AI_SERVICE_API_KEY="build-ai-dev-secret-key"`, `AI_SERVICE_WEBHOOK_SECRET="build-ai-dev-webhook-secret"`, with no strict-environment check (unlike the JWT key). AI: `SERVICE_AUTH_SECRET="build-internal-service-secret"`, `JWT_SECRET="dev-secret"`, and no environment concept at all. | backend `core/config.py:24-30`; ai `core/config.py:48,54` |
| N-6 | Medium | **AI inbound HMAC gaps.** No request id/nonce (replayable within the 300 s skew window); `X-Service-Identity` not in the signed material; query string excluded (`request.url.path`); no body hash or context in the canonical string; the idempotency store keys on caller-supplied values. | ai `core/service_auth.py:18-35,77-83` |
| N-7 | Medium | **No backend path to user-facing AI operations.** The trusted-context design (§19.1–19.2) has no implementation on either side; clients can only reach AI features directly. | backend: only `HttpAIServiceIngestionGateway` calls AI |
| N-8 | Medium | **Unusable default callback URL.** `"/content/ingestion/callbacks"` is relative; AI-service rejects it (no host). | backend `job_handlers.py:276` |
| N-9 | Medium | **No real two-service topology.** Each repo's compose has its own PostgreSQL (`build` vs `build_ai`), both bind host 5432 and 8000, there is no shared network or combined file; backend compose sets no `AI_SERVICE_URL` (default `localhost:8001`, AI listens on 8000); AI's nginx publishes AI-service on :80; both use the `postgres` superuser. | both `docker-compose.yml` |
| N-10 | Medium | **Shared-database exposure.** On one database with one superuser role, AI-service can read/write every backend table directly, bypassing any HMAC boundary. Its legacy `users` and `questions` models map onto backend tables of the same name (reads only; incompatible columns, so they fail rather than leak). | ai `db/models/user.py`, `db/models/question_bank.py`, `auth/routes.py:17`, `services/exam/question_service.py:13` |
| N-11 | Low | Duplicate mounts (`/v1/ingest` and `/api/v1/ingest`; `/exams` and `/api/v1/exams`); `services/ai/router.py` (`generate`, `ocr`) never mounted. | ai `main.py:48-51`, `api/v1/router.py:22,32` |
| N-12 | Medium | **Each side tests against a mock of the other.** Backend gateway tests use `httpx.MockTransport`; AI callback tests mock delivery; no test runs one service against the other (§21). | backend `tests/infrastructure/content/test_ai_gateway.py`; ai `tests/unit/test_callbacks_dispatcher.py` |

## 4. The 22 inspection points

| # | Point | Finding |
|---|---|---|
| 1 | Backend → AI calls | Ingestion dispatch only (+ dead status/cancel calls) — §1, X-1, X-2, N-4 |
| 2 | AI → backend callbacks | Ingestion job events only — X-3, X-4 |
| 3 | Service authentication | Mismatched schemes; static Bearer outbound and accepted inbound — X-1, X-4 |
| 4 | HMAC utilities | Two incompatible implementations (AI: method/path/ts/body; AI callbacks: ts.body; backend: body only) |
| 5 | Headers / canonical request | No shared spec; identity header and query string unsigned — N-6 |
| 6 | Timestamp / replay | AI inbound: timestamp, no nonce; backend callbacks: neither (event_id dedupe only) — N-6, X-4 |
| 7 | Request ids / idempotency | Backend idempotency key in a header AI ignores; AI requires it in body — N-4 |
| 8 | Body hashing | Bodies signed raw; no explicit body hash in the material |
| 9 | Directional secrets | None; AI one secret both ways, backend two unrelated secrets — X-6, N-5 |
| 10 | TenantContext propagation | Tenant id only, as header/body; no user, membership or role; UUID dropped by AI — X-5 |
| 11 | End-user token leakage | None found: backend never forwards user tokens |
| 12 | AI trust assumptions | Trusts raw `X-School-ID` and its own JWTs for users — A-2, A-4 |
| 13 | Callback authorization | Shared-secret only, static Bearer fallback; no binding of a callback to the dispatch that created it beyond job id/run/attempt — X-4 |
| 14 | Callback payload validation | Schema-validated; state machine rejects illegal transitions; event dedupe and stale checks; `details`/`metrics` stored as given |
| 15 | Task/job ownership | Not enforced per tenant on the backend; users can drive AI-owned states — N-1, N-3 |
| 16 | Failure / retry | Backend classifies retryable errors; AI callbacks retry with backoff; no reconciliation if callbacks are lost (status endpoint missing) — X-2 |
| 17 | Mocks vs real services | Mocks only — N-12 |
| 18 | Docker / network topology | Two disconnected stacks — N-9 |
| 19 | Environment / secrets | Defaults everywhere, no strict mode on AI — N-5 |
| 20 | AI gateway / task infrastructure | `TaskDispatcher` + Redis idempotency store exist and are reusable; `infrastructure/ai_gateway.py` stub is dead (M2 backlog) |
| 21 | Legacy identity in AI-service | All of A-1…A-5 remain |
| 22 | Shared database bypass | Yes, by database role — N-10 |

## 5. Decisions needed before the M3 design

1. **Backend-side boundary fixes in M3?** N-1 (cross-tenant job control), N-2 (caller-chosen callback URL) and N-3 (users fabricating AI states) are backend authorization defects at the boundary. Recommendation: fix them first in M3; they are prerequisites for trusting anything that crosses it.
2. **Callback destination.** Recommendation: the backend configures its own callback URL (one setting, absolute); never taken from a request; AI-service accepts callbacks only to an allow-listed backend origin.
3. **Protocol.** Recommendation, per §19.2–19.3: one written spec used in both directions — `X-BUILD-Timestamp`, `X-BUILD-Request-ID`, `X-BUILD-Signature`, a signed context header; canonical string of method, path with query, timestamp, request id, SHA-256 body hash and context hash; HMAC-SHA256; separate secret per direction; request-id replay store (Redis `SET NX` with TTL ≥ skew window); static Bearer removed on both sides; secrets required outside development.
4. **Scope of user-facing AI routes in M3.** Options: (a) put every AI-service user route behind service authentication + trusted context now and build backend endpoints only for the operations needed first; (b) M3 covers ingestion only and leaves A-1…A-4 to M4. Recommendation: (a) — close the open routes in M3 (they are the larger exposure), proxy a minimal first set through the backend, and leave removal of AI-service's legacy login/exam/user tables to M4.
5. **Task status (X-2).** Implement a signed status endpoint on AI-service for reconciliation of lost callbacks, or remove polling from the backend. Recommendation: implement status; drop cancel until AI-service can actually cancel.
6. **Topology and database roles.** Recommendation: M3 adds one combined compose (backend + AI-service + one PostgreSQL + Redis) to run the real-service tests required by §21, and separate database roles — backend owns its tables; AI-service gets a role with rights only on AI-owned tables. Ports, nginx exposure and production networking stay M6.
7. **AI-service tenant type.** Tenants are UUID strings end to end; the `int` school-id context goes. Recommendation: in M3 for the paths M3 touches (context arrives signed from the backend), with the rest of A-5 in M4.

## 6. Out of scope for M3 (recorded, not acted on)

AI-service legacy login/JWT/exam stack and its `users`/`questions`/`schools` models (M4); AI intelligence contracts and response schemas (M5); production networking, TLS, proxy client IP, secret management service (M6); the M2 hardening backlog.
