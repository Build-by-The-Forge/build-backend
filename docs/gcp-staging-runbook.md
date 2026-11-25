# GCP staging runbook

Covers `deploy/gcp/`. **Every command here changes cloud state and needs the owner's explicit yes before it is run.** Nothing has been run. Names assume `var.environment = staging`, so resources are prefixed `build-staging-`. Replace `$PROJECT`, `$REGION` and `$ZONE` with the values the owner chose.

Rules that apply to every step:

- A secret value is never typed on a command line, put in a file in the repository, or pasted into chat or CI. Generate it and pipe it straight into Secret Manager (`... | gcloud secrets versions add NAME --data-file=-`). Use hex or base64 without `+`, `/`, `=` when the value goes inside a URL (`openssl rand -hex 24`).
- Run the commands in Cloud Shell, not on a laptop that keeps shell history.
- Record what you did (date, who, what) in the release log.

## Decisions needed before anything starts

See "Decisions and actions for the owner" in `docs/gcp-staging-readiness.md`. The first deploy cannot begin without: a project and billing, the region, the Redis choice, the email-delivery decision, and the secret-handling method above.

## 1. First deploy

Order matters: Cloud Run will not create a revision that references a secret with no version, and the Redis VM will not start without its password.

**1.1 Project and tools.** In the new project, in Cloud Shell: `gcloud config set project $PROJECT`. Install nothing locally.

**1.2 Plan (changes nothing).** `cd deploy/gcp && cp terraform.tfvars.example terraform.tfvars` (fill in project, region, zone), then `terraform init` and `terraform plan -out=tfplan`. Read the plan: expect creates only, none for secret versions. Share the plan summary; do not continue without a yes.

**1.3 Foundation apply.** APIs, network, identities, secret containers, Artifact Registry and the database first:

```bash
terraform apply \
  -target=google_project_service.apis \
  -target=google_compute_network.vpc \
  -target=google_service_networking_connection.private_services \
  -target=google_secret_manager_secret.this \
  -target=google_service_account.backend \
  -target=google_sql_database.build \
  -target=google_artifact_registry_repository.images
```

**1.4 Fill the secrets.** List the names with `terraform output secret_names`. Then, per row:

| Secret (suffix after `build-staging-`) | How to create the value |
|---|---|
| `backend-auth-jwt-secret` | `openssl rand -base64 48 \| tr -d '\n'` (at least 32 bytes) |
| `backend-to-ai-secret`, `ai-to-backend-secret` | Two different values, each at least 32 bytes, never a known development value. The two directions must differ |
| `db-superuser-password` | A new value, then set it on Cloud SQL: `gcloud sql users set-password postgres --instance=build-staging-pg --prompt-for-password` (typed at the prompt, never an argument) |
| `db-backend-owner-password`, `db-backend-app-password`, `db-ai-owner-password`, `db-ai-app-password` | `openssl rand -hex 24`, one each |
| `redis-password` | `openssl rand -hex 24` |
| `backend-app-postgres-url` | Build from the app password: `postgresql+asyncpg://build_backend_app:<password>@<cloudsql_private_ip>:5432/build?ssl=require` |
| `backend-owner-database-url` | Same with `build_backend_owner` and its password |
| `ai-app-database-url`, `ai-owner-database-url` | Same with `build_ai_app` and `build_ai_owner` |
| `backend-redis-url` | `redis://:<redis password>@<redis_private_ip>:6379/0` |
| `ai-redis-url` | `redis://:<redis password>@<redis_private_ip>:6379/1` |
| `storage-*` | The four HMAC values from step 1.6 |

Build a URL without displaying it, for example:

```bash
PW=$(gcloud secrets versions access latest --secret=build-staging-db-backend-app-password)
printf 'postgresql+asyncpg://build_backend_app:%s@%s:5432/build?ssl=require' "$PW" "$DB_IP" \
  | gcloud secrets versions add build-staging-backend-app-postgres-url --data-file=-
unset PW
```

`?ssl=require` is the asyncpg form of "TLS required" (Cloud SQL is set to encrypted-only). **Not verified:** that the application's engine and `alembic/env.py` accept it. Step 1.9 proves it; if they do not, the fix is a code change in a separate PR.

**1.5 Full apply.** `terraform apply tfplan` (re-plan if anything changed). This creates the services, worker pools, jobs, VMs, buckets, alerts and uptime check, all running the placeholder image.

**1.6 Storage identities.** Create the two HMAC keys for the service accounts `build-staging-backend@` and `build-staging-ai@` (Console: Cloud Storage, Settings, Interoperability, or `gcloud storage hmac create <service-account-email>`). The secret is shown once: put access id and secret straight into the four `storage-*` secrets. If an organisation policy blocks HMAC keys, stop and report.

**1.7 Images.** Build and push `build-backend` (target `production`), `ai-service` (target `app`; needs the OCR model read token as a BuildKit secret) and `db-init` to the Artifact Registry URL from `terraform output artifact_registry`. Take each image's **registry digest** from the push output. Until the deploy workflow gets a push step (a follow-up PR after the owner approves federation), this is done by the owner or from Cloud Shell.

Gate checks on the pushed backend image (also in `.github/workflows/gcp-deploy.yml`): `GATE_OPEN` is `False` and `/opt/build-backend/production-image` exists.

**1.8 Roles, then migrations**, in this order, each waiting for success:

```bash
gcloud run jobs update build-staging-db-init --region $REGION --image <registry>/db-init@sha256:<digest>
gcloud run jobs execute build-staging-db-init --region $REGION --wait

gcloud run jobs update build-staging-backend-migrate --region $REGION --image <registry>/build-backend@sha256:<digest>
gcloud run jobs execute build-staging-backend-migrate --region $REGION --wait

gcloud run jobs update build-staging-ai-migrate --region $REGION --image <registry>/ai-service@sha256:<digest>
gcloud run jobs execute build-staging-ai-migrate --region $REGION --wait
```

`db-init` is the first thing that proves `CREATE EXTENSION vector` works as the `postgres` user on Cloud SQL. Record the pgvector version: `SELECT extversion FROM pg_extension WHERE extname='vector';` (Cloud SQL Studio or Auth Proxy from Cloud Shell). Compare it with the verification report.

**1.9 Services and workers by digest.**

```bash
gcloud run services update build-staging-ai      --region $REGION --image <registry>/ai-service@sha256:<digest>
gcloud run services update build-staging-backend --region $REGION --image <registry>/build-backend@sha256:<digest>
# Worker pools: check `gcloud run worker-pools --help` for the update syntax in your SDK version.
# Pools: build-staging-backend-worker, build-staging-backend-registration-worker, build-staging-ai-worker.
```

Terraform ignores the image, so these changes are not drift.

**1.10 Verify (the staging checklist; record the evidence of each).**

- [ ] `GET <backend_url>/health/ready` returns success; the uptime check is green.
- [ ] The backend's startup log shows `Learning memory: disabled by the production gate`; the metric `learning_memory_enabled` is 0; the "Learning Memory enabled" alert has not fired.
- [ ] The backend reaches ai-service over internal ingress (a signed call succeeds). If it fails with a 403 or timeout, the VPC egress / Private Google Access assumption in the verification report is wrong: stop and report.
- [ ] A student registers; the registration worker processes it (`SELECT count(*) FROM pending_registrations;` returns to 0).
- [ ] A document upload reaches Cloud Storage (this is where the `x-amz-checksum-sha256` and signing-region questions are settled), is scanned by ClamAV, and is dispatched to ingestion.
- [ ] An alert test: stop the ClamAV VM, confirm the alert, start it.
- [ ] Record: image digests, pgvector version, ClamAV VM memory headroom, date, who.

**Known blocker for the student journey:** in staging the backend uses `UnconfiguredEmailSender`, which drops every message (`app/bootstrap/container.py`). Verification and password-reset emails are never delivered, so a student cannot complete sign-up on staging until an email provider is chosen and wired. See the readiness report.

## 2. Rollback

Rule: code rolls back, the schema does not. Migrations are forward-only; a release that needs a schema change ships it expand-then-contract so the previous image still runs against the new schema.

**An API revision.** Find the previous revision and send all traffic back:

```bash
gcloud run revisions list --service build-staging-backend --region $REGION
gcloud run services update-traffic build-staging-backend --region $REGION --to-revisions <previous-revision>=100
```

Same for `build-staging-ai`.

**A worker pool.** Re-deploy the previous image digest (from the release log or the workflow summary): `gcloud run worker-pools update ... --image <previous digest>`. A pool has no traffic split.

**A bad migration.** Do not downgrade in place. Stop the workers (set instance count to 0), assess with the restore drill's clone, and either fix forward or restore (section 3). Decide with the owner: this loses data written since the restore point.

After any rollback: re-run the 1.10 checklist items that touch the rolled-back component, and write down why.

## 3. Restore drill

Purpose: prove the backups restore, and measure how long it takes (RTO) and how much is lost (RPO). Do it **before the first student uses staging**, then monthly. It creates a temporary Cloud SQL instance, so it needs the owner's yes and costs a little for its lifetime. **Never restore over the staging instance.**

Backups: automated daily at 02:00 UTC, 14 retained, point-in-time recovery on (7 days of logs): `gcloud sql backups list --instance build-staging-pg`.

1. Note the time; pick a point (a recent timestamp, UTC).
2. Clone to a new instance at that point:
   `gcloud sql instances clone build-staging-pg build-staging-pg-drill --point-in-time <timestamp> --network <vpc>`
   (check `gcloud sql instances clone --help` for the private-network flag in your SDK version).
3. When it is ready, record the elapsed time. That is the RTO for a database of this size.
4. Verify on the clone (Cloud SQL Studio or a client in Cloud Shell): `SELECT * FROM alembic_version;` matches staging; the four roles exist; `SELECT extversion FROM pg_extension WHERE extname='vector';`; row counts of a few tables match what they were at the chosen time; one retrieval query on `document_chunks` returns results.
5. Record RPO (the gap between the failure you simulated and the restore point) and any surprises.
6. Delete the clone: `gcloud sql instances delete build-staging-pg-drill` (confirm the name first).

Documents: the bucket is versioned; a deleted or overwritten object can be restored from a noncurrent version (kept 30 days). Test one: delete a test object, restore the prior version, confirm the SHA-256 matches.

Redis holds rate-limit counters, not records of truth: after a Redis loss, restart the VM; nothing is restored.

## 4. Secret rotation

Cadence: every 90 days, and immediately on any suspicion of exposure. Environment-variable secrets are read **when an instance starts**, so a rotated value reaches a service only with a new revision (`gcloud run services update <svc> --region $REGION --update-env-vars ROTATED=<date>` forces one; for pools, update the pool).

The application supports overlap for the signing secrets (`AUTH_JWT_PREVIOUS_SECRET` with `AUTH_JWT_PREVIOUS_KID`, `BACKEND_TO_AI_SECRET_PREVIOUS`, `AI_TO_BACKEND_SECRET_PREVIOUS`). Terraform does not wire the `*_PREVIOUS` variables, so they are added by hand for the overlap window and **will show as drift in the next plan; remove them with `--remove-secrets` once the overlap ends**.

| Secret | Procedure |
|---|---|
| JWT signing key | 1. Add the current value as a new secret `...-jwt-previous` and the old key id as `AUTH_JWT_PREVIOUS_KID`. 2. Add a new version of `backend-auth-jwt-secret` and set a new `AUTH_JWT_KID`. 3. New revision of the API and both worker pools. 4. After the access-token lifetime (15 minutes) and the refresh-token window you accept, remove the previous key |
| Service secrets (two directions) | Rotate one direction at a time. Put the old value in the `_PREVIOUS` variable on the verifying side, new value on both sides, new revisions on both services, then remove `_PREVIOUS`. Verify a signed call both ways |
| Database role passwords | Update the password secret, re-run `db-init` (it re-applies passwords), update the matching `...-url` secret, new revisions for everything using it. Owner roles first (migrations are not running), then app roles; expect a brief connection error window on the app roles |
| `postgres` password | `gcloud sql users set-password` with the prompt; new secret version |
| Redis password | New secret version for `redis-password` and both Redis URLs; restart the VM (`gcloud compute instances reset`); new revisions. Sign-in is refused for the minutes this takes |
| Storage HMAC keys | Create a second key for the service account, update the two secrets, new revision, confirm uploads and reads, then deactivate and delete the old key |
| Deploy federation | No secret: no key exists. To revoke, remove the repository from `github_repositories` and apply |

After rotating: confirm the old value no longer works where it should not, and log the rotation (date, who, which secret, never the value).

## 5. Registration-worker backlog

The worker pool `build-staging-backend-registration-worker` runs `python -m app.worker --registrations`. A student's registration is accepted into `pending_registrations`; the worker creates the account and issues the verification message. If it stops, new students are accepted but never get an account.

**What the alert covers today.** `build-staging-registration-pass-failed` counts logged `worker_loop_pass_failed` errors for the registrations loop, and the policy "registration worker failing" fires at three or more in five minutes. **It does not see a growing queue, a stopped worker, or per-row failures** (the service records those on the row and carries on; `app/application/identity/user_service.py`). A queue-length or oldest-age metric needs a code change (see the verification report, Recommendations).

**When it fires, or a student reports no account:**

1. Look at the pool: `gcloud run worker-pools describe build-staging-backend-registration-worker --region $REGION` (instance count should be 1, ready). Look at its logs in Cloud Logging: filter `worker_loop_pass_failed`.
2. Check the queue (Cloud SQL Studio, as a read-only user): `SELECT count(*), min(created_at), max(attempts) FROM pending_registrations;`. A growing count, an old `min(created_at)` or rising `attempts` confirms a backlog.
3. Likely causes and fixes: database unreachable or a rotated password not yet in a new revision (check the URL secret and revision); Redis down (VM alert); the pool at 0 instances (set it back to 1); a poison row (a row with a high `attempts` that keeps failing: read its error in the logs, then decide with the owner; do not delete a row without recording why).
4. Restart: deploy a new revision of the pool (same image) to restart the loop.
5. After recovery, confirm the count falls to zero and a test registration completes. Write down the cause and the time to recover.

Verification emails: even with a healthy worker, nothing reaches students on staging until an email provider exists (section 1, known blocker).

## 6. Redis and ClamAV VMs

Both are ordinary VMs the owner patches. Container-Optimized OS auto-updates the OS; the container images are pinned in `variables.tf`: bump deliberately (Redis by digest, ClamAV as in `deploy/compose.m3.yml`), apply, and check `docker ps` through the serial console or OS Login. ClamAV signatures update inside the container (`freshclam`); if the VM cannot reach the internet (NAT broken), scans keep working on stale signatures: check the NAT first when uploads sit in the scan stage.
