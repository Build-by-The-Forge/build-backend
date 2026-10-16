# Phase 3 readiness audit — document ingestion to retrieval (backend)

**Date:** 2026-10-16. **Baseline:** build-backend `a531c10` (main). The AI-service half and the plan built on both are in ai-service:
- `docs/phase3-ingestion-readiness-audit.md` (baseline `87a0d9e`);
- `docs/phase3-ingestion-plan.md`.

**Scope:** inspection only; no code changed. Line references are to `a531c10`.

## 1. Summary

- **BUILD never holds a document's bytes.**
  - There is no upload endpoint, object store, storage client or storage setting in `app/` or in the deployed topology (`deploy/compose.m3.yml`).
  - An asset is registered with a client-supplied `storage_uri`, which the domain only checks is not empty. Any string is accepted, and it is forwarded to the AI service as is.
- **The ingestion job lifecycle is complete and strict.** The state machine runs `uploaded → queued → processing → extracted → chunked → indexed → ready`, with stage evidence, retries, reprocessing and callback rules. The boundary gate proves it end to end on the failure outcome.
- **Nothing moves a job on its own.** Creating a job only queues it. Dispatch, reconciliation and due retries each need an explicit API call, and the backend runs no background work at all.
- **C22 is still the re-scoped failure test.** It proves the signed path ends `failed` with `INGESTION_PIPELINE_UNAVAILABLE`; the design's original C22 ("job `ready`") is not yet testable.

## 2. Findings

### Storage and asset registration

| Component | State | Evidence |
|---|---|---|
| Upload of file bytes | **Absent.** No endpoint receives file content | `app/api/content/` |
| Object storage | **Absent.** No S3 or MinIO client, no storage setting, no storage service in the topology | `app/`; `deploy/compose.m3.yml` |
| Asset registration | Client supplies `file_name`, `mime_type`, `file_size_bytes`, `content_sha256` and `storage_uri`; the backend stores them as given | `app/api/content/asset_schemas.py:11-17`; `app/api/content/assets.py:41, 154` |
| `storage_uri` validation | Non-empty only: no scheme, bucket, tenant prefix or reachability check | `app/domain/content/asset.py:66-67` |
| Size, hash and MIME | Declared by the client, never measured: the backend has no bytes to measure | as above |

### Ingestion jobs

| Component | State | Evidence |
|---|---|---|
| State machine | **Complete**, with ordered stages, stage evidence and terminal rules | `app/domain/content/job.py:60-72, 187-305` |
| Callback application | **Complete**: active-attempt check, ordering, idempotent events | `job.py:396-469`; `app/application/content/job_handlers.py:233` |
| Retry and reprocess | **Present**, rule-checked (`RetryNotDue`, a scheduled retry delay) | `job.py:36, 366`; `job_handlers.py:90-148` |
| Signed dispatch to the AI service | **Works** | `app/infrastructure/content/ai_gateway.py:84-123` |
| Reconciliation against AI task status | **Works** | `job_handlers.py:400` |
| Automatic dispatch | **Absent.** `CreateIngestionJobHandler` only queues; dispatch is a separate `POST /content/jobs/{id}/dispatch` | `job_handlers.py:61-73`; `app/api/content/jobs.py:226` |
| Automatic reconciliation of stuck jobs | **Absent.** Only `POST /content/jobs/{id}/reconcile` | `jobs.py:288` |
| Automatic due retries | **Absent.** Only `POST /content/jobs/{id}/retry` | `jobs.py:169` |
| Background work of any kind | **None.** The lifespan only initialises the database; there is no scheduler, worker or outbox process | `app/main.py:61-63` |

### Boundary tests

| Test | Asserts today | Evidence |
|---|---|---|
| C22 | Signed dispatch → worker → signed callback → job `failed` with `INGESTION_PIPELINE_UNAVAILABLE` (re-scoped in M3-08) | `boundary/test_ingestion_boundary.py:78-91`; `docs/phase1-m3-completion-report.md:95, 107` |
| C23 | Reconciliation reflects the AI task state, on the failure outcome; task status is tenant-scoped | `boundary/test_ingestion_boundary.py:97-115` |
| C22 as designed | "upload → dispatch → AI processes → signed callbacks → job `ready`" | `docs/phase1-m3-boundary-design.md:375`; not testable until storage and the AI pipeline exist |

## 3. What the backend must add for Phase 3

In dependency order. The plan in ai-service `docs/phase3-ingestion-plan.md` gives scope, acceptance criteria and gates.

1. **Storage and upload**:
   - a real upload path that stores the bytes;
   - a server-measured size and SHA-256, with the MIME type checked;
   - a `storage_uri` that the backend generates and validates (scheme, bucket, tenant prefix), never taken from the client.
2. **Background dispatch, reconciliation and due retries**, so that a queued job reaches the AI service and a stuck job is noticed without anyone calling an endpoint.
3. **C22 restored to its design**: upload to `ready`, with stage evidence.

## 4. Not changed by this audit

No source, test, dependency or configuration was modified.
