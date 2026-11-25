# GCP staging: verification report

**Status:** draft, 2026-11-25. Closes blueprint §10 items 2 and 3 only in part: what is below is from public Google Cloud documentation, and nothing was run against a Google Cloud project. Nothing has been created, enabled or paid for.

**How it was verified, and its limit.** Each finding below comes from a documentation search on 2026-11-25. The results gave page titles, URLs and excerpts. **I did not open and read the full pages.** So every row says what the excerpt supports, and anything the excerpt did not settle is marked **NOT CONFIRMED** with the check that settles it. Where a claim came from a vendor's own comparison page (not Google), it says so.

Access date for every URL below: **2026-11-25**.

## Summary

| # | Requirement | Result |
|---|---|---|
| 1 | Cloud SQL, PostgreSQL 17 with pgvector 0.8 | **Supported in principle; exact version on a PG 17 instance NOT CONFIRMED.** Latest release note: 0.8.5 |
| 2 | Managed Redis meeting Redis 8 | **Not met by any Memorystore product.** Options below; the requirement is not weakened |
| 3 | Cloud Run for backend, ai-service, workers | **Met.** Services for the two APIs, worker pools for the always-on loops, jobs for migrations |
| 4 | ClamAV | **Cannot run as a Cloud Run service** (raw TCP). A small Compute Engine VM is scaffolded |
| 5 | Cloud Storage and CDN | **Met for APKs.** The S3 adapter's use of GCS needs one staging test (checksum header) |
| 6 | Secret Manager, Monitoring, Logging | Secret Manager and worker-pool secrets confirmed from excerpts. Monitoring and Logging **not read** this session |
| 7 | Latency from Nigeria | A method you can run is in the last section |

## 1. Cloud SQL for PostgreSQL 17 and pgvector

- PostgreSQL 17 is offered: minor 17.11, regular support from 2024-10-22, deprecation 2033-02-01. Source: [Database versions and version policies](https://docs.cloud.google.com/sql/docs/postgres/db-versions) (excerpt).
- pgvector history from the release notes: 0.7.4 to 0.8.0 (November 2024), 0.8.0 to 0.8.1 (2025-11-19), **0.8.1 to 0.8.5 (2026-08-27)**. Source: [Cloud SQL for PostgreSQL release notes](https://docs.cloud.google.com/sql/docs/postgres/release-notes) (excerpt).
- **NOT CONFIRMED:** that 0.8.5 applies to PostgreSQL 17 specifically. The extensions page's per-version table was not readable in the excerpt ([Configure PostgreSQL extensions](https://docs.cloud.google.com/sql/docs/postgres/extensions)).
- Settle it with `SELECT extversion FROM pg_extension WHERE extname = 'vector';` on the staging instance. The first deploy step in the runbook records the answer.
- The repo's own stack runs pgvector **0.8.0** (`deploy/compose.m3.yml`). 0.8.5 is a newer patch of the same minor, so the gate here is ai-service's migration and retrieval tests against the staging instance, not a version number.
- `deploy/db-init/init-roles.sql` runs `CREATE EXTENSION vector` as the superuser. On Cloud SQL the `postgres` user is the closest equivalent, and it is not a true superuser. **NOT CONFIRMED** that `CREATE EXTENSION vector` succeeds as `postgres` and that `REVOKE ALL ON DATABASE ... FROM PUBLIC` behaves the same. The db-init job proves both on staging.
- africa-south1 is listed for Cloud SQL for PostgreSQL ([Region availability overview](https://docs.cloud.google.com/sql/docs/postgres/region-availability-overview), excerpt). The excerpt names machine series N2 and C4 for Enterprise Plus. **NOT CONFIRMED:** which edition and tier the staging instance can use there.

## 2. Managed Redis and the Redis 8 requirement

- Memorystore for Redis is based on Redis **7.2 and earlier**. Source: [Supported versions, Memorystore for Redis](https://docs.cloud.google.com/memorystore/docs/redis/supported-versions) (excerpt).
- Memorystore for Valkey supports Valkey 7.2, 8.0, 9.0 and 9.1 ([Supported versions, Memorystore for Valkey](https://docs.cloud.google.com/memorystore/docs/valkey/supported-versions), excerpt). **Valkey is not Redis 8.** Treating it as one would weaken the requirement, so it is not proposed.
- Redis's own site says Memorystore for Redis and Redis Cluster are frozen on 7.2 ([redis.io comparison](https://redis.io/blog/redis-vs-memorystore/)). That is a vendor page: use it as a pointer, not as proof. Google's own page says the same thing about 7.2.

**Nothing in Memorystore meets Redis 8.** Options:

| Option | Redis 8 | Managed | Notes |
|---|---|---|---|
| A. Redis Cloud through Google Cloud Marketplace ([Redis docs](https://redis.io/docs/latest/operate/rc/cloud-integrations/gcp-marketplace/)) | Redis states 8.x. **NOT CONFIRMED** for the plan and region you would buy | Yes | Billed through Google. Needs private connectivity to the VPC (**NOT CONFIRMED**: PSC or peering, and an africa-south1 or Europe region near the API) |
| B. Self-managed Redis 8 on a Compute Engine VM | Yes: you pin the image | No | **Scaffolded for staging** (`modules/redis_vm`). You own patching, persistence and failover |
| C. Memorystore for Valkey | No | Yes | Rejected. Revisit only by a decision to change the requirement, with a compatibility test |

**Recommendation:** B for staging now (cheap, honest about the requirement, exercises the real code path), and decide A or B for production once the first student journey has run. The backend uses Redis for rate-limit state with `AUTH_RATE_LIMIT_FAILURE_MODE=closed`, so Redis being down blocks sign-in: staging must prove the alert fires.

## 3. Cloud Run

- Worker pools reached general availability on **2026-04-14** ([Cloud Run release notes](https://docs.cloud.google.com/run/docs/release-notes), excerpt).
- Worker pools suit always-on, non-HTTP, pull-based work. They have no public endpoint, you set the instance count yourself (it does not autoscale), and billing is per instance lifetime ([Deployment options and resource model](https://docs.cloud.google.com/run/docs/resource-model), excerpt). Secrets are supported ([Configure secrets for worker pools](https://docs.cloud.google.com/run/docs/configuring/workerpools/secrets), excerpt).
- Jobs are run-to-completion. They fit `alembic upgrade head` and the role-init step.
- Mapping from the code (`app/worker.py`):

| Component | Command | Cloud Run resource |
|---|---|---|
| build-backend API | `uvicorn app.main:app` (port 8000) | Service |
| ai-service API | its own `uvicorn` | Service, internal ingress |
| backend worker (dispatch, retry, orphan sweep, recoverer, scans, scope assignments, attempt finalizer: the outbox dispatchers and ClamAV scans) | `python -m app.worker` | Worker pool, 1 instance |
| backend-registration-worker | `python -m app.worker --registrations` | Worker pool, 1 instance, separate from the above as in the compose topology |
| ai-service ingestion/OCR worker | `python -m app.worker` (ai-service) | Worker pool |
| Migrations | `alembic upgrade head` as the owner role | Job |

- **NOT CONFIRMED:** the Terraform provider's worker-pool resource schema. The CI validation job is the check.
- **NOT CONFIRMED:** that the backend can reach ai-service over internal ingress. Google's private-networking page says an internal Cloud Run call needs Direct VPC egress (all traffic routed to the VPC) and Private Google Access on the subnet ([Cloud Run private networking](https://docs.cloud.google.com/run/docs/securing/private-networking), excerpt). The Terraform does this and the first-deploy step proves it with a signed call.
- **Worker health.** `python -m app.worker --check` reads a heartbeat file in the container. A worker pool has no HTTP probe path, so Cloud Run cannot run that check for you (**NOT CONFIRMED** whether worker pools support a command or TCP probe). The runbook alerts on instance count and on log signals instead.
- africa-south1 is a Cloud Run location ([Cloud Run locations](https://docs.cloud.google.com/run/docs/locations), excerpt). The pricing tier differs between two Google pages: check the price when you pick the region.

## 4. ClamAV

- The backend worker talks to `clamd` over **raw TCP port 3310** (`CLAMAV_HOST`, `CLAMAV_PORT`).
- Cloud Run services and jobs can send traffic into a VPC but cannot receive it; the excerpt says only worker pools support Direct VPC ingress ([Container runtime contract](https://docs.cloud.google.com/run/docs/container-contract), excerpt). Cloud Run's own ingress is HTTP.
- **NOT CONFIRMED:** whether a worker pool can host `clamd` (no source for ClamAV on a worker pool was found).
- **Decision for staging:** a small Compute Engine VM on Container-Optimized OS running the repo's pinned `clamav/clamav:1.4` image, on the private subnet, port 3310 open only to the worker's service account. This is documented-certain, and it keeps files inside BUILD's network (the compose file's stated reason for self-hosting). Cost: one `e2-medium`-class VM (ClamAV needs roughly 2 GB of RAM). Memory size is **NOT CONFIRMED**; the staging run measures it.
- The VM needs outbound access for signature updates (`freshclam`): Cloud NAT covers it.

## 5. Cloud Storage and CDN

- A global external Application Load Balancer with a **backend bucket** and **Cloud CDN enabled** serves a bucket through the CDN. Cloud CDN has to be turned on explicitly on the backend bucket, and the regional load balancer's backend bucket does not support Cloud CDN. Sources: [Set up a backend bucket](https://docs.cloud.google.com/cdn/docs/setting-up-cdn-with-bucket), [Configure private bucket access](https://docs.cloud.google.com/cdn/docs/configure-private-bucket-access) (excerpts).
- The APK bucket is public-read behind the CDN by design (the file hash in the update contract is what protects integrity). The document bucket stays private and is **never** put behind the CDN.
- **S3 compatibility for documents.** The Cloud Storage XML API accepts S3 libraries when pointed at `https://storage.googleapis.com` with HMAC keys tied to a service account; the secret is shown once ([Interoperability](https://docs.cloud.google.com/storage/docs/interoperability), [Manage HMAC keys](https://docs.cloud.google.com/storage/docs/authentication/managing-hmackeys), excerpts). An organisation policy (`storage.restrictAuthTypes`) can block HMAC use.
- The adapter (`app/infrastructure/content/s3_object_storage.py`) uses only PutObject, GetObject, HeadObject, DeleteObject and ListObjectsV2, signature `s3v4`. Those are within what the excerpts describe. Two things are **NOT CONFIRMED** and are the first staging upload test:
  1. PutObject sends the **`x-amz-checksum-sha256`** header. Whether Cloud Storage accepts, ignores or rejects that header was not found in the excerpts.
  2. The signing region. `OBJECT_STORAGE_REGION` defaults to `us-east-1`; Google's documented value for S3 clients was not read.
- If (1) fails, the fix is a small adapter change (send the header only when configured). That is a code change in a different PR, not part of this one.
- The HMAC secret is a long-lived credential. Terraform creates the service accounts and bucket permissions; creating the HMAC key stays a manual step so the secret never enters Terraform state.

## 6. Secret Manager, Monitoring, Logging

- Secret Manager: for a worker pool, a secret can be mounted as a volume (always the latest version when read) or exposed as an environment variable (resolved at instance start, so pin a version rather than `latest`). Source: [Configure secrets for worker pools](https://docs.cloud.google.com/run/docs/configuring/workerpools/secrets) (excerpt). **Consequence:** rotating a secret that is an environment variable needs a new revision. The runbook says so.
- Cloud Monitoring (uptime checks, alert policies, log-based metrics) and Cloud Logging: **not read this session.** The Terraform uses `google_monitoring_uptime_check_config`, `google_monitoring_alert_policy`, `google_logging_metric` and a log bucket, which exist in the provider; CI validation checks the schema, and a plan against a real project checks the rest.
- The backend exports Prometheus metrics on port 9101 from the worker (`WORKER_METRICS_PORT`). Cloud Monitoring does not scrape that on its own. **No registration-backlog metric exists in the code today** (`app/core/metrics.py` has content-job and scope-assignment gauges only). See Recommendations.

## 7. Region latency from Nigeria: a method you can run

Cost and latency both matter, and the API and database share a region.

**Step 1: no project needed (do this now).** Google publishes a latency test, [gcping](https://gcping.com) (also a command-line tool). It times round trips from where you are to each Google Cloud region. **NOT CONFIRMED** in this session: that it lists `africa-south1`, `europe-west1` and `europe-west4`, and its exact command-line flags (check `gcping -h`).

Run it from the networks students actually use:

- a phone on MTN, Airtel and Glo (open gcping.com in the phone's browser);
- the FUTA campus Wi-Fi;
- a home or office line.

Take at least 20 runs per network at three times of day (morning, afternoon, evening), and record the median and the 95th percentile, not the best run. Write results into `deploy/gcp/benchmark/results.md` (a template is provided).

**Step 2: with a project (needs your yes).** Deploy the same tiny HTTPS endpoint (`deploy/gcp/benchmark/measure.sh` takes the URLs) to each of the three regions and time connect, TLS and first byte from the same networks. This measures the real path, including the load balancer and TLS, which the ping test does not.

**Step 3: decide.** Weigh the 95th percentile on mobile networks first, then price (the three regions differ), then service availability (Cloud SQL, Cloud Run and the VM image all have to exist in the region). The default in the Terraform is "no region": you must choose.

## Recommendations

1. **Redis decision (yours):** accept option B for staging; pick A or B for production after the first journey.
2. **Add a registration backlog metric to the backend** (pending count and oldest age, like the existing `content_scope_assignments_pending` and `content_scope_assignment_oldest_age_seconds`). Without it, the registration-worker alert can only watch for failures and a dead worker, not a growing queue. Small, separate PR in `app/`.
3. **Add a worker liveness signal that Cloud Run can see:** the heartbeat check is local to the container. Either a tiny HTTP `/health` beside the metrics server, or a Managed Prometheus sidecar that scrapes port 9101.
4. **Make the adapter's checksum header configurable** before the first GCS upload test, or confirm GCS accepts it.
5. **Give the first staging run a written pass/fail checklist** (the runbook has one) so "one student completes the journey" is evidence, not a claim.
6. **Pick one region once**, and keep the Cloud SQL instance, Cloud Run services, the VMs and the document bucket in it. Cross-region traffic is both slower and billed.
7. **Do not turn on `LEARNING_MEMORY_ENABLED`.** The Terraform sets it `false` and the deploy workflow refuses an image whose gate is open.

## Sources

Cloud SQL: [db-versions](https://docs.cloud.google.com/sql/docs/postgres/db-versions), [release notes](https://docs.cloud.google.com/sql/docs/postgres/release-notes), [extensions](https://docs.cloud.google.com/sql/docs/postgres/extensions), [regions](https://docs.cloud.google.com/sql/docs/postgres/region-availability-overview).
Redis: [Memorystore for Redis versions](https://docs.cloud.google.com/memorystore/docs/redis/supported-versions), [Memorystore for Valkey versions](https://docs.cloud.google.com/memorystore/docs/valkey/supported-versions), [Redis Cloud on Marketplace](https://redis.io/docs/latest/operate/rc/cloud-integrations/gcp-marketplace/), [vendor comparison](https://redis.io/blog/redis-vs-memorystore/), [Memorystore locations](https://docs.cloud.google.com/memorystore/docs/redis/regions).
Cloud Run: [release notes](https://docs.cloud.google.com/run/docs/release-notes), [resource model](https://docs.cloud.google.com/run/docs/resource-model), [worker pool secrets](https://docs.cloud.google.com/run/docs/configuring/workerpools/secrets), [container contract](https://docs.cloud.google.com/run/docs/container-contract), [private networking](https://docs.cloud.google.com/run/docs/securing/private-networking), [locations](https://docs.cloud.google.com/run/docs/locations).
Storage and CDN: [interoperability](https://docs.cloud.google.com/storage/docs/interoperability), [HMAC keys](https://docs.cloud.google.com/storage/docs/authentication/managing-hmackeys), [backend bucket CDN](https://docs.cloud.google.com/cdn/docs/setting-up-cdn-with-bucket), [private bucket access](https://docs.cloud.google.com/cdn/docs/configure-private-bucket-access).
