# Buckets. The document bucket is private and is never put behind the CDN. The
# APK bucket is public-read behind the CDN (cdn.tf): the file hash in the update
# contract is what protects integrity.

resource "google_storage_bucket" "documents" {
  name                        = "${var.project_id}-${local.name}-documents"
  location                    = var.region
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = false

  versioning {
    enabled = true
  }

  lifecycle_rule {
    condition {
      days_since_noncurrent_time = 30
      with_state                 = "ARCHIVED"
    }
    action {
      type = "Delete"
    }
  }

  depends_on = [google_project_service.apis]
}

resource "google_storage_bucket" "apk" {
  name                        = "${var.project_id}-${local.name}-apk"
  location                    = var.region
  uniform_bucket_level_access = true
  force_destroy               = false

  depends_on = [google_project_service.apis]
}

# Readable by anyone through the CDN: the release file is public by design.
resource "google_storage_bucket_iam_member" "apk_public" {
  bucket = google_storage_bucket.apk.name
  role   = "roles/storage.objectViewer"
  member = "allUsers"
}

# Per-service access to the document bucket (the boundary topology's identities:
# backend read, write and list; ai-service read only).
resource "google_storage_bucket_iam_member" "backend_documents" {
  bucket = google_storage_bucket.documents.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.backend.email}"
}

resource "google_storage_bucket_iam_member" "ai_documents" {
  bucket = google_storage_bucket.documents.name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${google_service_account.ai.email}"
}
