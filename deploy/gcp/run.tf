# Cloud Run: the two APIs as services, the always-on loops as worker pools, and
# migrations as jobs (jobs.tf). Every revision runs as its own service account,
# reaches the VPC through Direct VPC egress, and reads secrets by reference.
#
# Images: the placeholder until the deploy workflow moves each resource to a
# built image by digest. Terraform ignores image changes afterwards, so a deploy
# is not a Terraform change.
#
# Learning Memory stays off: LEARNING_MEMORY_ENABLED=false everywhere, and the
# production image refuses it anyway (GATE_OPEN is False; the workflow checks).

locals {
  # Cloud Run's deterministic URL form, so the two services can name each other
  # without a dependency cycle.
  backend_url = "https://${local.name}-backend-${data.google_project.this.number}.${var.region}.run.app"
  ai_url      = "https://${local.name}-ai-${data.google_project.this.number}.${var.region}.run.app"

  secret_id = { for name, s in google_secret_manager_secret.this : name => s.secret_id }

  # Settings the backend API and both of its worker pools share.
  backend_env = {
    APP_ENVIRONMENT              = var.environment
    AI_SERVICE_URL               = local.ai_url
    AUTH_RATE_LIMIT_FAILURE_MODE = "closed"
    LEARNING_MEMORY_ENABLED      = "false"
    OBJECT_STORAGE_ENDPOINT_URL  = "https://storage.googleapis.com"
    OBJECT_STORAGE_BUCKET        = google_storage_bucket.documents.name
    OBJECT_STORAGE_REGION        = var.object_storage_region
    CLAMAV_HOST                  = google_compute_address.clamav.address
    TRUSTED_PROXIES              = var.trusted_proxies
  }

  # Environment variable -> secret name (see secrets.tf).
  backend_secrets = {
    AUTH_JWT_SECRET                  = "backend-auth-jwt-secret"
    BACKEND_TO_AI_SECRET             = "backend-to-ai-secret"
    AI_TO_BACKEND_SECRET             = "ai-to-backend-secret"
    POSTGRES_URL                     = "backend-app-postgres-url"
    REDIS_URL                        = "backend-redis-url"
    OBJECT_STORAGE_ACCESS_KEY_ID     = "storage-backend-access-key-id"
    OBJECT_STORAGE_SECRET_ACCESS_KEY = "storage-backend-secret-access-key"
  }

  ai_env = {
    APP_ENVIRONMENT             = var.environment
    BACKEND_CALLBACK_URL        = "${local.backend_url}/content/ingestion/callbacks"
    MODEL_PROVIDER              = var.model_provider
    LEARNING_MEMORY_ENABLED     = "false"
    LOG_LEVEL                   = "INFO"
    OBJECT_STORAGE_ENDPOINT_URL = "https://storage.googleapis.com"
    OBJECT_STORAGE_BUCKET       = google_storage_bucket.documents.name
    OBJECT_STORAGE_REGION       = var.object_storage_region
  }

  ai_secrets = {
    BACKEND_TO_AI_SECRET             = "backend-to-ai-secret"
    AI_TO_BACKEND_SECRET             = "ai-to-backend-secret"
    DATABASE_URL                     = "ai-app-database-url"
    REDIS_URL                        = "ai-redis-url"
    OBJECT_STORAGE_ACCESS_KEY_ID     = "storage-ai-access-key-id"
    OBJECT_STORAGE_SECRET_ACCESS_KEY = "storage-ai-secret-access-key"
  }
}

resource "google_artifact_registry_repository" "images" {
  repository_id = local.name
  location      = var.region
  format        = "DOCKER"
  description   = "BUILD images (${var.environment}); deployed by digest"
  depends_on    = [google_project_service.apis]
}

# ---- Services -------------------------------------------------------------------

resource "google_cloud_run_v2_service" "backend" {
  name                = "${local.name}-backend"
  location            = var.region
  ingress             = "INGRESS_TRAFFIC_ALL"
  deletion_protection = true

  template {
    service_account = google_service_account.backend.email
    timeout         = "60s"

    scaling {
      min_instance_count = var.backend_min_instances
      max_instance_count = 5
    }

    vpc_access {
      egress = "ALL_TRAFFIC" # ai-service's internal ingress needs the call to come from the VPC
      network_interfaces {
        network    = google_compute_network.vpc.id
        subnetwork = google_compute_subnetwork.run.id
      }
    }

    containers {
      image = var.placeholder_image

      ports {
        container_port = 8000
      }

      resources {
        limits = {
          cpu    = "1"
          memory = "1Gi"
        }
      }

      dynamic "env" {
        for_each = local.backend_env
        content {
          name  = env.key
          value = env.value
        }
      }

      dynamic "env" {
        for_each = local.backend_secrets
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

      startup_probe {
        http_get {
          path = "/health/startup"
        }
        period_seconds    = 5
        failure_threshold = 24
      }

      liveness_probe {
        http_get {
          path = "/health/live"
        }
        period_seconds = 30
      }
    }
  }

  lifecycle {
    ignore_changes = [template[0].containers[0].image, client, client_version]
  }

  depends_on = [google_secret_manager_secret_iam_member.reader]
}

# The mobile app calls the backend directly. Authentication is the application's
# (JWT); Cloud Run's own IAM check would block the app.
resource "google_cloud_run_v2_service_iam_member" "backend_public" {
  name     = google_cloud_run_v2_service.backend.name
  location = var.region
  role     = "roles/run.invoker"
  member   = "allUsers"
}

resource "google_cloud_run_v2_service" "ai" {
  name                = "${local.name}-ai"
  location            = var.region
  ingress             = "INGRESS_TRAFFIC_INTERNAL_ONLY" # called only by the backend, over the VPC
  deletion_protection = true

  template {
    service_account = google_service_account.ai.email
    timeout         = "120s"

    scaling {
      min_instance_count = 0
      max_instance_count = 3
    }

    vpc_access {
      egress = "ALL_TRAFFIC"
      network_interfaces {
        network    = google_compute_network.vpc.id
        subnetwork = google_compute_subnetwork.run.id
      }
    }

    containers {
      image   = var.placeholder_image
      command = ["uvicorn"]
      args    = ["app.main:app", "--host", "0.0.0.0", "--port", "8000"]

      ports {
        container_port = 8000
      }

      resources {
        limits = {
          cpu    = "2"
          memory = "2Gi"
        }
      }

      dynamic "env" {
        for_each = local.ai_env
        content {
          name  = env.key
          value = env.value
        }
      }

      dynamic "env" {
        for_each = local.ai_secrets
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

      startup_probe {
        http_get {
          path = "/api/v1/system/health"
        }
        period_seconds    = 5
        failure_threshold = 24
      }
    }
  }

  lifecycle {
    ignore_changes = [template[0].containers[0].image, client, client_version]
  }

  depends_on = [google_secret_manager_secret_iam_member.reader]
}

# Internal ingress already limits who can reach it. Requests are authenticated by
# the Service Signature v1 header, not by a Google identity token, so the IAM
# check is opened to the network that internal ingress allows.
resource "google_cloud_run_v2_service_iam_member" "ai_internal" {
  name     = google_cloud_run_v2_service.ai.name
  location = var.region
  role     = "roles/run.invoker"
  member   = "allUsers"
}

# ---- Worker pools (always-on loops) ------------------------------------------------

resource "google_cloud_run_v2_worker_pool" "backend_worker" {
  name                = "${local.name}-backend-worker"
  location            = var.region
  deletion_protection = true

  scaling {
    manual_instance_count = 1
  }

  template {
    service_account = google_service_account.backend.email

    vpc_access {
      egress = "ALL_TRAFFIC"
      network_interfaces {
        network    = google_compute_network.vpc.id
        subnetwork = google_compute_subnetwork.run.id
      }
    }

    containers {
      image   = var.placeholder_image
      command = ["python", "-m", "app.worker"]

      resources {
        limits = {
          cpu    = "1"
          memory = "1Gi"
        }
      }

      dynamic "env" {
        for_each = local.backend_env
        content {
          name  = env.key
          value = env.value
        }
      }

      dynamic "env" {
        for_each = local.backend_secrets
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

  lifecycle {
    ignore_changes = [template[0].containers[0].image, client, client_version]
  }

  depends_on = [google_secret_manager_secret_iam_member.reader]
}

# Its own pool, as in the compose topology: registration's account-dependent work
# stays out of the web process, and starts and stops independently of the others.
resource "google_cloud_run_v2_worker_pool" "backend_registration_worker" {
  name                = "${local.name}-backend-registration-worker"
  location            = var.region
  deletion_protection = true

  scaling {
    manual_instance_count = 1
  }

  template {
    service_account = google_service_account.backend.email

    vpc_access {
      egress = "ALL_TRAFFIC"
      network_interfaces {
        network    = google_compute_network.vpc.id
        subnetwork = google_compute_subnetwork.run.id
      }
    }

    containers {
      image   = var.placeholder_image
      command = ["python", "-m", "app.worker", "--registrations"]

      resources {
        limits = {
          cpu    = "1"
          memory = "512Mi"
        }
      }

      dynamic "env" {
        for_each = local.backend_env
        content {
          name  = env.key
          value = env.value
        }
      }

      dynamic "env" {
        for_each = local.backend_secrets
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

  lifecycle {
    ignore_changes = [template[0].containers[0].image, client, client_version]
  }

  depends_on = [google_secret_manager_secret_iam_member.reader]
}

resource "google_cloud_run_v2_worker_pool" "ai_worker" {
  name                = "${local.name}-ai-worker"
  location            = var.region
  deletion_protection = true

  scaling {
    manual_instance_count = 1
  }

  template {
    service_account = google_service_account.ai.email

    vpc_access {
      egress = "ALL_TRAFFIC"
      network_interfaces {
        network    = google_compute_network.vpc.id
        subnetwork = google_compute_subnetwork.run.id
      }
    }

    containers {
      image   = var.placeholder_image
      command = ["python", "-m", "app.worker"]

      resources {
        limits = {
          cpu    = "2"
          memory = "4Gi"
        }
      }

      dynamic "env" {
        for_each = local.ai_env
        content {
          name  = env.key
          value = env.value
        }
      }

      dynamic "env" {
        for_each = local.ai_secrets
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

  lifecycle {
    ignore_changes = [template[0].containers[0].image, client, client_version]
  }

  depends_on = [google_secret_manager_secret_iam_member.reader]
}
