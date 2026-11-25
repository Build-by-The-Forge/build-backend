# Secret Manager: names only. No secret value, and no secret version, is created
# by Terraform or appears in this repository or in state. The owner adds each
# value by hand (runbook, first deploy); values that are DSNs or URLs are built
# from outputs of this configuration plus the passwords.
#
# Cloud Run resolves an environment-variable secret when an instance starts, so a
# rotated value reaches a service only with a new revision (runbook, rotation).

locals {
  secret_readers = {
    # Application signing and service-boundary secrets (two directions, never equal).
    "backend-auth-jwt-secret" = [google_service_account.backend.email]
    "backend-to-ai-secret"    = [google_service_account.backend.email, google_service_account.ai.email, google_service_account.migrate_ai.email]
    "ai-to-backend-secret"    = [google_service_account.backend.email, google_service_account.ai.email, google_service_account.migrate_ai.email]

    # Runtime database URLs (the least-privilege app roles).
    "backend-app-postgres-url" = [google_service_account.backend.email]
    "ai-app-database-url"      = [google_service_account.ai.email]

    # Migration database URLs (the owner roles): the migrate jobs only. The ai-service
    # migration imports the full service settings (its alembic/env.py), so its job
    # also reads the two boundary secrets and the Redis URL, under its own identity.
    "backend-owner-database-url" = [google_service_account.migrate.email]
    "ai-owner-database-url"      = [google_service_account.migrate_ai.email]

    # db-init inputs: the postgres user and the four role passwords.
    "db-superuser-password"     = [google_service_account.migrate.email]
    "db-backend-owner-password" = [google_service_account.migrate.email]
    "db-backend-app-password"   = [google_service_account.migrate.email]
    "db-ai-owner-password"      = [google_service_account.migrate.email]
    "db-ai-app-password"        = [google_service_account.migrate.email]

    # Redis: the password for the VM, the two URLs (backend db 0, ai-service db 1).
    "redis-password"    = [google_service_account.redis_vm.email]
    "backend-redis-url" = [google_service_account.backend.email]
    "ai-redis-url"      = [google_service_account.ai.email, google_service_account.migrate_ai.email]

    # Cloud Storage HMAC identities (XML API): backend read/write/list, ai read only.
    "storage-backend-access-key-id"     = [google_service_account.backend.email]
    "storage-backend-secret-access-key" = [google_service_account.backend.email]
    "storage-ai-access-key-id"          = [google_service_account.ai.email]
    "storage-ai-secret-access-key"      = [google_service_account.ai.email]
  }

  secret_bindings = merge([
    for name, readers in local.secret_readers : {
      for email in readers : "${name}/${email}" => { name = name, email = email }
    }
  ]...)
}

resource "google_secret_manager_secret" "this" {
  for_each  = local.secret_readers
  secret_id = "${local.name}-${each.key}"

  replication {
    auto {}
  }

  depends_on = [google_project_service.apis]
}

resource "google_secret_manager_secret_iam_member" "reader" {
  for_each  = local.secret_bindings
  secret_id = google_secret_manager_secret.this[each.value.name].id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${each.value.email}"
}
