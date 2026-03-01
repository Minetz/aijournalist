variable "project_id" {
  description = "GCP project ID"
  type        = string
}

variable "region" {
  description = "GCP region for Cloud Run and Artifact Registry"
  type        = string
  default     = "us-central1"
}

variable "env" {
  description = "Environment name: dev or prod"
  type        = string
  default     = "dev"
}

variable "image_tag" {
  description = "Docker image tag to deploy"
  type        = string
  default     = "latest"
}

variable "journalists" {
  description = "Map of journalist_id -> config for Cloud Scheduler jobs"
  type = map(object({
    mandate      = string
    jurisdiction = string
    tier         = string
    schedule     = string  # cron expression, e.g. "0 6 * * *"
  }))
  default = {}
}
