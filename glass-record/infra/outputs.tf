output "editor_url" {
  description = "Editor Cloud Run service URL"
  value       = module.editor_service.url
}

output "researcher_url" {
  description = "Researcher Cloud Run service URL"
  value       = module.researcher_service.url
}

output "artifact_registry_repo" {
  description = "Artifact Registry repository URL"
  value       = module.artifact_registry.repo_url
}

output "researcher_topic" {
  description = "Pub/Sub topic for researcher task dispatch"
  value       = module.pubsub.researcher_topic_name
}
