# P3-6 — backend ingestion worker: design (proposed)

Status: **proposed, for review before implementation** (plan decision D5: "a durable backend worker; its execution and recovery semantics are designed in P3-6"). Implementation starts after this is approved and P3-1 PR 5 has landed.

## 1. Goal

No ingestion job needs a manual endpoint call to make progress. A queued job is dispatched, a retryable failure is retried with backoff, a job lost in flight is recovered, and an object stored without a committed row is eventually deleted. All of this stays correct with several workers running, and across crashes and restarts.

**Non-goals:**
- changing the job state machine (`app/domain/content/job.py`) or the callback rules;
- a general-purpose task framework.

The manual endpoints (dispatch, retry, reconcile, reprocess) stay, for operators.

## 2. What exists

- **Job states:** `queued → processing → extracted → chunked → indexed → ready`, or `failed`.
- **Fields:**
  - `attempt_count` / `max_attempts`;
  - `next_retry_at`, set by `schedule_retry`, and `ensure_dispatchable` refuses a retry before it;
  - `last_dispatched_at`;
  - `run_number` (reprocess).
- **Dispatch** (`DispatchIngestionJobHandler`) is idempotent at the AI-service. The idempotency key is `{job}-r{run}-a{attempt}`, and a repeated dispatch returns the same task (`DUPLICATE`).
- **Callbacks** are applied once each, through the event ledger (`content_ingestion_events`), under a row lock.
- **Reconcile** (`ReconcileIngestionJobHandler`) asks the AI-service for a task's status and applies its undelivered events.
- **Locking:** `get_job_for_update` takes `SELECT … FOR UPDATE` on PostgreSQL.
- **Orphaned objects** (P3-1 PR 2): an object can exist with no row if a crash happened between `put` and commit, and the client never retried. Failed compensations are logged and counted (`content_upload_orphaned_objects_total`).

## 3. Process model

- **One image, its own entrypoint:** `python -m app.worker`. It runs the same code and configuration as the API, with no HTTP listener.
- **Any number of replicas.** Correctness never depends on how many run.
- **One asyncio loop with four independent loops**, each with its own interval and a bounded batch size:

| Loop | Interval (default) | Work per tick |
|---|---|---|
| Dispatcher | 2 s, woken early when a job is queued | dispatch up to 20 due jobs |
| Retrier | 10 s | schedule retries for up to 50 retryable failures |
| Recoverer | 60 s | reconcile up to 20 jobs stuck in flight |
| Orphan sweeper | 1 h | one paged pass over the asset prefixes |

**Efficiency:**
- An idle tick is a single indexed query.
- Every query uses an index that leads with `status` (section 10).
- A tick that finds a full batch runs again immediately instead of sleeping.

## 4. Claiming work: row locks, not leases

Each job is handled in its own short transaction:

```sql
SELECT … FROM content_ingestion_jobs
WHERE status = 'queued' AND (next_retry_at IS NULL OR next_retry_at <= now())
ORDER BY created_at
LIMIT :batch
FOR UPDATE SKIP LOCKED
```

For each row returned, the worker re-checks the state through the domain (`ensure_dispatchable`), dispatches, records the result, and commits.

- **Several workers:** `SKIP LOCKED` hands each queued job to at most one transaction at a time; the others skip it and take the next.
- **Crash during dispatch:** the transaction rolls back and the job is still `queued`. The next tick dispatches it again with the **same idempotency key**, so the AI-service answers `DUPLICATE` with the original task id. No duplicate work and no lost job.
- **Lock duration** is bounded by the gateway's timeout (10 s). A `SKIP LOCKED` worker never waits on it.
- **No new columns.** A lease (`claimed_by`, `claimed_until`) would add a migration and an expiry rule for a guarantee the row lock and the idempotent dispatch already give.

## 5. Retry and backoff

- **Which failures:** a job that is `failed` with `is_retryable` and `attempt_count < max_attempts`.
- **Backoff:** the retrier calls `schedule_retry(delay)` with `delay = min(base · 2^(attempt−1), cap)`, plus or minus 20% jitter. Defaults: base 30 s, cap 15 min, `max_attempts` 3.
- **Hand-off:** the job becomes `queued` with `next_retry_at`, and the dispatcher takes it when it is due.
- **Non-retryable failures** (`ASSET_INTEGRITY_MISMATCH`, `ASSET_NOT_IN_MANAGED_STORAGE`, and the like) are terminal. Only an authorized reprocess starts a new run.
- Selection is the same as in section 4: `status='failed' AND is_retryable AND attempt_count < max_attempts … FOR UPDATE SKIP LOCKED`.

## 6. Stuck-job recovery

A job counts as stuck when it is in `processing`, `extracted`, `chunked` or `indexed`, and its last progress (`updated_at`) is older than its stage deadline. Defaults: 10 min for `processing`, 30 min for later stages. The recoverer reconciles it with the existing handler:

| AI-service reports | Action |
|---|---|
| Events not yet delivered | They are applied through the ledger, exactly as callbacks are |
| `running` | Nothing to do; the deadline restarts from now (`touch`) |
| `failed`, or task unknown | `fail_processing("AI_TASK_LOST", retryable=True)`, then the retrier takes over |
| AI-service unreachable | Nothing changes; retried next tick, and counted |

**Worker interruption** (the C22/C23 recovery scenario): a job whose AI worker died stops reporting. It becomes stuck and is reconciled to `AI_TASK_LOST`, then retried with a new attempt and so a new idempotency key.

## 7. Orphaned-object reconciliation

This is the tracked requirement from P3-1 PR 2, §6.

1. List the objects under `tenants/` with `ListObjectsV2`, paginated at 1000 keys. The backend identity already has List permission on its bucket.
2. Parse each key as `tenants/{tenant}/assets/{asset_id}/{sha256}`. A key that does not parse is **reported, never deleted**: unknown keys are not ours to remove.
3. For each page, one query fetches the rows whose `id` is among the page's asset ids.
4. An object is an orphan when no row has that id, or the row's managed key differs. It is deleted only if its `LastModified` is older than the **grace period** (default 24 h, minimum 1 h). An in-flight upload, whose object exists before its row commits, is always younger than that.
5. Each deletion is logged with its code and reason (no keys, no bytes) and counted: `content_upload_orphaned_objects_deleted_total`. Objects kept within the grace period are counted too.

**Safety:**
- Running it twice changes nothing more.
- Two sweepers would only race to delete the same orphan, and `DeleteObject` is idempotent.
- `pg_try_advisory_lock` keeps it to one sweeper at a time anyway, so a pass is not wasted.

## 8. Who dispatches: the authorization context (decision needed)

Today a dispatch is signed as the **user** who called the dispatch endpoint (tenant, user, membership, role, `content.job.manage`), and the AI-service requires exactly that. A worker has no user.

| Option | How | Trade-off |
|---|---|---|
| **A. System actor** (recommended) | The worker signs a **system** context (`ServiceContext.for_system`) naming the job's tenant. The AI-service accepts a system actor for `/v1/ingest/dispatch` and task status only, with the tenant still taken from the verified context. | Authorization happens where it belongs: when an authorized user created or reprocessed the job (`require_permission(CONTENT_JOB_MANAGE)`, tenant-owned asset, managed storage). Dispatch is mechanical delivery of that decision. A small, explicit AI-side change, with tests that a system context cannot reach any other route. |
| B. Act as the job's creator | The worker re-signs as `created_by`, re-checking that the user's membership still grants the permission | It keeps a user in every signature, but a job is stuck if its creator leaves the tenant. It also needs membership lookups on every dispatch, and a worker impersonating users is a broader capability than a system actor that can only deliver jobs. |

Option A also needs the job's tenant. It is the asset's tenant, copied into the job at creation and checked by `owned_job`, so a worker can never dispatch a job into another tenant's context.

## 9. Shutdown and crashes

- **SIGTERM:**
  1. stop claiming;
  2. let in-flight transactions finish, within a 25 s grace period (under a typical 30 s termination window);
  3. exit.
- **A transaction cut short** rolls back. Every action is idempotent (dispatch key, callback ledger, conditional transitions), so the next tick redoes it safely.
- **Liveness:** each loop records its last completed tick. A probe (`python -m app.worker --check`) fails if a loop is more than 3 intervals late.

## 10. Data and indexes

- No new tables or columns.
- One migration adds a partial index for the loops' selections: `(status, next_retry_at, created_at)` on `content_ingestion_jobs`. It is reviewed by `scripts/review_migration.py` and checked by the schema-drift gate.

## 11. Configuration

`WORKER_DISPATCH_INTERVAL_SECONDS`, `WORKER_DISPATCH_BATCH`, `WORKER_RETRY_BASE_SECONDS`, `WORKER_RETRY_CAP_SECONDS`, `WORKER_STUCK_PROCESSING_SECONDS`, `WORKER_STUCK_STAGE_SECONDS`, `WORKER_ORPHAN_GRACE_SECONDS` (minimum 3600), `WORKER_ORPHAN_SWEEP_INTERVAL_SECONDS` and `WORKER_SHUTDOWN_GRACE_SECONDS`, with the defaults above, validated by range.

## 12. Observability

- **Counters:** jobs dispatched, dispatch failures (by code), retries scheduled, terminal failures, stuck jobs recovered (by outcome), orphans deleted and kept, sweep keys scanned.
- **Gauges:** queued jobs due, and the oldest due job's age (lag).
- **Logs:** structured, with job and correlation ids; never keys, bytes or credentials.

## 13. Tests

- **Unit:** the backoff formula and its bounds; deadline selection; key parsing (orphan sweep); the shutdown sequence.
- **PostgreSQL (`pg_smoke`):**
  - two workers ticking concurrently over 50 queued jobs dispatch each **exactly once**;
  - a transaction killed mid-dispatch leaves the job queued, and the next tick dispatches it with the same key;
  - retry selection under concurrency.
- **Real storage (storage gate):**
  - an orphan older than the grace period is deleted;
  - an orphan within it is kept, and so is an object with a row;
  - an unparseable key is kept and reported;
  - a second pass deletes nothing.
- **Boundary (C22/C23):**
  - upload → `ready` with no manual call;
  - an AI worker stopped mid-job is recovered and retried, not left stuck.

## 14. PRs

1. The jobs index migration and the system-actor dispatch path (both repos, with AI-side tests that a system context reaches only dispatch and status).
2. The worker process: dispatcher and retrier, shutdown, liveness.
3. The stuck-job recoverer.
4. The orphan sweeper (storage listing, grace period, advisory lock).
5. Compose and the boundary topology run the worker; C22/C23 automated.

## 15. Decisions for review

1. **Section 8: system actor (A) or creator re-sign (B).** Recommended: A.
2. **Defaults:** backoff 30 s → 15 min cap, 3 attempts; stuck deadlines 10 min (processing) and 30 min (later stages); orphan grace 24 h.
3. **Row locks without leases** (section 4).
