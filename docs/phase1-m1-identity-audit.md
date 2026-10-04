# Phase 1 — Milestone 1: Identity Audit

**Date:** 2026-10-02
**Repositories:** `build-backend` (branch `feat/learning-content`), `ai-service` (branch `main`)
**Governing documents:** `docs/BUILD_MASTER_PRD.md` (target state), Phase 1 plan (Workstreams 1, 2, 4, 5)
**Scope:** Read-only. Maps the current identity, tenant, authorization and service-boundary flow and inventories AI-service legacy identity/exam dependencies. No code was changed.

Severity: **Critical** = exploitable now / blocks production; **High** = breaks a required flow; **Medium/Low** = correctness or hygiene.

---

## 1. Current identity flow (as implemented)

```text
                    ┌──────────────────────── build-backend ────────────────────────┐
Client ── POST /identity/authenticate ──▶ UserService ──▶ "hash" = "hashed:"+password (B-1)
       ◀── access_token = "access:<user_id>"  (unsigned, B-2)
       ◀── refresh_token = session.refresh_token_hash value (B-4)

Client ── Bearer <token> + x-tenant-slug ──▶ get_current_principal   (accepts "access:<id>",
                                              │                         "refresh:<id>" or "<id>")
                                              ▼
                                   get_current_tenant_context  ── tenant by slug + ACTIVE
                                              │                    membership checked in DB  ✔
                                              ▼
                                   require_permission(role → permissions)  ✔
                    └──────────────────────────────────────────────────────────────────┘
                                              │
              backend → AI: Authorization: Bearer <ai_service_api_key>, X-Tenant-ID (X-1)
                                              ▼
                    ┌──────────────────────── ai-service ───────────────────────────┐
  /v1/ingest/dispatch requires HMAC X-Service-Identity/X-Timestamp/X-Service-Signature
                    → backend request rejected 401 (X-1); tenant UUID dropped (X-5)

  Separately, AI-service runs its OWN user identity:
Client ── POST /auth/login ──▶ legacy `users` table (int id, school_id, hashed_password)
       ◀── HS256 JWT signed with JWT_SECRET (default "dev-secret") {sub, school_id(int), role}
Client ── X-School-ID: <any int> ──▶ TenantMiddleware sets tenant from raw header (A-2)
  chat / explain / generate-questions / retrieve / tree: NO authentication (A-1)
  ws /ws/exam/{id}: NO authentication, tenant from raw x-school-id header (A-3)
                    └──────────────────────────────────────────────────────────────────┘
```

The two services have **two independent, incompatible identity systems** (UUID users + memberships in the backend; integer users + `school_id` in AI-service), and the only service-to-service channel between them does not authenticate in either direction.

## 2. Target identity flow (Phase 1 plan / PRD §60–65)

```text
Client ──▶ build-backend: authenticate (real hashing, signed tokens)
                │  principal (user_id)
                ▼  tenant + ACTIVE membership + role + permissions   (already correct)
                │
                │  service-authenticated request carrying trusted context:
                │  user_id, tenant_id (backend UUID), membership_id, role/permissions,
                │  correlation_id  — integrity-protected, replay-limited
                ▼
           ai-service: verifies the SERVICE, derives user/tenant ONLY from that verified
           context; never from client headers, request bodies, or its own user table.
```

---

## 3. Backend findings

| ID | Severity | Finding | Evidence |
|---|---|---|---|
| B-1 | **Critical** | Passwords are stored effectively in plaintext. The wired `Argon2PasswordHasher` returns `"hashed:" + password`; `argon2-cffi` is a declared dependency but unused. | `app/infrastructure/security/argon2_password_hasher.py`; wired in `app/bootstrap/container.py:45,67` |
| B-2 | **Critical** | Access tokens are forgeable. The wired `JWTTokenService` issues the literal string `access:<user_id>` (no signature, no expiry); `decode()` returns the token itself as `sub`, and `get_current_principal` strips `access:`/`refresh:` prefixes. `Bearer <user-uuid>`, `Bearer access:<uuid>` and `Bearer refresh:<uuid>` all authenticate as that user. | `app/infrastructure/security/jwt_token_service.py`; `app/core/dependencies.py` (`get_current_principal`) |
| B-3 | **Critical** | `POST /identity/forgot-password` returns the reset token in the HTTP response, so anyone who knows an email can reset that account's password. | `app/api/identity.py` (`forgot_password`) |
| B-4 | High (needs verification) | `POST /identity/authenticate` returns `session.refresh_token_hash.value` as the refresh token. Whether the stored value is the token itself was not traced in this audit. | `app/api/identity.py` (`authenticate_user`) |
| B-5 | Medium | `/identity/me` decodes tokens itself instead of using `get_current_principal`, duplicating (and diverging from) the auth path. | `app/api/identity.py` (`get_current_user`) |
| B-6 | Low | Unused duplicate placeholders: `infrastructure/identity/password_hasher.py`, `infrastructure/identity/token_service.py`; dead `TenantResolver` (`x-tenant-id`) and unused `tenant_header` setting. | `app/core/tenant.py`, `app/core/config.py:13` |
| B-7 | High (gap) | No API or service path creates tenants or grants memberships — only test fixtures do. Every tenant-scoped flow depends on memberships existing. | grep of `app/` and `scripts/` |
| B-8 | Medium (gap) | No AI-related permissions exist in `ROLE_PERMISSIONS`, so AI capabilities cannot yet be authorized per role. | `app/core/authorization.py` |
| B-9 | High | Default secrets for the AI boundary: `ai_service_api_key = "build-ai-dev-secret-key"`, `ai_service_webhook_secret = "build-ai-dev-webhook-secret"`. (Workstream 6.) | `app/core/config.py` |

**Already correct — preserve:**

- Tenant context is derived from `x-tenant-slug` **and verified against an active membership in the database**; role comes from the membership, not the client. A client cannot select a tenant it does not belong to. (`get_current_tenant_context`)
- Authorization: six membership roles (`owner`, `admin`, `faculty_admin`, `hod`, `lecturer`, `student`) — a superset of the PRD's four — with ~30 granular permissions, enforced via `require_permission` on every domain router. Only `health` is unauthenticated.

The backend's tenancy and authorization design is sound; it is undermined entirely by B-1/B-2/B-3, which make the authenticated principal forgeable.

---

## 4. Cross-service boundary findings

| ID | Severity | Finding | Evidence |
|---|---|---|---|
| X-1 | **High** | Backend → AI dispatch cannot authenticate. Backend sends `Authorization: Bearer <api_key>`; AI-service `/v1/ingest/dispatch` requires HMAC headers `X-Service-Identity`, `X-Timestamp`, `X-Service-Signature`. Result: 401. | backend `app/infrastructure/content/ai_gateway.py:91-96`; ai-service `app/api/v1/ingest.py:33`, `app/core/service_auth.py` |
| X-2 | High | Backend calls `GET /v1/ingest/tasks/{id}` and `POST /v1/ingest/tasks/{id}/cancel`; neither route exists in AI-service (only `/dispatch`). Result: 404. | backend `ai_gateway.py:181,219`; ai-service `app/api/v1/ingest.py` |
| X-3 | **High** | AI → backend callbacks never verify. AI signs `HMAC(SERVICE_AUTH_SECRET, "{timestamp}." + body)` into `X-Build-Signature`; backend verifies `HMAC(ai_service_webhook_secret, body)`. **Executed:** with an identical secret on both sides, backend `verify_webhook_signature` returns `False` for AI-service's real signature. | ai-service `app/core/callbacks/signer.py`, `dispatcher.py:134-142`; backend `app/infrastructure/content/ai_gateway.py:35-57`, `app/api/content/jobs.py:391-405` |
| X-4 | High | Backend webhook also accepts a static `Authorization: Bearer <ai_service_api_key>` as an alternative to HMAC, with no timestamp or replay protection. | backend `app/api/content/jobs.py:402-405` |
| X-5 | High | AI ingest sets tenant context with `int(payload.tenant_id)`; a backend UUID raises `ValueError`, which is silently swallowed. Real backend tenants never reach AI-service's tenant context. | ai-service `app/api/v1/ingest.py:37-42` |
| X-6 | Medium | Secret model differs per side: AI uses one `SERVICE_AUTH_SECRET` to both verify inbound and sign outbound; backend has `ai_service_api_key` and `ai_service_webhook_secret`. | both `config.py` |

Each side's tests exercise only its own half of the contract (mocked peer), which is why both suites pass while the integration cannot work.

The AI-service HMAC scheme (`app/core/service_auth.py`: method + path + timestamp + body, constant-time compare, ±300 s skew window) is the stronger of the two and a good basis for Workstream 5; it lacks nonce-based replay protection inside the window.

---

## 5. AI-service findings

| ID | Severity | Finding | Evidence |
|---|---|---|---|
| A-1 | **Critical** | `chat`, `explain`, `generate-questions`, `retrieve`, `tree/generate` have no authentication; tenant comes from the raw `X-School-ID` header, so any caller can read another tenant's retrieval data. `chat` also takes `user_id` as a caller-supplied parameter for memory lookup. | `app/api/v1/ai/*.py`; `app/core/middleware/tenant.py` (audit 2026-09-28 §9) |
| A-2 | **Critical** | `TenantMiddleware` trusts `X-School-ID` for every request; only routes that also run `require_authenticated_user` overwrite it from the JWT. | `app/core/middleware/tenant.py` |
| A-3 | High | Exam WebSocket `/ws/exam/{id}` has no authentication; tenant from raw `x-school-id` header. | `app/api/v1/ws/exam_ws.py:57-65` |
| A-4 | High | AI-service authenticates application users itself (`/auth/login`, `/auth/refresh`, `/auth/me`) against its legacy `users` table, issuing HS256 JWTs signed with `JWT_SECRET` (default `"dev-secret"`). On the shared database this cannot work: backend `users` has `password_hash`, no `school_id`/`role`. | `app/auth/routes.py`, `app/auth/token.py`, `app/core/config.py` |
| A-5 | Medium | Tenant context is a `ContextVar[int]` named `school_id`; `MemoryService` and document intake bridge it to `tenant_id` with `str()`. | `app/core/tenant.py`; `app/services/memory/memory_service.py`; `app/core/documents/intake.py:67` |
| A-6 | Low | `TokenVerifier` is unused dead code returning a hard-coded identity (`sub="user_id"`, `school_id=1`). | `app/core/token_verifier.py` |

---

## 6. AI-service legacy dependency map

Classification per Phase 1 plan §6.1.

| Location | What it does | Classification |
|---|---|---|
| `app/auth/routes.py` | User login / refresh / me against legacy `users` | **REMOVE** — backend owns user authentication |
| `app/auth/token.py` | Issues/decodes AI's own HS256 user JWTs | **REPLACE WITH BACKEND CONTEXT** |
| `app/auth/dependencies.py`, `app/auth/permissions.py`, `app/core/auth.py` | `require_*` role checks from AI's JWT claims | **REPLACE WITH BACKEND CONTEXT** — role/permissions come from the backend membership |
| `app/core/token_verifier.py` | Unused placeholder | **REMOVE** |
| `app/core/middleware/tenant.py` | Tenant from raw `X-School-ID` | **REMOVE** — replaced by verified service context |
| `app/core/tenant.py` | `ContextVar[int]` `school_id` | **REMODEL AS AI DOMAIN** — keep a request-scoped tenant context, as a backend tenant UUID string |
| `app/api/v1/ingest.py:37-42` | `int(tenant_id)` → `set_school_id` | **REPLACE WITH BACKEND CONTEXT** |
| `app/core/documents/intake.py:67` | `str(get_school_id())` | **REPLACE WITH BACKEND CONTEXT** |
| `app/services/memory/memory_service.py` | Temporary `str(get_school_id())` bridge (Item 2) | **REPLACE WITH BACKEND CONTEXT** |
| `app/services/rag/retrieval.py`, `app/services/ai/tenanted_retriever.py` | Retrieval tenant from `get_school_id()` | **REPLACE WITH BACKEND CONTEXT** |
| `app/core/tools/validator.py:57` | Accepts `tenant_id` or `school_id` keys | **REPLACE** — `tenant_id` only |
| `app/db/models/user.py`, `school.py`, `exam.py`, `exam_session.py`, `answer_sheet.py`, `question_bank.py` | Legacy shadow models (already excluded from migrations) | **REMOVE** — backend owns these domains |
| `app/api/v1/exams.py`, `app/api/v1/ai/exam.py`, `app/api/v1/ai/exam_submit.py`, `app/api/v1/ws/exam_ws.py`, `app/schemas/exam.py` | Exam CRUD, attempt lifecycle, submission, live session | **REMOVE** — backend owns the CBT lifecycle (PRD §61) |
| `app/services/exam/session_service.py`, `question_service.py`, `session_state.py`, `redis_session_store.py`, `timer.py`, `redis_timer.py`, `scoring.py`, `anti_cheat.py`, `exam_engine.py` | Exam runtime | **REMOVE** — backend lifecycle |
| `app/services/exam/adaptive_engine.py`, `fusion_engine.py`, `app/api/v1/ai/fusion_exam.py` | Adaptive difficulty / AI exam generation | **REMODEL AS AI DOMAIN** (likely) — generation/difficulty intelligence returned to the backend; *not inspected in depth, confirm before acting* |
| `tests/integration/conftest.py` (legacy `User` fixture), `scripts/seed.py` | Test/dev data | **TEST FIXTURE ONLY** — retire with the models |
| `app/schemas/ingest.py:34` ("Tenant/School identifier"), `app/core/documents/metrics.py:24`, `app/core/execution_context.py:140` | Wording / false positives | **DOCUMENTATION ONLY** |

---

## 7. Decisions needed before Milestone 2+

1. **Client → AI-service access.** The plan routes all client AI traffic through the backend. Confirm that AI-service's user-facing routes (`chat`, `retrieve`, …) become **service-only** (callable only by the backend), rather than accepting end-user tokens.
2. **Trusted-context format.** How the backend passes `user_id`, `tenant_id`, `membership_id`, role/permissions and `correlation_id`: signed headers covered by the HMAC, or a signed body envelope. Recommendation: reuse AI-service's HMAC scheme and include the context in the signed material.
3. **One service-auth scheme in both directions.** Recommendation: adopt AI-service's timestamped HMAC (method + path + timestamp + body) for backend → AI, align callbacks (AI → backend) to the same timestamped scheme, and drop the static bearer fallback (X-4). Decide whether each direction gets its own secret.
4. **Fate of AI exam intelligence** (`adaptive_engine`, `fusion_engine`, `fusion_exam`): move to backend, or remodel as AI generation APIs consumed by the backend.
5. **Tenant/membership provisioning (B-7).** Which milestone introduces the admin/onboarding path for tenants and memberships.

## 8. Suggested milestone mapping

| Finding | Milestone |
|---|---|
| B-1, B-2, B-3, B-4, B-5, B-6 | M2 — Backend authentication |
| A-2, A-5, X-5, B-7 | M3 — Tenant context |
| B-8 | M4 — Authorization |
| A-1, A-3, A-4, A-6, §6 map | M5 — AI legacy removal |
| X-1, X-2, X-3, X-4, X-6 | M6 — Service security |
| B-9, AI `JWT_SECRET` / `SERVICE_AUTH_SECRET` defaults | M7 — Security hardening |
