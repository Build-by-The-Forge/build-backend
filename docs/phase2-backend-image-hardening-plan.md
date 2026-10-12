# Backend production-image hardening: inspection findings and implementation plan

Status: **proposal, approved with conditions on 2026-10-12 (§5).** The approval
covers the sequence in §3 under the conditions in §5. It does not cover running
every item automatically: each step is verified before it is committed, and
anything that departs from this plan is brought back for a decision. The
inspection that produced it was read-only: no file in `build-backend` or
`ai-service` was changed, no branch was switched, nothing was pushed.

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

**Which versions get pinned:** exactly the set the Phase 0 baseline resolves. Phase 0 rebuilds from HEAD, whose floating requirements pick up today's newest releases, so its `pip freeze` is recorded and becomes the pins. That way the pinned set is the one the baseline gate actually tested. Supporting evidence for the jump from the local venv: the 2026-10-11 image's set (SQLAlchemy 2.1.4 and the rest) already passes the unit suite on Linux. If Phase 0 resolves anything newer than that set, C4 re-runs the suite on it before committing.

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
  | backend: known development secret | `is a known development value` |
  | backend: wildcard CORS | `CORS_ALLOWED_ORIGINS must list exact origins` |
  | ai-service: missing secret | `BACKEND_TO_AI_SECRET is required` |
  | ai-service: short secret | `AI_TO_BACKEND_SECRET must be at least` |
  | ai-service: plain-http callback URL | `BACKEND_CALLBACK_URL must use https` |
  | ai-service: deterministic model | `MODEL_PROVIDER=deterministic is refused` |

  Each `boots` case must answer health.
- **Image checks travel with the change they guard:** `scripts/check_backend_image.sh` is created in C5b (allowlist, no dev tools, no secrets, `pip check`) and extended in C6 (non-root, code not writable, `/outbox` ownership). Each commit's negative control runs the new checks against the previous image, where they must fail.
- **Baseline:** a full local gate run on the current HEAD (Phase 0) records the expected results.
- **After every image-affecting commit:** the full `scripts/m3_boundary_gate.sh` must give the same results as the baseline, covering the boundary suite, the Redis-down case (boundary C11), all 11 M6 cases and the ai-service offline OCR check. The new image checks also run.

## 3. Change sequence

The work goes on a new branch, `chore/backend-image-hardening`, created from `feat/learning-content` at 51cb753. Creating it does not touch the working tree, since there are no uncommitted changes. One concern per commit; each commit is tested on its own and can be reverted alone.

**First commit.** This plan, as `docs/phase2-backend-image-hardening-plan.md`.

**Precondition.** At least 15 GB free on C: (U7), re-checked before each image build.

**Phase 0: baseline (no commit).** Run the full local boundary gate on HEAD, building both images fresh. The ai-service image comes from `../ai-service` on `feat/m3-boundary`, so this run is also the first boundary-gate evidence for the OCR-stack work (paddle 3.3.1 and the rest). Record pass counts per suite, every M6 line, and `pip freeze --all` from the freshly built backend image: that freeze is what C4 pins. If the baseline fails, stop and report: hardening must not start from a red gate.

| # | Commit | Change | Acceptance | Regression tests | Rollback |
|---|---|---|---|---|---|
| C1a | `test(backend): M6 refusals must fail for the configuration reason` | `refuses()` captures output and passes only if the import exits non-zero, the failure is a settings `ValidationError`, and the output contains that case's message (answer 7). `boots()` prints the server log on failure instead of discarding it. | All 11 M6 lines pass on the Phase 0 images, each matching its category and message. Run by hand against the new `refuses()`, three unrelated failures must each be reported FAIL: (a) a valid production configuration with `POSTGRES_URL=not-a-url` (URL error at import); (b) a throwaway image `FROM` the backend image with one runtime dependency uninstalled (missing module); (c) a throwaway image with `app/core/config.py` made unreadable, run as an unprivileged user (permission error). The commit message records that the old `refuses()` reported each of them as "refused". | Full gate. | Revert (script only). |
| C1b | `test(backend): the M6 refusal check rejects unrelated failures` | `scripts/m6_refusal_selftest.sh`: builds the two throwaway images for (b) and (c), runs (a), (b) and (c) through the same `refuses()`, requires FAIL for each, then removes the images. Called from `m3_boundary_gate.sh`, so the check cannot quietly lose its teeth. | Self-test passes on current images. **Negative control:** with C1a reverted locally, the self-test fails. | Full gate. | Revert. |
| C2 | `style(backend): ruff format with the pinned ruff (no behaviour change)` | Moves the pre-commit ruff hook from v0.6.9 to the ruff version in the Phase 0 freeze (0.17.0 as of 2026-10-11), which is also the version C4 pins, so pre-commit and CI format identically; then `ruff format app tests scripts pg_smoke`. Mechanical. | `ruff format --check` clean. **Formatter-only proof:** (1) the commit is reproduced by running the same ruff on the parent commit, and the trees must be identical; (2) every changed `.py` file parses to an identical AST before and after (excluding docstring-whitespace changes, which are listed for inspection); (3) only `.py` files and `.pre-commit-config.yaml` change. Unit suite 1122 passed / 89 skipped, unchanged; `pg_smoke` unchanged. | Unit suite; postgres-gate replay. | Revert. |
| C3a | `style(backend): ruff's automatic lint fixes (no behaviour change)` | `ruff check --fix` with safe fixes only: 39 import-order fixes and 1 unused import. | Remaining findings are exactly the 7 hand-fix cases; suites unchanged; AST comparison as in C2 shows only import order and the removed import. | As C2. | Revert. |
| C3b | `fix(backend): the remaining lint findings, reviewed by hand` | 3 E501, 2 E402 and 2 F841, each read for intent: an unused variable can hide a missing assertion, and moving an import can change initialisation order. Each fix is listed in the commit message; any that touches a security check or error handling is called out with its test. Adds `.git-blame-ignore-revs` listing C2 and C3a. | `ruff check` clean, so known baseline failure KB1 is closed; suites unchanged. | As C2. | Revert. |
| C4 | `build(backend): exact pins; requirements files are the only install source` | Full-closure `requirements.txt` and `requirements-dev.txt` with platform markers (pins: the Phase 0 freeze; `requirements.txt` is what the runtime direct dependencies resolve to with that freeze as constraints, and `requirements-dev.txt` adds the rest); the dependency lists are removed from `pyproject.toml`; stale entries dropped (D10); the declaration test. The Dockerfile installs `requirements-dev.txt` (still everything, deliberately, so this commit changes pinning only) and no longer installs the empty project (D9). `ci.yml` installs `requirements-dev.txt` only, so lint uses the pinned ruff; the postgres-gate job already sets `PYTHONPATH: .`. These files must change together to stay consistent, so they are one commit. | Declaration test passes on both platforms; `pip check` clean; unit suite and postgres-gate pass **in a `python:3.13.16-slim` container** with exactly the pinned set; full gate matches the baseline. Local venv re-synced, best effort (U3), after a `pip freeze --all` backup. | Unit suite, `pg_smoke`, full gate. | Revert; installs go back to floating versions. Restore the local venv from the `pip freeze --all` backup. |
| C4b | `docs(backend): install from the pinned requirements` | README development setup: `pip install -r requirements-dev.txt`, replacing `pip install -r requirements.txt` and `pip install -e ".[dev]"`. | The README commands work in a fresh `python:3.13.16-slim` container. | n/a | Revert. |
| C5a | `build(backend): runtime-only production image, separate test image` | Multi-stage `runtime` / `test` / `production` (last, `FROM runtime`); explicit `COPY` allowlist (answer 4); compose: `boundary-tests` builds `target: test` as `build-m3-backend-test`, backend services build `target: production`. `boundary-tests` is in the `gate` profile, which the gate's `up --build backend ai-service ai-worker` does not build, and `compose run` reuses an existing image. So `m3_boundary_gate.sh` gains an explicit `--profile gate build boundary-tests`; without it the gate would silently test a stale image. These must change together for the gate to work. | `docker build .` produces the runtime image (no pytest, ruff or mypy; `/app` holds only the allowlist, checked by hand here and by C5b afterwards). The gate log shows the test image built in that run, and the full gate matches the baseline. | Full gate. | Revert; compose goes back to one image. |
| C5b | `test(backend): production image checks` | `scripts/check_backend_image.sh <image>`: `/app` is exactly the allowlist; no dev tools; no `.env`, `m3.env` or test directories; `pip check`. Called from `m3_boundary_gate.sh` on the production image. | Passes on the C5a image. **Negative control:** fails on the Phase 0 image (dev tools, extra files). | Gate. | Revert. |
| C5c | `build(backend): the gate tests images built from the checked-out sources` | Both images carry `org.opencontainers.image.revision` (backend: `git rev-parse HEAD`, suffixed `-dirty` for a dirty tree; ai-service: the HEAD of the checkout it was built from), passed in by the gate script. The gate prints both revisions and refuses to run the suite if the `boundary-tests` or `backend` image's revision differs from the checkout. CI publishes only the `production` target; the test image is never tagged for publication. | **Negative control:** with a stale `build-m3-backend-test` image whose label differs, the gate stops before running tests. | Gate. | Revert. |
| C6 | `build(backend): run as an unprivileged user (final stage)` | `app` user (UID/GID 10001); `USER app` at the end of `runtime` and `test`; `/outbox` created and owned by `app`; a README line on running `docker compose -f deploy/compose.m3.yml down -v` once after upgrading. The image check gains: UID ≠ 0, `/app` not writable by the runtime user, `/outbox` owned by it. | Check passes; **negative control:** it fails on the C5c image (root). Full gate on fresh volumes matches the baseline. That exercises the outbox write (backend) and read (sign-up and invitation flows), both migration chains, provisioning, health checks and M6. | Full gate. | Revert; `docker compose -f deploy/compose.m3.yml down -v` locally if a volume was created by the non-root image. |
| C7a | `build(backend): pin the base image` | `FROM python:3.13.16-slim@sha256:<digest>` (the digest recorded at implementation time). | Two builds of the same commit give the same package set; gate matches the baseline. | Gate. | Revert. |
| C7b | `build(backend): pin pip` | `pip==<version>` in the Dockerfile and `ci.yml`, replacing `pip install --upgrade pip`. | Builds and CI replay use the pinned pip. | Unit suite in the container. | Revert. |
| C8 | `ci(backend): dependency audit` | `security` job: pip-audit 2.10.1 on both requirements files; also runs weekly. | Replayed locally in a container: clean today. **Negative control:** adding `python-jose==3.5.0` makes it fail. | n/a | Revert. |
| C9a | `ci(backend): build, check and audit the production image` | `image` job: build `production`; `check_backend_image.sh`; `scripts/audit_image_packages.py` (from ai-service, with review dates added) and an empty `security/accepted-image-advisories.txt`; also weekly. | Replayed locally. **Negative controls:** an unaccepted advisory, a stale acceptance and an expired review date each fail it. | n/a | Revert. |
| C9b | `ci(backend): scan the image's OS packages with Trivy` | Trivy pinned by version and digest, `--pkg-types os --severity HIGH,CRITICAL --ignore-unfixed --exit-code 1`, full report logged; `security/trivyignore.yaml` (empty, or entries with `statement` and `expired_at`). | Run locally with the same pinned Trivy against the C7a image: results recorded in the commit message. If it reports fixable HIGH/CRITICAL findings, the base-image or `apt` remedy is brought back for decision before this commit, not silenced by exceptions. | n/a | Revert. |
| C10a | `ci(backend): boundary gate checks out the intended ai-service` | `ai_service_ref` defaults to a repository variable (`AI_SERVICE_REF`, falling back to `main`), documented in the workflow header. | `actionlint` passes. | n/a | Revert. |
| C10b | `ci(backend): boundary gate runs on pull requests` | Triggers: pull requests, push to `main`, and manual. No path filters, so a required check is never skipped. The workflow header notes that branch protection must require it (a check that never reports blocks the merge, rather than passing it). | `actionlint` passes. | n/a | Revert. |
| C11 | `chore(backend): remove the stray "tatus --short" file` | Deletes the tracked stray file. `t -q` is untracked and is **not** deleted (yours to remove); the `*-q` ignore pattern stays until you do. | `git status` clean. | n/a | Revert. |
| A1 | ai-service, separate branch: `ci(ai-service): remove the superseded ci.yml` | Branch `chore/remove-legacy-ci` from `feat/m3-boundary` (not from `main`; see answer 6). Deletes `.github/workflows/ci.yml`. Not on the backend branch. | The commit message maps each step of the old file to its `backend.yml` equivalent. Merges only after `feat/m3-boundary` reaches `main` and its `backend.yml` has passed in hosted CI. | n/a | Revert. |

Commit rules:
- **As separate as possible:** each commit carries one concern. Files are combined only when splitting them would leave the repository inconsistent (C4, C5a), and the commit message says why.
- **Gates:** every gate that passed at the baseline stays green after every commit. Known baseline failures are tracked by ID until the commit that fixes them, and each commit message names any it closes:
  - **KB1:** backend lint (D2), closed by C3b;
  - **KB2:** ai-service's legacy `ci.yml` (D14), closed by A1;
  - anything else Phase 0 finds red is added here before work continues.
- **Before each commit:** pre-commit runs (never skipped). The unit suite runs in the Linux container with the pinned versions (authoritative), and locally where App Control allows.
- **Image-affecting commits** (C4, C5a, C5c, C6, C7a) also need the full gate, matching the baseline.
- **Disk:** intermediate images are removed after each check.
- **Nothing is pushed.** You push the branch.

**After you push: hosted validation.** Local results do not stand in for it. The hosted runs to inspect are:
- `ci.yml`: `test` (now lint plus the unit suite), `postgres-gate`, `security` and `image`;
- `boundary-gate`, via a manual run with `ai_service_ref` set to the ai-service branch under test. It needs `AI_SERVICE_READ_TOKEN`, plus `AI_SERVICE_REF` if C10 lands.

Each run is read for its actual results, not just its status. Hosted CI is also the first place the backend and the shipped ai-service image (paddle 3.3.1) run together outside this machine. Any hosted-only failure is reported as such, and not fixed blind.

Not in this plan, and kept separate: ai-service non-root (R6); mypy enforcement (R5); Docker disk compaction (except as the U7 precondition).

## 4. Risks

| Risk | Mitigation |
|---|---|
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

## 6. Review log

Five review rounds were run on this plan; the fifth folded in the approval conditions. Each checked every claim against the repository, the image or a reproduction, and changed the plan where it was wrong or incomplete.

| Round | Found | Changed |
|---|---|---|
| 1 | C1's negative control could not show the defect. Image checks arrived after the changes they guard. A Linux-generated closure would not install on Windows (uvloop, colorama). The test stage could not install packages as `app`. Formatting with a newer ruff would leave the pre-commit hook on 0.6.9. No disk precondition. | Verified that all nine M6 refusal messages exist, and named them. Image checks moved into C5 and C6, each with a negative control against the previous image. Platform markers, `USER root` for the test stage's install, aligned ruff versions, the disk precondition (U7), and the scripts question (U6). |
| 2 | The gate script never rebuilds the `boundary-tests` image (it sits in a profile), so a split image would be tested stale. Exact pins in `pyproject.toml` would be a second, driftable list. C1's negative control and the ruff-pre-commit tag were unverified. | Explicit test-image build in the gate (C5). Verified that a production config with `POSTGRES_URL=not-a-url` fails import for an unrelated reason (C1 control), that ruff-pre-commit `v0.17.0` exists, and that the unit suite passes in Linux with the project not installed (1122/89). That made the requirements files the only declaration. Added R7. |
| 3 | C4 and C7 bundled separable changes. App Control could block the new ruff binary at the commit hook. Two audits would have had two exception lists. Where the authoritative test run happens was undefined. | Split C4b and C7a/C7b. Commit rules added (one concern per commit; hooks never skipped; Linux container authoritative; nothing pushed). One shared exception list. A risk row for the hook. |
| 4 | Phase 0 rebuilds with floating dependencies, so it would not test the 2026-10-11 versions the plan proposed to pin. Hosted validation after push was missing. D2 overstated what was observed. | Pins are now exactly the Phase 0 freeze (the set the baseline gate tested). Hosted validation steps added. D2 qualified by U1. Final consistency sweep (commit numbers, versions, references): clean. |
| 5 | Approval conditions; `seed_futa.py` usage; ai-service `main`'s `backend.yml` runs only integration and contract tests, so the legacy `ci.yml` is the only unit-test run there. | Decisions recorded (§5). U6 and U7 resolved. Split C1, C3, C5, C9 and C10 further. Startup-check category plus three negative controls. Test-image revision check. Trivy scope and thresholds. Dated exceptions. Known-baseline-failure tracking. A1 based on `feat/m3-boundary`. |
