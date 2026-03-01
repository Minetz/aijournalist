variable "project_id"           { type = string }
variable "region"               { type = string }
variable "editor_service_url"   { type = string }
variable "service_account"      { type = string }
variable "journalists" {
  type = map(object({
    mandate      = string
    jurisdiction = string
    tier         = string
    schedule     = string
  }))
}

# One Cloud Scheduler job per journalist
resource "google_cloud_scheduler_job" "journalist_cycle" {
  for_each = var.journalists

  name     = "glass-record-cycle-${each.key}"
  project  = var.project_id
  region   = var.region
  schedule = each.value.schedule
  time_zone = "UTC"

  http_target {
    uri         = "${var.editor_service_url}/run"
    http_method = "POST"

    body = base64encode(jsonencode({
      journalist_id = each.key
      mandate       = each.value.mandate
      jurisdiction  = each.value.jurisdiction
      tier          = each.value.tier
    }))

    headers = {
      "Content-Type" = "application/json"
    }

    oidc_token {
      service_account_email = var.service_account
      audience              = var.editor_service_url
    }
  }

  retry_config {
    retry_count          = 3
    min_backoff_duration = "30s"
    max_backoff_duration = "300s"
  }
}
