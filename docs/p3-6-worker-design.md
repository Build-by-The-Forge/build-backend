# P3-6 — backend ingestion worker: design (revision 2.2)

**Status:** proposed, for approval before implementation. This is plan decision D5: "a durable backend worker; its execution and recovery semantics are designed in P3-6". P3-1 PR 5, the prerequisite, has landed.

**Revision 2.2 (2026-10-27)** answers the review of 2.1 on #38.

- **The flaw:** in 2.1 the `lost` transition and the stream `XACK` were two steps. A reclaimer that died between them left an entry pending that no later pass would acknowledge.
- **The fix:** both now happen in one Lua script over both keys, which share a cluster slot. The script is also idempotent: a record already `lost` for that entry, or already expired, has its entry acknowledged.
- **New test:** fault injection at each point, then a restart, proves the entry is always eventually acknowledged and never executed (§7.3, §14).

**Revision 2.1 (2026-10-27)** answers the review of revision 2 on #38.

- **The flaw:** reclaiming a dead worker's stream entries by pending idle time (`XAUTOCLAIM`) could fence a *healthy* long-running worker. Idle time is independent of the renewed task lease.
- **The fix:** idle time now only nominates candidates (`XPENDING`, read-only). Reclaim is an atomic Lua transition on the task record that requires an expired lease and a matching owner. Renewal is a matching compare-and-set, so the two serialise in Redis.
- **New tests:** a handler renewing across five lease windows is never reclaimed, and concurrent renew-and-reclaim always yields exactly one outcome (§7.3, §14).

**Revision 2 (2026-10-27)** answers the review of revision 1 (build-backend#24). That PR was closed by the main-branch force push of 2026-10-26, not by a review decision.

1. **A task's liveness is now a renewed lease** in the AI-service's shared task record (§6, §7).
   - In revision 1, a task reported as `running` restarted the backend deadline. A crashed AI worker leaves its record `running`, and its stream message pending, forever, so recovery could postpone the job indefinitely.
   - Now an expired lease makes the task `stalled`, which the recoverer fails and retries.
   - A dead worker's stream entries are reclaimed and fenced.
   - A boundary test kills the worker and proves the job is retried to `ready`.
2. **Transaction and row-lock boundaries are explicit** (§4).
   - Each job is claimed, processed and committed in its own transaction, which locks exactly that one row.
   - No transaction holds a batch of locks across external calls. A lock is held for at most one bounded external call.
3. **The review's recommended decisions are adopted** (§16): the system actor, explicit tenant checks, the defaults, and no backend lease.

## 1. Goal

No ingestion job needs a manual endpoint call to make progress:

- a queued job is dispatched;
- a retryable failure is retried with backoff;
- a job whose AI worker died is recovered and retried;
- an object stored without a committed row is eventually deleted.

All of this stays correct with several workers running, and across crashes and restarts. A job is never left falsely `ready`, and nothing crosses tenants.

**Non-goals:**

- changing the job state machine (`app/domain/content/job.py`) or the callback rules;
- a general-purpose task framework.

The manual endpoints (dispatch, retry, reconcile, reprocess) stay, for operators.

## 2. What exists

- **Job states:** `queued → processing → extracted → chunked → indexed → ready`, or `failed`.
- **Fields:**
  - `attempt_count` / `max_attempts`;
  - `next_retry_at`;
  - `last_dispatched_at`;
  - `run_number`.
- **Dispatch** is idempotent at the AI-service. The key is `{job}-r{run}-a{attempt}`, and a repeated dispatch returns the same task (`DUPLICATE`).
- **Callbacks** are applied once each, through the event ledger, under the job's row lock.
  - A callback for another attempt, run or task is **stale** and changes nothing (boundary C21).
  - A ready job answers late callbacks as superseded. `ready` is reachable only through `indexed` for the current attempt.
- **Reconcile** asks the AI-service for a task's status and events, and applies the undelivered ones.
- **AI-service side today:**
  - A worker marks the task record `running` **once**, and nothing refreshes it.
  - Its execution lease lives only in process memory.
  - The task-status API, a different process, cannot see that lease.
  - The Redis stream consumer reads only new entries, so a crashed worker's entry stays pending.

  §7 changes all of this.

## 3. Process model

- **One image, its own entrypoint:** `python -m app.worker`. It runs the same code and configuration as the API, with no HTTP listener.
- **Replicas:** any number. Correctness never depends on how many run.
- **Database connections:** the worker has its own small pool, one connection per loop plus one.

There are four loops, each with its own interval and a bounded number of jobs per tick:

| Loop | Interval (default) | Work per tick |
|---|---|---|
| Dispatcher | 2 s, woken early when a job is queued | up to 20 due jobs |
| Retrier | 10 s | up to 50 retryable failures |
| Recoverer | 60 s | up to 20 jobs past their deadline |
| Orphan sweeper | 1 h | one paged pass over the asset prefixes |

**Idle cost:**

- An idle tick is one indexed query.
- A tick that reaches its limit runs again at once instead of sleeping.

## 4. Claiming work: one transaction per job

Every loop handles jobs **one at a time, one transaction each**. No transaction selects or locks a batch:

```text
repeat up to the loop's per-tick limit:
    BEGIN
      SELECT … FROM content_ingestion_jobs
      WHERE <the loop's condition>           -- e.g. status='queued' AND due
      ORDER BY created_at
      LIMIT 1
      FOR UPDATE SKIP LOCKED                 -- locks exactly this one row
      (no row → COMMIT and end the tick)
      re-check the state through the domain   -- e.g. ensure_dispatchable
      at most one external call, bounded      -- dispatch / task status (10 s)
      record the outcome on the job
    COMMIT                                    -- releases the row lock
```

**Locks held:** one row, for at most one external call. The gateway's total timeout is 10 s, with connect and read timeouts inside it. `lock_timeout` and `statement_timeout` are set on the worker's sessions, so a transaction can never be held longer than the call bound plus query time. No connection is held across a sleep.

**Callbacks during a dispatch:** the AI-service may call back about a job whose dispatch transaction is still open. That callback waits at most until the commit (≤ 10 s) because it takes the same row lock. If the backend answers it 503 instead, the AI-service's delivery retries it. A queued job's first callback can only follow its dispatch, so there is nothing to apply until then.

**Several workers:** `SKIP LOCKED` gives each job to at most one transaction at a time. The others skip it and take the next due job.

**Crash in the middle:** the transaction rolls back and the job is unchanged, for example still `queued`. The next tick repeats the same step with the **same idempotency key**, so the AI-service answers `DUPLICATE` with the original task. Nothing is lost and nothing runs twice.

**No backend lease columns:** the row lock covers the claim and the idempotency key covers the external effect. A `claimed_by` / `claimed_until` lease would add a migration and an expiry rule for no extra guarantee. Liveness of the *AI task* is a separate signal (§7).

## 5. Retry and backoff

- **Which failures:** a job that is `failed`, `is_retryable`, and has `attempt_count < max_attempts`.
- **The delay:** the retrier calls `schedule_retry(delay)` with `delay = min(base · 2^(attempt−1), cap)`, plus or minus 20% jitter.
- **Defaults:** base 30 s, cap 15 min, `max_attempts` 3.
- **Hand-off:** the job becomes `queued` with `next_retry_at`, and the dispatcher takes it when it is due.
- **Terminal failures:** non-retryable failures, such as `ASSET_INTEGRITY_MISMATCH` or `ASSET_REFERENCE_REJECTED`, are terminal. Only an authorized reprocess starts a new run.
- **Claiming:** per job, as in §4.

## 6. Stuck-job recovery

A job is past its deadline when it is in `processing`, `extracted`, `chunked` or `indexed`, and its `updated_at` is older than the stage deadline. Defaults: 10 min for `processing`, 30 min for later stages. The recoverer claims it as in §4 and asks the AI-service for its task:

| AI-service reports | Action |
|---|---|
| Events not yet delivered | Applied through the ledger, exactly as callbacks are |
| `running` **with a live lease** (`lease_until` in the future) | The task is alive and making progress: `touch`, so the deadline restarts |
| `stalled` (lease expired), `failed`, or task unknown | `fail_processing("AI_TASK_LOST", retryable=True)`; the retrier takes over with a new attempt, and so a new idempotency key |
| AI-service unreachable | Nothing changes. Retried next tick, and counted. |

**`running` alone never extends a deadline.** Only a lease the AI worker renewed recently does (§7). A dead worker stops renewing, so its lease expires within `TASK_LEASE_SECONDS`, and the next recoverer pass fails and retries the job.

**Hard cap:** a job in flight longer than `WORKER_MAX_IN_FLIGHT_SECONDS` is failed `AI_TASK_TIMEOUT` (retryable) even if its lease is live. The default is 3600 s, above the AI-service's own extraction deadline of 1800 s. This catches a worker that renews its lease but never finishes.

## 7. Task liveness on the AI-service side (new)

1. **A renewed lease in the shared task record.**
   - When a worker starts a task, it writes `state=running`, `worker_id`, `lease_until = now + TASK_LEASE_SECONDS` (default 60 s) and `heartbeat_at` to the task record in Redis.
   - While the handler runs, a background renewal extends `lease_until` every `TASK_LEASE_SECONDS / 3`. Each stage report (`extracted`, `chunked`, `indexed`) renews it too.
   - A terminal state clears the lease.
   - The renewal is a compare-and-set on `worker_id`, so a fenced worker (point 3) cannot renew a task it no longer owns.
2. **Status reports liveness.**
   - `GET /v1/ingest/tasks/{id}` reports `running` only while `lease_until` is in the future. Otherwise it reports `stalled`, with `lease_until` and `heartbeat_at` included.
   - `stalled` is derived from the record and the clock, never stored, so it needs no writer.
3. **A dead worker's stream entries are reclaimed and fenced, and only a dead worker's.**
   - **Stream idle time only nominates candidates.** Redis measures a pending entry's idle time from its last delivery or claim, independently of the task lease. A healthy handler that runs longer than any idle threshold keeps its entry pending, so idle time alone must never reclaim, claim or acknowledge anything. There is no `XAUTOCLAIM`, because it transfers ownership of every idle entry it returns.
   - **Finding candidates:** each AI worker periodically lists pending entries with `XPENDING … IDLE TASK_LEASE_SECONDS × 2`, which is read-only and changes no ownership.
   - **The lease decides, and the transition and the acknowledgement are one step.** The task record and the stream live in the same Redis instance. In a Redis Cluster, both keys carry the same hash tag (`{ai-tasks}`), so they share a slot. For each candidate, a single Lua script takes both keys and the entry id and runs atomically:
     1. **Record live:** if the record is not terminal, `lease_until < now` (the server's `TIME`, so clock skew between workers does not matter) and `worker_id` equals the entry's pending consumer, it sets `state=lost`, records the fence token and the entry id (`lost_entry`), and `XACK`s the entry, **without running it**.
     2. **Record already lost for this entry** (`state=lost` and `lost_entry` equals the entry id): it only `XACK`s. This makes the reclaim idempotent, so no recorded state can strand a pending entry.
     3. **Record gone:** the record has expired after its TTL, so there is nothing to fence and nothing that can run. It `XACK`s. The backend sees the task as unknown and recovers the job with a new attempt (§6).
     4. **Otherwise** (a live lease, another owner, or another terminal state), it changes nothing.

     A record whose lease is live is left untouched, so a renewing handler is never reclaimed, however long it runs. No crash can separate the `lost` transition from the acknowledgement, because both happen inside one script. A reclaimer that dies before or after the script leaves a state the next pass handles (case 1, or cases 2 and 3).
   - **Renewal is guarded by the same atomicity.** It is a Lua compare-and-set that extends `lease_until` only while `worker_id` still matches and the state is `running`. A renewal and a reclaim of the same record therefore serialise in Redis: either the renewal lands first and the reclaim sees a live lease, or the reclaim lands first and the renewal is refused, after which the worker stops and reports nothing.
   - **Recovery belongs to the backend alone:** a new attempt with a new task. So a reclaimed entry is never executed twice, and the stream does not grow without bound.
4. **A zombie cannot cause a false `ready`.**
   - Suppose a "dead" worker was only partitioned, and finishes the old attempt after the backend has retried.
   - Its callbacks name the old attempt and are **stale** at the backend ledger, so they change nothing.
   - Its write to the index replaces the same run's chunks with the same deterministic content (same document, run and chunker), so the index is unchanged.
   - `ready` requires the current attempt's `indexed` callback, which follows the current attempt's committed write.

## 8. Orphaned-object reconciliation

This is the tracked requirement from P3-1 PR 2, §6.

1. List the objects under `tenants/` with `ListObjectsV2`, paginated at 1000 keys. The backend identity has List permission on its bucket.
2. Parse each key as `tenants/{tenant}/assets/{asset_id}/{sha256}`. A key that does not parse is **reported, never deleted**.
3. For each page, one query fetches the rows whose `id` is among the page's asset ids. An object is an orphan when no row has that id, or the row's tenant or managed key differs.
4. An orphan is deleted only if its `LastModified` is older than the **grace period**: default 24 h, minimum 1 h. An upload in progress, whose object exists before its row commits, is always younger than that.
5. Each deletion is logged with its code and reason, never keys or bytes, and counted. Kept objects are counted too.

**Safety:**

- Running it twice changes nothing more.
- `DeleteObject` is idempotent.
- `pg_try_advisory_lock` keeps it to one sweeper at a time.

## 9. Who dispatches: a system actor, tightly scoped

The worker signs a **system** context (`ServiceContext.for_system`) naming the job's tenant. The tenant is the asset's tenant, copied into the job at creation.

**AI-service accepts a system actor for exactly two routes:** `POST /v1/ingest/dispatch` and `GET /v1/ingest/tasks/{id}`. For both, the tenant comes from the verified context.

**Tenant ownership is checked on every call:**

- a dispatch stores the context's tenant on the task;
- a status lookup for a task of another tenant is 404, as today (C23, task-status tenant scoping).

**Authorization stays where it was decided:** when an authorized user created or reprocessed the job (`require_permission(CONTENT_JOB_MANAGE)`, a tenant-owned asset, managed storage). Dispatch is mechanical delivery of that decision.

**Tests:**

- a system context is refused (403) on every other AI route: chat, explain, generate, retrieve, memory;
- a system context naming tenant A cannot read or dispatch tenant B's tasks;
- the backend worker never signs a context for a tenant other than the job's.

## 10. Shutdown and crashes

**SIGTERM:**

1. stop claiming;
2. let in-flight transactions finish, within a 25 s grace period;
3. exit.

**A transaction cut short** rolls back. Every action is idempotent (the dispatch key, the callback ledger, conditional transitions), so the next tick redoes it safely.

**Liveness probe:** each loop records its last completed tick. `python -m app.worker --check` fails if a loop is more than 3 intervals late.

## 11. Data and indexes

- **Backend:** no new tables or columns. One migration adds a partial index for the loops' selections: `(status, next_retry_at, created_at)` on `content_ingestion_jobs`. It is reviewed by `scripts/review_migration.py` and checked by the schema-drift gate.
- **AI-service:** the task record gains `worker_id`, `lease_until` and `heartbeat_at` fields. It is a Redis hash with a TTL, so no schema migration is needed.

## 12. Configuration

**Backend:**

- `WORKER_DISPATCH_INTERVAL_SECONDS`
- `WORKER_DISPATCH_BATCH`
- `WORKER_RETRY_BASE_SECONDS`
- `WORKER_RETRY_CAP_SECONDS`
- `WORKER_STUCK_PROCESSING_SECONDS`
- `WORKER_STUCK_STAGE_SECONDS`
- `WORKER_MAX_IN_FLIGHT_SECONDS`
- `WORKER_ORPHAN_GRACE_SECONDS` (minimum 3600)
- `WORKER_ORPHAN_SWEEP_INTERVAL_SECONDS`
- `WORKER_SHUTDOWN_GRACE_SECONDS`

**AI-service:**

- `TASK_LEASE_SECONDS` (default 60; minimum 15)

All take the defaults above and are validated by range.

## 13. Observability

- **Counters:**
  - jobs dispatched;
  - dispatch failures, by code;
  - retries scheduled;
  - terminal failures;
  - recoveries, by outcome (alive / stalled / lost / unreachable);
  - in-flight cap hits;
  - stream entries reclaimed;
  - orphans deleted and kept.
- **Gauges:**
  - queued jobs due, and the oldest one's age;
  - tasks with an expired lease.
- **Logs:** structured, with job, task and correlation ids. Never keys, bytes or credentials.

## 14. Tests

**Unit:**

- the backoff formula and its bounds;
- deadline selection;
- `running` with an expired lease is reported `stalled`;
- the recoverer touches only on a live lease, and fails on `stalled`;
- the in-flight cap;
- key parsing (orphan sweep);
- the shutdown sequence.

**PostgreSQL (`pg_smoke`):**

- two workers ticking concurrently over 50 queued jobs dispatch each **exactly once**;
- **a transaction holds exactly one row lock.** While a dispatch call is in progress, another session can lock every other due job;
- a transaction killed mid-dispatch leaves the job queued, and the next tick dispatches it with the same key;
- a callback arriving during a dispatch transaction is applied after its commit.

**AI-service (Redis):**

- the lease is renewed while a handler runs, and lapses when the worker stops;
- **a healthy handler is never reclaimed:** it renews its lease across at least five lease windows while its entry stays pending well past the idle threshold. Reclaim passes run throughout. The task stays `running` with its owner, the entry stays pending, and the handler completes normally;
- a dead consumer's entry (no renewals, lease expired) is marked `lost` and acknowledged without being run, in one script: after it, the record is `lost` **and** the entry is no longer pending, with no state where only one holds;
- **crash and restart:** a reclaimer stopped by fault injection at each point (before the script, between candidate listing and the script, and after the script before its next pass) is restarted, and the entry is eventually acknowledged and never executed. The same holds when a record is already `lost` with that `lost_entry` but the entry is still pending, as an older or interrupted reclaim would leave it, and when the record has expired;
- **the race:** a renewal and a reclaim of the same record, issued concurrently many times, always end in exactly one outcome. Either the lease is extended and nothing is reclaimed, or the task is `lost`, the renewal is refused and the worker stops. Never both;
- a fenced worker's renewal and state writes are refused.

**Real storage (storage gate):**

- an orphan older than the grace period is deleted;
- an orphan within it is kept, and so is an object with a row;
- an unparseable key is kept and reported;
- a second pass deletes nothing.

**Boundary (C22/C23):**

- upload → `ready` with no manual call;
- **the AI worker is killed mid-job** (`docker kill` while the job is in `processing`), then started again.
  - The lease expires, the recoverer fails the job `AI_TASK_LOST`, and the retrier dispatches attempt 2.
  - The job reaches `ready` with `attempt_count == 2`, and only attempt 2's events are applied.
  - It is not merely touched: the test asserts the attempt changed.
- the killed attempt's late callbacks, replayed, are stale;
- a system context cannot reach chat or retrieve, nor another tenant's task.

## 15. PRs

1. **AI-service:** the task lease and its atomic renewal, `stalled` in status, lease-conditioned reclaim and fencing, and system-actor access limited to dispatch and status. This PR includes its Redis and route tests.
2. **Backend:** the jobs index migration, and the system-actor dispatch path through the gateway.
3. **Backend:** the worker process (dispatcher and retrier, per-job transactions, shutdown, liveness), with the `pg_smoke` concurrency and lock tests.
4. **Backend:** the recoverer (lease-aware, with the in-flight cap).
5. **Backend:** the orphan sweeper.
6. **Compose and the boundary topology** run the worker, with C22 (no manual call) and C23 (worker killed and recovered) automated.

## 16. Decisions

These are the review's recommendations, adopted in this revision:

| Decision | Choice |
|---|---|
| Dispatch authorization | A: system actor, restricted to dispatch and task status (§9) |
| Tenant isolation | Tenant ownership checked on every task lookup and dispatch; cross-tenant attempts tested (§9, §14) |
| Retry policy | 3 attempts; exponential backoff from 30 s to a 15 min cap, with ±20% jitter |
| Stuck-job deadlines | 10 min for `processing`, 30 min for later stages; extended only by a live AI lease; hard cap 1 h |
| Orphan cleanup | 24 h grace (minimum 1 h); unknown key formats never deleted |
| Row locks versus leases | No backend lease: one transaction per job, locking one row (§4). Task liveness comes from the AI-service lease (§7). |
