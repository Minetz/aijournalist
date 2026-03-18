"""
FastAPI router for public records request management.

Endpoints:
  POST /records-requests/draft          — Draft requests for a published story
  GET  /records-requests/{journalist_id}         — List all requests
  GET  /records-requests/{journalist_id}/{request_id} — Get single request
  PATCH /records-requests/{journalist_id}/{request_id}/status — Update status
"""
import datetime

import structlog
from fastapi import APIRouter, HTTPException
from google.cloud import firestore
from pydantic import BaseModel

from tools.records_requests.drafter import draft_records_requests
from tools.records_requests.tracker import (
    VALID_STATUSES,
    get_request,
    list_requests,
    save_draft,
    update_status,
)

log = structlog.get_logger()
router = APIRouter(prefix="/records-requests", tags=["records-requests"])


class DraftRequest(BaseModel):
    journalist_id: str
    cycle_id: str
    story_title: str
    sub_questions: list[str]
    evidence_summary: str
    jurisdiction: str
    max_requests: int = 2


class StatusUpdate(BaseModel):
    status: str
    notes: str = ""


@router.post("/draft")
async def draft_requests(req: DraftRequest) -> dict:
    """
    Draft public records request letters for a published story.
    Drafts are saved to Firestore with status='draft' and returned in full.
    """
    today = datetime.date.today().isoformat()
    drafts = await draft_records_requests(
        story_title=req.story_title,
        sub_questions=req.sub_questions,
        evidence_summary=req.evidence_summary,
        jurisdiction=req.jurisdiction,
        today=today,
        max_requests=req.max_requests,
    )
    if not drafts:
        return {"status": "ok", "drafted": 0, "requests": []}

    db = firestore.AsyncClient()
    saved = []
    for draft in drafts:
        request_id = await save_draft(
            db=db,
            journalist_id=req.journalist_id,
            cycle_id=req.cycle_id,
            story_title=req.story_title,
            draft=draft,
        )
        saved.append({"request_id": request_id, **draft.to_dict()})

    return {"status": "ok", "drafted": len(saved), "requests": saved}


@router.get("/{journalist_id}")
async def list_journalist_requests(
    journalist_id: str,
    status: str | None = None,
    limit: int = 50,
) -> dict:
    """List records requests for a journalist, optionally filtered by status."""
    if status and status not in VALID_STATUSES:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid status '{status}'. Valid: {sorted(VALID_STATUSES)}",
        )
    db = firestore.AsyncClient()
    requests = await list_requests(db, journalist_id, status_filter=status, limit=limit)
    return {"journalist_id": journalist_id, "count": len(requests), "requests": requests}


@router.get("/{journalist_id}/{request_id}")
async def get_single_request(journalist_id: str, request_id: str) -> dict:
    """Get a single records request by ID."""
    db = firestore.AsyncClient()
    req = await get_request(db, journalist_id, request_id)
    if not req:
        raise HTTPException(status_code=404, detail=f"Request {request_id} not found")
    return req


@router.patch("/{journalist_id}/{request_id}/status")
async def update_request_status(
    journalist_id: str,
    request_id: str,
    body: StatusUpdate,
) -> dict:
    """Update the lifecycle status of a records request."""
    if body.status not in VALID_STATUSES:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid status '{body.status}'. Valid: {sorted(VALID_STATUSES)}",
        )
    db = firestore.AsyncClient()
    req = await get_request(db, journalist_id, request_id)
    if not req:
        raise HTTPException(status_code=404, detail=f"Request {request_id} not found")
    await update_status(db, journalist_id, request_id, body.status, body.notes)
    return {"status": "ok", "request_id": request_id, "new_status": body.status}
