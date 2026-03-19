"""
FastAPI router for maintenance operations.

Endpoints:
  POST /maintenance/compress-logs   — Archive old activity_log entries to GCS
                                      and delete them from Firestore.
  GET  /maintenance/log-stats/{journalist_id} — Count current activity_log entries
                                                and oldest entry date.

These endpoints are intended to be called by a weekly Cloud Scheduler job,
not by end users. Protect them behind IAM or service-account OIDC in production.
"""
import structlog
from fastapi import APIRouter, HTTPException
from google.cloud import firestore, storage
from pydantic import BaseModel, Field

from agents.shared.gemini import get_settings
from agents.shared.log_compression import compress_activity_log

log = structlog.get_logger()
router = APIRouter(prefix="/maintenance", tags=["maintenance"])


class CompressLogsRequest(BaseModel):
    journalist_id: str
    keep_days: int = Field(default=90, ge=7, le=365)


@router.post("/compress-logs")
async def compress_logs(req: CompressLogsRequest) -> dict:
    """
    Archive activity_log entries older than keep_days to GCS (JSONL) and
    delete them from Firestore.

    Safe to call multiple times — GCS files are appended, not overwritten.
    """
    settings = get_settings()
    db = firestore.AsyncClient()
    gcs = storage.Client(project=settings.google_cloud_project)

    try:
        result = await compress_activity_log(
            db=db,
            gcs_client=gcs,
            journalist_id=req.journalist_id,
            bucket_name=settings.gcs_evidence_bucket,
            keep_days=req.keep_days,
        )
    except Exception as exc:
        log.error("compress_logs_failed", journalist_id=req.journalist_id, error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))

    return {
        "status": "ok",
        "journalist_id": req.journalist_id,
        "keep_days": req.keep_days,
        **result,
    }


@router.get("/log-stats/{journalist_id}")
async def log_stats(journalist_id: str) -> dict:
    """
    Return a quick summary of the activity_log size for a journalist.
    Fetches up to 1000 entries to count and find the oldest timestamp.
    """
    db = firestore.AsyncClient()
    try:
        snaps = await (
            db.collection("journalists")
            .document(journalist_id)
            .collection("activity_log")
            .order_by("timestamp", direction=firestore.Query.ASCENDING)
            .limit(1000)
            .get()
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    entries = [s.to_dict() for s in snaps]
    oldest = entries[0].get("timestamp", "") if entries else ""
    count = len(entries)
    capped = count == 1000

    return {
        "journalist_id": journalist_id,
        "count": count,
        "count_capped_at": 1000 if capped else None,
        "oldest_entry": oldest,
    }
