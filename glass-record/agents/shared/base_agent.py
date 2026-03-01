import datetime

import structlog
from google.cloud import firestore

log = structlog.get_logger()


async def log_action(
    db: firestore.AsyncClient,
    journalist_id: str,
    cycle_id: str,
    action: str,
    data: dict,
) -> None:
    """Write an immutable action log entry to Firestore."""
    entry = {
        "journalist_id": journalist_id,
        "cycle_id": cycle_id,
        "action": action,
        "data": data,
        "timestamp": datetime.datetime.utcnow().isoformat(),
    }
    await (
        db.collection("journalists")
        .document(journalist_id)
        .collection("activity_log")
        .add(entry)
    )
    log.info("action_logged", action=action, journalist_id=journalist_id, cycle_id=cycle_id)


async def get_journalist_doc(
    db: firestore.AsyncClient,
    journalist_id: str,
) -> dict:
    """Fetch the canonical journalist document from Firestore."""
    ref = db.collection("journalists").document(journalist_id)
    snap = await ref.get()
    if not snap.exists:
        raise ValueError(f"Journalist {journalist_id} not found in Firestore")
    return snap.to_dict()


async def register_journalist(
    db: firestore.AsyncClient,
    journalist_id: str,
    mandate: str,
    jurisdiction: str,
    tier: str = "free",
) -> None:
    """Write the immutable journalist record at spawn time."""
    ref = db.collection("journalists").document(journalist_id)
    snap = await ref.get()
    if snap.exists:
        return  # already registered — mandate is immutable, never overwrite
    await ref.set(
        {
            "journalist_id": journalist_id,
            "mandate": mandate,
            "jurisdiction": jurisdiction,
            "tier": tier,
            "created_at": datetime.datetime.utcnow().isoformat(),
        }
    )
    log.info("journalist_registered", journalist_id=journalist_id, jurisdiction=jurisdiction)
