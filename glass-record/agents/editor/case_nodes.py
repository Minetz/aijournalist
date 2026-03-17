"""
LangGraph node: update_case_state

Runs after publish. Synthesises accumulated investigation knowledge from this
cycle's evidence and prior case state in Firestore, then writes the updated
state back to journalists/{id}/case_state/current.

This is the core of cumulative case building — each cycle builds on the last,
tracking proven facts, open questions, and recommended investigation threads.
"""
import structlog
from google.cloud import firestore

from agents.editor.events import emit
from agents.shared.base_agent import get_journalist_doc, log_action
from agents.shared.case_state import persist_case_state_update
from agents.shared.gemini import get_llm
from agents.shared.state import EditorState

log = structlog.get_logger()


async def update_case_state(state: EditorState) -> dict:
    """
    Post-publish node: synthesise proven facts, open questions, and investigation
    threads from this cycle's evidence and write them to Firestore case_state/current.

    Skipped silently if compliance failed (no story was published this cycle).
    """
    if not state.get("compliance_passed", False):
        return {}

    journalist_id = state["config"].journalist_id
    cycle_id = state["cycle_id"]
    db = firestore.AsyncClient()

    journalist_doc = await get_journalist_doc(db, journalist_id)
    mandate = journalist_doc["mandate"]

    # Collect evidence IDs from all researcher results this cycle
    evidence_ids: list[str] = []
    for r in state.get("researcher_results", []):
        evidence_ids.extend(r.get("evidence_ids", []))

    # Fetch the actual evidence documents
    evidence_docs: list[dict] = []
    for eid in evidence_ids[:30]:
        snap = await (
            db.collection("journalists")
            .document(journalist_id)
            .collection("evidence_locker")
            .document(eid)
            .get()
        )
        if snap.exists:
            evidence_docs.append(snap.to_dict())

    emit(journalist_id, "updating_case_state", {"cycle_id": cycle_id})

    llm = get_llm(temperature=0.1)
    await persist_case_state_update(
        db=db,
        journalist_id=journalist_id,
        cycle_id=cycle_id,
        llm=llm,
        mandate=mandate,
        story_title=state["selected_story"],
        evidence_docs=evidence_docs,
    )

    await log_action(db, journalist_id, cycle_id, "case_state_updated", {
        "evidence_count": len(evidence_docs),
        "story": state["selected_story"],
    })
    emit(journalist_id, "case_state_updated", {
        "cycle_id": cycle_id,
        "evidence_used": len(evidence_docs),
    })
    log.info("case_state_updated", journalist_id=journalist_id, evidence=len(evidence_docs))
    return {}
