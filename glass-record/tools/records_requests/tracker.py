"""
Firestore tracker for public records request lifecycle.

Requests are stored at:
  journalists/{journalist_id}/records_requests/{request_id}

Status lifecycle:
  draft → submitted → acknowledged → received | denied | appealed
"""
import datetime
import uuid

import structlog
from google.cloud import firestore

from tools.records_requests.drafter import RecordsRequestDraft
from tools.records_requests.registry import get_registry_entry

log = structlog.get_logger()

VALID_STATUSES = {"draft", "submitted", "acknowledged", "received", "denied", "appealed"}


def _due_date(jurisdiction: str, from_date: str) -> str:
    entry = get_registry_entry(jurisdiction)
    base = datetime.datetime.fromisoformat(from_date)
    # Add response_days as calendar days (conservative approximation of business days)
    due = base + datetime.timedelta(days=entry["response_days"])
    return due.date().isoformat()


async def save_draft(
    db: firestore.AsyncClient,
    journalist_id: str,
    cycle_id: str,
    story_title: str,
    draft: RecordsRequestDraft,
) -> str:
    """Persist a drafted records request. Returns the request_id."""
    request_id = str(uuid.uuid4())
    now = datetime.datetime.utcnow().isoformat()
    doc = {
        "request_id": request_id,
        "journalist_id": journalist_id,
        "cycle_id": cycle_id,
        "story_title": story_title,
        "status": "draft",
        "created_at": now,
        "updated_at": now,
        "due_date": _due_date(draft.jurisdiction, now),
        **draft.to_dict(),
    }
    await (
        db.collection("journalists")
        .document(journalist_id)
        .collection("records_requests")
        .document(request_id)
        .set(doc)
    )
    log.info("records_request_saved", journalist_id=journalist_id,
             request_id=request_id, title=draft.title)
    return request_id


async def update_status(
    db: firestore.AsyncClient,
    journalist_id: str,
    request_id: str,
    status: str,
    notes: str = "",
) -> None:
    """Update the status of an existing request."""
    if status not in VALID_STATUSES:
        raise ValueError(f"Invalid status '{status}'. Must be one of: {VALID_STATUSES}")
    await (
        db.collection("journalists")
        .document(journalist_id)
        .collection("records_requests")
        .document(request_id)
        .update({
            "status": status,
            "updated_at": datetime.datetime.utcnow().isoformat(),
            **({"notes": notes} if notes else {}),
        })
    )
    log.info("records_request_updated", journalist_id=journalist_id,
             request_id=request_id, status=status)


async def list_requests(
    db: firestore.AsyncClient,
    journalist_id: str,
    status_filter: str | None = None,
    limit: int = 50,
) -> list[dict]:
    """List records requests for a journalist, optionally filtered by status."""
    query = (
        db.collection("journalists")
        .document(journalist_id)
        .collection("records_requests")
        .order_by("created_at", direction=firestore.Query.DESCENDING)
        .limit(limit)
    )
    if status_filter:
        query = query.where("status", "==", status_filter)
    docs = await query.get()
    return [d.to_dict() for d in docs]


async def get_request(
    db: firestore.AsyncClient,
    journalist_id: str,
    request_id: str,
) -> dict | None:
    snap = await (
        db.collection("journalists")
        .document(journalist_id)
        .collection("records_requests")
        .document(request_id)
        .get()
    )
    return snap.to_dict() if snap.exists else None
