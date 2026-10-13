# Phase 1 — Milestone 6: Production Gate Report

**Milestone:** M6 — Production Integration & Security Gate (closes Phase 1)
**Date:** 2026-10-10
**Governing documents:** `docs/PHASE_1_PLAN.md` §8–§12, §22 M6; the M3/M4/M5 reports and designs

## 1. Verdict

**The Phase 1 engineering gate passes locally on fresh infrastructure.** Every item in the §12 checklist is met in code and verified by tests, with three exceptions that are open before a production launch (§4):
1. the hosted two-repository gate has not run;
2. no production email provider is wired, so password reset and email verification cannot deliver in staging or production;
3. TLS between the services is required by configuration, but the TLS endpoints themselves are deployment work.

None of the three weakens a security property. Each is a deployment or operations dependency, stated plainly so it is not mistaken for done.

## 2. Gate evidence (final commits: build-backend `3121c8a`, ai-service `f3e2077`)

| Gate | Result |
|---|---|
| Real two-service gate `scripts/m3_boundary_gate.sh`: PostgreSQL 17 + Redis 8 from empty volumes, least-privilege roles, both migration chains as owners, backend + AI-service + worker | **176 passed** |
| C11 with Redis stopped | **3 passed** (both receivers 503, unsigned still 401) |
| Production startup path (`scripts/m6_production_startup.sh`) | **11/11**: both services boot with `APP_ENVIRONMENT=production`; 9 unsafe configurations are refused |
| Backend full suite (at `3121c8a`) | 1122 passed, 89 skipped, 0 failed |
| Backend `postgres-gate` mirror, fresh PG17 + Redis 8 | empty → head, single head, round trip, no schema drift, `pg_smoke` 20 passed + 1 known xfail, real-Redis suites 7 + 30 + 52 passed |
| ai-service full suite, fresh PG17 + Redis 8 | 808 passed; failures **only** in the OCR stack, outside Phase 1 scope (§5) |

## 3. §12 Production readiness checklist

| Area | Item | Status and evidence |
|---|---|---|
| Architecture | Backend authoritative for identity / tenancy / academic state | ✅ M2; M4 removed AI-service users, schools, exams and questions (`ai-service/docs/phase1-m4-completion-report.md` §3) |
| | AI-service is an intelligence layer | ✅ No user, exam or legacy model remains; boundary test: only signed routes and system probes exist |
| | Ownership documented | ✅ M4 report §3; enforced by DB roles (C24/C25) and table-ownership checks (M6 gate) |
| Identity | Production-safe auth, passwords, tokens, reset | ✅ M2 (Argon2id, signed rotating tokens, session checks, single-use reset codes). ⚠️ No email provider in staging/production (§4) |
| | AI-service does not authenticate users | ✅ M4; gate: no `/auth/*`, no JWT settings |
| Tenancy | Canonical, unforgeable tenant | ✅ Tenant from membership (backend) and from the signed context (AI); forged header, body and context are refused (C4, C15, C29, M6 attacks) |
| | Cross-tenant reads/writes blocked | ✅ C16, C19, C23, M5-4, M6 cross-tenant memory |
| Authorization | Roles, server-side permissions, negative tests | ✅ M2 role matrix; `ai.use` / `ai.questions.generate`; 403 tests on both sides (C14, M5-5) |
| AI-service | Legacy identity and exam dependencies removed | ✅ M4 |
| | AI persistence isolated | ✅ `build_ai_app` has no backend privileges (C24) |
| | Trusted identity/tenant context; canonical tenant ids in memory | ✅ String request scope from the verified context only (M3-10); memory keyed by tenant UUID + user (M5) |
| Service security | Backend → AI authentication, request integrity | ✅ BUILD Service Signature v1, C1–C12 |
| | Secrets externally configured | ✅ No defaults in staging/production; refusals proven at startup (M6) |
| | Correlation ids end to end | ✅ Backend request id → signed context → AI-service logs and `X-Correlation-ID` (M6) |
| | Unauthorized service requests rejected | ✅ C2–C13 |
| Configuration | No unsafe production defaults; required config validated | ✅ Both services; `AI_SERVICE_URL` and `BACKEND_CALLBACK_URL` must be https (M6) |
| | Rate limiting operational | ✅ Redis-backed auth and AI limits; real-stack lock test (429) |
| | Request/upload limits | ✅ 1 MiB on every backend route and every signed AI route; 413 tested on the real stack. No file bytes pass through the API |
| | CORS/security config explicit | ✅ Exact-origin `CORS_ALLOWED_ORIGINS` (empty = none); security headers; docs off in staging/production on both services |
| Verification | Fresh PG17 migrations, Redis 8 tests | ✅ §2 |
| | Backend, AI-service, security, cross-service tests | ✅ §2 (AI-service: documented OCR exceptions only) |
| | Production startup path | ✅ §2 |
| | Clean trees, narrow commits | ✅ Only the two untracked audit documents remain, kept by instruction |

## 4. Open before production launch (not engineering defects)

| Item | Why it is open | What closes it |
|---|---|---|
| Hosted `boundary-gate` | Needs the `AI_SERVICE_READ_TOKEN` secret and a push | Configure the token, push, run the workflow once; the local gate script is identical |
| Email delivery in staging/production | `UnconfiguredEmailSender` drops messages by design: no provider is wired yet | Choose and wire a provider before launch. Reset and verification codes are generated and stored safely, but they cannot be delivered |
| TLS/mTLS between services (E.4) | Responses are unsigned. Config now *requires* https in staging/production, but the endpoints (ingress, certificates) are deployment work | Terminate TLS at both services' ingresses; mTLS optional |

## 5. Known, documented test exceptions (ai-service, outside Phase 1 scope)

- `test_service_stubs.py::test_image_ocr_providers_return_data`: fails on the pre-M3 baseline; OCR provider stubs.
- `test_ocr_service.py` (two tests): **intermittent in the full suite**, passes alone (3/3). `app/services/ocr/paddle.py` sets `PaddleOCR = None` when the `paddleocr` import raises during a full run, and `OCRService()` builds the real provider before the test patches it. No M3–M6 commit touches OCR. Fix: make the test patch the provider class before construction, and log the swallowed import error (OCR workstream, Phase 2).
- **Resolved in M6:** the Redis idempotency test (root cause: a module-global client across event loops, plus a silent in-memory fallback; `cf34052`).

## 6. M6 changes

**ai-service**
- `cf34052`: idempotency fails closed; one Redis client per event loop; the URL's database number is honoured.
- `23ea46b`: correlation id from the verified context into logs and the `X-Correlation-ID` header.
- `f3e2077`: no docs or OpenAPI in staging/production.

**build-backend**
- `3e25ed0`: `AI_SERVICE_URL` must be https outside development.
- `cd4b0b1`: request body limit on every route.
- `e6440d9`: explicit CORS origins; docs exposure.
- `3121c8a`: client address from trusted proxies only.
- `f7f2100`: real-stack attack list and §10 database checks.
- `991968b`: production startup path in the gate.

## 7. Residual risks and follow-ups (Phase 2 candidates)

- Backend `GET /` returns the environment name, and `/metrics` is unauthenticated. Restrict both to the internal network at deployment, or gate them in code.
- AI-service has no rate limiting of its own. It is reachable only from the backend, which limits per user.
- Memory reports after attempt submission are best effort with no retry marker (M5 report §4).
- Two model stacks in ai-service (`services/ai`, `core/models`) to consolidate.
- Local ruff 0.16.5 versus CI's ruff: files touched in M3–M6 were formatted with the repository's configured style (line length 130), so some diffs include line re-wraps.
- Replay-store Redis timeouts remain at their defaults until production latency is measured.
