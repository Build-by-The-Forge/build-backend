# GCP staging: readiness report

Status 2026-11-26. **Nothing has been created, enabled, applied or paid for.** The configuration under `deploy/gcp/` passes `terraform fmt`, `init -backend=false` and `validate` in CI (job "GCP Terraform validate"); no `plan` was run, because a plan needs a real project and credentials. Companion documents: [verification report](gcp-staging-verification.md), [runbook](gcp-staging-runbook.md).

## What exists

| Concern | File | Notes |
|---|---|---|
| Provider, variables | `versions.tf`, `variables.tf` | No default project or region |
| Networking | `network.tf` | VPC, one subnet, private services access, Cloud NAT, firewall for Redis and ClamAV from the Cloud Run subnet only |
| Database | `database.tf` | Cloud SQL PostgreSQL 17, private IP only, TLS required, daily backups, 14 kept, point-in-time recovery, deletion protection |
| Redis 8 | `redis.tf` | VM, no public address, password read from Secret Manager at boot, append-only persistence on its own disk |
| ClamAV | `clamav.tf` | VM running the pinned image, port 3310 open to the Cloud Run subnet only |
| Buckets, CDN | `storage.tf`, `cdn.tf` | Private versioned document bucket; public APK bucket behind Cloud CDN (skipped until a domain is set) |
| Identities | `iam.tf` | Seven service accounts, no keys; keyless GitHub federation (skipped until repositories are listed) |
| Secrets | `secrets.tf` | 19 secret containers, names only; per-secret reader lists |
| Services, pools | `run.tf` | Backend (public), ai-service (internal ingress), backend worker, registration worker, ai worker |
| Jobs | `jobs.tf`, `db-init/` | db-init (roles from `deploy/db-init/init-roles.sql`), backend migrate, ai migrate |
| Monitoring | `monitoring.tf` | Uptime check, 5xx, database disk, VM absent, registration failures, **Learning Memory enabled** |
| Workflows | `.github/workflows/gcp-*.yml` | Validate (static). Dry build with gate checks, `workflow_dispatch` only, no credentials, no push |

Learning Memory: `LEARNING_MEMORY_ENABLED` is `"false"` in every service, pool and job (CI refuses a change), the production image carries the marker and `GATE_OPEN` is `False` (checked by the dry build), staging refuses the setting at startup (checked by the dry build), and an alert fires if the "enabled" log line ever appears.

## Required secrets (names only; values are entered by the owner, never by Terraform)

All prefixed `build-staging-`.

Application: `backend-auth-jwt-secret`, `backend-to-ai-secret`, `ai-to-backend-secret`.
Database: `db-superuser-password`, `db-backend-owner-password`, `db-backend-app-password`, `db-ai-owner-password`, `db-ai-app-password`, `backend-app-postgres-url`, `backend-owner-database-url`, `ai-app-database-url`, `ai-owner-database-url`.
Redis: `redis-password`, `backend-redis-url`, `ai-redis-url`.
Storage: `storage-backend-access-key-id`, `storage-backend-secret-access-key`, `storage-ai-access-key-id`, `storage-ai-secret-access-key`.

Outside Secret Manager (GitHub, when the push step is added): the ai-service read token for the cross-repository checkout and the OCR model token the ai-service image build needs (`OCR_MODELS_TOKEN`). **Not needed and not wired:** any model-provider key (G-33 is not recorded; `MODEL_PROVIDER` stays `deterministic`) and any email-provider key (none is chosen).

## Permissions

- The person applying Terraform needs, in the project: Owner, or the combination of Project IAM Admin, Service Usage Admin, Compute Admin, Cloud SQL Admin, Cloud Run Admin, Secret Manager Admin, Storage Admin, Artifact Registry Admin, Service Account Admin, Workload Identity Pool Admin, Monitoring Editor and Logs Configuration Writer. Owner is simplest for the first apply.
- Runtime identities are least-privilege (see `iam.tf`, `secrets.tf`, `storage.tf`). The deploy identity can deploy and run jobs and push images; it cannot read secrets or change IAM.

## Costs (what bills; prices NOT CHECKED this session)

I did not read current prices, and the three candidate regions differ. Billable items: Cloud SQL instance and storage and backups; backend service with one always-on instance (`backend_min_instances`); three worker pools with one always-on instance each; ai-service while it runs; two VMs and a 10 GB disk; Cloud NAT (hourly plus per-GB, and all Cloud Run traffic is routed through it); Artifact Registry storage; Cloud Storage; log and metric volume beyond the free tier; the load balancer and CDN once `apk_domain` is set. The cheapest honest lever is `backend_min_instances = 0` and pausing pools when staging is idle. Fill the estimate table in `deploy/gcp/benchmark/results.md` from the Pricing Calculator for the chosen region.

## Dependencies and ordering

1. Owner decisions below. 2. Project and billing. 3. Foundation apply, secrets, full apply (runbook 1.2 to 1.5). 4. Storage HMAC keys. 5. Images pushed (needs the push step and tokens). 6. db-init, then the two migrations. 7. Services and pools by digest. 8. The staging checklist (runbook 1.10).

## Decisions and actions for the owner

**Decisions**

1. **Project and billing:** project ID, billing account, who is Owner.
2. **Region:** run the latency benchmark (verification report, section 7), then choose. Cloud SQL, Cloud Run, both VMs and the document bucket all go in it.
3. **Redis 8:** accept the VM for staging, or choose Redis Cloud through the Marketplace. Nothing in Memorystore meets Redis 8. Decide separately for production.
4. **Email delivery (blocks the student journey):** staging uses `UnconfiguredEmailSender`, which drops every message, so sign-up verification and password reset cannot complete. Choose a provider and have the adapter written, or decide to run staging with a documented test-only path. This is outside this PR.
5. **Terraform state location:** a versioned bucket created by hand, then uncomment the backend block.
6. **APK domain** (optional now): enables the CDN.
7. **Federation:** approve keyless GitHub deploys (`github_repositories`), which unlocks the push-and-deploy workflow in a follow-up.
8. **Alert recipient** (`alert_email`).

**Actions only you can take**

- Create the project, link billing, and give the applying person the permissions above.
- Run the plan and read it; say yes to each apply, in writing.
- Enter every secret value (runbook 1.4) and create the storage HMAC keys (1.6).
- Run the benchmark from phones on MTN, Airtel and Glo and from campus Wi-Fi.
- Run the restore drill before any student uses staging.

## Self-review: things found before review

- **Email is the real blocker** for "one student completes the journey on staging" (decision 4).
- **Client IPs behind Cloud Run:** `TRUSTED_PROXIES` is empty. If the throttle sees Cloud Run's front-end address instead of the student's, all students share one rate-limit bucket. Check on staging with two devices before anything else depends on it.
- **The registration alert is weak** by construction (it sees only logged pass failures), and the worker pools expose no health the platform can use. Both need small backend changes (recommendations).
- **Unverified assumptions, each with its test:** `?ssl=require` accepted by the engine and alembic; Cloud Storage accepts `x-amz-checksum-sha256` and the signing region; `CREATE EXTENSION vector` as `postgres`; backend to ai-service over internal ingress; pgvector version on PostgreSQL 17; worker pools' probe options.
- **Image builds are not automated yet:** the ai-service image needs two tokens and a cross-repository checkout, so the dry workflow builds only the backend and db-init images.
- **`deletion_protection = true`** on Cloud Run resources, Cloud SQL and the VMs means `terraform destroy` needs a deliberate change first. That is intended; remember it when tearing staging down.
- **Cloud Run request body limit:** uploads are capped at 25 MB (`MAX_UPLOAD_BYTES`), under Cloud Run's request size limit as I understand it. **NOT CONFIRMED**, since I did not read the limits page.
- **Not from this PR (it touches no requirements file):** the "Dependency audit" job fails on a `virtualenv` advisory in the development requirements (`PYSEC-2026-4402`, fixed in 21.14.13). It needs its own change or an accepted-advisory entry under the project's advisory policy.

## Recommendations

1. Add the email provider adapter before the first staging run; it is the longest pole.
2. Add `pending_registrations` count and oldest-age gauges, and a worker heartbeat the platform can read (a tiny HTTP health beside the metrics server). Then replace the log-based registration alert with a real backlog alert.
3. Make the storage checksum header optional by configuration before the first Cloud Storage test.
4. Pin the Redis image by digest before the first apply, and give both VMs a patching routine.
5. Run the restore drill and the benchmark in the first week, and put the results in `deploy/gcp/benchmark/results.md` and the release log.
6. After staging works, add the push-and-deploy job (federation, digests, migrate, deploy, smoke check) as its own PR with its own review.
7. Fix the `virtualenv` advisory on `main` so CI is green for everyone.
