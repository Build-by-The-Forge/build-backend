output "backend_url" {
  description = "The backend's public URL (the mobile app's API base)."
  value       = local.backend_url
}

output "ai_url" {
  description = "The ai-service's internal URL (reachable only from the VPC)."
  value       = local.ai_url
}

output "cloudsql_private_ip" {
  description = "Host for the database URLs the owner stores in Secret Manager."
  value       = google_sql_database_instance.main.private_ip_address
}

output "cloudsql_instance" {
  value = google_sql_database_instance.main.name
}

output "redis_private_ip" {
  description = "Host for the two Redis URLs (backend db 0, ai-service db 1)."
  value       = google_compute_address.redis.address
}

output "clamav_private_ip" {
  value = google_compute_address.clamav.address
}

output "documents_bucket" {
  value = google_storage_bucket.documents.name
}

output "apk_bucket" {
  value = google_storage_bucket.apk.name
}

output "apk_cdn_ip" {
  description = "Point the apk_domain DNS A record here."
  value       = var.apk_domain == "" ? null : google_compute_global_address.apk["apk"].address
}

output "artifact_registry" {
  description = "Image repository the deploy workflow pushes to."
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.images.repository_id}"
}

output "deployer_service_account" {
  value = google_service_account.deployer.email
}

output "workload_identity_provider" {
  description = "Value for the deploy workflow's provider input; empty until github_repositories is set."
  value       = length(var.github_repositories) == 0 ? null : google_iam_workload_identity_pool_provider.github[0].name
}

output "secret_names" {
  description = "Secret Manager entries to fill by hand (names only)."
  value       = sort([for s in google_secret_manager_secret.this : s.secret_id])
}
