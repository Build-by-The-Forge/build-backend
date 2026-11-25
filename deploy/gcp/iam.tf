# Runtime identities, one per concern. None has a key: Cloud Run and the VMs use
# their attached identity. Roles are the smallest that work; secret and bucket
# access is granted per resource (secrets.tf, storage.tf).

resource "google_service_account" "backend" {
  account_id   = "${local.name}-backend"
  display_name = "build-backend API and workers (${var.environment})"
}

resource "google_service_account" "ai" {
  account_id   = "${local.name}-ai"
  display_name = "ai-service API and worker (${var.environment})"
}

resource "google_service_account" "migrate" {
  account_id   = "${local.name}-migrate"
  display_name = "migrations and db-init jobs (${var.environment})"
}

resource "google_service_account" "migrate_ai" {
  account_id   = "${local.name}-migrate-ai"
  display_name = "ai-service migration job (${var.environment})"
}

resource "google_service_account" "deployer" {
  account_id   = "${local.name}-deployer"
  display_name = "deploy workflow (${var.environment})"
}

locals {
  runtime_accounts = {
    backend    = google_service_account.backend.email
    ai         = google_service_account.ai.email
    migrate    = google_service_account.migrate.email
    migrate_ai = google_service_account.migrate_ai.email
    redis      = google_service_account.redis_vm.email
    clamav     = google_service_account.clamav_vm.email
  }
}

# Logs and metrics from every runtime identity.
resource "google_project_iam_member" "log_writer" {
  for_each = local.runtime_accounts
  project  = var.project_id
  role     = "roles/logging.logWriter"
  member   = "serviceAccount:${each.value}"
}

resource "google_project_iam_member" "metric_writer" {
  for_each = local.runtime_accounts
  project  = var.project_id
  role     = "roles/monitoring.metricWriter"
  member   = "serviceAccount:${each.value}"
}

# The deployer can deploy and run jobs, push images, and act as the runtime
# identities (to attach them to a revision). It cannot read a secret, change
# IAM or touch the database.
resource "google_project_iam_member" "deployer_run" {
  project = var.project_id
  role    = "roles/run.developer"
  member  = "serviceAccount:${google_service_account.deployer.email}"
}

resource "google_artifact_registry_repository_iam_member" "deployer_push" {
  repository = google_artifact_registry_repository.images.name
  location   = var.region
  role       = "roles/artifactregistry.writer"
  member     = "serviceAccount:${google_service_account.deployer.email}"
}

resource "google_service_account_iam_member" "deployer_acts_as" {
  for_each = {
    backend    = google_service_account.backend.name
    ai         = google_service_account.ai.name
    migrate    = google_service_account.migrate.name
    migrate_ai = google_service_account.migrate_ai.name
  }
  service_account_id = each.value
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.deployer.email}"
}

# Workload Identity Federation for GitHub Actions: no key is ever created. Only
# the listed repositories can impersonate the deployer. Skipped while the list is empty.
resource "google_iam_workload_identity_pool" "github" {
  count                     = length(var.github_repositories) == 0 ? 0 : 1
  workload_identity_pool_id = "${local.name}-github"
  depends_on                = [google_project_service.apis]
}

resource "google_iam_workload_identity_pool_provider" "github" {
  count                              = length(var.github_repositories) == 0 ? 0 : 1
  workload_identity_pool_id          = google_iam_workload_identity_pool.github[0].workload_identity_pool_id
  workload_identity_pool_provider_id = "github"

  attribute_mapping = {
    "google.subject"       = "assertion.sub"
    "attribute.repository" = "assertion.repository"
  }
  attribute_condition = "assertion.repository in [${join(", ", [for r in var.github_repositories : "'${r}'"])}]"

  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }
}

resource "google_service_account_iam_member" "github_impersonates_deployer" {
  for_each           = toset(var.github_repositories)
  service_account_id = google_service_account.deployer.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github[0].name}/attribute.repository/${each.value}"
}
