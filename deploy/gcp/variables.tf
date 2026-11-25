variable "project_id" {
  description = "The Google Cloud project for staging. No default: the project is created and billed by the owner, not by this configuration."
  type        = string
}

variable "region" {
  description = "One region for the API, the database and the VMs (africa-south1, europe-west1 or europe-west4 until the latency benchmark decides). No default on purpose."
  type        = string
}

variable "zone" {
  description = "A zone inside var.region, for the Redis and ClamAV VMs."
  type        = string
}

variable "environment" {
  description = "Resource-name suffix and APP_ENVIRONMENT. The application validates secrets strictly for staging and production."
  type        = string
  default     = "staging"

  validation {
    condition     = contains(["staging", "production"], var.environment)
    error_message = "environment must be staging or production."
  }
}

# Images. Defaults are Google's public hello image so the first plan and apply
# can create the infrastructure before any image has been built; the deploy
# workflow then moves each service to a built image by digest. Terraform ignores
# later image changes (see run.tf), so it never fights the workflow.
variable "placeholder_image" {
  type    = string
  default = "us-docker.pkg.dev/cloudrun/container/hello"
}

variable "db_tier" {
  description = "Cloud SQL machine tier. Confirm the tier exists for the chosen region before applying."
  type        = string
  default     = "db-custom-2-7680"
}

variable "db_availability_type" {
  description = "ZONAL for staging, REGIONAL for production."
  type        = string
  default     = "ZONAL"
}

variable "redis_image" {
  description = "Redis 8, which BUILD requires. Pin by digest before the first apply."
  type        = string
  default     = "redis:8"
}

variable "redis_machine_type" {
  type    = string
  default = "e2-small"
}

variable "clamav_image" {
  description = "Pinned by digest, as in deploy/compose.m3.yml."
  type        = string
  default     = "clamav/clamav:1.4@sha256:8ad6197396974726c35d017e50aaaaf4b91745726a04faec8480c203edd98052"
}

variable "clamav_machine_type" {
  description = "clamd loads its signature database into memory; the size is to be measured on staging."
  type        = string
  default     = "e2-medium"
}

variable "model_provider" {
  description = "ai-service MODEL_PROVIDER. Stays deterministic until G-33 is recorded: no production provider receives content before then."
  type        = string
  default     = "deterministic"
}

variable "object_storage_region" {
  description = "The signing region the S3 client uses against Cloud Storage's XML API. Not confirmed; see docs/gcp-staging-verification.md section 5."
  type        = string
  default     = "us-east-1"
}

variable "trusted_proxies" {
  description = "TRUSTED_PROXIES for the backend (comma-separated CIDRs). Empty until the staging run shows which source addresses Cloud Run presents."
  type        = string
  default     = ""
}

variable "apk_domain" {
  description = "Domain for the APK CDN (for example apk.staging.example). Empty skips the load balancer and CDN."
  type        = string
  default     = ""
}

variable "alert_email" {
  description = "Where alerts go. Empty creates policies with no notification channel."
  type        = string
  default     = ""
}

variable "github_repositories" {
  description = "owner/name of repositories allowed to deploy through Workload Identity Federation. Empty creates no federation."
  type        = list(string)
  default     = []
}

variable "backend_min_instances" {
  type    = number
  default = 1
}
