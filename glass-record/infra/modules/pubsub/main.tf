variable "project_id" { type = string }

resource "google_pubsub_topic" "researcher_tasks" {
  name    = "glass-record-researcher-tasks"
  project = var.project_id

  message_retention_duration = "86400s"  # 24 hours
}

resource "google_pubsub_subscription" "researcher_push" {
  name    = "glass-record-researcher-push"
  topic   = google_pubsub_topic.researcher_tasks.name
  project = var.project_id

  push_config {
    push_endpoint = var.researcher_service_url
  }

  ack_deadline_seconds       = 600
  message_retention_duration = "86400s"
  retry_policy {
    minimum_backoff = "10s"
    maximum_backoff = "300s"
  }
}

variable "researcher_service_url" {
  type    = string
  default = ""
}

output "researcher_topic_name" {
  value = google_pubsub_topic.researcher_tasks.name
}
