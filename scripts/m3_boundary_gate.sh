#!/usr/bin/env bash
# M3 real two-service boundary gate (design Part C), one command:
#
#   scripts/m3_boundary_gate.sh            # fresh stack, full suite, teardown
#   KEEP_STACK=1 scripts/m3_boundary_gate.sh
#
# Builds backend and ../ai-service, starts PostgreSQL 17 and Redis 8 from
# empty volumes, creates the least-privilege roles, runs both Alembic chains
# as their owner roles, starts both services (AI-service unpublished) and the
# AI worker, checks the production image's contents, then runs boundary/
# inside the network from the test image. C11 runs with Redis stopped; then
# the M6 production startup checks and their self-test, and the AI-service
# offline OCR check. Exit status is non-zero if any of them fails.
set -euo pipefail

cd "$(dirname "$0")/.."
COMPOSE=(docker compose --env-file deploy/m3.env -f deploy/compose.m3.yml)

# The revisions under test, recorded once per run: compose labels every image
# with them (org.opencontainers.image.revision). "-dirty" marks uncommitted
# changes to what an image is built from. AI_SERVICE_DIR must be the checkout
# compose builds from (../ai-service).
AI_DIR=${AI_SERVICE_DIR:-../ai-service}
revision_of() { # repository [git status arguments...]
  local repo=$1 rev
  shift
  rev=$(git -C "$repo" rev-parse HEAD)
  if [[ -n "$(git -C "$repo" status --porcelain "$@")" ]]; then rev="$rev-dirty"; fi
  echo "$rev"
}
BACKEND_REVISION=$(revision_of . -- Dockerfile .dockerignore requirements.txt requirements-dev.txt pyproject.toml \
  alembic.ini alembic app scripts tests pg_smoke boundary)
AI_SERVICE_REVISION=$(revision_of "$AI_DIR" --untracked-files=no)
export BACKEND_REVISION AI_SERVICE_REVISION
echo "backend revision:    $BACKEND_REVISION ($(git branch --show-current || true))"
echo "ai-service revision: $AI_SERVICE_REVISION ($(git -C "$AI_DIR" branch --show-current || true) at $AI_DIR)"

# Fresh random values for every name deploy/m3.env lacks. Existing values
# are kept, so an older file gains the newer names (object storage, P3-1)
# without any of its secrets being replaced.
python - <<'PY'
import os
import secrets

names = ["POSTGRES_SUPERUSER_PASSWORD", "BUILD_BACKEND_OWNER_PASSWORD", "BUILD_BACKEND_APP_PASSWORD",
         "BUILD_AI_OWNER_PASSWORD", "BUILD_AI_APP_PASSWORD", "BACKEND_TO_AI_SECRET", "AI_TO_BACKEND_SECRET",
         "OBJECT_STORAGE_ADMIN_ACCESS_KEY", "OBJECT_STORAGE_ADMIN_SECRET_KEY",
         "OBJECT_STORAGE_BACKEND_ACCESS_KEY", "OBJECT_STORAGE_BACKEND_SECRET_KEY",
         "OBJECT_STORAGE_AI_ACCESS_KEY", "OBJECT_STORAGE_AI_SECRET_KEY"]
path = "deploy/m3.env"
present, ends_with_newline = set(), True
if os.path.exists(path):
    with open(path) as fh:
        text = fh.read()
    present = {line.split("=", 1)[0].strip() for line in text.splitlines()
               if "=" in line and not line.lstrip().startswith("#")}
    ends_with_newline = text == "" or text.endswith("\n")
missing = [n for n in names if n not in present]
if missing:
    print("deploy/m3.env: fresh random values for " + ", ".join(missing))
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    with os.fdopen(fd, "a") as fh:
        if not ends_with_newline:
            fh.write("\n")
        fh.writelines(f"{n}={secrets.token_hex(10 if n.endswith('_ACCESS_KEY') else 32)}\n" for n in missing)
PY

cleanup() {
  if [[ -z "${KEEP_STACK:-}" ]]; then
    "${COMPOSE[@]}" --profile gate down -v --remove-orphans >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

"${COMPOSE[@]}" --profile gate down -v --remove-orphans >/dev/null 2>&1 || true
"${COMPOSE[@]}" up -d --build --wait backend ai-service ai-worker
# The test image: `up --build` skips profile services and `compose run`
# reuses an existing image, so build it from this checkout explicitly.
"${COMPOSE[@]}" --profile gate build boundary-tests

# Every image must come from the revisions recorded above; a stale image or a
# checkout that moved is never tested.
if ! scripts/check_image_revisions.sh "$BACKEND_REVISION" "$AI_SERVICE_REVISION"; then
  echo "refusing to run the gate on images that do not match the recorded revisions" >&2
  exit 1
fi

# The model-mirror token is a build secret only: it must not appear in the
# image's history or configuration.
if [[ -n "${OCR_MODELS_TOKEN:-}" ]]; then
  if docker history --no-trunc build-m3-ai-service | grep -qF "$OCR_MODELS_TOKEN"      || docker image inspect build-m3-ai-service | grep -qF "$OCR_MODELS_TOKEN"; then
    echo "OCR_MODELS_TOKEN leaked into the ai-service image" >&2
    exit 1
  fi
  echo "model-mirror token: not present in image history or config"
fi

status=0
# The production image holds what production runs and nothing else.
scripts/check_backend_image.sh build-m3-backend || status=$?

"${COMPOSE[@]}" run --rm boundary-tests "$@" -q -m "not redis_down" || status=$?

# Storage secret keys: in no image layer or configuration, and in no log
# written by the run so far.
scripts/check_storage_secrets.sh || status=$?

echo "C11: stopping redis"
"${COMPOSE[@]}" stop redis
"${COMPOSE[@]}" run --rm --no-deps boundary-tests -q -m redis_down || status=$?
"${COMPOSE[@]}" start redis

# M6: the production startup path, with the same images.
scripts/m6_production_startup.sh || status=$?
# The M6 refusal check itself: unrelated startup failures must not count as
# refusals (fixtures built from this run's backend image).
scripts/m6_refusal_selftest.sh || status=$?

# Phase 2 Step 2: real OCR in the AI-service image with networking disabled,
# from the models baked into it (no runtime download).
"${AI_SERVICE_DIR:-../ai-service}/scripts/test_offline_ocr_image.sh" build-m3-ai-service || status=$?

# The whole run tested one revision of each repository: neither checkout may
# have moved since it was recorded.
for repo in backend ai-service; do
  if [[ $repo == backend ]]; then
    now=$(revision_of . -- Dockerfile .dockerignore requirements.txt requirements-dev.txt pyproject.toml \
      alembic.ini alembic app scripts tests pg_smoke boundary)
    recorded=$BACKEND_REVISION
  else
    now=$(revision_of "$AI_DIR" --untracked-files=no)
    recorded=$AI_SERVICE_REVISION
  fi
  if [[ $now != "$recorded" ]]; then
    echo "$repo checkout changed during the run: $recorded -> $now" >&2
    status=1
  fi
done
echo "tested: backend $BACKEND_REVISION, ai-service $AI_SERVICE_REVISION"

exit "$status"
