#!/usr/bin/env bash
# M6 production startup path (plan §12 "Production startup path passes").
#
# Uses the images built by scripts/m3_boundary_gate.sh. Each service is started
# with APP_ENVIRONMENT=production:
#   - with a valid production configuration it must boot and answer health;
#   - with each unsafe configuration it must refuse to start, and refuse for
#     the named reason: a settings validation error carrying that rule's
#     message. Any other failure (a bad database URL, a missing module, an
#     unreadable file) is reported as FAIL, never counted as a refusal.
# Nothing here needs TLS endpoints to exist: startup validates configuration,
# it does not call the other service.
#
# Sourcing this file defines the checks without running them.
set -uo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.." || exit 1
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
  -e LEARNING_MEMORY_ENABLED=false
)
# One byte under MIN_SERVICE_SECRET_BYTES (32).
SHORT_SECRET=$(rnd | cut -c1-31)
# Listed in KNOWN_DEVELOPMENT_SERVICE_SECRETS and long enough (47 bytes) to
# pass the length rule, so only the known-value rule can refuse it.
KNOWN_DEV_SECRET=test-only-backend-to-ai-secret-0123456789abcdef

fail=0
pass() { echo "  ok   $*"; }
bad() { echo "  FAIL $*"; fail=1; }

# Why an import failed, in one line, without configuration values: pydantic's
# input_value can carry secrets, so only the rule's message or the exception
# class is reported.
startup_error() {
  local value
  value=$(grep -oE 'Value error, [^[]*' <<<"$1" | head -1 | sed -E 's/ +$//')
  if [[ -n $value ]]; then
    echo "$value"
  else
    grep -oE '^[A-Za-z_][A-Za-z0-9_.]*(Error|Exception)\b' <<<"$1" | tail -1
  fi
}

BOOT_LOG=""
boots() { # service health_path extra-args...
  local service=$1 health=$2; shift 2
  local out
  if out=$("${COMPOSE[@]}" run --rm --no-deps "$@" --entrypoint sh "$service" -c "
    uvicorn app.main:app --host 127.0.0.1 --port 8000 >/tmp/server.log 2>&1 & pid=\$!
    for i in \$(seq 40); do
      python -c 'import urllib.request; urllib.request.urlopen(\"http://127.0.0.1:8000$health\", timeout=1)' 2>/dev/null && { kill \$pid; exit 0; }
      kill -0 \$pid 2>/dev/null || { cat /tmp/server.log; exit 1; }
      sleep 0.5
    done
    cat /tmp/server.log; exit 1" 2>&1); then
    return 0
  fi
  BOOT_LOG=$(sed -E -e 's/input_value=.*/input_value=<redacted>/' -e 's/^/       /' <<<"$out" | tail -40)
  return 1
}

REFUSAL_GOT=""
refuses() { # service expected-message [--unset VAR]... extra-args...
  local service=$1 expected=$2; shift 2
  local unset=() out status
  while [[ ${1:-} == --unset ]]; do
    unset+=(-u "$2")
    shift 2
  done
  if ((${#unset[@]})); then
    out=$("${COMPOSE[@]}" run --rm --no-deps "$@" --entrypoint env "$service" "${unset[@]}" python -c "import app.main" 2>&1)
  else
    out=$("${COMPOSE[@]}" run --rm --no-deps "$@" --entrypoint python "$service" -c "import app.main" 2>&1)
  fi
  status=$?
  if ((status == 0)); then
    REFUSAL_GOT="started without error"
    return 1
  fi
  REFUSAL_GOT=$(startup_error "$out")
  REFUSAL_GOT=${REFUSAL_GOT:-"exit status $status, no error recognised"}
  grep -q "validation error for Settings" <<<"$out" && grep -qF -- "$expected" <<<"$out"
}

check_refusal() { # label service expected-message [--unset VAR]... extra-args...
  local label=$1 expected=$3
  shift
  if refuses "$@"; then
    pass "$label"
  else
    bad "$label: expected a settings validation error with \"$expected\"; got: $REFUSAL_GOT"
  fi
}

main() {
  echo "Production startup path"
  if boots backend /health/live "${BACKEND_PROD[@]}"; then pass "backend boots in production"; else bad "backend did not boot in production"; echo "$BOOT_LOG"; fi
  if boots ai-service /api/v1/system/health "${AI_PROD[@]}"; then pass "ai-service boots in production"; else bad "ai-service did not boot in production"; echo "$BOOT_LOG"; fi

  echo "Unsafe production configuration is refused, for the named reason"
  check_refusal "backend: missing JWT secret" backend "AUTH_JWT_SECRET is required" \
    "${BACKEND_PROD[@]}" -e AUTH_JWT_SECRET=
  check_refusal "backend: plain-http AI_SERVICE_URL" backend "AI_SERVICE_URL must be an absolute https URL" \
    "${BACKEND_PROD[@]}" -e AI_SERVICE_URL=http://ai-service:8000
  check_refusal "backend: equal directional secrets" backend "BACKEND_TO_AI and AI_TO_BACKEND secrets must differ" \
    "${BACKEND_PROD[@]}" -e AI_TO_BACKEND_SECRET="$B2A"
  check_refusal "backend: short service secret" backend "BACKEND_TO_AI_SECRET must be at least 32 bytes" \
    "${BACKEND_PROD[@]}" -e BACKEND_TO_AI_SECRET="$SHORT_SECRET"
  check_refusal "backend: known development secret" backend "BACKEND_TO_AI_SECRET is a known development value" \
    "${BACKEND_PROD[@]}" -e BACKEND_TO_AI_SECRET="$KNOWN_DEV_SECRET"
  check_refusal "backend: wildcard CORS" backend "CORS_ALLOWED_ORIGINS must list exact origins" \
    "${BACKEND_PROD[@]}" -e CORS_ALLOWED_ORIGINS='*'
  # Absent, not empty: ai-service treats an empty value as present (and short).
  check_refusal "ai-service: missing secret" ai-service "BACKEND_TO_AI_SECRET is required" \
    --unset BACKEND_TO_AI_SECRET "${AI_PROD[@]}"
  check_refusal "ai-service: short secret" ai-service "AI_TO_BACKEND_SECRET must be at least 32 bytes" \
    "${AI_PROD[@]}" -e AI_TO_BACKEND_SECRET=short
  check_refusal "ai-service: plain-http callback URL" ai-service "BACKEND_CALLBACK_URL must use https" \
    "${AI_PROD[@]}" -e BACKEND_CALLBACK_URL=http://backend:8000/content/ingestion/callbacks
  check_refusal "ai-service: deterministic model" ai-service "MODEL_PROVIDER=deterministic is refused" \
    "${AI_PROD[@]}" -e MODEL_PROVIDER=deterministic
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  main
  exit "$fail"
fi
