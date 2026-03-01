project_id = "glass-record-dev"
region     = "us-central1"
env        = "dev"
image_tag  = "latest"

journalists = {
  "un-security-council-001" = {
    mandate      = "Investigate human rights implications of UN Security Council decisions."
    jurisdiction = "UN"
    tier         = "free"
    schedule     = "0 6 * * *"  # 06:00 UTC daily
  }
}
