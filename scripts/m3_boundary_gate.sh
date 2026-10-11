#!/usr/bin/env bash
# M3 real two-service boundary gate (design Part C), one command:
#
#   scripts/m3_boundary_gate.sh            # fresh stack, full suite, teardown
#   KEEP_STACK=1 scripts/m3_boundary_gate.sh
#
# Builds backend and ../ai-service, starts PostgreSQL 17 and Redis 8 from
# empty volumes, creates the least-privilege roles, runs both Alembic chains
# as their owner roles, starts both services (AI-service unpublished) and the
# AI worker, then runs boundary/ inside the network. C11 runs last, with
# Redis stopped. Exit status is the suite's.
set -euo pipefail

cd "$(dirname "$0")/.."
COMPOSE=(docker compose --env-file deploy/m3.env -f deploy/compose.m3.yml)

if [[ ! -f deploy/m3.env ]]; then
  echo "generating deploy/m3.env with fresh random secrets"
  python - <<'PY'
import secrets
names = ["POSTGRES_SUPERUSER_PASSWORD", "BUILD_BACKEND_OWNER_PASSWORD", "BUILD_BACKEND_APP_PASSWORD",
         "BUILD_AI_OWNER_PASSWORD", "BUILD_AI_APP_PASSWORD", "BACKEND_TO_AI_SECRET", "AI_TO_BACKEND_SECRET"]
with open("deploy/m3.env", "w") as fh:
    fh.writelines(f"{n}={secrets.token_hex(32)}\n" for n in names)
PY
fi

cleanup() {
  if [[ -z "${KEEP_STACK:-}" ]]; then
    "${COMPOSE[@]}" --profile gate down -v --remove-orphans >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

"${COMPOSE[@]}" --profile gate down -v --remove-orphans >/dev/null 2>&1 || true
"${COMPOSE[@]}" up -d --build --wait backend ai-service ai-worker

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
"${COMPOSE[@]}" run --rm boundary-tests "$@" -q -m "not redis_down" || status=$?

echo "C11: stopping redis"
"${COMPOSE[@]}" stop redis
"${COMPOSE[@]}" run --rm --no-deps boundary-tests -q -m redis_down || status=$?
"${COMPOSE[@]}" start redis

# M6: the production startup path, with the same images.
scripts/m6_production_startup.sh || status=$?

# Phase 2 Step 2: real OCR in the AI-service image with networking disabled,
# from the models baked into it (no runtime download).
"${AI_SERVICE_DIR:-../ai-service}/scripts/test_offline_ocr_image.sh" build-m3-ai-service || status=$?

exit "$status"
