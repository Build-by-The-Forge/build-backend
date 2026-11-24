# The boundary gate's kept logs

The boundary gate (`.github/workflows/boundary-gate.yml`, `scripts/m3_boundary_gate.sh`) builds both services, runs the suite and removes the whole stack. Until now a failure left only the last 150 lines of each service's log, and by then the window that explained it was often gone. Every run now uploads the services' complete logs and the AI task queue's state as an artifact, pass or fail.

This is observability only. It changes no check, no queue behaviour and no result: the gate step alone decides the job's outcome, and the upload step cannot fail a passing gate (`continue-on-error`) or turn a failed one green.

## Where to find it

The artifact is named `boundary-gate-logs-<run id>-<attempt>-<job>` and is kept for 14 days, so it is tied to the workflow run, the attempt and the job. `MANIFEST.txt` at its top repeats them (the run's URL, attempt, workflow, job, event, GitHub's SHA) with the backend and ai-service revisions under test. For a pull request run the backend revision is the PR's merge commit, not the branch head.

## What it holds

Two snapshots, each a directory:

| Directory | Taken | Why |
|---|---|---|
| `after-main-suite/` | Straight after the main suite, which holds the two-worker dispatch test | Later steps stop and restart services, and a container that is recreated loses its log |
| `final/` | On every exit, before the stack is removed | The whole run's logs |

Each holds:

- `<service>.log`: the service's complete log with timestamps, for every service in the stack (`ai-worker`, `ai-worker-faults`, `ai-service`, `backend`, `backend-worker` with both replicas, `redis`, `postgres` and the rest). That includes the AI worker's full log: task IDs, job IDs, worker identity and timestamps. Compose keeps a container's log across stop and start until the container is removed.
- `ai-stream-state.txt`: the AI task stream's length, the worker group's consumers, and its pending entries (entry ID, consumer, idle milliseconds, delivery count). Entry IDs, never a task payload: no command that returns entry contents is issued.

## Redaction

Everything is redacted before it is written. Removed: the value of every secret in `deploy/m3.env` (and the model-mirror token), `Authorization`, `Cookie` and signature headers, bearer and JWT tokens, `password`, `secret`, `token`, `api_key`, `signature` and `credential` fields, credentials inside URLs, e-mail addresses, and request query strings. Kept: task, job, tenant and worker identifiers, entry IDs, timestamps and messages, because an investigation needs them.

As a recorded check, each written file is searched again for every known secret value. A file that still holds one is deleted and replaced by a one-line `REDACTION-FAILED` note, so an unredacted file is never uploaded. `tests/test_boundary_gate_logs.py` proves both: that each of those kinds of content is removed from a log while the identifiers survive, and that a filter that fails to remove a secret leads to the file being withheld.

## Reading a lost task

For a job that reports `AI_TASK_LOST`, take the stream entry ID from the failing test's dispatch evidence and search the `ai-worker` log for it and its task ID. The events that decide it are `ai_service_task_started`, `ai_service_task_lease_unconfirmed`, `ai_service_task_fenced` and `ai_service_stream_entry_reclaimed` (which names the consumer and the outcome). `ai-stream-state.txt` shows which consumers existed and what was still pending.

## What it does not hold

Nothing beyond what the services print themselves, filtered as above. The artifact is as sensitive as the run's own log: it is private to the repository's readers, and expires after 14 days.

## Synthetic data only

**The gate must only ever run against synthetic test data.** The stack it starts holds documents, accounts and conversations made by the boundary tests, from empty volumes. It must never be pointed at, restored from, or fed with production student conversations, uploaded documents or real student records, whether by a changed compose file, a restored volume or a replayed request.

The artifact's redaction (secrets, credentials, e-mail addresses, query strings) is not a substitute for this. It removes what it recognises; it cannot make real student content safe to keep in a workflow artifact, and personal or academic content in a log is not something a pattern filter finds. If real data were ever in a gate run, treat the run's artifact as an incident: delete it and the run's logs, and tell the repository's owner.
