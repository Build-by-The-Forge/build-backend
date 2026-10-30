# Phase 3 release record: FUTA course ingestion to retrieval

**Audited on 2026-10-30, at build-backend `807895e` and ai-service `208ea52`.**

**Release decision: not yet recorded.** See [Decision](#decision). The product owner records it after reading the limitations below.

**Summary:** every exit criterion has evidence. The correctness guarantees held under real worker death, record loss and racing attempts. Two limits matter most for the decision: no production deployment is defined yet, so the forced-shutdown requirement below is unverified; and retrieval quality on real documents has been compared, not certified.

## Exit criteria

| Requirement | Result | Evidence |
|---|---|---|
| ADR and real-document evaluation | Met, limited scope | ADR 001; ai-service #32. Approved for comparing strategies only |
| P3-6 implemented to the approved design | Met | Design rev 2.5; PRs below; [differences from the design](#differences-from-the-design) |
| C22: upload → automatic ingestion → `ready` → retrieval | Passed | Boundary gate. At `ready`, every chunk is from the job's own attempt and the fence names it |
| C23: worker killed → lease expiry → `AI_TASK_LOST` → attempt 2 → `ready` | Passed | Boundary gate, with a real SIGKILL |
| Race, both orderings | Passed | Boundary gate, real PostgreSQL. A held stale write is refused by the database fence |
| Tenant isolation | Passed | Boundary gate: the other tenant retrieves nothing, and cross-tenant calls are refused |
| Stale callbacks rejected | Passed | Boundary gate: attempt 1's signed callback is answered `stale` and the job does not change |
| Queued tasks wait; hard cap holds | **Unit-tested only** | `test_recoverer.py`. No end-to-end backlog simulation |
| Extraction-deadline flake | Reproduced, root-caused, corrected, regression-tested, stress-tested | ai-service `docs/p3-2-extraction-deadline-race.md`. Not proven impossible |
| Observability test isolation | Fixed | #49: file alone, each test alone, ten repeats, full suite |
| Full cross-service suite | Passed | Gate run 41057565422 on both mains |

### Final gate, run 41057565422

Tested backend `807895e` and ai-service `208ea52`:

| Phase | Result |
|---|---|
| Main boundary run | 193 passed |
| Race | 2 passed |
| C23 prepare, then verify | 1 passed, 1 passed |
| Object storage down | 2 passed |
| Redis down | 3 passed |
| Production startup, refusal self-test, offline OCR with the real engine | passed |

The seven required checks are green on the final merge of each repository.

## Accepted limitations, pending the decision

| Limitation | Impact | Follow-up |
|---|---|---|
| A native OCR call hangs permanently | OCR is unavailable on that worker. Scanned documents fail with the permanent `EXTRACTION_TIMEOUT` and need a manual reprocess after restart. Only logs show it | Killable OCR process; alerting |
| A page render hangs permanently | That extraction and the worker's graceful shutdown stay blocked until forced termination. Not observed | Evaluate process isolation for rendering |
| Forced termination is required for those hangs | Depends on the deployment requirement below | Verify when a deployment exists |
| Queue backlog | Unit-tested, not simulated end to end | Backlog simulation in a future reliability test |
| Chunks searchable before `ready` | If an attempt commits chunks and then fails to reach `ready`, those chunks are searchable until the next attempt replaces them (design §7.5) | Gate retrieval on job state in Mobile API Contracts |

## Deployment requirement: unverified

**Neither repository contains a production deployment configuration, and no hosting platform is named.** Only the database provider (Supabase) has been decided. So the reviewer's supervisor check could not be completed. Any deployment must provide:

1. SIGTERM to each worker process, which must run directly in exec form, not behind a shell that drops signals.
2. A finite stop timeout. For the backend worker it must exceed `WORKER_SHUTDOWN_GRACE_SECONDS` (25 s); 35 s is suitable.
3. SIGKILL when that timeout expires.
4. Automatic restart of a killed worker.

What is tested today:

- Under `docker stop -t 8`, the real OCR service with a healthy call exited with code 0. With a permanently hung call, it received SIGTERM, could not exit, and was ended by SIGKILL (exit 137).
- C23 proves jobs recover after that kill.

Two related facts:

- The AI worker has no bound of its own on draining after SIGTERM, so a long job runs until it ends or is killed; recovery covers the kill.
- `deploy/compose.m3.yml` sets no stop timeout, so Docker's 10 s default applies, shorter than the backend worker's 25 s grace. A killed dispatch rolls back safely, so this is harmless in the gate.

## What this release does not establish

- **Retrieval quality.** On 40 questions over text-layer pages of 141 real PDFs, recall@5 was dense 0.675, hybrid 0.625, keyword 0.325, with no significant difference between dense and hybrid. The questions have had no human review, and the 1,459 scanned pages (45%) are unmeasured.
- **Absence of the extraction race.** 6,000 clean stress iterations against 3 failures in 4,200 before the fix. That result would occur by chance about 1.4% of the time with no fix. The stress runs use a fake OCR engine.
- **Production behaviour.** No test ran on the production database provider or a production host.
- **Metrics in use.** Counters and logs exist, but no alerts or dashboards are configured.

These stay on a separate quality track, outside this release gate: human review of the questions, scanned-page evaluation, and the dense, hybrid and weighted comparison. Hybrid stays the default until that comparison is done.

## Review record

The reviewer's GitHub integration returned 403 each time, so **no formal GitHub approval exists** for these PRs. Each verdict is recorded as a PR comment naming the reviewed commit:

| PR | Verdict |
|---|---|
| build-backend #38 (design) | No further findings; the product owner accepted that as approval |
| ai-service #32 (evaluation) | Approved for limited comparative purpose |
| build-backend #42, #43 (4a, worker) | Approved |
| ai-service #40 (extraction fix) | Conditionally approved; the condition is the deployment requirement above |

The other P3-6 PRs merged on their own gates under the agreed rule: ai-service #33 to #39; build-backend #39 to #41 and #44 to #49.

## Differences from the design

- **A lost record ends the attempt.** Design §7.1 and §14 allow an attempt whose record was lost to still reach `ready` if it finishes before recovery. Since ai-service #34, it cannot report anything, so it ends on attempt 2. This is stricter than the design.
- **Queued tasks wait.** §6 was clarified on 2026-10-30 (#47). The hard cap is unchanged.
- **The locked dispatch step** is bounded at 15 s in total: 10 s for the AI call and 5 s for the storage check that §4 did not count.
- **`scripts/review_migration.py`**, named in §11, does not exist. Migrations are checked by the postgres gate.

## Decision

To be completed by the product owner:

- [ ] **Accept** the limitations above for Phase 3, with the deployment requirement carried into the first deployment.
- [ ] **Hold** until: ______

Decided by: ______ Date: ______

## Next

Mobile API Contracts and Boundary Gate, written from the intended public API and checked against the backend. Then FUTA Maps, Offline AI, and integration and launch readiness. The mobile repository is `Build-UI`.
