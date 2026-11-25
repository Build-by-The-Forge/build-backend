# ClamAV for the backend worker's malware scan (CLAMAV_HOST, port 3310).
# clamd speaks raw TCP, which Cloud Run services cannot receive, so it runs on a
# small VM in the private subnet (docs/gcp-staging-verification.md section 4).
# No public address; port 3310 is open only to the Cloud Run subnet
# (network.tf). Files never leave BUILD's network.

resource "google_service_account" "clamav_vm" {
  account_id   = "${local.name}-clamav"
  display_name = "ClamAV VM (${var.environment})"
}

resource "google_compute_address" "clamav" {
  name         = "${local.name}-clamav"
  region       = var.region
  address_type = "INTERNAL"
  subnetwork   = google_compute_subnetwork.run.id
}

resource "google_compute_instance" "clamav" {
  name         = "${local.name}-clamav"
  zone         = var.zone
  machine_type = var.clamav_machine_type
  tags         = ["clamav"]

  boot_disk {
    initialize_params {
      image = "cos-cloud/cos-stable"
      size  = 20
    }
  }

  network_interface {
    subnetwork = google_compute_subnetwork.run.id
    network_ip = google_compute_address.clamav.address
  }

  service_account {
    email  = google_service_account.clamav_vm.email
    scopes = ["https://www.googleapis.com/auth/logging.write", "https://www.googleapis.com/auth/monitoring.write"]
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
      docker rm -f clamav 2>/dev/null || true
      docker run -d --name clamav --restart=always -p 3310:3310 \
        -e CLAMAV_NO_MILTERD=true ${var.clamav_image}
    EOT
  }

  allow_stopping_for_update = true
  deletion_protection       = true
}
