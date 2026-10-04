# Phase 1 — Milestone 2: Completion Report

**Milestone:** M2 — Production Identity and Tenant Foundation (backend)
**Status:** Complete (2026-10-04)
**Governing documents:** `docs/PHASE_1_PLAN.md` (Revision 1), `docs/phase1-m2-identity-design.md` (accepted 2026-10-02, decisions D1–D9), `docs/phase1-m2-schema-drift-investigation.md`

## 1. Verdict and evidence

M2 is complete. The reviewed state is `feat/learning-content` at `ca54e3d`; `main` is `f529abd` (merge of PR #8), whose second parent is `ca54e3d` and whose tree is identical to it (`git diff ca54e3d f529abd` is empty), so `main` carries exactly the reviewed code.

| Gate | Result |
|---|---|
| Full backend suite (SQLite, at `ca54e3d`) | 697 passed, 7 skipped (the skips are the real-Redis tests, which run in the gate) |
| PostgreSQL gate, local, fresh PostgreSQL 17.10 + Redis 8.10.2, at `ca54e3d` | empty database → head: pass; single head `0022`: pass; latest-migration round trip: pass; ORM/schema drift: none unexpected; `pg_smoke`: 15 passed, 1 expected failure (known `device_id` defect, §7); real-Redis tests: 7 passed |
| PostgreSQL gate, hosted (GitHub Actions `postgres-gate`, PR #8) | Pass |
| Hosted `test` job | Not run: its `lint` step fails first on the known ruff version mismatch (§7). Unrelated to M2 behaviour; the same suite passes locally. |

Suite size went from 324 tests at the start of M2 to 697.

## 2. What M2 delivered

33 commits, `efbd706` … `ca54e3d` (2026-10-02 → 2026-10-04), each verified on fresh PostgreSQL 17 (and Redis 8 where relevant) before it was committed.

**Credentials and sessions**
- Argon2id password hashing with rehash-on-login, timing-safe unknown-user path, 12–128 character passwords (`efbd706`).
- Signed HS256 access tokens with `kid` rotation (current + previous key), `iss`/`aud`/`sub`/`sid`/`typ`/`iat`/`nbf`/`exp`/`jti`; no signing key may default outside development (`6975b9b`, `a7f6d1f`). Tokens carry user and session only; tenant, membership and role are read from the database on every request.
- Per-request session and account-status enforcement: logout, revocation, expiry and disablement take effect on the next request (`4ae454f`).
- Opaque refresh tokens stored as SHA-256, rotated on every use, reuse (including a lost concurrent race) revokes the whole session; 14-day idle / 30-day absolute lifetime; authenticated logout and logout-all (`3648b28`).

**Recovery and verification**
- Password reset by out-of-band code (`EmailSender` port; development outbox; no provider wired in staging/production), never returned by the API, single use, earlier codes invalidated, all sessions ended on reset, blocked accounts refused (`b7a66ca`, `5bc2db5`).
- Authenticated change-password that ends other sessions by default (`99dce87`).
- Email verification by one-time code (`793a591`); unverified accounts may sign in but get no tenant access (D4, `8031d23`).

**Abuse controls and audit**
- Redis rate limits per IP and per email, and temporary sign-in locks, kept separate from account status; attempts counted before the password check so concurrent bursts admit only the limit; explicit Redis-failure mode with no fail-open (`56e4f21`, `f40fc73`).
- Secrets redacted at the logging boundary; database errors no longer echo parameters (`2329715`); expected client errors logged at INFO (`1b2e23f`).
- `login_events` and `security_events` recorded in their own transactions, with no secrets or attempted emails (`1954a27`).

**Tenancy**
- `memberships.user_id` foreign key, refusing to migrate over orphans (`721b0cc`).
- Tenant invitations: hashed codes, one pending invitation per address, atomic acceptance by the invited verified account only, never changing an existing membership (`0778a23`, `0ddda4b`).
- Per-tenant email-domain join (D5): off by default, exact domains only, student role only, revoked members cannot rejoin, concurrent joins converge on one membership (`b93bda8`, `b9864c1`).
- Idempotent operator command for a tenant and its first owner; password never on the command line; concurrent runs cannot duplicate (`3966a67`).
- Membership permissions and the role grant hierarchy owner > admin > faculty_admin > hod > lecturer > student; member management with re-checked caller role, no self-management, and a last-owner guard under row locks (`91e66dc`, `d460b48`).
- `GET /identity/memberships` for stateless tenant switching (`fb1b1a2`).

**Database integrity**
- Schema drift investigation and fix: the catalogue redesign had no migration, so every catalogue endpoint and question creation failed on a migrated database; migration 0019 corrects it (`7da689b`, `25038db`, `cd543d4`).
- PostgreSQL production-schema CI gate (`ff875b4`).
- Removed dead code: identity placeholders, `TenantResolver`, the unused domain `RefreshToken`, and the unused global role tables (D7, migration 0022) (`eb7e5e2`, `b2685c6`, `5a884d3`).
- Migrations never silently destroy data: 0018, 0019, 0022 and the downgrades of 0020/0021 refuse and report when rows would be lost (`ca54e3d`).

## 3. Design sequence (§9) against delivery

| # | Planned | Delivered |
|---|---|---|
| 1 | Argon2id, timing-safe login, password bounds | `efbd706` |
| 2 | Re-hash data migration | Dropped by D1 (no real accounts) |
| 3 | Signing-key configuration | `6975b9b` |
| 4 | Signed access JWT, single principal path | `a7f6d1f` |
| 5 | Per-request session/status enforcement | `4ae454f` |
| 6 | Rotating refresh tokens, reuse detection, authenticated logout | `3648b28` |
| 7 | Reset rework, EmailSender, change-password | `b7a66ca`, `5bc2db5`, `99dce87` |
| 8 | Email verification, D4 | `793a591`, `8031d23` |
| 9 | Rate limiting and temporary lock | `56e4f21`, `f40fc73` |
| 10 | Login/security events, log redaction | `2329715`, `1b2e23f`, `1954a27` |
| 11 | `memberships.user_id` FK (0018) | `721b0cc`, `8b3dc09` |
| — | Not planned: schema drift fix and CI gate | `7da689b`, `25038db`, `cd543d4`, `ff875b4` |
| 12 | `tenant_invitations` (+ D5 storage) | `0778a23` (0020), `b93bda8` (0021) |
| 13 | Provisioning command | `3966a67` |
| 14 | Membership APIs, permissions, grant hierarchy, last-owner guard | `91e66dc`, `0ddda4b`, `d460b48` |
| 15 | `GET /identity/memberships` (+ D5 join path) | `b9864c1`, `fb1b1a2` |
| 16 | Remove dead placeholders and `TenantResolver` | `eb7e5e2`, `b2685c6` |
| 17 | Drop global role tables (D7) | `5a884d3` (0022), `ca54e3d` |

## 4. Decisions D1–D9

| ID | Decision | Outcome |
|---|---|---|
| D1 | No real accounts → no re-hash migration | Applied |
| D2 | HS256 with `kid` rotation | Implemented, previous-key acceptance tested |
| D3 | Bearer access token; refresh token in device secure storage | Implemented (client contract: one refresh in flight per session, §7) |
| D4 | Unverified accounts sign in, no tenant access | Enforced before any tenant lookup |
| D5 | Invitation and per-tenant verified-domain join | Both implemented; domain join is eligibility for student only |
| D6 | Operator command now, admin API later | Command delivered; API deferred |
| D7 | Drop unused global role system | Done, with a data guard |
| D8 | Scoped roles deferred to Phase 2 | Respected: roles are tenant-wide; tenant-wide manage rights limited to admins and owners |
| D9 | Access 15 min; refresh 14-day idle / 30-day absolute | Implemented and configurable |

## 5. Test strategy (§8) coverage

| Area | Coverage |
|---|---|
| Hasher | Argon2id format, salting, wrong password, legacy/invalid formats rejected, rehash on outdated parameters |
| Tokens | Round trip; expired; not yet valid; wrong issuer/audience; wrong key; unknown/missing `kid`; algorithm swap; `alg: none`; refresh token as access; previous key accepted, retired key rejected |
| Refresh | Rotation; reuse revokes the session; expiry; concurrent refresh on PostgreSQL |
| Reset/verification codes | Single use, expiry, hash-only storage, concurrent consumption on PostgreSQL |
| Grant hierarchy / last owner | Role matrix; last-owner race on PostgreSQL (and shown to fail without the row lock) |
| Integration flows | Register → verify → sign in → protected route → refresh → logout → old token rejected; reset via outbox; D4 statuses; provisioning command end to end; invitation lifecycle |
| Attack / negative | Forged and tampered tokens; reused refresh; unauthenticated logout; reset code never in a response; brute force hits the limit; cross-tenant access; lecturer invites admin; admin demotes owner; member changes own role |
| **Partial** | Enumeration by timing: unknown emails get a dummy verification (asserted in tests), but there is no wall-clock timing measurement |

## 6. Deviations from the design

- The temporary lock is a short-lived Redis key, not `users.status = LOCKED`, so abuse controls never change account state (design §12).
- Tenant-scoped membership APIs take the tenant from the path (`/tenants/{slug}/...`); other routes keep `x-tenant-slug`.
- Migration numbers moved: 0019 became the catalogue correction, so invitations are 0020, join policies 0021, role-table removal 0022.
- Added beyond the plan: the catalogue drift fix and the PostgreSQL CI gate, both from the drift investigation.

## 7. Hardening backlog (separate from M2)

Known items, deliberately not part of M2:

1. **`device_id` at sign-in:** an unregistered client `device_id` violates `sessions.device_id`'s foreign key → 500. Recorded as a strict expected failure in the gate.
2. **Ruff alignment:** pre-commit pins ruff 0.6.9, CI installs the latest; the hosted `lint` step fails and blocks the `test` job.
3. **Email delivery:** no provider is wired in staging/production, so reset and verification emails are dropped there until one is chosen.
4. **`scripts/seed_futa.py`:** synchronous engine, SQLite default; likely not runnable against PostgreSQL. Should become a deterministic academic bootstrap/import.
5. **Client IP behind a proxy:** per-IP limits use the direct peer; needs a trusted-proxy configuration (M6), with the acceptance checks agreed during M2.
6. **Security-event reads:** no read API yet; needs `tenant_id` ownership semantics and tenant-scoped authorization.
7. **Registration enumeration:** registering an existing email returns 409; needs an explicit onboarding decision.
8. **Deferred catalogue models:** `curriculum_versions`, `course_prerequisites` (not migrated, marked in code).
9. **Other dead code:** `infrastructure/ai_gateway.py` stub, `infrastructure/redis.py`.
10. **PostgreSQL coverage:** grow the PostgreSQL integration suite beyond the smoke set; some older tests seed memberships inline in ways that may not be valid under PostgreSQL foreign keys.
11. **Client contract:** at most one refresh in flight per session (refresh reuse is treated as theft).
12. **Untracked file:** `docs/backend-audit-2026-09-28.md` remains untracked pending a decision.

## 8. Handover to M3

M2 provides, for every authorized request, a database-verified `TenantContext(user_id, tenant_id, membership_id, role)`, plus permissions resolved from the membership. M3 (Backend → AI security boundary) is to carry that context to AI-service in signed service requests, so AI-service never sees end-user tokens and never decides tenancy or authorization itself (design §3.7, plan M3).
