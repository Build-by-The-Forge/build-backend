terraform {
  required_version = ">= 1.9"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = ">= 7.0, < 8.0"
    }
  }

  # State: local until the project exists. Before the first apply, decide where
  # state lives (a versioned bucket in the project, created by hand, is the
  # usual choice) and uncomment this. State holds resource ids, never secret
  # values: no secret is created by this configuration.
  #
  # backend "gcs" {
  #   bucket = "<state bucket>"
  #   prefix = "build/staging"
  # }
}

provider "google" {
  project = var.project_id
  region  = var.region
}
