# Cloud Run jobs: role setup and the two migrations. Run in this order on the
# first deploy and after any change to the schema (runbook):
#   1. db-init          creates the four least-privilege roles and the vector extension
#   2. backend-migrate  alembic upgrade head, as build_backend_owner
#   3. ai-migrate       alembic upgrade head, as build_ai_owner (after the backend's)
# The runtime roles never migrate; the owner roles never serve requests.

locals {
  db_host = google_sql_database_instance.main.private_ip_address
}

resource "google_cloud_run_v2_job" "db_init" {
  name                = "${local.name}-db-init"
  location            = var.region
  deletion_protection = true

  template {
    template {
      service_account = google_service_account.migrate.email
      max_retries     = 0
      timeout         = "300s"

      vpc_access {
        egress = "PRIVATE_RANGES_ONLY"
        network_interfaces {
          network    = google_compute_network.vpc.id
          subnetwork = google_compute_subnetwork.run.id
        }
      }

      containers {
        image = var.placeholder_image

        env {
          name  = "PGHOST"
          value = local.db_host
        }
        env {
          name  = "PGUSER"
          value = "postgres"
        }
        env {
          name  = "PGDATABASE"
          value = google_sql_database.build.name
        }
        env {
          name  = "PGSSLMODE"
          value = "require"
        }

        dynamic "env" {
          for_each = {
            PGPASSWORD                 = "db-superuser-password"
            BACKEND_OWNER_PASSWORD     = "db-backend-owner-password"
            BACKEND_APP_PASSWORD       = "db-backend-app-password"
            AI_OWNER_PASSWORD          = "db-ai-owner-password"
            AI_APP_PASSWORD            = "db-ai-app-password"
          }
          content {
            name = env.key
            value_source {
              secret_key_ref {
                secret  = local.secret_id[env.value]
                version = "latest"
              }
            }
          }
        }
      }
    }
  }

  lifecycle {
    ignore_changes = [template[0].template[0].containers[0].image, client, client_version]
  }

  depends_on = [google_secret_manager_secret_iam_member.reader]
}

resource "google_cloud_run_v2_job" "backend_migrate" {
  name                = "${local.name}-backend-migrate"
  location            = var.region
  deletion_protection = true

  template {
    template {
      service_account = google_service_account.migrate.email
      max_retries     = 0
      timeout         = "900s"

      vpc_access {
        egress = "PRIVATE_RANGES_ONLY"
        network_interfaces {
          network    = google_compute_network.vpc.id
          subnetwork = google_compute_subnetwork.run.id
        }
      }

      containers {
        image   = var.placeholder_image
        command = ["alembic"]
        args    = ["upgrade", "head"]

        env {
          name = "DATABASE_URL"
          value_source {
            secret_key_ref {
              secret  = local.secret_id["backend-owner-database-url"]
              version = "latest"
            }
          }
        }
      }
    }
  }

  lifecycle {
    ignore_changes = [template[0].template[0].containers[0].image, client, client_version]
  }

  depends_on = [google_secret_manager_secret_iam_member.reader]
}

# The ai-service's alembic/env.py imports the full service settings, so this job
# carries the same settings as the service, minus the storage identity.
resource "google_cloud_run_v2_job" "ai_migrate" {
  name                = "${local.name}-ai-migrate"
  location            = var.region
  deletion_protection = true

  template {
    template {
      service_account = google_service_account.migrate_ai.email
      max_retries     = 0
      timeout         = "900s"

      vpc_access {
        egress = "PRIVATE_RANGES_ONLY"
        network_interfaces {
          network    = google_compute_network.vpc.id
          subnetwork = google_compute_subnetwork.run.id
        }
      }

      containers {
        image   = var.placeholder_image
        command = ["alembic"]
        args    = ["upgrade", "head"]

        dynamic "env" {
          for_each = { for k, v in local.ai_env : k => v if !startswith(k, "OBJECT_STORAGE") }
          content {
            name  = env.key
            value = env.value
          }
        }

        dynamic "env" {
          for_each = {
            DATABASE_URL         = "ai-owner-database-url"
            BACKEND_TO_AI_SECRET = "backend-to-ai-secret"
            AI_TO_BACKEND_SECRET = "ai-to-backend-secret"
            REDIS_URL            = "ai-redis-url"
          }
          content {
            name = env.key
            value_source {
              secret_key_ref {
                secret  = local.secret_id[env.value]
                version = "latest"
              }
            }
          }
        }
      }
    }
  }

  lifecycle {
    ignore_changes = [template[0].template[0].containers[0].image, client, client_version]
  }

  depends_on = [google_secret_manager_secret_iam_member.reader]
}
