# Cloud SQL for PostgreSQL 17, private IP only. One database ("build") holds
# both services' schemas, as in deploy/compose.m3.yml.
#
# Roles are NOT created here: a google_sql_user would put its password in
# Terraform state. The db-init Cloud Run job (db-init.tf, deploy/gcp/db-init/)
# creates the four least-privilege roles from deploy/db-init/init-roles.sql with
# passwords read from Secret Manager:
#   build_backend_owner  migrations      build_backend_app  backend runtime
#   build_ai_owner       ai migrations   build_ai_app       ai-service runtime
# The built-in `postgres` user only runs db-init. Its password is set once by
# hand (runbook, first deploy) and kept in Secret Manager.

resource "google_sql_database_instance" "main" {
  name                = "${local.name}-pg"
  region              = var.region
  database_version    = "POSTGRES_17"
  deletion_protection = true

  settings {
    tier              = var.db_tier
    edition           = "ENTERPRISE"
    availability_type = var.db_availability_type
    disk_type         = "PD_SSD"
    disk_autoresize   = true

    ip_configuration {
      ipv4_enabled    = false
      private_network = google_compute_network.vpc.id
      ssl_mode        = "ENCRYPTED_ONLY"
    }

    backup_configuration {
      enabled                        = true
      start_time                     = "02:00"
      point_in_time_recovery_enabled = true
      transaction_log_retention_days = 7
      backup_retention_settings {
        retained_backups = 14
        retention_unit   = "COUNT"
      }
    }

    maintenance_window {
      day          = 7 # Sunday
      hour         = 3
      update_track = "stable"
    }

    insights_config {
      query_insights_enabled = true
    }

    database_flags {
      name  = "log_min_duration_statement"
      value = "1000"
    }
  }

  depends_on = [google_service_networking_connection.private_services]
}

resource "google_sql_database" "build" {
  name     = "build"
  instance = google_sql_database_instance.main.name
}
