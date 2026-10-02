# Phase 1 — Milestone 2: Identity & Tenant Architecture (Design)

**Date:** 2026-10-02
**Status:** Proposal — for review. **No M2 code changes until approved.**
**Repositories inspected:** `build-backend` (branch `feat/learning-content`), `ai-service` (branch `main`)
**Governing documents:** `docs/BUILD_MASTER_PRD.md`; `docs/PHASE_1_PLAN.md` (Revision 1 governs); `docs/phase1-m1-identity-audit.md`

This milestone is **backend-only**. AI-service is not changed in M2; it consumes M2's output in M3 (signed trusted context) and M4 (legacy removal). Architectural rule preserved throughout: **Backend = identity + tenant + authorization authority. AI-service = intelligence subsystem operating on trusted backend context.**

This design deliberately does not "fix" authentication by swapping the fake token for a JWT. It covers the whole lifecycle: credentials, sessions and tokens, refresh, logout and revocation, password reset, verification, account status, tenant provisioning, membership provisioning, role assignment and revocation, and the context M3 hands to AI-service.

---

## 1. Current State

### 1.1 What is actually wired

| Concern | Wired implementation | Reality |
|---|---|---|
| Password hashing | `Argon2PasswordHasher` (`infrastructure/security/`) | Stores `"hashed:" + password` — plaintext. `argon2-cffi` installed, unused. |
| Access token | `JWTTokenService` (`infrastructure/security/`) | Returns literal `access:<user_id>`; `decode()` returns the token as `sub`; no signature, expiry, issuer, audience. |
| Principal | `core/dependencies.get_current_principal` | Accepts `Bearer <uuid>`, `access:<uuid>`, `refresh:<uuid>`; checks only that the user row exists — not status, not session. Rebuilds the whole DI container per request. |
| Refresh | `RefreshSessionHandler` | Refresh token = `refresh:<user_id>` (predictable), stored **plaintext** in `sessions.refresh_token_hash`, compared in plaintext; no rotation persisted, no expiry check. |
| Logout | `POST /identity/logout` | Takes `session_id` in the body, **no authentication** — anyone can revoke any session they can name. |
| Forgot password | `ForgotPasswordHandler` | Token returned in the HTTP response (account takeover). Lookup works only because the "hasher" is deterministic; a real salted Argon2 would break it. |
| Reset password | `ResetPasswordHandler` | Does not revoke existing sessions or other outstanding reset tokens. |
| Account status | — | `users.status`, `is_active`, `is_verified` exist; **never checked** at login or per request. |
| Email verification | — | `verification_tokens` table exists; no flow. |
| Enumeration | register / authenticate | Register returns 409 "User already exists". Login skips hashing for unknown emails (timing oracle) and validates password format only for existing users (422 vs 401). |
| Rate limiting / CORS / body limits | — | None in the backend. |
| Audit | — | `login_events`, `security_events`, `audit_logs` tables exist; nothing writes them. |
| `/identity/me` | own token parsing | Duplicates and diverges from `get_current_principal`. |

### 1.2 Tenancy and authorization (sound — preserve)

- `get_current_tenant_context`: tenant chosen by `x-tenant-slug`, **accepted only with an active membership in the database**; role comes from the membership.
- `core/authorization.py`: six roles (`owner`, `admin`, `faculty_admin`, `hod`, `lecturer`, `student`), ~30 permissions, `require_permission` on every domain router.
- `TenantContext(user_id, tenant_id, membership_id, role)` is already the exact shape M3 will sign and forward to AI-service.

### 1.3 Schema already present (migration 0001/0003) but unused

| Table | Useful columns | Used today |
|---|---|---|
| `users` | `status` (`ACTIVE`, `PENDING_VERIFICATION`, `LOCKED`, `DISABLED`, `DELETED`), `is_verified`, `is_active`, `version` | partly |
| `sessions` | `user_id`→users FK, `refresh_token_hash`, `ip_address`, `user_agent`, `expires_at`, `last_seen_at`, `revoked_at`, `device_id` | partly |
| `refresh_tokens` | `session_id`→sessions FK, `token_hash`, `expires_at`, `rotated_at`, `revoked_at` | **no** — a ready rotation ledger |
| `verification_tokens` | `user_id`, `token_hash`, `expires_at`, `consumed_at` | **no** |
| `password_reset_tokens` | `user_id`, `token_hash`, `expires_at`, `consumed_at` | yes |
| `login_events`, `security_events`, `audit_logs`, `devices`, `profiles` | — | **no** |
| `roles`, `permissions`, `role_permissions`, `role_assignments` | a second, **global** role system | **no** — conflicts with membership roles |
| `tenants` | `id` (UUID string), `slug` (unique), `status` | read-only |
| `memberships` | `tenant_id`→tenants FK, `user_id`, `role`, `status` (`active`/`archived`/`invited`), unique(`tenant_id`,`user_id`) | read-only |

### 1.4 Provisioning

- **Users:** `POST /identity/users` (public self-registration).
- **Tenants:** only `scripts/seed_futa.py` (creates FUTA + academic structure; not idempotent; creates **no owner user and no membership**) and test fixtures.
- **Memberships:** test fixtures only. Domain supports `create`, `change_role`, `archive`; repositories are read-only; no API.
- **Bootstrap gap:** there is no legitimate way to produce the first tenant administrator.

### 1.5 AI-service identity dependencies (unchanged in M2)

Mapped in `phase1-m1-identity-audit.md` §6. Additional M2-relevant points: AI tasks (`AIExecutionContext`, ingest schemas) carry `tenant_id` and `correlation_id` but **no actor/user**, and `tenant_id` comes from the request body, not verified context — M3 binds both to the signed context.

### 1.6 Tests

- `tests/test_identity.py` (15 tests), `tests/integration/auth/test_auth_dependency.py` (4).
- Most API tests obtain tokens by calling the real `/identity/authenticate` — good: they will keep working once tokens are real. One test hard-codes the fake `access:` format.
- Tenants/memberships are created directly as ORM models in fixtures.
- Missing: token tamper/expiry/alg tests, refresh reuse, disabled-account login, reset-token leakage, enumeration, rate limiting, invitation flows, cross-tenant membership attacks.

---

## 2. Problems (to be solved by M2)

1. Credentials are stored recoverably (plaintext).
2. Identity is forgeable from a user id; refresh tokens are predictable.
3. Session lifecycle is incomplete: no rotation, no reuse detection, unauthenticated logout, no revocation on password change, no status checks.
4. Password reset leaks the token and cannot work with a real hasher.
5. Account lifecycle (verification, lock, disable, delete) is modelled but not enforced.
6. No tenant or membership provisioning; no first-administrator bootstrap; `memberships.user_id` has no FK to `users`.
7. Two competing role systems (global `roles/*` vs membership roles).
8. No rate limiting, no auth audit trail, enumeration leaks.

---

## 3. Target Architecture

### 3.1 Credentials

- **Argon2id** via `argon2-cffi` (`PasswordHasher`, OWASP-recommended parameters; parameters in config). `check_needs_rehash` on successful login to upgrade parameters transparently.
- Password policy: keep ≥12 characters; add maximum length (e.g. 128) to bound hashing cost.
- **Timing-safe login:** when the email is unknown, verify against a fixed dummy hash so response time does not reveal account existence; validate password format before the user lookup.

### 3.2 Tokens and sessions

```text
login ──▶ session (sessions row)
           ├─ access token  : signed JWT, short-lived (~15 min)
           └─ refresh token : opaque, random, rotating (ledger in refresh_tokens)
```

**Access token** (JWT):

| Claim | Value |
|---|---|
| `iss` | backend issuer id |
| `aud` | backend API audience |
| `sub` | user id |
| `sid` | session id |
| `iat`, `nbf`, `exp` | ~15 min lifetime |
| `jti` | unique id |
| header `kid` | signing-key id (rotation) |

- **No tenant, role or permissions in the token.** Tenant is chosen per request (`x-tenant-slug`) and the membership/role is read from the database on each request — the existing, correct design. Role changes and membership revocation therefore take effect immediately, without waiting for token expiry.
- Validation: algorithm pinned (reject `none` and unexpected algorithms), signature, `exp`/`nbf` with small leeway, `iss`, `aud`.
- **Per-request session check:** principal resolution also verifies that the `sid` session is not revoked or expired and that the user status permits access. This costs one indexed lookup (the current code already loads the user) and gives immediate effect to logout, password reset, disable and lock.

**Refresh token**:

- 256-bit random opaque value; only its **SHA-256** is stored (deterministic lookup; Argon2 is unsuitable here and for reset/verification tokens).
- **Rotation** on every refresh, recorded in `refresh_tokens` (`token_hash`, `expires_at`, `rotated_at`, `revoked_at`).
- **Reuse detection:** presenting an already-rotated token revokes the entire session (token-theft signal) and records a security event.
- Session limits: idle timeout and absolute lifetime (e.g. 30 days) via `sessions.expires_at` / `last_seen_at`.

**Logout:** authenticated; revokes the caller's own session (`sid` from the token). Add "log out all sessions" for the user.

**Transport (React Native):** `Authorization: Bearer <access>`; refresh token kept in secure device storage and sent only to the refresh endpoint. No cookies for the mobile client (cookie handling can be added for a future web client).

### 3.3 Password reset

- Request: uniform response whether or not the email exists (no enumeration); 256-bit token, SHA-256 stored, ~30–60 min expiry, single use; previous outstanding tokens for the user invalidated.
- **Delivery out-of-band** through an `EmailSender` port; development implementation writes to a local outbox/log, never to the HTTP response.
- Completion: set new password, consume token, **revoke all sessions**, record a security event.

### 3.4 Email verification and account status

- Registration creates the user as `PENDING_VERIFICATION` and issues a verification token (same token scheme, `verification_tokens`).
- Status is the single source of truth (`users.status`); `is_active` / `is_verified` are kept consistent with it (or retired later).
- Enforcement on login and per request:

| Status | Login | Requests |
|---|---|---|
| `ACTIVE` | yes | yes |
| `PENDING_VERIFICATION` | per decision D4 | per decision D4 |
| `LOCKED` | no | no |
| `DISABLED` | no | no |
| `DELETED` | no | no |

### 3.5 Tenant provisioning

- **First tenant / first owner:** an idempotent operator command (`scripts/provision_tenant.py`), run with database credentials, that creates a tenant (or finds it by slug) and creates or links an **owner** user and an active owner membership. This is the bootstrap path BUILD lacks today; `seed_futa.py` keeps the academic structure.
- **Later tenants:** the same command. A platform-operator API is deferred (decision D6).
- Model unchanged: tenants are independent organizations; faculties, departments, programmes and memberships hang off `tenant_id`, so University A and B coexist without redesign.

### 3.6 Membership provisioning

- **Invitations** (new table `tenant_invitations`): `tenant_id`, `email`, `role`, `token_hash`, `invited_by_user_id`, `expires_at`, `accepted_at`, `revoked_at`, `status`. A separate table is used because invitees may not have accounts yet (`memberships.user_id` is non-nullable).
- **Accept:** an authenticated user whose **verified email** matches the invitation accepts it → active membership is created (or reactivated).
- **Role grant hierarchy:** `owner > admin > faculty_admin > hod > lecturer > student`. A member may invite or assign only roles **below** their own; only an owner can create another owner or admin. The **last active owner** cannot be removed or demoted.
- **Operations:** invite, list invitations, revoke invitation, accept, list members, change role, revoke (archive) membership, reactivate.
- **Student onboarding:** per decision D5.
- **Tenant switching:** stateless — `GET /identity/memberships` lists the caller's active memberships; the client sends `x-tenant-slug` per request; the backend verifies membership every time (existing behaviour).
- **New permissions:** `tenant.member.read`, `tenant.member.invite`, `tenant.member.manage`, `tenant.settings.manage`.

### 3.7 Boundary consumed by AI-service (M3)

M2 produces, for every authorized request, a verified `TenantContext(user_id, tenant_id, membership_id, role)`. In M3 the backend signs this context into AI requests (Revision 1 §19.2). AI-service never sees end-user tokens.

---

## 4. Database Changes (backend Alembic, after 0017)

All new migrations must run on both PostgreSQL and SQLite (lesson from B2: no dialect-only SQL without a guard).

| # | Change | Notes |
|---|---|---|
| 0018 | `memberships.user_id` → FK `users.id` | Fails if orphan rows exist; migration checks and reports first. |
| 0019 | Create `tenant_invitations` | Unique active invitation per (`tenant_id`, `email`); index on `token_hash`. |
| 0020 | Indexes: unique `refresh_tokens.token_hash`; index `password_reset_tokens.token_hash`, `verification_tokens.token_hash` | Lookup by hash. |
| 0021 *(optional, D1)* | Data migration: re-hash existing `hashed:<plaintext>` passwords with Argon2id | Plaintext is recoverable from the current format, so every existing row can be upgraded in place — and must be, promptly. |
| later *(D7)* | Drop the unused global `roles`, `permissions`, `role_permissions`, `role_assignments` | Destructive; separate, reviewed migration. |

No changes to `users`, `sessions`, `refresh_tokens`, `verification_tokens`, `password_reset_tokens` columns are required.

---

## 5. API Changes (backend)

| Method & path | Auth | Change |
|---|---|---|
| `POST /identity/users` | public, rate-limited | Creates `PENDING_VERIFICATION` user, sends verification; generic response for existing email (D5 dependent). |
| `POST /identity/verify-email` | public, rate-limited | Consume verification token. |
| `POST /identity/authenticate` | public, rate-limited | Returns `access_token`, `refresh_token`, `expires_in`, `session_id`. |
| `POST /identity/refresh` | refresh token | Rotates; returns new pair; reuse → session revoked. |
| `POST /identity/logout` | access token | Revokes own session (no `session_id` from the body). |
| `POST /identity/logout-all` | access token | Revokes all the user's sessions. |
| `POST /identity/forgot-password` | public, rate-limited | Always 200; **never returns the token**. |
| `POST /identity/reset-password` | reset token | Revokes all sessions. |
| `POST /identity/change-password` | access token | Re-auth with current password; revokes other sessions. |
| `GET /identity/me` | access token | Uses `get_current_principal` (single auth path). |
| `GET /identity/memberships` | access token | Caller's tenants and roles. |
| `POST /tenants/{slug}/invitations` | `tenant.member.invite` | Invite with role (grant hierarchy enforced). |
| `GET /tenants/{slug}/invitations`, `DELETE …/{id}` | `tenant.member.invite` | List / revoke. |
| `POST /invitations/accept` | access token, verified email | Accept → membership. |
| `GET /tenants/{slug}/members` | `tenant.member.read` | List members. |
| `PATCH /tenants/{slug}/members/{membership_id}` | `tenant.member.manage` | Change role (hierarchy, last-owner guard). |
| `DELETE /tenants/{slug}/members/{membership_id}` | `tenant.member.manage` | Archive membership. |

Removed: `/identity/me`'s private token parsing; `session_id`-in-body logout. Unchanged: all domain routes (`require_permission`), `x-tenant-slug` semantics.

---

## 6. Security Model

- **Secrets:** JWT signing key(s) and Argon2 parameters come from configuration; **no default signing key** — startup fails in `production`/`staging` without one (a small, M2-necessary slice of Workstream 6). Support a current and a previous key (`kid`) for rotation.
- **Rate limiting** (Redis-backed, per IP and per account): authenticate, register, forgot/reset password, verify, refresh, invitation create/accept. Progressive backoff; temporary `LOCKED` status after repeated failures, with automatic unlock.
- **Enumeration:** uniform responses and timing for login, forgot-password and (per D5) registration.
- **Audit:** write `login_events` (success/failure, ip, user agent) and `security_events` (password reset, password change, refresh reuse, lock/unlock, role change, membership revoke, invitation accept).
- **Logging:** never log passwords, tokens, token hashes, or `Authorization` headers; add a log-redaction test.
- **Fixture bypass:** tests authenticate through the real login endpoint or a test helper that issues real signed tokens with a test key — never the old string format.
- CORS, request-size limits and broader hardening remain in M6/Workstream 6, except the auth rate limits above.

---

## 7. Migration Strategy

- **Code:** replace the placeholder adapters behind the existing ports (`PasswordHasher`, `TokenService`) rather than rewriting `UserService`; delete the unused duplicate placeholders (`infrastructure/identity/password_hasher.py`, `token_service.py`), the dead `TenantResolver`, and the `/me` private parser.
- **Data:** if any real accounts exist (D1), migration 0021 re-hashes every `hashed:` password to Argon2id in place. Existing sessions and refresh tokens are invalidated at cut-over (all users re-authenticate once).
- **Compatibility:** none for the old token formats — they are the vulnerability. The one test that hard-codes `access:` is rewritten.
- **Order:** credentials and tokens first (they make everything else meaningful), then lifecycle, then provisioning.
- **Verification on every step:** fresh PostgreSQL 17 (backend chain 0001 → new head) and fresh SQLite; full backend suite.

---

## 8. Test Strategy

**Unit**

- Hasher: hash/verify, wrong password, rehash-on-parameter-change, legacy format rejected after migration.
- Tokens: valid; expired; `nbf` in future; wrong `iss`/`aud`; tampered payload; tampered signature; `alg: none`; wrong key; unknown `kid`; rotated (previous) key accepted.
- Refresh: rotation; reuse of a rotated token revokes the session; expired refresh.
- Reset/verification tokens: single use, expiry, hash-only storage.
- Role grant hierarchy and last-owner guard.

**Integration (fresh PostgreSQL 17; Redis 8 where rate limits apply)**

- Register → verify → login → access protected route → refresh → logout → old access token rejected.
- Password reset end-to-end via the outbox; token never in the response; all sessions revoked afterwards.
- Disabled / locked / deleted / pending users per D4.
- Provisioning CLI: creates tenant + owner idempotently; owner can log in and reach `/identity/tenant-context`.
- Invitation lifecycle: invite → accept (verified email) → member can act within role; wrong email cannot accept; expired/revoked invitation rejected.

**Attack / negative**

- Forged token from a user id; `refresh:` as access; tampered JWT; `alg: none`; reused refresh token; unauthenticated logout of another session; reset token in response; enumeration via status code or timing (bounded check); brute force hits the rate limit; cross-tenant: member of A sends `x-tenant-slug: B`; privilege escalation: lecturer invites admin, admin demotes last owner, member changes own role.

**Regression**

- Full backend suite (currently 324 passed) stays green; SQLite and PostgreSQL migration runs.

---

## 9. Implementation Sequence (narrow commits, each verified)

| # | Commit | Depends on |
|---|---|---|
| 1 | Argon2id hasher behind the existing port; timing-safe login; password max length | — |
| 2 | Data migration re-hashing legacy passwords (if D1 = yes) | 1 |
| 3 | Signing-key configuration with no default in production/staging | — |
| 4 | Signed access JWT with `sid`; validation; single principal path (`/me` uses it) | 3 |
| 5 | Per-request session and account-status enforcement | 4 |
| 6 | Opaque rotating refresh tokens with reuse detection; authenticated logout / logout-all | 4 |
| 7 | Password reset rework: hashed tokens, `EmailSender` port + outbox, no token in response, session revocation; change-password | 6 |
| 8 | Email verification flow and status rules (D4) | 7 |
| 9 | Auth rate limiting (Redis) and temporary lock | 1 |
| 10 | `login_events` / `security_events` recording; log-redaction test | 6 |
| 11 | Migration 0018: `memberships.user_id` FK | — |
| 12 | Migration 0019 + domain/repo: `tenant_invitations` | 11 |
| 13 | Provisioning CLI (tenant + owner, idempotent) | 1, 11 |
| 14 | Membership APIs and new permissions; grant hierarchy; last-owner guard | 12 |
| 15 | `GET /identity/memberships` (tenant switching) | 14 |
| 16 | Remove dead identity placeholders and `TenantResolver` | 4 |
| 17 | (D7) Drop global role tables | review |

Stop after each commit's verification; M2 is complete when the M2 slice of the Phase 1 test matrix (§8) passes on fresh infrastructure.

---

## 10. Risks / Decisions Required

### Decisions

| ID | Decision | Recommendation |
|---|---|---|
| D1 | Do any real (non-test) accounts exist in any backend database? | If yes: migration 0021 re-hashes in place. If no: skip 0021 and drop legacy rows. |
| D2 | JWT signing: symmetric (HS256) or asymmetric (ES256/EdDSA + JWKS)? | **HS256 with `kid` rotation**: only the backend verifies user tokens (AI-service uses service HMAC per Revision 1). Revisit if another verifier appears. |
| D3 | Token transport for the mobile client | Bearer access token + refresh token in secure storage; no cookies. |
| D4 | Can `PENDING_VERIFICATION` users log in? | Allow login, but block invitation acceptance and tenant-scoped actions until verified. Requires an email provider choice (outbox in development). |
| D5 | Student onboarding | Staff roles: invitation only. Students: invitation **or** per-tenant verified email-domain join (e.g. `@futa.edu.ng`, configurable, default off) — decide whether to include domain-join in M2. |
| D6 | Who creates tenants? | Operator CLI now; platform-admin API deferred. |
| D7 | The unused global `roles`/`permissions`/`role_assignments` tables | Drop in a separate reviewed migration; membership roles are the only role system. |
| D8 | Scoped roles (`hod`/`faculty_admin` limited to a faculty/department, PRD §60 "Scope") | Out of M2; design the scope columns in Phase 2 with the academic catalogue. Roles stay tenant-wide in M2. |
| D9 | Access/refresh lifetimes | Access 15 min; refresh idle 14 days, absolute 30 days. |

### Risks

- **Per-request session lookup** adds one indexed query per request; acceptable, and required for immediate revocation. Cacheable later if needed.
- **Email delivery** is a new external dependency; mitigated by the `EmailSender` port and a development outbox.
- **Migration portability** (PostgreSQL + SQLite) — every new migration is verified on both, per B2.
- **Cut-over** invalidates all existing sessions; acceptable pre-launch.
- **Scope creep** into authorization redesign (D8) or platform administration (D6) — explicitly deferred.
- **Secret handling** overlaps M6; only the JWT-key requirement is pulled forward because M2 is meaningless without it.
