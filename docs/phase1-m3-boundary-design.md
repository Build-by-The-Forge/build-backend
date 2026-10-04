# Phase 1 — Milestone 3: Backend ↔ AI-Service Security Boundary — Design

**Status:** Draft for review · **Date:** 2026-10-04 · **No code has been changed.**
**Inputs:** `docs/phase1-m3-reconnaissance.md` (findings X-*, A-*, N-*), the M3 rulings of 2026-10-04 (decisions 1–7 accepted, with refinements), `docs/PHASE_1_PLAN.md` §19.1–19.4, §21.

This document has three parts: **A** the wire protocol, **B** the security and sequence model (including what changes on each side), **C** the acceptance matrix. Part D lists the implementation sequence, and Part E the points still needing a decision.

---

## 0. Principles

1. **The backend is the authority.** It authenticates the user, resolves tenant and membership from its database, and authorizes the operation. Only then does it call AI-service.
2. **A signature proves origin and integrity, not permission.** The signed context tells AI-service *on whose behalf, within which tenant* it is working. AI-service uses it to scope its work; it never treats it as an independent authorization source and cannot change it. The backend never acts on anything AI-service sends unless the backend's own rules allow it.
3. **Business operations versus processing events.** Users invoke business operations on the backend. AI-service reports processing events. Users never invoke processing transitions; AI-service never invokes business operations.
4. **Nothing on the wire is chosen by an end user that decides where data goes or which tenant it belongs to.** Destinations come from configuration; tenant comes from the backend's verified context.
5. **Defence in depth below the protocol:** separate database roles, so even a compromised AI-service cannot write backend state.
6. **Proven against the real services**, not mocks (plan §21).

---

## Part A — Protocol specification: BUILD Service Signature v1

One protocol, used in both directions. Each direction has its own secret.

### A.1 Parties and secrets

| Direction | Sender id (`X-BUILD-Service`) | Secret (signer and verifier share it) |
|---|---|---|
| backend → AI-service | `build-backend` | `BACKEND_TO_AI_SECRET` |
| AI-service → backend | `ai-service` | `AI_TO_BACKEND_SECRET` |

- A receiver accepts only the one sender id defined for its direction. AI-service accepts only `build-backend`; the backend accepts only `ai-service`.
- Each secret is at least 32 bytes of random data, generated independently. The two secrets must differ; a service refuses to start if they are equal.
- Each direction also has an optional `…_PREVIOUS` secret for rotation. A receiver verifies against the current secret, then the previous one. Signers always use the current secret.
- **Required outside development.** In `staging`/`production` both services refuse to start if a secret is missing, shorter than 32 bytes, or equal to a known development default. There are no built-in defaults; development generates a random per-process secret only when explicitly configured for single-process tests.
- The static Bearer keys (`AI_SERVICE_API_KEY`, `AI_SERVICE_WEBHOOK_SECRET`, `SERVICE_AUTH_SECRET`) are removed. No route accepts a Bearer service key.

### A.2 Headers

| Header | Format | Required |
|---|---|---|
| `X-BUILD-Service` | Sender id, exact ASCII string from A.1 | always |
| `X-BUILD-Timestamp` | Unix time in **seconds**, base-10 ASCII integer, no sign, no leading zeros | always |
| `X-BUILD-Request-ID` | UUID version 4, canonical lowercase 8-4-4-4-12 hex form (36 chars), freshly generated per request | always |
| `X-BUILD-Context` | Base64url (RFC 4648 §5) of the canonical context bytes (A.4), **no padding**; at most 4096 characters | always (see A.4 for `system` actors) |
| `X-BUILD-Signature` | `v1=` followed by 64 lowercase hex characters | always |

Header names are case-insensitive as in HTTP; values are case-sensitive.

### A.3 Canonical request

The canonical request is exactly eight lines joined by a single line feed (`\n`, 0x0A), with **no trailing line feed**, encoded as UTF-8 (all fields are ASCII):

```text
v1
<X-BUILD-Service value>
<METHOD>
<REQUEST-TARGET>
<X-BUILD-Timestamp value>
<X-BUILD-Request-ID value>
<BODY_SHA256>
<CONTEXT_SHA256>
```

- `METHOD` is the HTTP method in uppercase ASCII (`GET`, `POST`, …).
- `REQUEST-TARGET` is the path and query **exactly as sent on the wire**: the raw, percent-encoded path, then `?` and the raw query string if the query string is non-empty. It is not decoded, normalised or reordered. A receiver reconstructs it from the raw ASGI `raw_path` and `query_string`. Senders must not rely on intermediaries rewriting it. (M3 routes are reached without path-rewriting proxies; M6 confirms the production proxy preserves the request target.)
- `BODY_SHA256` is the lowercase hex SHA-256 of the exact body bytes sent. An empty or absent body hashes to `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`.
- `CONTEXT_SHA256` is the lowercase hex SHA-256 of the context bytes obtained by base64url-decoding `X-BUILD-Context` (not of the header text).

`signature = lowercase_hex( HMAC-SHA256( key = UTF-8 bytes of the direction's secret, message = canonical request bytes ) )`, sent as `v1=<signature>`.

Signing the service id, the version, the full request target, the body hash and the context hash means none of them can be changed — including swapping the tenant inside the context, adding a query parameter, or claiming a different sender — without invalidating the signature.

### A.4 Context

The context is a JSON object serialised canonically: keys sorted by Unicode code point, separators `,` and `:` with no whitespace, ASCII-only output (non-ASCII escaped as `\uXXXX`), UTF-8 encoded, no trailing newline. Python reference: `json.dumps(ctx, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")`.

| Field | Type | `actor = "user"` | `actor = "system"` |
|---|---|---|---|
| `v` | integer `1` | required | required |
| `actor` | `"user"` or `"system"` | `"user"` | `"system"` |
| `tenant_id` | UUID string (lowercase canonical) | required | required |
| `user_id` | UUID string or `null` | required | `null` |
| `membership_id` | UUID string or `null` | required | `null` |
| `role` | membership role string or `null` | required | `null` |
| `permissions` | array of permission strings, sorted ascending, unique | the permissions the backend checked for **this** operation (normally one); never the user's full set | `[]` |
| `correlation_id` | string, 1–128 chars `[A-Za-z0-9._:-]` | required | required |

- Unknown fields are rejected, as are missing required fields and wrong types. The receiver re-serialises the decoded object canonically and requires the result to be **byte-identical** to the decoded header bytes. This rules out ambiguous encodings such as duplicate keys or different spacing.
- `system` context is used where no end user is acting: AI-service callbacks, status reconciliation, scheduled retries. It always names the tenant the message concerns.
- The context is **not** an authorization source for AI-service. AI-service may only *narrow* behaviour with it (scope retrieval and memory to `tenant_id`/`user_id`, and refuse if the route's declared permission is missing from `permissions`). It can never widen behaviour.

### A.5 Verification (receiver)

The steps below run in this order. Every failure returns `401` with the body `{"error": "invalid service authentication"}`, the same for all causes. The precise reason is logged internally, never returned.

1. All five headers present; signature header matches `^v1=[0-9a-f]{64}$`.
2. `X-BUILD-Service` equals the sender id this receiver accepts.
3. Timestamp matches `^[1-9][0-9]{0,11}$` and is within **±60 seconds** of the receiver's clock.
4. Request id is a canonical lowercase UUIDv4.
5. Context header decodes (base64url, no padding, ≤ 4096 chars), parses as JSON, passes the schema in A.4, and re-serialises byte-identically.
6. Body is read in full, up to **1 MiB** (larger → `413`, before any hashing of the remainder), and hashed.
7. Signature recomputed with the current secret, then the previous one; compared in constant time (`hmac.compare_digest`).
8. Replay check, **only after the signature is valid** (so an attacker cannot burn request ids): Redis `SET svcauth:<receiver-id>:<sender-id>:<request-id> 1 NX EX 180`. If the key already exists, reject. The TTL of 180 s is longer than the whole acceptance window (±60 s), so an id cannot be reused before its timestamp has gone stale.
9. Route-level checks (Part B), for example: the context tenant matches the resource's tenant, and the declared permission is present.

**Redis unavailable:** the receiver fails **closed**. It answers `503 service temporarily unavailable` and processes nothing. Unlike sign-in rate limits, replay protection is part of the boundary's integrity, and both services already depend on Redis. (This is a decision point; see E.1.)

**Clock:** both services run NTP-synchronised; the ±60 s window is the tolerance.

### A.6 Responses

Responses are not signed in M3. The caller authenticated the receiver by sending to its configured URL; confidentiality and integrity in transit come from TLS on the internal network (M6). This residual risk is recorded in E.4.

### A.7 Test vector (both repositories must reproduce it exactly)

```text
secret            test-only-backend-to-ai-secret-0123456789abcdef
X-BUILD-Service   build-backend
method            POST
request-target    /v1/ai/generate-questions?lang=en
X-BUILD-Timestamp 1760000000
X-BUILD-Request-ID 3f1c0d9e-6b0a-4c55-9d43-1c2b8f7a9e10
body              {"topic":"Thermodynamics","count":5}
context JSON      {"actor":"user","correlation_id":"corr-001","membership_id":"a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d","permissions":["ai.questions.generate"],"role":"lecturer","tenant_id":"6f1c2a7e-4b3d-4c8e-9a1f-2d3e4f5a6b7c","user_id":"0b9d8c7a-6e5f-4a3b-8c2d-1e0f9a8b7c6d","v":1}
X-BUILD-Context   eyJhY3RvciI6InVzZXIiLCJjb3JyZWxhdGlvbl9pZCI6ImNvcnItMDAxIiwibWVtYmVyc2hpcF9pZCI6ImExYjJjM2Q0LWU1ZjYtNGE3Yi04YzlkLTBlMWYyYTNiNGM1ZCIsInBlcm1pc3Npb25zIjpbImFpLnF1ZXN0aW9ucy5nZW5lcmF0ZSJdLCJyb2xlIjoibGVjdHVyZXIiLCJ0ZW5hbnRfaWQiOiI2ZjFjMmE3ZS00YjNkLTRjOGUtOWExZi0yZDNlNGY1YTZiN2MiLCJ1c2VyX2lkIjoiMGI5ZDhjN2EtNmU1Zi00YTNiLThjMmQtMWUwZjlhOGI3YzZkIiwidiI6MX0
BODY_SHA256       7c60810327978fdb8394acfbccc7e2287850b1309330d9cb3cda5bae3c4aa70d
CONTEXT_SHA256    bd5bf4d02c7c63f22a40f52b497eab2ea1078fa1155956c81c111830fc2d5e06
canonical request "v1\nbuild-backend\nPOST\n/v1/ai/generate-questions?lang=en\n1760000000\n3f1c0d9e-6b0a-4c55-9d43-1c2b8f7a9e10\n7c60810327978fdb8394acfbccc7e2287850b1309330d9cb3cda5bae3c4aa70d\nbd5bf4d02c7c63f22a40f52b497eab2ea1078fa1155956c81c111830fc2d5e06"
X-BUILD-Signature v1=be014f19af31ec051f99db00598a19eb80bc4de18d517f408d2abaca2f719f19
```

Both repositories hold this vector (plus negative vectors: each single-field change must alter the signature) in their unit tests. The implementation is written independently in each repository; the shared vectors, not shared code, prove that the two compute the same thing.

---

## Part B — Security and sequence model

### B.1 User → backend → AI-service (user-facing AI operations)

```text
Client ──Bearer access token──► Backend /ai/{chat|explain|generate-questions}
  1. get_current_principal       (signed JWT, live session, account status — M2)
  2. tenant context              (x-tenant-slug → active tenant, active membership, verified email — M2)
  3. require_permission          (ai.use or ai.questions.generate)
  4. per-user AI rate limit      (cost/abuse guard)
  5. validate + bound input      (size, fields); build request body
  6. build context {actor:user, tenant_id, user_id, membership_id, role, permissions:[checked], correlation_id}
  7. sign (A.3) with BACKEND_TO_AI_SECRET, POST to AI_SERVICE_URL/v1/ai/...
                                   │
AI-service /v1/ai/...  ◄───────────┘
  8. verify (A.5)                — any failure: 401, nothing executed
  9. route check                  declared permission ∈ context.permissions, else 403
 10. set tenant/user scope        from context only (string UUIDs); request body cannot name a tenant or user
 11. run the intelligence operation (retrieval, memory, LLM) scoped to context.tenant_id/user_id
 12. return the result
Backend 13. map the result to its own response schema; persists nothing in M3 (accepting generated
            questions into the question bank is a backend business operation, M5)
```

Tampering and failure paths:

- **Modified body, query, context or sender id, or the wrong secret:** the signature mismatches, so AI-service returns 401.
- **Replayed request:** the request id was already seen, so 401. A replay with a new timestamp but the same id is also 401, and changing the id breaks the signature.
- **Stale timestamp:** 401.
- **Redis down:** 503 on AI-service; the backend maps it to 503.
- **AI-service unreachable or timing out:** the backend returns 502/504 with a stable error code; nothing is persisted.
- **A client calling AI-service directly with an end-user JWT or no headers:** 401, because AI-service accepts only signed backend requests on these routes.

### B.2 Ingestion: business operations versus processing events

**Public backend API** (tenant user, `content.job.manage`, tenant from context). These are *business operations*:

| Operation | Endpoint | Rule |
|---|---|---|
| Start processing a job | `POST /content/jobs/{id}/dispatch` | job must belong to the caller's tenant, else **404**; request body carries no callback URL |
| Retry a failed job | `POST /content/jobs/{id}/retry` | same tenant rule; only from `failed` with `is_retryable` |
| Reprocess an asset | `POST /content/assets/{id}/reprocess` | same tenant rule |
| Read jobs | `GET` job endpoints | already tenant-filtered; checked again |

**Removed from the public API** (N-3): `POST /content/jobs/{id}/start`, `/progress`, `/complete`, `/fail`. These transitions become internal methods, reachable only from verified AI-service callbacks (B.3). Operators keep no manual override in M3; one may later be added as a platform-operator command, not a tenant API.

**Tenant-less (platform) jobs** (`tenant_id` null) cannot be operated through the tenant API: they answer 404. Platform content is an operator concern (D6) and has no API in M3.

Dispatch sequence:

```text
User ─► Backend POST /content/jobs/{id}/dispatch
  1. principal + tenant context + content.job.manage
  2. load job; job.tenant_id == context.tenant_id, else 404 (N-1)
  3. build dispatch body {job_id, asset_id, source_id, run_number, attempt_count, idempotency_key,
     mime_type, content_sha256, storage_uri, correlation_id}   — no tenant field, no callback URL
  4. context {actor:user, tenant_id: job.tenant_id, user_id, membership_id, role, permissions:["content.job.manage"], correlation_id}
  5. sign, POST AI_SERVICE_URL/v1/ingest/dispatch
AI-service:
  6. verify (A.5); tenant for the task = context.tenant_id (string UUID)
  7. idempotency: Redis key ingest:<tenant_id>:<idempotency_key> (existing store, string tenant)
  8. enqueue task recording {external_task_id, job_id, tenant_id, run_number, attempt_count}
  9. 202 {external_task_id, status}
Backend 10. job.record_dispatch(external_task_id); persist
```

### B.3 AI-service → backend (processing events)

```text
AI-service worker ─► POST BACKEND_CALLBACK_URL   (from AI-service configuration only)
  headers: A.2 with X-BUILD-Service: ai-service, signed with AI_TO_BACKEND_SECRET
  context: {actor:system, tenant_id: task.tenant_id, user_id:null, membership_id:null, role:null, permissions:[], correlation_id}
  body:    {event_id, job_id, external_task_id, run_number, attempt_count, event_type, stage, metrics, error_*}
Backend /content/ingestion/callbacks:
  1. verify (A.5) against AI_TO_BACKEND_SECRET; X-BUILD-Service must be ai-service. Bearer no longer accepted (X-4)
  2. job = get by job_id; unknown → 404, no state created
  3. job.tenant_id == context.tenant_id, else 404 (a callback for tenant A cannot touch tenant B's job)
  4. external_task_id == job's recorded external_task_id, else stale (ignored, 200 already_processed)
  5. existing: event_id dedupe, run/attempt staleness, state-machine transitions only (no regression)
  6. metrics/details bounded: ≤ 64 KiB total, JSON objects only, stored as data, never interpreted as commands
```

**Callback destination (N-2):**
- The dispatch request carries no callback URL. AI-service ignores any URL found in a request and uses only `BACKEND_CALLBACK_URL` from its own configuration: an absolute URL to the one fixed path `/content/ingestion/callbacks`.
- At startup AI-service validates it: an `https` scheme outside `development`; no userinfo, fragment or query; the exact path above.
- Callbacks are sent with `follow_redirects=False`. A redirect counts as a delivery failure, which is retried and never followed.
- Because the destination is operator configuration, not request data, no request can point AI-service elsewhere. No general SSRF filter is built.

**Status reconciliation (X-2):**
- AI-service gains `GET /v1/ingest/tasks/{external_task_id}`, signed backend → AI with a `system` context naming the task's tenant. AI-service answers only if the task's tenant equals the context tenant; otherwise 404.
- The backend keeps `fetch_job_status` on the signed protocol and uses it in an explicit `POST /content/jobs/{id}/reconcile` business operation (same tenant rule). That operation applies the reported state through the same transition rules as callbacks.
- A scheduled sweep is out of scope for M3.
- `cancel_ingestion_job` is **removed** from the backend gateway until AI-service can actually cancel.

### B.4 AI-service user routes after M3

| Route group | After M3 |
|---|---|
| `/api/v1/ai/chat`, `/explain`, `/generate-questions` | Moved under one router at `/v1/ai/...`, **signed backend requests only**, context `actor=user` required |
| `/api/v1/ai/retrieve`, `/tree/*`, `/read/*` | Signed backend requests only; not proxied by the backend in M3 (no client path until M5 defines them) |
| `/api/v1/ingest/*` duplicate mount | Removed; `/v1/ingest/*` remains (signed) |
| Legacy user auth: `/auth/*`, `/exams`, `/api/v1/exams`, `/api/v1/ai/exam/*`, fusion exam, `ws /ws/exam/{id}` | **Not mounted** unless `LEGACY_USER_ROUTES_ENABLED=true` (default `false`, refused outside development). Deleted in M4 (decision E.2) |
| `TenantMiddleware` (`X-School-ID`) | Removed: tenant comes only from verified context (A-2) |
| `/health`, `/system/*` | Unauthenticated; must not reveal configuration |

Tenant type: the paths touched in M3 use a `ContextVar[str]` tenant id (UUID string) set from the verified context. These are ingestion, intake, retrieval, memory, chat, explain and question generation. The integer `school_id` remains only inside the legacy routes M4 deletes (A-5 completed in M4).

Chat memory is keyed by the context `user_id`. The caller-supplied `user_id` parameter is removed (A-1).

### B.5 Backend AI endpoints (minimal surface)

| Endpoint | Permission (new) | Who has it | Forwards to |
|---|---|---|---|
| `POST /ai/chat` | `ai.use` | all roles | `POST /v1/ai/chat` |
| `POST /ai/explain` | `ai.use` | all roles | `POST /v1/ai/explain` |
| `POST /ai/generate-questions` | `ai.questions.generate` | lecturer and above | `POST /v1/ai/generate-questions` |

- These endpoints use the tenant context (`x-tenant-slug`), so D4 (verified email) applies.
- Input is bounded (for example, message ≤ 4,000 characters; count ≤ 50).
- Each endpoint has a per-user rate limit through the existing throttle.
- Responses are mapped to backend response schemas.
- Nothing is persisted.
- AI-service routes declare the permission they require, and AI-service refuses if it is missing from the context (narrowing only).

### B.6 Topology and database roles

**One combined Compose file** (`deploy/compose.m3.yml` in build-backend, building `../ai-service`) with services:
- `postgres` (one database, `build`);
- `redis`;
- `db-init` (creates roles, idempotent);
- `backend-migrate` and `ai-migrate` (run each Alembic chain with the owner roles);
- `backend` (published port);
- `ai-service` (**not published**, internal network only).

`AI_SERVICE_URL=http://ai-service:8000`; `BACKEND_CALLBACK_URL=http://backend:8000/content/ingestion/callbacks` (development scheme).

**PostgreSQL roles (least privilege):**

| Role | Login | Rights |
|---|---|---|
| `build_backend_owner` | migrations only | owns backend tables and `alembic_version` |
| `build_backend_app` | backend runtime | `SELECT/INSERT/UPDATE/DELETE` on backend tables, via default privileges from the owner |
| `build_ai_owner` | migrations only | owns `learning_memory`, `session_memory`, `ai_service_alembic_version` |
| `build_ai_app` | AI-service runtime | `SELECT/INSERT/UPDATE/DELETE` on the AI-owned tables only; **no privileges on any backend table**; `CONNECT` and `USAGE` on schema only |

- `PUBLIC` loses its default `CREATE` privilege on the `public` schema.
- Superuser credentials are used by nothing except `db-init`.
- AI-service's legacy `users`, `questions` and `schools` reads therefore fail with "permission denied" on the shared database. That is consistent with those routes being unmounted (B.4) and deleted in M4.

### B.7 Configuration after M3

| Service | Setting | Rule |
|---|---|---|
| backend | `AI_SERVICE_URL` | required outside development |
| backend | `BACKEND_TO_AI_SECRET`, `AI_TO_BACKEND_SECRET` (+ `_PREVIOUS`) | A.1 rules; distinct |
| ai-service | `APP_ENVIRONMENT` (new: development/testing/staging/production) | strict validation in staging/production |
| ai-service | `BACKEND_TO_AI_SECRET`, `AI_TO_BACKEND_SECRET` (+ `_PREVIOUS`) | A.1 rules; distinct |
| ai-service | `BACKEND_CALLBACK_URL` | B.3 rules |
| ai-service | `LEGACY_USER_ROUTES_ENABLED` | default false; refused outside development |
| both | `REDIS_URL` | required; replay store |
| removed | `AI_SERVICE_API_KEY`, `AI_SERVICE_WEBHOOK_SECRET`, `SERVICE_AUTH_SECRET`, `ALLOWED_SERVICE_IDENTITIES`, `SERVICE_AUTH_MAX_SKEW_SECONDS` | — |

`JWT_SECRET` in AI-service stays only while legacy routes exist and is required whenever they are enabled.

---

## Part C — Acceptance matrix

M3 is complete when every row passes. Rows marked **real** must run against the combined topology (B.6) with both real services, not mocks.

| # | Invariant | Test | Where |
|---|---|---|---|
| C1 | Both implementations compute identical signatures | Test vector A.7 + negative vectors | unit, both repos |
| C2 | Backend identity is authentic | valid signed request → accepted | **real** |
| C3 | Body cannot be altered | change one body byte after signing → 401 | **real** |
| C4 | Context cannot be altered | swap `tenant_id` (and separately `user_id`, `permissions`) after signing → 401 | **real** |
| C5 | Query cannot be altered | add/change a query parameter → 401 | **real** |
| C6 | Sender cannot be swapped | `X-BUILD-Service: ai-service` towards AI-service → 401 | **real** |
| C7 | Directional secrets | request signed with the other direction's secret → 401, both directions | **real** |
| C8 | Stale requests refused | timestamp outside ±60 s → 401 | **real** |
| C9 | Replays refused | same signed request twice → second 401 | **real** |
| C10 | Missing or malformed headers/context refused | each header missing; bad base64; non-canonical JSON; unknown field → 401 | **real** |
| C11 | Replay store fails closed | Redis stopped → 503, nothing processed | **real** |
| C12 | No static Bearer anywhere | Bearer service key → 401 on every AI route and on the callback | **real** |
| C13 | AI user routes closed to clients | direct call with end-user JWT / no auth / `X-School-ID` → 401 on chat, explain, generate-questions, retrieve, tree, read; legacy routes absent (404) | **real** |
| C14 | Context narrows only | signed context lacking the route's permission → 403 | **real** |
| C15 | Tenant is authoritative end to end | backend AI call uses the DB-verified tenant; a client cannot choose it (header/body tenant ignored) | **real** |
| C16 | Tenant A cannot operate tenant B's job | dispatch/retry/reprocess/reconcile/get B's job from A → 404 | backend integration + **real** |
| C17 | Users cannot fabricate AI state | start/progress/complete/fail endpoints gone (404/405); no other path sets extracted/indexed/completed | backend integration |
| C18 | Callback destination not attacker-controlled | dispatch body with `callback_url` → ignored; AI-service posts only to `BACKEND_CALLBACK_URL`; redirect not followed | **real** + AI unit |
| C19 | Callback cannot cross tenants | signed callback whose context tenant ≠ job tenant → 404, job unchanged | **real** |
| C20 | Callback cannot create state | callback for unknown job → 404, nothing created | **real** |
| C21 | Callbacks cannot regress or duplicate | replayed event, stale run/attempt, wrong external task id, illegal transition → no change | backend integration + **real** |
| C22 | Full ingestion path works | upload → dispatch → AI processes → signed callbacks → job `ready`, scoped to the tenant | **real** |
| C23 | Status reconciliation | reconcile reflects AI-service task state; other tenant's task → 404 | **real** |
| C24 | AI-service cannot write backend tables | as `build_ai_app`: `UPDATE memberships`, `SELECT users`, `INSERT INTO questions` → permission denied | **real** (DB) |
| C25 | AI-service can use its own tables | as `build_ai_app`: read/write `learning_memory`, `session_memory` | **real** (DB) |
| C26 | Secrets enforced | each service refuses to start in production with missing/short/equal/default secrets; Bearer settings gone | unit, both repos |
| C27 | User-facing AI flow works | client → backend `/ai/chat` (and explain, generate-questions) → AI-service → response, with tenant/user scoping visible in AI-service | **real** |
| C28 | No regressions | backend full suite, `postgres-gate`, AI-service suite | CI / local |

---

## Part D — Implementation sequence

Narrow, verified commits in the existing style. "B" marks build-backend, "A" ai-service.

1. **B:** tenant ownership on every ingestion-job operation (N-1); remove the public start/progress/complete/fail endpoints (N-3); remove caller `callback_url` (N-2, backend half).
2. **B, A:** protocol library: canonical request, context, sign/verify, replay store, with test vector A.7 and the negative vectors. Code written separately in each repo.
3. **A:** `APP_ENVIRONMENT`, strict secret validation, directional secrets, `BACKEND_CALLBACK_URL`; remove `SERVICE_AUTH_SECRET` and the identity allow-list.
4. **B:** directional secrets and validation; remove `AI_SERVICE_API_KEY`/`AI_SERVICE_WEBHOOK_SECRET`.
5. **A:** inbound verification on `/v1/ingest/dispatch`; tenant from context as a string; idempotency key from the body; duplicate mount removed.
6. **B:** signed dispatch (body per B.2, `idempotency_key` in the body, no tenant/callback fields); Bearer removed.
7. **A:** signed callbacks to the configured URL only, no redirects.
8. **B:** callback verification + tenant/task binding + bounded metrics; Bearer removed (X-3, X-4).
9. **A + B:** signed task status endpoint; backend reconcile operation; cancel removed (X-2).
10. **A:** close user routes: signed-only `/v1/ai/{chat,explain,generate-questions,retrieve,tree,read}`; remove `TenantMiddleware`; string tenant context on touched paths; legacy routes behind the disabled flag.
11. **B:** `ai.use` / `ai.questions.generate` permissions; `/ai/chat`, `/ai/explain`, `/ai/generate-questions` endpoints with per-user limits.
12. **B:** combined compose, `db-init` roles script, migrations run as owner roles.
13. **B (+A where needed):** real two-service test suite covering Part C, runnable with one command against the compose stack.
14. M3 completion report against Part C.

Commits 1–4 change no behaviour across the boundary on their own. From 5 to 8 the ingestion path is broken by design until both halves land. It is broken today anyway (X-1, X-3, N-4).

---

## Part E — Decisions still needed

1. **E.1 Redis unavailable → fail closed (503)** for service authentication. *Recommended.* The alternative is a per-process fallback, which would allow replays across replicas.
2. **E.2 Legacy AI-service user routes in M3:** unmount behind a default-off development flag now, delete in M4. *Recommended.* The alternative is leaving them mounted until M4: they are authenticated only by a JWT signed with `"dev-secret"` unless configured, so effectively forgeable.
3. **E.3 Proxied operations:** chat, explain, generate-questions only. Retrieve, tree and read are closed but not proxied until M5. *Recommended.*
4. **E.4 Responses unsigned in M3**, relying on the internal network now and TLS in M6. *Recommended*, recorded as residual risk.
5. **E.5 Real-service tests in hosted CI:** they need both repositories in one workflow. If cross-repository checkout is available, add a `boundary-gate` job; otherwise M3 exits on a documented local run and the hosted job moves to M6. *Your call.*
6. **E.6 Permissions forwarded:** only those the backend checked for the operation (normally one). *Recommended*, per plan §19.2.
7. **E.7 Tenant-less (platform) ingestion jobs** are not operable through the tenant API in M3. *Recommended.*
