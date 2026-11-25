# One VPC. Cloud Run reaches Cloud SQL, Redis and ClamAV through Direct VPC
# egress on this subnet. Nothing here has a public address except the Cloud Run
# backend service and the optional APK load balancer.

resource "google_compute_network" "vpc" {
  name                    = local.name
  auto_create_subnetworks = false
  depends_on              = [google_project_service.apis]
}

resource "google_compute_subnetwork" "run" {
  name                     = "${local.name}-run"
  region                   = var.region
  network                  = google_compute_network.vpc.id
  ip_cidr_range            = "10.20.0.0/24"
  private_ip_google_access = true # internal ingress between Cloud Run services needs this
}

# Private services access: Cloud SQL's private IP lives in a peered range.
resource "google_compute_global_address" "private_services" {
  name          = "${local.name}-private-services"
  purpose       = "VPC_PEERING"
  address_type  = "INTERNAL"
  prefix_length = 20
  network       = google_compute_network.vpc.id
}

resource "google_service_networking_connection" "private_services" {
  network                 = google_compute_network.vpc.id
  service                 = "servicenetworking.googleapis.com"
  reserved_peering_ranges = [google_compute_global_address.private_services.name]
}

# Outbound internet for the VMs (ClamAV signature updates, image pulls) and for
# Cloud Run traffic that is routed through the VPC.
resource "google_compute_router" "this" {
  name    = local.name
  region  = var.region
  network = google_compute_network.vpc.id
}

resource "google_compute_router_nat" "this" {
  name                               = local.name
  router                             = google_compute_router.this.name
  region                             = var.region
  nat_ip_allocate_option             = "AUTO_ONLY"
  source_subnetwork_ip_ranges_to_nat = "ALL_SUBNETWORKS_ALL_IP_RANGES"
}

# The only inbound paths to the VMs: Redis and ClamAV, from the Cloud Run subnet.
resource "google_compute_firewall" "redis" {
  name          = "${local.name}-redis-from-run"
  network       = google_compute_network.vpc.name
  direction     = "INGRESS"
  source_ranges = [google_compute_subnetwork.run.ip_cidr_range]
  target_tags   = ["redis"]
  allow {
    protocol = "tcp"
    ports    = ["6379"]
  }
}

resource "google_compute_firewall" "clamav" {
  name          = "${local.name}-clamav-from-run"
  network       = google_compute_network.vpc.name
  direction     = "INGRESS"
  source_ranges = [google_compute_subnetwork.run.ip_cidr_range]
  target_tags   = ["clamav"]
  allow {
    protocol = "tcp"
    ports    = ["3310"]
  }
}
