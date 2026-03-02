import datetime

import structlog
from google.cloud import firestore
from langchain_core.messages import HumanMessage
from pydantic import BaseModel

from agents.shared.base_agent import get_journalist_doc, log_action
from agents.shared.gemini import get_llm
from agents.verification.prompts import VERIFICATION_PROMPT

log = structlog.get_logger()


class VerificationResult(BaseModel):
    corroborated: bool
    confidence: float
    supporting_evidence_ids: list[str]
    contradicting_evidence_ids: list[str]
    response: str
    editorial_note: str = "NONE — verification agents do not make editorial decisions."


async def _fetch_evidence_summary(
    db: firestore.AsyncClient,
    journalist_id: str,
    max_items: int = 20,
) -> str:
    ref = (
        db.collection("journalists")
        .document(journalist_id)
        .collection("evidence_locker")
        .order_by("credibility_score", direction=firestore.Query.DESCENDING)
        .limit(max_items)
    )
    docs = await ref.get()
    lines = []
    for doc in docs:
        e = doc.to_dict()
        claims = "; ".join(e.get("claims", []))
        lines.append(
            f"[{e['evidence_id']}] {e['source_title']} "
            f"(credibility {e.get('credibility_score', 0):.2f})\n"
            f"  Claims: {claims}"
        )
    return "\n\n".join(lines) if lines else "No evidence in locker."


async def verify_tip(
    journalist_id: str,
    tip_id: str,
    tip_content: str,
) -> VerificationResult:
    db = firestore.AsyncClient()
    journalist_doc = await get_journalist_doc(db, journalist_id)
    evidence_summary = await _fetch_evidence_summary(db, journalist_id)

    llm = get_llm(temperature=0.0).with_structured_output(VerificationResult)
    prompt = VERIFICATION_PROMPT.format(
        mandate=journalist_doc["mandate"],
        tip_content=tip_content,
        evidence_summary=evidence_summary,
    )
    result: VerificationResult = await llm.ainvoke([HumanMessage(content=prompt)])

    # Write verification back to the tip document
    verification_doc = {
        **result.model_dump(),
        "verified_at": datetime.datetime.utcnow().isoformat(),
    }
    await (
        db.collection("journalists")
        .document(journalist_id)
        .collection("tips")
        .document(tip_id)
        .update({"verification": verification_doc})
    )

    await log_action(db, journalist_id, tip_id, "tip_verified", {
        "corroborated": result.corroborated,
        "confidence": result.confidence,
    })
    log.info("tip_verified", journalist_id=journalist_id, tip_id=tip_id,
             corroborated=result.corroborated)
    return result
