#!/usr/bin/env bash
# M6 production startup path (plan §12 "Production startup path passes").
#
# Uses the images built by scripts/m3_boundary_gate.sh. Each service is started
# with APP_ENVIRONMENT=production:
#   - with a valid production configuration it must boot and answer health;
#   - with each unsafe configuration it must refuse to start.
# Nothing here needs TLS endpoints to exist: startup validates configuration,
# it does not call the other service.
set -uo pipefail

cd "$(dirname "$0")/.."
COMPOSE=(docker compose --env-file deploy/m3.env -f deploy/compose.m3.yml)
rnd() { python -c "import secrets; print(secrets.token_hex(32))"; }

B2A=$(rnd); A2B=$(rnd); JWT=$(rnd)
BACKEND_PROD=(
  -e APP_ENVIRONMENT=production
  -e AUTH_JWT_SECRET="$JWT"
  -e AI_SERVICE_URL=https://ai-service.internal
  -e BACKEND_TO_AI_SECRET="$B2A"
  -e AI_TO_BACKEND_SECRET="$A2B"
  -e AUTH_RATE_LIMIT_FAILURE_MODE=closed
)
AI_PROD=(
  -e APP_ENVIRONMENT=production
  -e BACKEND_CALLBACK_URL=https://api.build.example/content/ingestion/callbacks
  -e BACKEND_TO_AI_SECRET="$B2A"
  -e AI_TO_BACKEND_SECRET="$A2B"
  -e MODEL_PROVIDER=openai
)

fail=0
pass() { echo "  ok   $*"; }
bad() { echo "  FAIL $*"; fail=1; }

boots() { # service health_path extra-args...
  local service=$1 health=$2; shift 2
  "${COMPOSE[@]}" run --rm --no-deps "$@" --entrypoint sh "$service" -c "
    uvicorn app.main:app --host 127.0.0.1 --port 8000 >/tmp/server.log 2>&1 & pid=\$!
    for i in \$(seq 40); do
      python -c 'import urllib.request; urllib.request.urlopen(\"http://127.0.0.1:8000$health\", timeout=1)' 2>/dev/null && { kill \$pid; exit 0; }
      kill -0 \$pid 2>/dev/null || { cat /tmp/server.log; exit 1; }
      sleep 0.5
    done
    cat /tmp/server.log; exit 1" >/dev/null 2>&1
}

refuses() { # service extra-args...
  local service=$1; shift
  ! "${COMPOSE[@]}" run --rm --no-deps "$@" --entrypoint python "$service" -c "import app.main" >/dev/null 2>&1
}

echo "Production startup path"
boots backend /health/live "${BACKEND_PROD[@]}" && pass "backend boots in production" || bad "backend did not boot in production"
boots ai-service /api/v1/system/health "${AI_PROD[@]}" && pass "ai-service boots in production" || bad "ai-service did not boot in production"

echo "Unsafe production configuration is refused"
refuses backend "${BACKEND_PROD[@]}" -e AUTH_JWT_SECRET= && pass "backend: missing JWT secret" || bad "backend accepted a missing JWT secret"
refuses backend "${BACKEND_PROD[@]}" -e AI_SERVICE_URL=http://ai-service:8000 && pass "backend: plain-http AI_SERVICE_URL" || bad "backend accepted http AI_SERVICE_URL"
refuses backend "${BACKEND_PROD[@]}" -e AI_TO_BACKEND_SECRET="$B2A" && pass "backend: equal directional secrets" || bad "backend accepted equal secrets"
refuses backend "${BACKEND_PROD[@]}" -e BACKEND_TO_AI_SECRET=build-internal-service-secret && pass "backend: known development secret" || bad "backend accepted a development secret"
refuses backend "${BACKEND_PROD[@]}" -e CORS_ALLOWED_ORIGINS='*' && pass "backend: wildcard CORS" || bad "backend accepted wildcard CORS"
refuses ai-service "${AI_PROD[@]}" -e BACKEND_TO_AI_SECRET= && pass "ai-service: missing secret" || bad "ai-service accepted a missing secret"
refuses ai-service "${AI_PROD[@]}" -e AI_TO_BACKEND_SECRET=short && pass "ai-service: short secret" || bad "ai-service accepted a short secret"
refuses ai-service "${AI_PROD[@]}" -e BACKEND_CALLBACK_URL=http://backend:8000/content/ingestion/callbacks && pass "ai-service: plain-http callback URL" || bad "ai-service accepted an http callback URL"
refuses ai-service "${AI_PROD[@]}" -e MODEL_PROVIDER=deterministic && pass "ai-service: deterministic model" || bad "ai-service accepted the deterministic model"

exit "$fail"
