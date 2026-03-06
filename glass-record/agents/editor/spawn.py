"""
Spawn API — MVP 9.

POST /spawn creates a new journalist:
1. Validates the request (mandate must be non-empty, jurisdiction must be known).
2. Registers the journalist in Firestore (mandate immutability enforced).
3. Creates a Cloud Scheduler job to trigger the daily investigation cycle.

Run as part of the Editor Cloud Run service.
"""
import os
import re
import uuid

import structlog
from fastapi import APIRouter, HTTPException
from google.cloud import firestore, scheduler_v1
from pydantic import BaseModel, field_validator

from agents.shared.base_agent import register_journalist
from agents.shared.gemini import get_settings

log = structlog.get_logger()
router = APIRouter()

KNOWN_JURISDICTIONS = {
    "UN", "EU", "ICC", "ICJ", "US_FEDERAL", "NATO", "WORLD_BANK", "ECHR"
}

_CRON_RE = re.compile(
    r"^(\*|[0-9,\-\*/]+)\s+"  # minute
    r"(\*|[0-9,\-\*/]+)\s+"   # hour
    r"(\*|[0-9,\-\*/]+)\s+"   # day-of-month
    r"(\*|[0-9,\-\*/]+)\s+"   # month
    r"(\*|[0-9,\-\*/]+)$"     # day-of-week
)


class SpawnRequest(BaseModel):
    mandate: str
    jurisdiction: str
    tier: str = "free"
    schedule: str = "0 6 * * *"  # UTC cron; default: 06:00 daily

    @field_validator("mandate")
    @classmethod
    def mandate_not_empty(cls, v: str) -> str:
        if len(v.strip()) < 20:
            raise ValueError("Mandate must be at least 20 characters.")
        return v.strip()

    @field_validator("jurisdiction")
    @classmethod
    def jurisdiction_known(cls, v: str) -> str:
        if v.upper() not in KNOWN_JURISDICTIONS:
            raise ValueError(
                f"Unknown jurisdiction '{v}'. Known: {sorted(KNOWN_JURISDICTIONS)}"
            )
        return v.upper()

    @field_validator("schedule")
    @classmethod
    def valid_cron(cls, v: str) -> str:
        if not _CRON_RE.match(v.strip()):
            raise ValueError(f"Invalid cron expression: '{v}'")
        return v.strip()


class SpawnResponse(BaseModel):
    journalist_id: str
    mandate: str
    jurisdiction: str
    tier: str
    schedule: str
    scheduler_job: str | None = None
    warning: str | None = None


@router.post("/spawn", response_model=SpawnResponse)
async def spawn_journalist(req: SpawnRequest) -> SpawnResponse:
    """Create a new autonomous journalist and schedule its daily cycle."""
    journalist_id = f"{req.jurisdiction.lower()}-{uuid.uuid4().hex[:8]}"
    settings = get_settings()

    log.info("spawn_start", journalist_id=journalist_id, jurisdiction=req.jurisdiction)

    # Register in Firestore (idempotent — mandate protected from overwrite)
    db = firestore.AsyncClient()
    await register_journalist(
        db,
        journalist_id=journalist_id,
        mandate=req.mandate,
        jurisdiction=req.jurisdiction,
        tier=req.tier,
    )

    # Create Cloud Scheduler job (best-effort — journalist is already registered)
    job_name: str | None = None
    warning: str | None = None
    try:
        job_name = await _create_scheduler_job(
            journalist_id=journalist_id,
            mandate=req.mandate,
            jurisdiction=req.jurisdiction,
            tier=req.tier,
            schedule=req.schedule,
            project_id=settings.google_cloud_project,
        )
    except Exception as exc:
        warning = f"Journalist registered but scheduler job failed: {exc}"
        log.error("scheduler_job_failed", error=str(exc), journalist_id=journalist_id)

    log.info("spawn_complete", journalist_id=journalist_id, scheduler_job=job_name)
    return SpawnResponse(
        journalist_id=journalist_id,
        mandate=req.mandate,
        jurisdiction=req.jurisdiction,
        tier=req.tier,
        schedule=req.schedule,
        scheduler_job=job_name,
        warning=warning,
    )


async def _get_editor_service_url(project_id: str, region: str) -> str:
    """
    Look up the Editor Cloud Run service URL via the Cloud Run API.
    Falls back to EDITOR_SERVICE_URL env var if set (useful for local dev).
    """
    if url := os.environ.get("EDITOR_SERVICE_URL", "").rstrip("/"):
        return url

    from google.cloud import run_v2
    run_client = run_v2.ServicesAsyncClient()
    name = f"projects/{project_id}/locations/{region}/services/glass-record-editor"
    service = await run_client.get_service(name=name)
    return service.uri.rstrip("/")


async def _create_scheduler_job(
    journalist_id: str,
    mandate: str,
    jurisdiction: str,
    tier: str,
    schedule: str,
    project_id: str,
    region: str = "us-central1",
) -> str:
    """
    Create a Cloud Scheduler job that POSTs to the Editor /run endpoint daily.
    The Editor service URL is resolved at runtime via the Cloud Run API so there
    is no circular dependency in Terraform.
    """
    import json, base64

    client = scheduler_v1.CloudSchedulerClient()
    parent = f"projects/{project_id}/locations/{region}"

    base_url = await _get_editor_service_url(project_id, region)
    editor_url = f"{base_url}/run"

    body = json.dumps({
        "journalist_id": journalist_id,
        "mandate": mandate,
        "jurisdiction": jurisdiction,
        "tier": tier,
    }).encode()

    job = scheduler_v1.Job(
        name=f"{parent}/jobs/glass-record-cycle-{journalist_id}",
        schedule=schedule,
        time_zone="UTC",
        http_target=scheduler_v1.HttpTarget(
            uri=editor_url,
            http_method=scheduler_v1.HttpMethod.POST,
            body=body,
            headers={"Content-Type": "application/json"},
            oidc_token=scheduler_v1.OidcToken(
                service_account_email=os.environ.get(
                    "SCHEDULER_SA_EMAIL",
                    f"glass-record-scheduler@{project_id}.iam.gserviceaccount.com",
                ),
                audience=base_url,  # audience must match the service URL, not /run
            ),
        ),
        retry_config=scheduler_v1.RetryConfig(
            retry_count=3,
            min_backoff_duration={"seconds": 30},
            max_backoff_duration={"seconds": 300},
        ),
    )

    result = client.create_job(parent=parent, job=job)
    return result.name
