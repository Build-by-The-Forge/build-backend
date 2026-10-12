# Backend production-image hardening: inspection findings and implementation plan

Status: **approved with conditions (§5); C1a to C3a done; C3b to C10 to run as
one coordinated implementation under the unified brief of 2026-10-12 (§3.3).**
Section 3 is the canonical roadmap: completed work in §3.1, the re-inspection of
both repositories in §3.2, the remaining phases in §3.4. The approval does not
cover pushing, merging or deploying. Anything that departs from this plan, or
hits a stop condition (§3.6), is brought back for a decision.

## 0. Baseline

| Item | Value |
|---|---|
| Repository | `build-backend` |
| Branch | `feat/learning-content` (not switched) |
| HEAD | `51cb7534a0ffe08afdb74969c8e34908f2d1cb1e` (2 commits ahead of `origin/feat/learning-content`: 14f49be, 51cb753; unpushed) |
| Uncommitted changes | none |
| Untracked | `docs/backend-audit-2026-09-28.md` (left alone); `t -q` (ignored by the `*-q` pattern in `.gitignore`) |
| Image inspected | `build-m3-backend:latest`, built 2026-10-11 11:46 UTC. The only later commit (51cb753) changes CI only, so the image matches HEAD's application code |
| Local test baseline | `pytest -q` (SQLite, local venv, Python 3.12.10): **1122 passed, 89 skipped** |
| Linux test baseline | Same suite on a clean `git archive HEAD`, Python 3.13.16, exactly the image's package versions, project not installed: **1122 passed, 89 skipped**; `pip check` clean |

Evidence was gathered by reading files, inspecting the existing image (`docker run --network none`), running pip-audit 2.10.1 in a throwaway container, linting a clean `git archive HEAD` export in a Linux container, and replaying ai-service's `ci.yml` locally. Hosted CI history could not be read: `gh` is not installed and both repositories are private.

## 0a. Phase 0 baseline (measured 2026-10-12)

Run on backend `93a1e4f` (51cb753's code plus this document) and ai-service `68da1cc` (`feat/m3-boundary`), both images built fresh. Implementation files unchanged.

| Gate or check | Result |
|---|---|
| `scripts/m3_boundary_gate.sh` | **exit 0** (12:14 to 12:46 UTC) |
| Boundary suite | 176 passed, 3 deselected |
| Redis-down case (boundary C11) | 3 passed |
| M6 production boot | backend and ai-service both boot |
| M6 unsafe configuration | 9 of 9 reported "refused" (exit status only; see below) |
| ai-service offline OCR (paddle 3.3.1 image) | both checks OK. This is the first boundary-gate run of the OCR-stack work |
| Lint, ruff 0.17.0 (the Phase 0 set's), clean export | 47 findings (40 automatically fixable); 198 files would be reformatted. **KB1, unchanged** |
| Unit suite, Linux Python 3.13.16, exactly the Phase 0 versions, project not installed | 1122 passed, 89 skipped; `pip check` clean |
| Backend image `pip freeze` | 69 distributions. Six resolved newer than on 2026-10-11: filelock 4.1.1, platformdirs 4.13.0, pydantic 2.14.1, pydantic-core 2.50.1, pytest-env 1.8.0, virtualenv 21.14.7. Floating dependencies drifted within a day (D1); C4 pins this set. |

**What each M6 refusal actually prints.** The gate checks only the exit status, so this was measured separately: each case was run with the same compose services and production configuration, and the final error recorded.

| Case | Category | Actual message | Matches its label? |
|---|---|---|---|
| backend: missing JWT secret | settings `ValidationError` | `AUTH_JWT_SECRET is required when app_environment is 'production'` | yes |
| backend: plain-http AI_SERVICE_URL | settings `ValidationError` | `AI_SERVICE_URL must be an absolute https URL` | yes |
| backend: equal directional secrets | settings `ValidationError` | `BACKEND_TO_AI and AI_TO_BACKEND secrets must differ` | yes |
| backend: known development secret | settings `ValidationError` | `BACKEND_TO_AI_SECRET must be at least 32 bytes` | **no.** The case's value, `build-internal-service-secret`, is 29 bytes, so the length rule fires before the known-value rule. The known-value rule is never exercised by the gate. |
| backend: wildcard CORS | settings `ValidationError` | `CORS_ALLOWED_ORIGINS must list exact origins, not wildcards` | yes |
| ai-service: missing secret | settings `ValidationError` | `BACKEND_TO_AI_SECRET must be at least 32 bytes` | **no.** The case sets an *empty* value, and ai-service treats only an absent variable as missing; compose always sets it. |
| ai-service: short secret | settings `ValidationError` | `AI_TO_BACKEND_SECRET must be at least 32 bytes` | yes |
| ai-service: plain-http callback URL | settings `ValidationError` | `BACKEND_CALLBACK_URL must use https` | yes |
| ai-service: deterministic model | settings `ValidationError` | `MODEL_PROVIDER=deterministic is refused when APP_ENVIRONMENT=production` | yes |
| *control:* backend, valid production config, `POSTGRES_URL=not-a-url` | `sqlalchemy.exc.ArgumentError` | `Could not parse SQLAlchemy URL` | not a security refusal, yet today's `refuses()` would count it as one (D7 confirmed) |

**Fixes verified (measurement only):**
- the backend case with `BACKEND_TO_AI_SECRET=test-only-backend-to-ai-secret-0123456789abcdef` (a listed development value of 47 bytes) refuses with `BACKEND_TO_AI_SECRET is a known development value`;
- the ai-service case with the variable truly absent (`--entrypoint env ... -u BACKEND_TO_AI_SECRET`) refuses with `BACKEND_TO_AI_SECRET is required when APP_ENVIRONMENT=production`.

Changing the backend case's input removes the only M6 coverage of the backend's 32-byte minimum for service secrets, so C1a adds an explicit backend short-secret case. ai-service already has one.

**Known baseline failures after Phase 0:** KB1 (backend lint) and KB2 (ai-service legacy `ci.yml`), as expected. The two M6 cases above are gate defects, not failures, and C1a fixes them.

## 1. Findings

**Confirmed defects** are reproduced with evidence. **Recommendations** are improvements without a demonstrated failure.

### Confirmed defects

| # | Finding | Severity | Evidence |
|---|---|---|---|
| D1 | **Dependencies are unpinned, and local, CI and image environments differ.** `pyproject.toml` has lower bounds only (`fastapi>=0.115.0`, ...), so every build resolves the newest releases. | High | 11 packages differ between the local venv and the image: SQLAlchemy 2.0.52 vs **2.1.4** (a minor version), FastAPI 0.141.1 vs 0.143.0, Starlette, pydantic, alembic, asyncpg, uvicorn, opentelemetry-sdk, ruff, mypy. Python is 3.12 locally, 3.13 in CI and the image. |
| D2 | **The hosted backend `ci.yml` test job cannot pass: Lint fails before the tests run.** | High | On a clean `git archive HEAD` in Linux, both ruff 0.17.0 (what CI installs today) and 0.6.9 (the pre-commit pin) report 47 lint errors (39 import-order, 3 line-length, 2 import-position, 2 unused-variable, 1 unused-import) and **198 files** that would be reformatted. The unit tests (1122) therefore cannot run in hosted CI (hosted history unseen, U1). |
| D3 | **Development and test tools ship in the production image.** | Medium | The Dockerfile runs `pip install .[dev]`. The image contains pytest, pytest-asyncio, pytest-cov, pytest-env, respx, ruff, mypy, pre-commit and aiosqlite (69 distributions in total). |
| D4 | **The boundary gate depends on D3.** The `boundary-tests` service in `deploy/compose.m3.yml` runs `python -m pytest` *inside the production image* (`image: build-m3-backend`). | Medium (it blocks fixing D3) | `deploy/compose.m3.yml:177-202`. If dev tools are simply removed, the gate breaks. |
| D5 | **The container runs as root.** | Medium | There is no `USER` in the Dockerfile; `id -un` in the image prints `root`; `/app` is `root 755`. |
| D6 | **`/outbox` does not exist in the image.** Docker therefore creates the `outbox` named volume owned by root. | Medium (it blocks non-root) | `ls /outbox` in the image fails. The backend appends to `/outbox/emails.jsonl` (`app/infrastructure/email/outbox_email_sender.py:29-30`), and the boundary tests read sign-up and invitation codes from it (`boundary/conftest.py:36,169`). A non-root backend could not write there. |
| D7 | **The M6 startup gate can pass for the wrong reason.** In `scripts/m6_production_startup.sh:49-52`, `refuses()` counts *any* failure of `import app.main` as "unsafe configuration refused". | High (gate integrity) | `import app.main` in the image without configuration fails with `sqlalchemy.exc.ArgumentError: Could not parse SQLAlchemy URL`, an unrelated error that would satisfy every `refuses` check. A missing module or a permission error after hardening would also count as a pass. |
| D8 | **The image ships non-runtime files.** `COPY . .` brings `tests/`, `boundary/`, `pg_smoke/`, `deploy/` (compose, SQL, env example), `docker-compose.yml`, `Dockerfile`, `README.md`, `.pre-commit-config.yaml`, pip's `build/` leftovers and two stray files. | Low | Listing of `/app` in the image (21 entries). `.dockerignore` does exclude `.env*`, `deploy/m3.env`, databases, logs and `docs/`, and **no secret was found in the image**: `deploy/db-init/init-roles.sql` uses psql variables; compose reads every secret from `deploy/m3.env`. |
| D9 | **The installed project package is empty.** The Dockerfile runs `pip install .[dev]` before the code is copied, so the installed `build-backend` holds metadata only and no `app` modules. The app imports only because `/app` is the working directory. | Low | `importlib.metadata.distribution('build-backend').files` lists `pyproject.toml` and `egg-info` files only. |
| D10 | **`requirements.txt` is a stale second manifest**, unpinned and different from `pyproject.toml`. It lists `python-jose[cryptography]`, `passlib[bcrypt]`, `email-validator`, `python-dotenv` and `greenlet`, which nothing imports, and the README tells developers to install it. | Medium | Through it, the local venv has python-jose 3.5.0 (**CVE-2026-85394**, no fix) and ecdsa 0.19.2 (**PYSEC-2026-1325**, no fix). Neither is imported by `app/`, `alembic/`, `scripts/`, `tests/`, `boundary/` or `pg_smoke/`. |
| D11 | **Nothing audits the backend's dependencies or image.** | Medium | `.github/workflows/ci.yml` has no pip-audit, image audit or OS-level scan. The image audited clean today (pip-audit: 69 distributions, no known advisories), but with D1 that only describes the build of 2026-10-11. |
| D12 | **The hosted boundary gate tests the wrong ai-service by default.** `ai_service_ref` defaults to `main`, and the gate runs only on push to `main` (and manually). | Medium | `.github/workflows/boundary-gate.yml:16,39`. Per the Phase 1 record (launch blocker 1), ai-service `main` does not contain the M3 boundary work, which is on `feat/m3-boundary` and not yet merged. |
| D13 | **A stray committed file:** `tatus --short` (24 KB of captured `git diff --check` output, committed in 372fe3e). `.gitignore` has a `*-q` pattern that exists only to hide another stray file (`t -q`). | Low | No secrets in either. |
| D14 | **ai-service's old `ci.yml` fails as configured** (question 6 below). | Medium | Replayed locally with its own settings (PostgreSQL 15, Redis 7, no migrations, `pytest --cov`, no path). Bare `pytest` also collects `scripts/run_smoke_test.py`, whose two functions error at setup: **904 passed, 1 skipped, 2 errors** gives a non-zero exit. Its upload step expects a `coverage.xml` that the step never generates. |

### Recommendations (no demonstrated failure)

| # | Recommendation |
|---|---|
| R1 | Pin the base image to the Python patch version the image already uses (`python:3.13.16-slim`), and its digest. Today `python:3.13-slim` floats. |
| R2 | Pin `pip` in the Dockerfile and CI (`pip install --upgrade pip` is unpinned in both). |
| R3 | Add OS-level image scanning (Debian packages), which pip-audit does not cover, e.g. Trivy, pinned by version. |
| R4 | Run a weekly scheduled audit: once pins are fixed, new advisories appear without any commit. |
| R5 | Remove dead tool configuration: `[tool.black] target-version = ["py314"]` (black is not installed or used); `[tool.mypy] python_version = "3.13"` (mypy is not run in CI). Whether mypy should be enforced is a separate decision. |
| R6 | Cross-repo: ai-service also runs as root (no `USER` in its Dockerfile). The same treatment should follow there, as its own step. |
| R7 | A production start with a missing or malformed `POSTGRES_URL` is refused, but only by a raw `sqlalchemy.exc.ArgumentError` at import (verified with a valid production configuration and `POSTGRES_URL=not-a-url`), not by a configuration check with a clear message like the other strict-environment settings. Worth adding to `Settings` as a separate change, with its own M6 case. |
| R8 | Cross-repo (found 2026-10-12): ai-service pins only direct dependencies (its `requirements.txt` has 15 direct entries), so transitive versions resolve at build time, the same class of problem as D1. This belongs to an ai-service workstream. |
| R9 | Cross-repo (found 2026-10-12): ai-service's CI security job installs `bandit` and `pip-audit` unpinned, and its Dockerfile uses a floating `python:3.12-slim` and an unpinned pip (see D-B). |

### Unresolved questions (need a decision or evidence I could not get)

| # | Question |
|---|---|
| U1 | Hosted CI history for both repositories is not visible from this machine. Are the backend `ci.yml` `test` job (D2) and the ai-service `ci.yml` (D14) already red on GitHub? I expect so, from the local evidence. |
| U2 | Is the local Windows venv expected to stay on Python 3.12? `requires-python = ">=3.12"` while CI and the image use 3.13. The plan keeps `>=3.12` and checks pins against both. |
| U3 | Windows App Control on this machine blocks some newly installed native libraries (seen with ujson and paddle 3 in ai-service). Re-syncing the backend venv to the pinned set (e.g. SQLAlchemy 2.1.4, pydantic-core, asyncpg wheels) may hit it. The plan makes the Linux container the authoritative test environment and treats the local venv as best effort. |
| U4 | Where should the ai-service `ci.yml` removal be committed: on `feat/m3-boundary` (unpushed, so it travels with the OCR work) or on its own small branch? |
| U5 | Should the boundary gate also run on pull requests (about 60 minutes per run), or stay on push to `main` plus manual runs? |
| U6 | **Resolved: `scripts/seed_futa.py` is excluded from the image.** Searched both repositories' workflows, compose files, scripts, Dockerfiles and docs: nothing runs it. Only design and completion documents mention it. The M2 completion report (item 4) records that it uses a synchronous engine with a SQLite default, is "likely not runnable against PostgreSQL", and "should become a deterministic academic bootstrap/import". The deployed bootstrap path is `scripts/provision_tenant.py`. If production seeding is needed later, it becomes an explicit, controlled one-off operation, not a script shipped in the web image. `scripts/check_schema_drift.py` (CI, run from the checkout) is also excluded. |
| U7 | **Resolved:** C: had 38.6 GB free on 2026-10-12, with Docker's disk image compacted to 17.9 GB. The verified `ai-service:p331` image was kept. The precondition (at least 15 GB, ideally 18 to 20 GB) is re-checked before Phase 0 and before every image build. |

## 2. Answers to the seven questions

**1. Which dependency file is authoritative, and how will drift be detected?**
`requirements.txt` (runtime) and `requirements-dev.txt` (`-r requirements.txt` plus dev and test tools) become the **only** dependency declaration, used by the image, CI and local development. They hold exact pins for the **full** dependency closure, not just direct dependencies.

`pyproject.toml` stops declaring dependencies: its `dependencies` and `[dev]` lists are removed, and it keeps the project name and tool configuration (pytest, ruff, mypy). Nothing installs the project any more: the image runs from `/app`, and tests import `app` from the repository root. **Verified:** on a clean export of HEAD in Linux Python 3.13.16, with exactly the image's package versions and the project not installed, the unit suite gives 1122 passed, 89 skipped, the same as the local baseline. A second list in `pyproject.toml` would only be something else that can drift.

Drift is caught by a unit test (`tests/unit/test_dependency_declarations.py`, modelled on ai-service's):
- every requirements line is an exact `==` pin, with markers evaluated for Linux and Windows;
- `pyproject.toml` declares no dependencies, and keeps its project metadata and tool configuration;
- **imports to distributions:** every import in `app/`, `alembic/` and `scripts/provision_tenant.py` is either standard library (`sys.stdlib_module_names`), local (`app`, `scripts`), or provided by a distribution pinned in `requirements.txt`. The import-to-distribution mapping comes from the installed metadata (`importlib.metadata.packages_distributions()`), so `jwt` → PyJWT and `argon2` → argon2-cffi need no hand table. Imports in `tests/`, `pg_smoke/` and `boundary/` may also use `requirements-dev.txt`;
- **closure:** for every pinned distribution, each requirement in its own metadata (markers and requested extras evaluated) is itself pinned. Exact direct pins are not enough if transitive versions can still move;
- no dev tool is in `requirements.txt`;
- the Dockerfile's runtime stage installs `requirements.txt` only.

**Install workflows verified in C4:**
- `pip install -r requirements.txt` in a fresh Linux container, then `pip check` and `import app.main` under a development configuration;
- `pip install -r requirements-dev.txt` in a fresh Linux container, then the unit suite and `pg_smoke`;
- the same file on the Windows venv, best effort (U3);
- the image build.

`pip check` runs in the image during the image checks.

The closure is generated on Linux, where the image runs. Platform-specific dependencies get environment markers, so the same files install on Windows: `uvloop` (required by `uvicorn[standard]` only off Windows) gets `; sys_platform != "win32"`, and `colorama` (pytest, Windows only) gets `; sys_platform == "win32"`. The declaration test evaluates markers for both platforms, as ai-service's now does.

**Which versions get pinned:** a fresh resolution on the day C4a is implemented, in `python:3.13.16-slim`. It is not the Phase 0 set or any earlier image's set, because floating dependencies drifted within a day (§0a). Differences from the Phase 0 set are listed in the C4a commit, and nothing is upgraded deliberately. The pinned set then has to pass the unit suite, the postgres-gate replay and the full gate before it is committed.

**2. How will production dependencies be separated from development and test tooling?**
A multi-stage Dockerfile:
- `runtime` installs `requirements.txt` and copies only runtime files;
- `test` builds on `runtime`, adds `requirements-dev.txt` plus `tests/`, `boundary/`, `pg_smoke/`, `scripts/` and `pyproject.toml` (pytest configuration);
- the **last** stage, `production`, is `FROM runtime`, so a plain `docker build .` can never produce the test image.

Compose's `boundary-tests` service builds `target: test` as `build-m3-backend-test` (fixes D4). Backend services build `target: production`. An image check asserts that pytest, ruff, mypy, pre-commit, respx and aiosqlite are absent from the production image.

**3. How will the image run as non-root without breaking migrations, permissions or health checks?**
A fixed system user (`app`, UID/GID 10001, no login shell, no home), switched to with `USER` at the end of `runtime`. The details:
- **Code:** copied root-owned and not writable by `app`, so a compromised process can't rewrite it.
- **Migrations:** `alembic upgrade head` (the `backend-migrate` service) only reads `alembic/` and `alembic.ini` and talks to PostgreSQL, so it needs no writable path. If `DATABASE_URL` were missing, alembic would fall back to `sqlite:///./build.db` in `/app`, and that now fails instead of silently creating a file.
- **Outbox:** `/outbox` is created in the image, owned by `app` (fixes D6). Docker gives a newly created named volume the ownership of the image directory. An `outbox` volume that already exists locally keeps root ownership: the gate always starts with `down -v`, and a developer runs `docker compose -f deploy/compose.m3.yml down -v` once.
- **Port:** 8000 is not privileged.
- **Health check:** the compose health check uses Python's `urllib` and needs no privileges.
- **Writes:** `PYTHONDONTWRITEBYTECODE=1` is already set and the boundary suite runs with `-p no:cacheprovider`, so nothing writes into `/app`. The M6 script writes `/tmp/server.log`, and `/tmp` stays writable.
- **Test stage:** `test` starts `FROM runtime` (which ends as `app`), switches to `USER root` only to install `requirements-dev.txt` and copy the test files, then ends with `USER app`, so the boundary tests run as the same unprivileged user.

**4. Which files enter the image, and how are unnecessary files and secrets excluded?**
Production image: `app/`, `alembic/`, `alembic.ini` and `scripts/provision_tenant.py`. The last is the operator's tenant-provisioning CLI (`python -m scripts.provision_tenant`); the boundary tests and `pg_smoke/test_provisioning_cli.py` use it. Explicit `COPY` lines replace `COPY . .`, so new files in the repository never reach the image by default. `.dockerignore` stays as a second layer: it keeps `.env*`, `deploy/m3.env`, databases and logs out of the build context altogether. An image check asserts that `/app` contains exactly that allowlist, and that the image has no `.env`, `m3.env` or `tests/`.

**5. Where will package and image audits run, and what governs exceptions?**
- **Dependencies:** a new `security` job in backend `ci.yml`, with pip-audit 2.10.1 (pinned) on `requirements.txt` and `requirements-dev.txt` (`--no-deps`; the files are a full closure).
- **The built image, Python packages:** a new `image` job builds `production`, runs the image checks, and runs `scripts/audit_image_packages.py`, the same logic as ai-service, on the image's own `pip freeze`.
- **The built image, operating system (approved):** Trivy scans the image's Debian packages. pip-audit and Trivy are not interchangeable: pip-audit covers Python distributions and Trivy covers OS packages, so Trivy runs with `--pkg-types os` and Python advisories stay pip-audit's job. Details:
  - Trivy is pinned by version and image digest;
  - it fails on HIGH or CRITICAL advisories that have a fixed package (`--severity HIGH,CRITICAL --ignore-unfixed --exit-code 1`), and the full report at every severity goes to the job log;
  - exceptions go in `security/trivyignore.yaml`, each with an `id`, a `statement` (the reason) and an `expired_at` review date, after which it stops applying.
- **Schedule:** the security and image jobs also run weekly (R4).
- **Python exception list:** both pip-audit runs (requirements files and image) read `security/accepted-image-advisories.txt`. Each entry carries a review date as well as the reason (`<id> <package> <review-by YYYY-MM-DD>  # reason`). An entry past its review date fails the audit, like a stale entry, until it is re-assessed.
- **Exception policy, the same as ai-service's:** an exception is allowed only when no fixed release exists, or the fix is incompatible and that has been demonstrated. Each entry (Python or OS) needs the advisory ID, the package, a reason, a review date, and a written assessment in `docs/` that shows the vulnerable code is unreachable or not exploitable here. The audit fails on any advisory that isn't listed, and on any listed entry that no longer matches. No exceptions are needed today.

**6. What should happen to the old ai-service `ci.yml`?**
**Remove it.** It is broken (D14) and fully superseded: `backend.yml` ("AI Service CI") runs on a superset of its triggers (every pull request, not only those into `main`, plus push to `main`) and adds PostgreSQL 17 and Redis 8, migrations, migration review, the 80% coverage floor, quality and security jobs, the image build, the offline OCR check and the image audit. Deleting it changes no gate except the failing one, **but only where `backend.yml` runs the full suite.** On ai-service `main`, `backend.yml` still runs `pytest tests/integration tests/contracts` only, so there the old `ci.yml` is the only thing running the unit tests. The full suite with the 80% floor arrived in 2641c73, which is on `feat/m3-boundary` alone. So the removal is an isolated ai-service change on its own branch, created from `feat/m3-boundary`, and it merges only after `feat/m3-boundary` is on `main` and its `backend.yml` has passed in hosted CI. Branch protection should then require `backend.yml`'s jobs instead of the old `test` check; whether it currently requires that check needs looking at on GitHub. Not part of the backend branch.

**7. How will hardening be validated against the boundary gate and startup-security tests?**
- **Order:** the M6 checks are tightened *first* (C1a, C1b), so that every later commit is validated by checks that can't pass for the wrong reason. Each `refuses` case must pass three conditions:
  - exit non-zero;
  - fail in the right **category**: a settings validation error (pydantic `ValidationError` for `Settings`), not an import, URL or permission error;
  - print its own message, all of which exist today:

  | Case | Required message |
  |---|---|
  | backend: missing JWT secret | `AUTH_JWT_SECRET is required` |
  | backend: plain-http AI_SERVICE_URL | `AI_SERVICE_URL must be an absolute https URL` |
  | backend: equal directional secrets | `secrets must differ` |
  | backend: short service secret (new case: `BACKEND_TO_AI_SECRET` of 31 bytes) | `BACKEND_TO_AI_SECRET must be at least 32 bytes` |
  | backend: known development secret (input changed to `test-only-backend-to-ai-secret-0123456789abcdef`, 47 bytes) | `BACKEND_TO_AI_SECRET is a known development value` |
  | backend: wildcard CORS | `CORS_ALLOWED_ORIGINS must list exact origins` |
  | ai-service: missing secret (input changed: variable unset in the container, not empty) | `BACKEND_TO_AI_SECRET is required` |
  | ai-service: short secret | `AI_TO_BACKEND_SECRET must be at least` |
  | ai-service: plain-http callback URL | `BACKEND_CALLBACK_URL must use https` |
  | ai-service: deterministic model | `MODEL_PROVIDER=deterministic is refused` |

  Each `boots` case must answer health.
- **Image checks travel with the change they guard:** `scripts/check_backend_image.sh` is created in C5b (allowlist, no dev tools, no secrets, `pip check`) and extended in C6 (non-root, code not writable, `/outbox` ownership). Each commit's negative control runs the new checks against the previous image, where they must fail.
- **Baseline:** a full local gate run on the current HEAD (Phase 0) records the expected results.
- **After every image-affecting commit:** the full `scripts/m3_boundary_gate.sh` must give the same results as the baseline, covering the boundary suite, the Redis-down case (boundary C11), all M6 cases (11 at baseline, 12 from C1a) and the ai-service offline OCR check. The new image checks also run.

## 3. Change sequence

### 3.1 Done (on `chore/backend-image-hardening`, unpushed)

| Step | Commits | Result |
|---|---|---|
| Plan | 93a1e4f | This document |
| Phase 0 | 41ce621 (record) | Gate green on the unchanged code; two M6 cases refused for the wrong rule (§0a) |
| C1a | a57d668 | M6 refusals count only a settings `ValidationError` with the case's own message; 12 lines (2 boots, 10 refusals); failures show the rule's message or the exception class, never configuration values |
| C1b | 58b7eec, 2f66bc0 | `scripts/m6_refusal_selftest.sh` (bad database URL, missing module, unreadable config, redacted boot log), run by the gate on every run |
| C1b fix | f3bb396 | Self-test cleanup survives interruption: asks Docker for the run's images, removes fixture containers first (never via the base tag), sweeps leftovers at start |
| C2 | cb97f23 | `ruff format` (0.17.0), 198 files, identical AST and comments, reproducible exactly |
| C3a | 939be32, c978c07, 2f0f7ab, f3aa82e | Final newline in `pyproject.toml`; `known-first-party` for app, scripts, tests, pg_smoke, boundary (classification was per file before); imports sorted (141 findings, 139 files); unused import removed |

**Baseline after C3a (f3aa82e).** These are re-run after every later phase, not assumed:
- unit suite 1122 passed, 89 skipped;
- `ci.yml` postgres-gate replay: migrations to head, single head, round-trip, schema-drift check, pg_smoke 20 passed + 1 xfailed, Redis counter 7, service auth 30, signed callbacks 46;
- full boundary gate: boundary 176, Redis-down 3, M6 12, self-test 4, offline OCR both OK;
- ruff 0.17.0 and 0.6.9: format clean, 4 lint findings (C3b).

ruff 0.17.0 is used throughout; the pre-commit hook still pins 0.6.9 until C4c.

### 3.2 Re-inspection before the unified run (2026-10-12, read-only)

**Backend (f3aa82e).**
- The tree is clean apart from the untracked `docs/backend-audit-2026-09-28.md`.
- `Dockerfile`, `.dockerignore`, both compose files, both workflows, `requirements.txt` and `.pre-commit-config.yaml` are unchanged since the original inspection. D1, D3 to D6 and D8 to D13 therefore still stand. D2 is down to 4 findings (C3b), and D7 is fixed (C1a, C1b).
- The backend has no image publication step, so "audit before publish" requires nothing for the backend today. If a publish step is added later, it must depend on the image job (C9b).

**The four C3b findings, read in context:**
- **`app/application/common/uow.py:77-78` (E402).** Two content repository imports were appended above `ContentUnitOfWorkPort` (125e77c, 3e7c1bf). Both modules import only `app.domain.*`, so moving them into the import block cannot create a cycle.
- **`tests/integration/content/test_content_asset_api.py:18` (F841).** `admin_headers` is never used. The admin setup itself is needed, because `seed_tenant_context(admin_id, "admin")` creates tenant A, but no step acts as the admin.
- **`tests/integration/content/test_content_source_api.py:85` (F841).** `reg_source_id` is never used. The platform source's visibility is asserted by code in steps 9 and 10. Step 11 checks the negative direct GET (a foreign lecturer gets 403 on tenant A's source); there is no positive direct GET of the platform source, which is what the ID would serve.

**ai-service (`feat/m3-boundary`, 68da1cc).**
- The local remote-tracking ref `origin/feat/m3-boundary` is also at 68da1cc. Not fetched; the remote is not re-checked here.
- The Dockerfile's two stages use `python:3.12-slim` (floating); `pip install --upgrade pip` is unpinned; there is no `USER`, so it runs as root (R6).
- The requirements files pin direct dependencies only (`requirements.txt`: 15 direct entries), so transitive versions resolve at build time (R8).
- `backend.yml`'s image job runs build → offline OCR → package audit → publish (on `main` only), the right order. Its security job installs `bandit` and `pip-audit` unpinned (R9).
- Pre-commit: ruff v0.1.8, black 26.3.1, mypy v1.7.1. The legacy `ci.yml` is still present (A1, out of scope).

**Tools and environment.**
- Local images: shellcheck 0.10.0, gitleaks 8.30.1, actionlint (tagged `latest`; its version is recorded when used), `python:3.13-slim` (3.13.16), postgres:17, redis:8.
- 28.0 GB free on C:.

### 3.3 How the remaining work runs (unified brief, 2026-10-12)

C3b to C10 run as one coordinated implementation, in order, without an approval pause between commits. Every rule below still holds:
- **Commits:** separate, reviewable commits, one concern each. Files are combined only where splitting would leave the repository inconsistent, and the commit message says so. Nothing is squashed; earlier commits are not amended.
- **Branch and remote:** no reset, rebase, force checkout or discarded change. No push, merge, release, deploy or remote change. The untracked audit documents in both repositories are left alone.
- **No weakening:** tests, security checks, the coverage floor, audits and boundary checks are not weakened. There are no blanket suppressions; any exception names the package, advisory, reason, scope and review date.
- **Secrets:** never in code, command output, build arguments, image layers, logs or fixtures.
- **Deletion:** nothing is removed except what a step itself creates (the self-test fixtures, the gate's own `down -v`, temporary images built for a check). No other images, volumes, caches or data are deleted.
- **Tools:** ruff 0.17.0. pip-audit 2.10.1. Trivy and gitleaks pinned by version.
- **Per phase:** its focused checks run before each commit. Its record (commits, files, checks, results, limitations) is kept for the final report.
- **Baselines:** if one changes, the cause is identified, as an intended and documented change or a regression, before continuing.

### 3.4 Remaining phases

**C3b: the four remaining lint findings** (closes KB1)

| # | Commit | Change | Acceptance and checks | Rollback |
|---|---|---|---|---|
| C3b-1 | `fix(backend): unit-of-work imports at the top of the module` | Move the two imports at `uow.py:77-78` into the import block; nothing else. | E402 cleared. With imports removed, the AST is unchanged. `app.application.common.uow` and every module importing it import cleanly in fresh interpreters. Unit suite. | Revert |
| C3b-2 | `test(backend): drop an unused header in the asset API test` | Remove `admin_headers = ...` only; the admin registration and tenant seeding stay. | F841 cleared; the test passes; unit suite. | Revert |
| C3b-3 | Per decision D-A | **Recommended:** use `reg_source_id`. A foreign-tenant lecturer's direct GET of the platform source returns 200: the positive counterpart of step 11 (`test(backend): foreign tenants can read a platform source directly`). If the API refuses it, stop and report; that is a behaviour question, not a lint fix. **Alternative:** remove the assignment. | F841 cleared. The test passes, and the test count is unchanged (the assertion goes inside the existing test). Unit suite. | Revert |
| C3b-4 | `chore(backend): ignore the mechanical commits in git blame` | `.git-blame-ignore-revs` listing cb97f23 (format) and 2f0f7ab (import sorting), full SHAs. | The file lists both. | Revert |

After C3b: `ruff check` is clean with 0.17.0 and 0.6.9, closing KB1. Full gate and postgres-gate replay.

**C4: dependency declarations and tool versions**

| # | Commit | Change | Acceptance and checks | Rollback |
|---|---|---|---|---|
| C4a | `build(backend): exact pins for the full dependency closure` | See below. These files must change together, so they are one commit. | Each file installs in a fresh container; `pip check` clean. Unit suite, postgres-gate replay and full gate on the pinned set. Local venv re-synced, best effort (U3), after a `pip freeze --all` backup. | Revert; restore the venv from the backup |
| C4b | `test(backend): dependency declarations cannot drift` | The declaration test (answer 1): exact pins; closure; imports mapped to distributions through installed metadata, with standard-library and local imports excluded; no dev tool in the runtime file; `pyproject.toml` declares none. It runs in the existing `ci.yml` test job. The Dockerfile assertion is added in C5a, once the stage exists. | **Negative controls:** an unpinned line, a missing transitive pin and an undeclared import each make it fail. | Revert |
| C4c | `build(backend): pre-commit uses the pinned ruff` | `.pre-commit-config.yaml`: ruff-pre-commit v0.6.9 → v0.17.0 (tag verified); hook arguments unchanged. | `pre-commit run --all-files` changes nothing, since the tree is already 0.17.0-clean. | Revert |
| C4d | `docs(backend): install from the pinned requirements` | README development setup. | The commands work in a fresh container. | Revert |

C4a in detail:
- **Files:** `requirements.txt` (runtime closure) and `requirements-dev.txt` (`-r requirements.txt` plus the dev and test closure), exact pins with platform markers (uvloop off Windows, colorama on Windows only).
- **`pyproject.toml`:** its dependency lists are removed; metadata and tool configuration stay.
- **Stale entries:** python-jose, passlib, email-validator, python-dotenv and greenlet are dropped as direct entries, unless the import scan finds a use.
- **Installs:** the Dockerfile installs `requirements-dev.txt`. The image keeps the same contents, because this commit is about pinning only. `ci.yml` installs `requirements-dev.txt`.
- **Versions:** a **fresh resolution on the day**, in `python:3.13.16-slim`, not the Phase 0 set. Differences from Phase 0 are listed in the commit and re-tested. Nothing is upgraded deliberately.

**C5: production image separate from the test image**

| # | Commit | Change | Acceptance and checks | Rollback |
|---|---|---|---|---|
| C5a | `build(backend): runtime-only production image, separate test image` | See below. These files must change together for the gate to work. | `docker build .` gives the runtime image. Full gate green, with boundary tests from the test image. Migrations (`backend-migrate`) and provisioning (`scripts.provision_tenant`, called by the boundary tests) work. | Revert |
| C5b | `test(backend): production image checks` | `scripts/check_backend_image.sh <image>`, called by the gate. See below. | Passes on the C5a image. **Negative controls:** it fails on the Phase 0 image, and on an image built `FROM` production with one extra file in `/app`. | Revert |
| C5c | `build(backend): the gate tests images built from the checked-out sources` | Revision labels on both images. The gate refuses to run if the backend or test image's revision differs from the checkout. CI never tags the test target for publication. | **Negative control:** a stale test image stops the gate before any test runs. | Revert |

C5a in detail:
- **Stages:** `runtime` / `test` / `production` (last).
- **Image contents:** an explicit `COPY` allowlist: `app/`, `alembic/`, `alembic.ini` and `scripts/provision_tenant.py`. `seed_futa.py` is excluded (U6).
- **Compose:** `boundary-tests` builds `target: test` as `build-m3-backend-test`; the backend services build `target: production`.
- **Gate:** it builds `boundary-tests` explicitly.
- **Declaration test:** gains the Dockerfile assertion.

C5b checks that:
- `/app` holds exactly the allowlist;
- no dev tools are present (pytest, ruff, mypy, pre-commit, respx, aiosqlite, coverage);
- there is no `.env`, `m3.env` or test directory;
- `pip check` passes;
- installed versions equal `requirements.txt`.

**C6: non-root production container**

| # | Commit | Change | Acceptance and checks | Rollback |
|---|---|---|---|---|
| C6 | `build(backend): run as an unprivileged user (final stage)` | See below. | See below. | Revert; locally `docker compose -f deploy/compose.m3.yml down -v` if a volume was created by the non-root image |

The change:
- user `app`, UID and GID 10001, no login shell, no home;
- code and site-packages stay root-owned and are not writable by `app`;
- `/outbox` is created owned by `app`, mode 0750;
- `USER app` at the end of `runtime` and `test`, with `USER root` only for the test stage's install;
- the check script gains the non-root checks;
- a README line on the one-time `down -v`.

Acceptance:
- **User:** effective UID ≠ 0 in both images.
- **Writes:** writing under `/app` or site-packages as `app` fails.
- **Outbox:** written by the backend and read by the boundary tests (same UID, files 0644).
- **Operation:** migrations run. Health checks stay green. `docker stop` ends the backend cleanly within compose's grace period (uvicorn is PID 1 and handles SIGTERM). Temporary files go to `/tmp`; logs go to stdout.
- **Gate:** the full gate on fresh volumes matches the baseline.
- **Negative control:** the check fails on the C5c image (root).
- **No compensation:** no broader permissions or capabilities were added to make a path work.

**C7: build toolchain**

| # | Commit | Change | Acceptance and checks | Rollback |
|---|---|---|---|---|
| C7a | `build(backend): pin the base image` | `FROM python:3.13.<patch>-slim@sha256:<digest>`, resolved and recorded at implementation time, not copied from earlier observations; every stage derives from it. A Dockerfile comment states how to upgrade (new patch tag and digest, then the full gate). | Two builds of the same commit give the same package set; gate green. | Revert |
| C7b | `build(backend): pin pip` | `pip==<version>` in the Dockerfile and `ci.yml`, replacing `pip install --upgrade pip`. No setuptools or wheel step remains once the project is not installed (C4a); if one does, it is pinned too. | Builds and the CI replay use the pinned pip; unit suite in the container. | Revert |

The ai-service toolchain is decision D-B.

**C8: audit tooling and policy** (run locally; wired into CI in C9)

| # | Commit | Change | Acceptance and checks | Rollback |
|---|---|---|---|---|
| C8a | `test(backend): audit the pinned dependencies` | `scripts/audit_dependencies.py`: pip-audit 2.10.1, `--no-deps`, on `requirements.txt` (runtime scope, gating) and `requirements-dev.txt` (dev scope, reported separately). It reads `security/accepted-advisories.txt` (dated entries) and fails on unaccepted, stale or expired entries. | Clean today. **Negative controls:** adding `python-jose==3.5.0` (CVE-2026-85394) fails it, as does a stale entry or an expired date. | Revert |
| C8b | `test(backend): audit the packages in the production image` | `scripts/audit_image_packages.py`, taken from ai-service with review dates added, on the production image's own `pip freeze --all`. | Clean today. **Negative controls:** unaccepted, stale, expired. | Revert |
| C8c | `test(backend): scan the image's OS packages` | Trivy pinned by version and digest: `--pkg-types os --severity HIGH,CRITICAL --ignore-unfixed --exit-code 1`, full report logged. `security/trivyignore.yaml` is empty, or holds entries with `statement` and `expired_at`. Trivy covers Debian packages, which pip-audit does not, so it is not redundant. | Run locally on the C7a image, results recorded. Fixable HIGH or CRITICAL findings stop the run and are reported: the remedy (base image or apt) is a decision, not an exception. | Revert |

The policy goes in a short `docs/` section: no exceptions today; any future one needs evidence, affected version, exposure, mitigation and a review or removal condition.

**C9: CI integration and ongoing checks**

| # | Commit | Change | Acceptance and checks | Rollback |
|---|---|---|---|---|
| C9a | `ci(backend): dependency audit job` | A `security` job runs C8a. It needs the network, which is kept apart from the offline OCR check. | actionlint; job commands replayed locally. | Revert |
| C9b | `ci(backend): build, check and audit the production image` | An `image` job: build `production` → C5b check → C8b audit → C8c scan. Failures name the package, version, advisory and policy. The workflow notes that any future publish step must `needs:` this job. | actionlint; job commands replayed locally; a failing audit fails the job. | Revert |
| C9c | `ci(backend): weekly audits` | A `schedule` (weekly) and `workflow_dispatch` on the same workflow, running `security` and `image`. No second pipeline. | actionlint. | Revert |
| C9d | Per decision D-D | gitleaks 8.30.1 (pinned) over the repository in CI. | Clean on the branch. **Negative control:** a planted fake token in a scratch copy is detected. | Revert |

Secrets: the backend build uses no build secrets. The gate's check that `OCR_MODELS_TOKEN` is absent from the ai-service image stays.

**C10: AI-service boundary-gate integration**

| # | Commit | Change | Acceptance and checks | Rollback |
|---|---|---|---|---|
| C10a | `ci(backend): boundary gate checks out the intended ai-service revision` | See below. | actionlint. A local run of the gate script logs both SHAs. The token step is simulated with an empty token: it fails with the message and prints nothing secret. | Revert |
| C10b | `ci(backend): boundary gate runs on pull requests` | Pull requests, push to `main`, and manual. No path filters, so a required check is never skipped. The header notes branch protection. | actionlint. | Revert |

C10a in detail:
- **Default:** `ai_service_ref` defaults explicitly to `feat/m3-boundary`, per D-C, until the ai-service branch is merged through the approved process. The header documents the one-line switch to `main`, made only after that merge is verified.
- **Traceability:** the job prints the resolved ai-service and backend SHAs.
- **Token:** the missing-token check stays. A failed checkout gets a diagnostic follow-up step (`if: failure()`) that names the likely causes and never prints the token.
- **Fresh images:** CI builds fresh images on every run (`up --build`, the explicit test-image build from C5a, the revision check from C5c), so nothing extra is needed. This is confirmed and noted in the record.

**After C10, if D-E is accepted:** `chore(backend): remove the stray "tatus --short" file` (the old C11). `t -q` is untracked and stays; it's yours to remove.

### 3.5 Final regression (after the last commit)

1. ruff lint and format with 0.17.0, and pre-commit (all hooks).
2. Unit suite against 1122 passed / 89 skipped, with any difference explained.
3. postgres-gate replay: migrations, schema drift, pg_smoke, Redis, service auth, signed callbacks.
4. Production image: build, startup, content check, non-root check.
5. Dependency audit, image package audit, OS scan.
6. Full boundary gate: boundary 176, Redis-down 3, M6 12, self-test 4, offline OCR.
7. gitleaks over every commit on the branch (`51cb753..HEAD`), plus a final diff review.
8. `git status` in both repositories: all intended work committed; untracked files untouched; ai-service unchanged unless D-B says otherwise.

A gate is reported as passed only if it completed and passed.

### 3.6 Stop and report, instead of guessing, when

- the branch or HEAD does not contain the approved baseline;
- a file, workflow or build target differs materially from this plan;
- a change needs a product or business decision;
- a security control would have to be weakened to pass;
- a migration or domain-behaviour change appears necessary (for example, C3b-3 if the API refuses the direct GET);
- the ai-service revision the gate needs is unavailable or incompatible;
- a required hosted check cannot be meaningfully reproduced locally;
- disk space or Docker state makes further testing unsafe (below 15 GB free);
- C8c finds fixable HIGH or CRITICAL OS advisories.

Routine implementation details are resolved without stopping.

### 3.7 Out of scope

- Pushing or merging either repository.
- Creating or publishing the OCR model release.
- The legacy ai-service `ci.yml` (A1), which needs its own authorisation after the replacement is established on `main`.
- Audit documents and other untracked files.
- Phase 2 document ingestion.
- Reopening finished work without evidence of a regression.
- Treating local validation as proof of hosted CI or deployment readiness.
- The ai-service follow-ups: non-root (R6), transitive pins (R8), pinned CI audit tools (R9), and its toolchain (D-B), unless D-B includes it.

### 3.8 Final handover

The final report covers:
- starting and ending commits and branch;
- every commit, grouped C3b to C10;
- files and controls changed per phase;
- unit, postgres-gate, boundary, image, lint, pre-commit, audit and secret-scan results;
- exceptions, skips, environment limits and accepted advisories;
- whether CI was verified locally only or also hosted;
- remaining blockers (ai-service merge and ref switch, hosted secrets `AI_SERVICE_READ_TOKEN` and `AI_SERVICE_REF` if used, the OCR model release);
- confirmation that nothing was pushed or merged and that unrelated work was preserved.

**After you push: hosted validation.** Local results do not stand in for it. The hosted runs to inspect are:
- `ci.yml`: `test`, `postgres-gate`, `security` and `image`;
- `boundary-gate`: a manual run, plus its pull-request run, against the ai-service revision under test.

Each run is read for its actual results, not just its status.

**Definition of done:** C3b to C10 are committed as reviewable changes; every reproducible gate passes; the remaining hosted-only prerequisites are listed; the branch is ready for human review and a separately authorised push or merge.

## 4. Risks

| Risk | Mitigation |
|---|---|
| A fresh resolution in C4a picks up a release that behaves differently from the Phase 0 set. | Differences are listed in the commit and the full regression runs on the pinned set before the commit; a failure stops the run (§3.6) rather than being worked around. |
| The positive direct-GET assertion in C3b-3 fails because the API forbids it. | That is a behaviour question, so the run stops and reports it (§3.6); the alternative is to remove the variable (D-A). |
| C8c finds fixable HIGH or CRITICAL OS advisories in the base image. | The run stops; the remedy (a newer patch image or an apt upgrade) is a decision, not an exception entry. |
| The hosted gate checks out a moving branch (`feat/m3-boundary`). | The job prints the resolved ai-service SHA; D-C offers a SHA pin instead. |
| Pinning to the image's versions changes the *local* environment (SQLAlchemy 2.0 to 2.1 among others). | Already de-risked: the unit suite passes on exactly those versions in Linux (1122 passed, 89 skipped, project not installed), and Phase 0 runs the gate on them. Anything that fails locally only is investigated, not worked around. |
| The C2 mechanical formatting diff is large (198 files) and can conflict with other branches built on `feat/learning-content`. | It is behaviour-neutral, isolated in one commit and listed in `.git-blame-ignore-revs`. Other branches can run the same `ruff format` before rebasing. If you'd rather not, C2 and C3 can be dropped and CI lint narrowed instead (not recommended: it leaves D2's lint gate meaningless). |
| Non-root breaks a write path the inspection missed. | The only write in `app/`, `scripts/` and `alembic/` is the outbox (searched for `open(..., "w"/"a")`, `write_text`, `write_bytes`, `mkdir`, `tempfile`). The full gate on fresh volumes exercises the outbox, migrations, provisioning and health. |
| App Control blocks the ruff binary that pre-commit downloads for C2, so commits fail at the hook. | Hooks are never skipped. If it happens, I stop and ask; options are allowing the binary, or running pre-commit in a Linux container against the same working tree. |
| App Control blocks native wheels in the re-synced local venv. | The Linux container is authoritative (U3). Before re-syncing, `pip freeze --all` the venv so it can be restored exactly. |
| Disk space (C: has 6.7 GB free) for repeated image builds. | Remove intermediate images after each check; prune only build cache and images created in this work. |

## 5. Decisions and conditions (2026-10-12)

| # | Decision |
|---|---|
| 1 | Plan approved with these conditions. It is committed as the first commit on `chore/backend-image-hardening`, and Phase 0 is recorded before any implementation file changes. |
| 2 | C2 and C3 approved, as separate commits. C2 must be proven formatter-only; lint fixes are reviewed for behaviour changes, especially in security checks and error handling. That is why C3 is split into automatic (C3a) and hand-reviewed (C3b) fixes. Gates already failing at baseline are tracked (KB1, KB2), not promised green after every commit. |
| 3 | Requirements files are the source of truth, with exact pins for the full closure. `pyproject.toml` keeps metadata and tool configuration only. The drift test covers import versus distribution names, standard-library and local imports, and transitive closure. Every supported install workflow is verified (answer 1). |
| 4 | Trivy approved for OS packages, alongside pip-audit for Python. Both pinned; thresholds and dated exceptions as in answer 5. |
| 5 | The old ai-service `ci.yml` is removed in a separate ai-service change (A1), from `feat/m3-boundary`, merged only after the replacement is established on `main`. |
| 6 | Boundary gate runs on pull requests, pushes to `main` and manually (C10b). |
| 7 | `seed_futa.py` excluded (U6, resolved with evidence). |
| 8 | Disk precondition met (U7). Phase 0 does not start below the threshold. |
| Also | Startup-check negative tests cover a bad database URL, a missing module and a permission failure, and check category and message, not exit status (C1a, C1b). The test image is built from the checked-out sources and checked by revision, never published, and the final image stage is runtime-only and non-root (C5a, C5c, C6). OCR raw per-line corpus results stay out of Git. |

### Decisions of 2026-10-12 (unified brief for C3b to C10)

| # | Decision |
|---|---|
| B1 | C3b to C10 run as one coordinated implementation in separate commits, without approval pauses between commits, under the rules in §3.3 and the stop conditions in §3.6. |
| B2 | Dependency pins come from a fresh resolution at C4a time, not from an earlier image (answer 1). The pre-commit ruff is aligned to 0.17.0 (C4c). |
| B3 | The boundary gate uses `feat/m3-boundary` until the ai-service branch is merged through the approved process, and `main` only after that is verified (C10a). |
| B4 | The legacy ai-service `ci.yml` stays out of scope (A1). |
| B5 | Final regression includes secret scanning (§3.5). |

### Open decisions before the run (decided below)

| # | Question | Recommendation |
|---|---|---|
| D-A | C3b-3, the unused `reg_source_id`: add the positive direct-GET assertion it was presumably for, or remove the assignment? | **Add the assertion** (a foreign-tenant lecturer reads the platform source directly: 200). It is the missing counterpart of step 11. If the API refuses, the run stops and reports. |
| D-B | C7 for ai-service: pin its base images and pip in this run on a separate ai-service branch, or leave them to an ai-service workstream? | **Leave them to an ai-service workstream**, together with R6, R8 and R9. Changing ai-service mid-run would put a second, unmerged ai-service branch next to `feat/m3-boundary`, which is the revision the gate is meant to test. |
| D-C | C10a: default the gate to the branch `feat/m3-boundary`, or to its commit SHA (68da1cc)? | **The branch, with the resolved SHA printed in every run.** A SHA pin is more reproducible but needs a backend commit for every ai-service change until the merge. |
| D-D | C9d: add gitleaks to CI, or keep secret scanning local (final regression only)? | **Add it to CI** (pinned 8.30.1). Nothing scans committed files for secrets today, and the brief asks for proof that none leak. |
| D-E | Remove the stray committed `tatus --short` file (the old C11) after C10? | **Yes**, as its own `chore` commit. It is captured terminal output with no secrets. |

**Decided 2026-10-12** (the run is authorised on these terms):

| # | Decision | Conditions |
|---|---|---|
| D-A | Add the check | First verify the API's authorisation and response contract for a platform source. Assert the success status and the resource's identity. If the API does not support it, stop and report; application behaviour is not changed to clear lint. |
| D-B | Defer | ai-service toolchain, transitive pins, unpinned CI tools and non-root stay follow-up work (R6, R8, R9). No ai-service source, branch or document is changed in this run. |
| D-C | The branch, resolved once | `feat/m3-boundary` is resolved to a concrete commit at the start of each gate run. That SHA is printed and recorded, and every gate step in the run uses that same revision. The gate refuses to continue if the ai-service revision changes mid-run (the image's revision label from C5c must equal the recorded SHA). |
| D-D | Add gitleaks to CI | Pinned to 8.30.1, with the download verified by checksum. Scan tracked content with a supported configuration and redaction (no secret values in logs). Test the failure path. |
| D-E | Remove the file | First confirm that nothing references it (tooling, scripts, docs, CI) and that it is captured output; then delete it in its own commit. |

Run safeguards added with the decisions:
- the asset test keeps its tenant-A setup;
- no dependency is removed on "appears unused" alone: indirect imports and runtime paths are checked first;
- the gate tests a fresh test image and also verifies the production image;
- audits and secret scanning fail closed;
- backend changes only on `chore/backend-image-hardening`;
- stop on any behaviour change, unclear security implication, unexpected ai-service revision, unforeseen migration or application change, or gate that cannot run reliably.

## 6. Review log

Seven review rounds have shaped this plan: five before approval, one after Phase 0, and one for the unified brief. Each checked every claim against the repository, the image or a reproduction, and changed the plan where it was wrong or incomplete.

| Round | Found | Changed |
|---|---|---|
| 1 | C1's negative control could not show the defect. Image checks arrived after the changes they guard. A Linux-generated closure would not install on Windows (uvloop, colorama). The test stage could not install packages as `app`. Formatting with a newer ruff would leave the pre-commit hook on 0.6.9. No disk precondition. | Verified that all nine M6 refusal messages exist, and named them. Image checks moved into C5 and C6, each with a negative control against the previous image. Platform markers, `USER root` for the test stage's install, aligned ruff versions, the disk precondition (U7), and the scripts question (U6). |
| 2 | The gate script never rebuilds the `boundary-tests` image (it sits in a profile), so a split image would be tested stale. Exact pins in `pyproject.toml` would be a second, driftable list. C1's negative control and the ruff-pre-commit tag were unverified. | Explicit test-image build in the gate (C5). Verified that a production config with `POSTGRES_URL=not-a-url` fails import for an unrelated reason (C1 control), that ruff-pre-commit `v0.17.0` exists, and that the unit suite passes in Linux with the project not installed (1122/89). That made the requirements files the only declaration. Added R7. |
| 3 | C4 and C7 bundled separable changes. App Control could block the new ruff binary at the commit hook. Two audits would have had two exception lists. Where the authoritative test run happens was undefined. | Split C4b and C7a/C7b. Commit rules added (one concern per commit; hooks never skipped; Linux container authoritative; nothing pushed). One shared exception list. A risk row for the hook. |
| 4 | Phase 0 rebuilds with floating dependencies, so it would not test the 2026-10-11 versions the plan proposed to pin. Hosted validation after push was missing. D2 overstated what was observed. | Pins are now exactly the Phase 0 freeze (the set the baseline gate tested). Hosted validation steps added. D2 qualified by U1. Final consistency sweep (commit numbers, versions, references): clean. |
| 5 | Approval conditions; `seed_futa.py` usage; ai-service `main`'s `backend.yml` runs only integration and contract tests, so the legacy `ci.yml` is the only unit-test run there. | Decisions recorded (§5). U6 and U7 resolved. Split C1, C3, C5, C9 and C10 further. Startup-check category plus three negative controls. Test-image revision check. Trivy scope and thresholds. Dated exceptions. Known-baseline-failure tracking. A1 based on `feat/m3-boundary`. |
| 6 | Phase 0 measured (§0a). The gate is green, but two M6 refusals fire for the length rule instead of the rule they name. | C1a corrects both inputs and adds a backend short-secret case (12 M6 lines); acceptance criteria rewritten to match the measured messages. Submitted for approval before implementation. |
| 7 | The unified brief (C3b to C10) and a read-only re-inspection of both repositories at f3aa82e / 68da1cc. | §3 rewritten as the canonical roadmap: completed work, re-inspection findings, run rules, remaining phases with commits and checks, final regression, stop conditions, out of scope, handover. Pins switch to a fresh resolution at C4a time. New R8 and R9 (ai-service). Open decisions D-A to D-E. |
