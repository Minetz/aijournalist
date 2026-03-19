"""
LangGraph node: detect_contradictions

Runs after researcher_worker fan-in, before synthesise_results.

Identifies conflicting claims across all collected evidence for the current
cycle and stores them in Firestore (journalists/{id}/contradictions/) for
full transparency. Contradictions are surfaced in the published article
under a dedicated "Disputed Claims" section.
"""
import datetime
import json
import uuid

import structlog
from google.cloud import firestore
from langchain_core.messages import HumanMessage

from agents.editor.events import emit
from agents.shared.base_agent import log_action
from agents.shared.gemini import get_llm_with_fallback
from agents.shared.state import EditorState

log = structlog.get_logger()

CONTRADICTION_DETECTION_PROMPT = """
You are an investigative journalist cross-checking evidence for internal contradictions.

Story: {story_title}

Evidence collected (format: evidence_id: claim1 | claim2 | ...):
{evidence_claims}

Identify factual contradictions — cases where two or more sources make directly
opposing claims about the same event, person, organisation, date, or figure.

Return ONLY valid JSON — no markdown, no commentary:
{{
  "contradictions": [
    {{
      "description": "Brief description of what the contradiction is about",
      "claim_a": "Specific claim from source A",
      "source_a_id": "evidence_id of source A",
      "claim_b": "Specific opposing claim from source B",
      "source_b_id": "evidence_id of source B",
      "severity": "high|medium|low",
      "resolution_suggestion": "How a journalist could investigate further to resolve this"
    }}
  ]
}}

Only include genuine factual contradictions, not differences in framing or emphasis.
If there are no contradictions, return {{"contradictions": []}}.
""".strip()


async def detect_contradictions(state: EditorState) -> dict:
    """
    After researchers complete, scan all collected evidence for contradicting claims.
    Stores contradictions in Firestore and returns them in state for article synthesis.
    """
    journalist_id = state["config"].journalist_id
    cycle_id = state["cycle_id"]
    db = firestore.AsyncClient()

    # Gather all evidence IDs from this cycle
    evidence_ids: list[str] = []
    for r in state.get("researcher_results", []):
        evidence_ids.extend(r.get("evidence_ids", []))

    if not evidence_ids:
        return {"contradictions": []}

    # Fetch evidence documents
    evidence_docs: list[dict] = []
    for eid in evidence_ids[:40]:
        snap = await (
            db.collection("journalists")
            .document(journalist_id)
            .collection("evidence_locker")
            .document(eid)
            .get()
        )
        if snap.exists:
            evidence_docs.append(snap.to_dict())

    # Need at least 2 sources to find a contradiction
    if len(evidence_docs) < 2:
        return {"contradictions": []}

    # Build compact claims map for the LLM
    claims_lines: list[str] = []
    for e in evidence_docs:
        eid = e.get("evidence_id", "")
        claims = e.get("claims", [])[:3]
        if claims:
            claims_lines.append(f"{eid}: {' | '.join(claims)}")

    emit(journalist_id, "detecting_contradictions", {
        "evidence_count": len(evidence_docs),
        "cycle_id": cycle_id,
    })

    llm = get_llm_with_fallback(temperature=0.0)
    prompt = CONTRADICTION_DETECTION_PROMPT.format(
        story_title=state.get("selected_story", ""),
        evidence_claims="\n".join(claims_lines[:50]),
    )

    try:
        response = await llm.ainvoke([HumanMessage(content=prompt)])
        raw = response.content
        if isinstance(raw, list):
            raw = "".join(p["text"] if isinstance(p, dict) else str(p) for p in raw)
        result = json.loads(raw)
        contradictions: list[dict] = result.get("contradictions", [])
    except Exception:
        log.warning("contradiction_detection_failed", journalist_id=journalist_id)
        return {"contradictions": []}

    # Persist contradictions to Firestore for public transparency
    if contradictions:
        now = datetime.datetime.utcnow().isoformat()
        batch = db.batch()
        for c in contradictions:
            c["cycle_id"] = cycle_id
            c["detected_at"] = now
            ref = (
                db.collection("journalists")
                .document(journalist_id)
                .collection("contradictions")
                .document(str(uuid.uuid4()))
            )
            batch.set(ref, c)
        await batch.commit()

    await log_action(db, journalist_id, cycle_id, "contradictions_detected", {
        "count": len(contradictions),
        "high_severity": sum(1 for c in contradictions if c.get("severity") == "high"),
    })
    emit(journalist_id, "contradictions_detected", {
        "count": len(contradictions),
        "cycle_id": cycle_id,
    })
    log.info("contradictions_detected", count=len(contradictions), journalist_id=journalist_id)
    return {"contradictions": contradictions}
