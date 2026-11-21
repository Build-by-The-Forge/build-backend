#!/usr/bin/env bash
# Keeps the boundary gate's service logs and the AI task-queue state, so a
# failure can be explained after the stack is torn down. Sourced by
# scripts/m3_boundary_gate.sh; it needs the COMPOSE array that script builds.
#
# It only ever writes files under GATE_LOG_DIR and never fails: with
# GATE_LOG_DIR unset it does nothing, and an error here can't change the
# gate's exit status in either direction.
#
# What is kept, per snapshot (a subdirectory named by the label):
#   <service>.log        the service's complete log with timestamps, for every
#                        service of the stack (compose keeps a container's log
#                        across stop/start, until the container is removed)
#   ai-stream-state.txt  the AI task stream's length, the worker group's
#                        consumers and pending entries (IDs, idle times and
#                        delivery counts only; never a task payload)
# and at the top of GATE_LOG_DIR, MANIFEST.txt: the run, attempt, job and
# revisions the logs belong to.
#
# Redaction. Everything is redacted BEFORE it is written: the values of every
# secret in deploy/m3.env, authorization and cookie headers, bearer and JWT
# tokens, password/secret/token/signature fields, credentials inside URLs,
# e-mail addresses and query strings. Task, job, tenant and worker identifiers,
# timestamps and messages are kept: they are what an investigation needs. As a
# check, each written file is searched again for every known secret value; a
# file that still holds one is deleted and replaced by a REDACTION-FAILED note,
# so an unredacted file is never uploaded.

# The AI service's task stream and consumer group, in the AI Redis database.
GATE_AI_STREAM='{ai-tasks}:stream:ai_tasks'
GATE_AI_GROUP='ai_worker_group'
GATE_AI_REDIS_DB=1

GATE_SECRET_NAME='(PASSWORD|SECRET|KEY|TOKEN)'

# Known secret values (at least 8 characters): from the gate's env file and
# the model-mirror token, one per line.
gate_secret_values() {
  local file=${GATE_ENV_FILE:-deploy/m3.env} name value
  if [[ -r $file ]]; then
    while IFS='=' read -r name value; do
      name=${name//[[:space:]]/}
      [[ $name =~ ^[A-Za-z_][A-Za-z0-9_]*$ && $name =~ $GATE_SECRET_NAME ]] || continue
      value=${value%$'\r'}
      value=${value#\"}
      value=${value%\"}
      [[ ${#value} -ge 8 ]] && printf '%s\n' "$value"
    done <"$file"
  fi
  local mirror=${OCR_MODELS_TOKEN:-}
  [[ ${#mirror} -ge 8 ]] && printf '%s\n' "$mirror"
  return 0
}

# stdin to stdout, redacted. A sed script is built once per call.
gate_redact() {
  local script value escaped
  script=$(mktemp) || return 1
  while IFS= read -r value; do
    escaped=$(printf '%s' "$value" | sed -e 's/[][\/.*^$&|]/\&/g')
    printf 's/%s/[REDACTED]/g\n' "$escaped" >>"$script"
  done < <(gate_secret_values)
  cat >>"$script" <<'SED'
s#eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]*#[REDACTED]#g
s#([Bb]earer)[ =]+[A-Za-z0-9._~+/=-]+#\1 [REDACTED]#g
s#(://)[^/@ "']+:[^/@ "']+@#\1[REDACTED]@#g
s#([A-Za-z0-9._%+-]+)@([A-Za-z0-9-]+\.)+[A-Za-z]{2,}#[REDACTED-EMAIL]#g
s#((authorization|proxy-authorization|cookie|set-cookie|x-build-signature|x-build-context)["']?[ ]*[:=][ ]*)[^\r\n]*#\1[REDACTED]#Ig
s#((password|passwd|secret|token|api[_-]?key|signature|credential)[A-Za-z_]*["']?[ ]*[:=][ ]*["']?)[^"', }&]+#\1[REDACTED]#Ig
s#((GET|POST|PUT|PATCH|DELETE|HEAD) [^ ?"]+)\?[^ "]*#\1?[REDACTED-QUERY]#g
SED
  sed -E -f "$script"
  local rc=$?
  rm -f "$script"
  return $rc
}

# Writes stdin, redacted, to a file; then checks the file for any known secret.
gate_write_redacted() { # file
  local file=$1 value
  gate_redact >"$file" 2>/dev/null || {
    printf 'REDACTION-FAILED: the filter did not run; nothing from this file is kept\n' >"$file"
    return 0
  }
  while IFS= read -r value; do
    if grep -qF -- "$value" "$file" 2>/dev/null; then
      printf 'REDACTION-FAILED: a known secret survived the filter; nothing from this file is kept\n' >"$file"
      return 0
    fi
  done < <(gate_secret_values)
  return 0
}

gate_ai_stream_state() {
  local redis=("${COMPOSE[@]}" exec -T redis redis-cli -n "$GATE_AI_REDIS_DB")
  echo "captured: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "== XLEN"
  "${redis[@]}" XLEN "$GATE_AI_STREAM" || true
  echo "== XINFO GROUPS"
  "${redis[@]}" XINFO GROUPS "$GATE_AI_STREAM" || true
  echo "== XINFO CONSUMERS $GATE_AI_GROUP"
  "${redis[@]}" XINFO CONSUMERS "$GATE_AI_STREAM" "$GATE_AI_GROUP" || true
  echo "== XPENDING $GATE_AI_GROUP (summary)"
  "${redis[@]}" XPENDING "$GATE_AI_STREAM" "$GATE_AI_GROUP" || true
  echo "== XPENDING $GATE_AI_GROUP (entries: id, consumer, idle ms, deliveries)"
  "${redis[@]}" XPENDING "$GATE_AI_STREAM" "$GATE_AI_GROUP" - + 200 || true
}

# What the logs belong to: the workflow run, attempt and job, and the
# revisions under test. Written once, at the first snapshot.
gate_manifest() { # directory
  local manifest="$1/MANIFEST.txt"
  [[ -e $manifest ]] && return 0
  {
    echo "run:        ${GITHUB_SERVER_URL:-}/${GITHUB_REPOSITORY:-}/actions/runs/${GITHUB_RUN_ID:-local}"
    echo "attempt:    ${GITHUB_RUN_ATTEMPT:-}"
    echo "workflow:   ${GITHUB_WORKFLOW:-}"
    echo "job:        ${GITHUB_JOB:-}"
    echo "event:      ${GITHUB_EVENT_NAME:-}"
    echo "github sha: ${GITHUB_SHA:-}"
    echo "backend:    ${BACKEND_REVISION:-}"
    echo "ai-service: ${AI_SERVICE_REVISION:-}"
    echo "started:    $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  } >"$manifest" 2>/dev/null || true
}

capture_gate_logs() { # label
  local label=${1:-snapshot} dir=${GATE_LOG_DIR:-} out service services
  [[ -n $dir ]] || return 0
  out="$dir/$label"
  mkdir -p "$out" 2>/dev/null || return 0
  gate_manifest "$dir"
  services=$("${COMPOSE[@]}" --profile gate --profile faults config --services 2>/dev/null) || services=""
  for service in $services; do
    "${COMPOSE[@]}" --profile gate --profile faults logs --no-color --timestamps "$service" 2>&1 |
      gate_write_redacted "$out/$service.log" || true
  done
  gate_ai_stream_state 2>&1 | gate_write_redacted "$out/ai-stream-state.txt" || true
  return 0
}
