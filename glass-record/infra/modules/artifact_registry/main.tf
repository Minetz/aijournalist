variable "project_id" { type = string }
variable "region"     { type = string }

resource "google_artifact_registry_repository" "agents" {
  location      = var.region
  repository_id = "agents"
  format        = "DOCKER"
  project       = var.project_id
  description   = "Glass Record agent Docker images"
}

output "repo_url" {
  value = "${var.region}-docker.pkg.dev/${var.project_id}/agents"
}
