"""
Verification Agent — mounted as a router on the Editor service.
Handles public tip submission and async verification.
"""
import asyncio
import datetime
import uuid

import structlog
from fastapi import APIRouter, BackgroundTasks, HTTPException
from google.cloud import firestore
from pydantic import BaseModel, field_validator

from agents.verification.nodes import verify_tip

router = APIRouter()
log = structlog.get_logger()

_MAX_TIP_LENGTH = 5_000
_MIN_TIP_LENGTH = 10


class TipRequest(BaseModel):
    content: str

    @field_validator("content")
    @classmethod
    def content_length(cls, v: str) -> str:
        v = v.strip()
        if len(v) < _MIN_TIP_LENGTH:
            raise ValueError(f"Tip must be at least {_MIN_TIP_LENGTH} characters.")
        if len(v) > _MAX_TIP_LENGTH:
            raise ValueError(f"Tip must be at most {_MAX_TIP_LENGTH} characters.")
        return v


class TipResponse(BaseModel):
    tip_id: str
    status: str
    message: str


@router.post("/tips/{journalist_id}", response_model=TipResponse)
async def submit_tip(
    journalist_id: str,
    req: TipRequest,
    background_tasks: BackgroundTasks,
) -> TipResponse:
    """
    Accept a public tip. Stores it immediately, then runs verification
    asynchronously in the background so the response is instant.
    """
    tip_id = str(uuid.uuid4())
    db = firestore.AsyncClient()

    tip_doc = {
        "tip_id": tip_id,
        "journalist_id": journalist_id,
        "content": req.content,
        "submitted_at": datetime.datetime.utcnow().isoformat(),
        "verification": None,
    }

    try:
        await (
            db.collection("journalists")
            .document(journalist_id)
            .collection("tips")
            .document(tip_id)
            .set(tip_doc)
        )
    except Exception as exc:
        log.error("tip_store_failed", error=str(exc))
        raise HTTPException(status_code=500, detail="Failed to store tip.")

    # Verify in background — does not block the submitter
    background_tasks.add_task(_run_verification, journalist_id, tip_id, req.content)

    log.info("tip_received", journalist_id=journalist_id, tip_id=tip_id)
    return TipResponse(
        tip_id=tip_id,
        status="received",
        message=(
            "Your tip has been received and will be assessed by the Verification Agent "
            "against the evidence locker. The result will be published publicly."
        ),
    )


async def _run_verification(journalist_id: str, tip_id: str, content: str) -> None:
    try:
        await verify_tip(journalist_id, tip_id, content)
    except Exception as exc:
        log.error("verification_failed", journalist_id=journalist_id,
                  tip_id=tip_id, error=str(exc))
