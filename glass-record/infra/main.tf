terraform {
  required_version = ">= 1.7"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.30"
    }
  }
  backend "gcs" {
    bucket = "glass-record-tf-state"
    prefix = "terraform/state"
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

# ── Artifact Registry ────────────────────────────────────────────────────────

module "artifact_registry" {
  source     = "./modules/artifact_registry"
  project_id = var.project_id
  region     = var.region
}

# ── Pub/Sub ──────────────────────────────────────────────────────────────────

module "pubsub" {
  source     = "./modules/pubsub"
  project_id = var.project_id
}

# ── Editor Cloud Run service (one per journalist) ────────────────────────────

module "editor_service" {
  source          = "./modules/cloud_run"
  project_id      = var.project_id
  region          = var.region
  service_name    = "glass-record-editor"
  image           = "${var.region}-docker.pkg.dev/${var.project_id}/agents/editor:${var.image_tag}"
  env_vars        = local.shared_env_vars
  service_account = google_service_account.agent_runner.email
}

# ── Researcher Cloud Run service ─────────────────────────────────────────────

module "researcher_service" {
  source          = "./modules/cloud_run"
  project_id      = var.project_id
  region          = var.region
  service_name    = "glass-record-researcher"
  image           = "${var.region}-docker.pkg.dev/${var.project_id}/agents/researcher:${var.image_tag}"
  env_vars        = merge(local.shared_env_vars, { RESEARCHER_MODE = "pubsub" })
  service_account = google_service_account.agent_runner.email
}

# ── Cloud Scheduler ──────────────────────────────────────────────────────────

module "scheduler" {
  source              = "./modules/scheduler"
  project_id          = var.project_id
  region              = var.region
  editor_service_url  = module.editor_service.url
  service_account     = google_service_account.scheduler_invoker.email
  journalists         = var.journalists
}

# ── Service Accounts ─────────────────────────────────────────────────────────

resource "google_service_account" "agent_runner" {
  account_id   = "glass-record-agent"
  display_name = "Glass Record Agent Runner"
}

resource "google_service_account" "scheduler_invoker" {
  account_id   = "glass-record-scheduler"
  display_name = "Glass Record Cloud Scheduler Invoker"
}

resource "google_project_iam_member" "agent_firestore" {
  project = var.project_id
  role    = "roles/datastore.user"
  member  = "serviceAccount:${google_service_account.agent_runner.email}"
}

resource "google_project_iam_member" "agent_storage" {
  project = var.project_id
  role    = "roles/storage.objectAdmin"
  member  = "serviceAccount:${google_service_account.agent_runner.email}"
}

resource "google_project_iam_member" "agent_pubsub" {
  project = var.project_id
  role    = "roles/pubsub.publisher"
  member  = "serviceAccount:${google_service_account.agent_runner.email}"
}

resource "google_project_iam_member" "agent_vertex" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.agent_runner.email}"
}

# ── Cloud Storage: evidence locker ───────────────────────────────────────────

resource "google_storage_bucket" "evidence" {
  name                        = "glass-record-evidence-${var.env}"
  location                    = var.region
  uniform_bucket_level_access = true
  force_destroy               = false

  lifecycle_rule {
    action { type = "SetStorageClass"; storage_class = "NEARLINE" }
    condition { age = 90 }
  }

  versioning { enabled = true }
}

resource "google_storage_bucket_iam_member" "agent_evidence_rw" {
  bucket = google_storage_bucket.evidence.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.agent_runner.email}"
}

locals {
  shared_env_vars = {
    GOOGLE_CLOUD_PROJECT      = var.project_id
    GOOGLE_GENAI_USE_VERTEXAI = "true"
    GEMINI_MODEL              = "gemini-1.5-pro-002"
    GCS_EVIDENCE_BUCKET       = google_storage_bucket.evidence.name
    PUBSUB_RESEARCHER_TOPIC   = module.pubsub.researcher_topic_name
  }
}
