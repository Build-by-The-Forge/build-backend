#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
COMPOSE=(docker compose --env-file deploy/m3.env -f deploy/compose.m3.yml -f deploy/compose.p3-6-kill.yml)
GATE_TRIGGER=p36_worker_kill_gate
runner_pid=

postgres_sql() {
  "${COMPOSE[@]}" exec -T postgres psql -X -v ON_ERROR_STOP=1 -U postgres -d build "$@"
}

remove_trigger() {
  postgres_sql <<'SQL' >/dev/null 2>&1 || true
DROP TRIGGER IF EXISTS p36_worker_kill_gate ON public.document_chunks;
DROP FUNCTION IF EXISTS public.p36_pause_ingestion_chunk();
DROP TABLE IF EXISTS public.p36_worker_kill_gate;
SQL
}

cleanup() {
  remove_trigger
}
trap cleanup EXIT

echo "C23: applying short recovery timings for the isolated worker-kill scenario"
"${COMPOSE[@]}" up -d --wait backend-worker ai-worker

remove_trigger
postgres_sql <<'SQL'
CREATE TABLE public.p36_worker_kill_gate (backend_pid integer PRIMARY KEY);
GRANT SELECT, INSERT ON public.p36_worker_kill_gate TO build_ai_app;
CREATE OR REPLACE FUNCTION public.p36_pause_ingestion_chunk() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.content LIKE '%P36_WORKER_KILL_BOUNDARY_MARKER%' AND NEW.attempt = 1 THEN
        INSERT INTO public.p36_worker_kill_gate (backend_pid)
        VALUES (pg_backend_pid())
        ON CONFLICT (backend_pid) DO NOTHING;
        PERFORM pg_sleep(180);
    END IF;
    RETURN NEW;
END
$$;
CREATE TRIGGER p36_worker_kill_gate
BEFORE INSERT ON public.document_chunks
FOR EACH ROW EXECUTE FUNCTION public.p36_pause_ingestion_chunk();
SQL

echo "C23: starting the real boundary test; waiting for its index write to pause"
"${COMPOSE[@]}" --profile gate run --rm boundary-tests -q -m worker_kill &
runner_pid=$!

for _ in $(seq 1 240); do
  if ! kill -0 "$runner_pid" 2>/dev/null; then
    wait "$runner_pid"
    echo "C23 test ended before the worker reached the injected index pause" >&2
    exit 1
  fi
  if postgres_sql -Atqc \
    "SELECT EXISTS (SELECT 1 FROM public.p36_worker_kill_gate g JOIN pg_stat_activity a ON a.pid = g.backend_pid WHERE a.wait_event = 'PgSleep')" \
    | grep -qx t; then
    echo "C23: killing the AI worker while its index transaction is in progress"
    "${COMPOSE[@]}" kill --signal SIGKILL ai-worker
    remove_trigger
    "${COMPOSE[@]}" up -d --wait ai-worker
    wait "$runner_pid"
    echo "P3-6: verifying uncertain dispatch reuses the accepted idempotency key"
    "${COMPOSE[@]}" --profile gate run --rm --entrypoint python boundary-tests \
      -m pytest -p no:cacheprovider -p no:env \
      tests/integration/content/test_real_ai_dispatch.py -q
    echo "C23: AI worker restarted; recovery, retry, index fence and stale callback passed"
    exit 0
  fi
  sleep 1
done

echo "C23: timed out waiting for the worker's index transaction" >&2
"${COMPOSE[@]}" logs --no-color --tail 150 ai-worker backend-worker >&2 || true
exit 1
