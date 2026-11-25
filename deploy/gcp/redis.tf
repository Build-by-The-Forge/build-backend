# Redis 8 on a Compute Engine VM. No Memorystore product runs Redis 8 (see
# docs/gcp-staging-verification.md section 2), and the requirement is not
# weakened. The owner owns patching, persistence and failover; the alert policy
# in monitoring.tf watches the VM.
#
# The password is read at boot from Secret Manager with the VM's own identity,
# so it is never in Terraform, the image or the instance metadata.

resource "google_service_account" "redis_vm" {
  account_id   = "${local.name}-redis"
  display_name = "Redis VM (${var.environment})"
}

resource "google_compute_address" "redis" {
  name         = "${local.name}-redis"
  region       = var.region
  address_type = "INTERNAL"
  subnetwork   = google_compute_subnetwork.run.id
}

resource "google_compute_disk" "redis" {
  name = "${local.name}-redis-data"
  zone = var.zone
  type = "pd-balanced"
  size = 10
}

resource "google_compute_instance" "redis" {
  name         = "${local.name}-redis"
  zone         = var.zone
  machine_type = var.redis_machine_type
  tags         = ["redis"]

  boot_disk {
    initialize_params {
      image = "cos-cloud/cos-stable"
    }
  }

  attached_disk {
    source      = google_compute_disk.redis.id
    device_name = "redis-data"
  }

  network_interface {
    subnetwork = google_compute_subnetwork.run.id
    network_ip = google_compute_address.redis.address
  }

  service_account {
    email  = google_service_account.redis_vm.email
    scopes = ["cloud-platform"]
  }

  shielded_instance_config {
    enable_secure_boot          = true
    enable_vtpm                 = true
    enable_integrity_monitoring = true
  }

  metadata = {
    enable-oslogin = "TRUE"
    startup-script = <<-EOT
      #!/bin/bash
      set -euo pipefail
      DISK=/dev/disk/by-id/google-redis-data
      MNT=/mnt/disks/redis
      blkid "$DISK" >/dev/null 2>&1 || mkfs.ext4 -m 0 -F "$DISK"
      mkdir -p "$MNT" && mount -o discard,defaults "$DISK" "$MNT" 2>/dev/null || true
      chown 999:999 "$MNT"

      TOKEN=$(curl -s -H 'Metadata-Flavor: Google' \
        http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token \
        | sed -n 's/.*"access_token": *"\([^"]*\)".*/\1/p')
      PASSWORD=$(curl -s -H "Authorization: Bearer $TOKEN" \
        "https://secretmanager.googleapis.com/v1/projects/${var.project_id}/secrets/${google_secret_manager_secret.this["redis-password"].secret_id}/versions/latest:access" \
        | sed -n 's/.*"data": *"\([^"]*\)".*/\1/p' | base64 -d)
      [ -n "$PASSWORD" ] || { echo "redis-password has no version yet" >&2; exit 1; }

      docker rm -f redis 2>/dev/null || true
      docker run -d --name redis --restart=always -p 6379:6379 -v "$MNT":/data \
        ${var.redis_image} redis-server --requirepass "$PASSWORD" --appendonly yes --save 60 1000
    EOT
  }

  # Replacing the VM replaces nothing durable (the data disk is separate), but a
  # change to the startup script should not restart Redis during a deploy.
  allow_stopping_for_update = true
  deletion_protection       = true
}
