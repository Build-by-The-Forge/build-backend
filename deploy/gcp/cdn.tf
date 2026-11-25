# APK delivery: global external Application Load Balancer, a backend bucket with
# Cloud CDN enabled, and a Google-managed certificate. Skipped until a domain is
# chosen (var.apk_domain). DNS for the domain points at the address below.

locals {
  cdn = var.apk_domain == "" ? toset([]) : toset(["apk"])
}

resource "google_compute_global_address" "apk" {
  for_each = local.cdn
  name     = "${local.name}-apk"
}

resource "google_compute_backend_bucket" "apk" {
  for_each    = local.cdn
  name        = "${local.name}-apk"
  bucket_name = google_storage_bucket.apk.name
  enable_cdn  = true

  cdn_policy {
    cache_mode        = "USE_ORIGIN_HEADERS"
    client_ttl        = 3600
    default_ttl       = 3600
    max_ttl           = 86400
    negative_caching  = false
    serve_while_stale = 0
  }
}

resource "google_compute_url_map" "apk" {
  for_each        = local.cdn
  name            = "${local.name}-apk"
  default_service = google_compute_backend_bucket.apk["apk"].id
}

resource "google_compute_managed_ssl_certificate" "apk" {
  for_each = local.cdn
  name     = "${local.name}-apk"
  managed {
    domains = [var.apk_domain]
  }
}

resource "google_compute_target_https_proxy" "apk" {
  for_each         = local.cdn
  name             = "${local.name}-apk"
  url_map          = google_compute_url_map.apk["apk"].id
  ssl_certificates = [google_compute_managed_ssl_certificate.apk["apk"].id]
}

resource "google_compute_global_forwarding_rule" "apk" {
  for_each              = local.cdn
  name                  = "${local.name}-apk"
  target                = google_compute_target_https_proxy.apk["apk"].id
  port_range            = "443"
  ip_address            = google_compute_global_address.apk["apk"].address
  load_balancing_scheme = "EXTERNAL_MANAGED"
}
