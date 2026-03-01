variable "project_id"      { type = string }
variable "region"          { type = string }
variable "service_name"    { type = string }
variable "image"           { type = string }
variable "env_vars"        { type = map(string) }
variable "service_account" { type = string }
variable "max_instances"   { type = number; default = 10 }
variable "concurrency"     { type = number; default = 80 }
variable "timeout_seconds" { type = number; default = 3600 }

resource "google_cloud_run_v2_service" "service" {
  name     = var.service_name
  location = var.region
  project  = var.project_id

  template {
    service_account = var.service_account

    scaling {
      min_instance_count = 0
      max_instance_count = var.max_instances
    }

    containers {
      image = var.image

      dynamic "env" {
        for_each = var.env_vars
        content {
          name  = env.key
          value = env.value
        }
      }

      resources {
        limits = {
          cpu    = "2"
          memory = "2Gi"
        }
      }
    }

    timeout = "${var.timeout_seconds}s"
    max_instance_request_concurrency = var.concurrency
  }
}

output "url" {
  value = google_cloud_run_v2_service.service.uri
}
