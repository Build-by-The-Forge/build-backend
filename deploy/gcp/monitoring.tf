# Logging, uptime check and alerts. Alerts go to var.alert_email when set; without
# it the policies still exist and show incidents in the console.
#
# Not here, and why (docs/gcp-staging-verification.md, Recommendations 2 and 3):
# the backend exports no registration-backlog metric and no worker heartbeat that
# Cloud Monitoring can read, so the registration-worker alert watches the signals
# that do exist: the worker's own failure log and the Learning Memory log line.
# A real backlog alert needs a small code change in a separate PR.

resource "google_logging_project_bucket_config" "default" {
  project        = var.project_id
  location       = "global"
  bucket_id      = "_Default"
  retention_days = 30
}

resource "google_monitoring_notification_channel" "email" {
  count        = var.alert_email == "" ? 0 : 1
  display_name = "BUILD ${var.environment} alerts"
  type         = "email"
  labels = {
    email_address = var.alert_email
  }
  depends_on = [google_project_service.apis]
}

locals {
  channels     = [for c in google_monitoring_notification_channel.email : c.id]
  backend_host = trimprefix(local.backend_url, "https://")
}

# ---- Uptime ------------------------------------------------------------------------

resource "google_monitoring_uptime_check_config" "backend" {
  display_name = "${local.name} backend ready"
  timeout      = "10s"
  period       = "60s"

  http_check {
    path           = "/health/ready"
    port           = 443
    use_ssl        = true
    validate_ssl   = true
    request_method = "GET"
  }

  monitored_resource {
    type = "uptime_url"
    labels = {
      project_id = var.project_id
      host       = local.backend_host
    }
  }

  depends_on = [google_project_service.apis]
}

resource "google_monitoring_alert_policy" "backend_down" {
  display_name          = "${local.name}: backend not ready"
  combiner              = "OR"
  notification_channels = local.channels

  conditions {
    display_name = "readiness check failing"
    condition_threshold {
      filter          = "metric.type=\"monitoring.googleapis.com/uptime_check/check_passed\" AND metric.label.check_id=\"${google_monitoring_uptime_check_config.backend.uptime_check_id}\" AND resource.type=\"uptime_url\""
      comparison      = "COMPARISON_GT"
      threshold_value = 1
      duration        = "120s"
      aggregations {
        alignment_period     = "300s"
        per_series_aligner   = "ALIGN_NEXT_OLDER"
        cross_series_reducer = "REDUCE_COUNT_FALSE"
        group_by_fields      = ["resource.label.*"]
      }
    }
  }
}

# ---- Errors and capacity --------------------------------------------------------------

resource "google_monitoring_alert_policy" "backend_5xx" {
  display_name          = "${local.name}: backend 5xx responses"
  combiner              = "OR"
  notification_channels = local.channels

  conditions {
    display_name = "more than 5 server errors in 5 minutes"
    condition_threshold {
      filter          = "metric.type=\"run.googleapis.com/request_count\" AND resource.type=\"cloud_run_revision\" AND resource.label.service_name=\"${google_cloud_run_v2_service.backend.name}\" AND metric.label.response_code_class=\"5xx\""
      comparison      = "COMPARISON_GT"
      threshold_value = 5
      duration        = "0s"
      aggregations {
        alignment_period   = "300s"
        per_series_aligner = "ALIGN_SUM"
      }
    }
  }
}

resource "google_monitoring_alert_policy" "database_disk" {
  display_name          = "${local.name}: database disk above 85%"
  combiner              = "OR"
  notification_channels = local.channels

  conditions {
    display_name = "disk utilization"
    condition_threshold {
      filter          = "metric.type=\"cloudsql.googleapis.com/database/disk/utilization\" AND resource.type=\"cloudsql_database\" AND resource.label.database_id=\"${var.project_id}:${google_sql_database_instance.main.name}\""
      comparison      = "COMPARISON_GT"
      threshold_value = 0.85
      duration        = "300s"
      aggregations {
        alignment_period   = "300s"
        per_series_aligner = "ALIGN_MEAN"
      }
    }
  }
}

# Redis and ClamAV run on VMs, so Google does not watch them for us. A scan can't
# finish while ClamAV is down; a sign-in is refused while Redis is down
# (AUTH_RATE_LIMIT_FAILURE_MODE=closed).
resource "google_monitoring_alert_policy" "vm_down" {
  for_each              = { redis = google_compute_instance.redis.instance_id, clamav = google_compute_instance.clamav.instance_id }
  display_name          = "${local.name}: ${each.key} VM not reporting"
  combiner              = "OR"
  notification_channels = local.channels

  conditions {
    display_name = "no uptime data for 5 minutes"
    condition_absent {
      filter   = "metric.type=\"compute.googleapis.com/instance/uptime\" AND resource.type=\"gce_instance\" AND resource.label.instance_id=\"${each.value}\""
      duration = "300s"
      aggregations {
        alignment_period   = "60s"
        per_series_aligner = "ALIGN_MEAN"
      }
    }
  }
}

# ---- Log-based signals ----------------------------------------------------------------

# The worker logs worker_loop_pass_failed with loop=registrations when a pass
# raises (app/worker.py). Sustained failures mean registrations are not being
# processed, whatever the queue length.
resource "google_logging_metric" "registration_pass_failed" {
  name   = "${local.name}-registration-pass-failed"
  filter = "severity>=ERROR AND SEARCH(\"worker_loop_pass_failed\") AND SEARCH(\"registrations\")"
  metric_descriptor {
    metric_kind = "DELTA"
    value_type  = "INT64"
  }
}

resource "google_monitoring_alert_policy" "registration_worker" {
  display_name          = "${local.name}: registration worker failing"
  combiner              = "OR"
  notification_channels = local.channels

  conditions {
    display_name = "three or more failed registration passes in 5 minutes"
    condition_threshold {
      filter          = "metric.type=\"logging.googleapis.com/user/${google_logging_metric.registration_pass_failed.name}\" AND resource.type=\"cloud_run_worker_pool\""
      comparison      = "COMPARISON_GT"
      threshold_value = 2
      duration        = "0s"
      aggregations {
        alignment_period   = "300s"
        per_series_aligner = "ALIGN_SUM"
      }
    }
  }

  documentation {
    content   = "Registration passes are failing. See docs/gcp-staging-runbook.md, 'Registration-worker backlog'."
    mime_type = "text/markdown"
  }
}

# Learning Memory must stay disabled. The backend logs "Learning memory: enabled"
# only if the gate let it through; any occurrence is a page.
resource "google_logging_metric" "learning_memory_enabled" {
  name   = "${local.name}-learning-memory-enabled"
  filter = "SEARCH(\"Learning memory: enabled\")"
  metric_descriptor {
    metric_kind = "DELTA"
    value_type  = "INT64"
  }
}

resource "google_monitoring_alert_policy" "learning_memory_enabled" {
  display_name          = "${local.name}: Learning Memory enabled"
  combiner              = "OR"
  notification_channels = local.channels

  conditions {
    display_name = "the enabled line was logged"
    condition_threshold {
      filter          = "metric.type=\"logging.googleapis.com/user/${google_logging_metric.learning_memory_enabled.name}\""
      comparison      = "COMPARISON_GT"
      threshold_value = 0
      duration        = "0s"
      aggregations {
        alignment_period   = "60s"
        per_series_aligner = "ALIGN_SUM"
      }
    }
  }
}
