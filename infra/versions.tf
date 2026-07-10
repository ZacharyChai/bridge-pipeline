terraform {
  required_version = ">= 1.5"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
  zone    = var.zone
  # Auth via Application Default Credentials — no keys in code. Set one of:
  #   gcloud auth application-default login        (interactive), or
  #   GOOGLE_APPLICATION_CREDENTIALS=/path/key.json (service-account key)
}
