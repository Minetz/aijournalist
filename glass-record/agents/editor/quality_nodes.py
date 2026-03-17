"""
LangGraph node: assess_evidence_quality

Runs after detect_contradictions, before synthesise_results.

For each sub-question, fetches its collected evidence and checks the maximum
credibility_score. Sub-questions where no evidence was collected OR where all
evidence scores below CREDIBILITY_THRESHOLD are reformulated by the LLM into
more targeted follow-up questions aimed at primary sources and official records.

At most MAX_FOLLOWUPS follow-up researchers are spawned to cap cost.
"""
import json

import structlog
from google.cloud import firestore
from langchain_core.messages import HumanMessage
from langgraph.types import Send

from agents.editor.events import emit
from agents.shared.base_agent import log_action
from agents.shared.gemini import get_llm
from agents.shared.state import EditorState, ResearcherState

log = structlog.get_logger()

CREDIBILITY_THRESHOLD = 0.5
MAX_FOLLOWUPS = 2

_FOLLOWUP_PROMPT = """
You are an investigative journalist editor reviewing research quality.

The following sub-questions returned evidence rated below {threshold} credibility
(unverified, single-source, or from unreliable outlets):

{low_quality_questions}

For each, write ONE more targeted follow-up question that would surface primary
sources, official records, or authoritative reporting. Be specific and actionable
for a search engine.

Return ONLY valid JSON — no markdown, no commentary:
{{"followups": ["targeted question 1", "targeted question 2"]}}
""".strip()


async def assess_evidence_quality(state: EditorState) -> dict:
    """
    Check credibility scores of all collected evidence per sub-question.
    Returns followup_sub_questions (may be empty) for routing by
    spawn_followup_researchers().
    """
    journalist_id = state["config"].journalist_id
    cycle_id = state["cycle_id"]
    db = firestore.AsyncClient()

    # Build map: sub_question → max credibility score seen (None if no evidence)
    sub_q_max_score: dict[str, float | None] = {}
    for r in state.get("researcher_results", []):
        sub_q = r.get("sub_question", "")
        max_score: float | None = None
        for eid in r.get("evidence_ids", []):
            snap = await (
                db.collection("journalists")
                .document(journalist_id)
                .collection("evidence_locker")
                .document(eid)
                .get()
            )
            if snap.exists:
                score = snap.to_dict().get("credibility_score", 0.5)
                max_score = score if max_score is None else max(max_score, score)
        sub_q_max_score[sub_q] = max_score

    # Identify sub-questions with no evidence or all evidence below threshold
    low_quality: list[str] = [
        q for q, score in sub_q_max_score.items()
        if score is None or score < CREDIBILITY_THRESHOLD
    ]
    low_quality = low_quality[:MAX_FOLLOWUPS]

    await log_action(db, journalist_id, cycle_id, "evidence_quality_assessed", {
        "sub_questions_checked": len(sub_q_max_score),
        "low_quality_count": len(low_quality),
    })

    if not low_quality:
        log.info("evidence_quality_ok", journalist_id=journalist_id,
                 checked=len(sub_q_max_score))
        return {"followup_sub_questions": []}

    emit(journalist_id, "evidence_quality_followup", {
        "low_quality_count": len(low_quality),
        "cycle_id": cycle_id,
    })

    # LLM reformulates low-quality questions into primary-source-targeted follow-ups
    llm = get_llm(temperature=0.1)
    prompt = _FOLLOWUP_PROMPT.format(
        threshold=CREDIBILITY_THRESHOLD,
        low_quality_questions="\n".join(f"- {q}" for q in low_quality),
    )
    try:
        response = await llm.ainvoke([HumanMessage(content=prompt)])
        raw = response.content
        if isinstance(raw, list):
            raw = "".join(p["text"] if isinstance(p, dict) else str(p) for p in raw)
        followups: list[str] = json.loads(raw).get("followups", [])
    except Exception:
        log.warning("followup_reformulation_failed", journalist_id=journalist_id)
        followups = [
            f"Find primary source documents and official records about: {q}"
            for q in low_quality
        ]

    followups = followups[:MAX_FOLLOWUPS]
    log.info("followups_generated", count=len(followups), journalist_id=journalist_id)
    return {"followup_sub_questions": followups}


def spawn_followup_researchers(state: EditorState) -> list[Send] | str:
    """
    Conditional edge after assess_evidence_quality.
    Spawns follow-up researcher workers for low-quality sub-questions,
    or routes directly to synthesise_results if none needed.
    """
    followups = state.get("followup_sub_questions", [])
    if not followups:
        return "synthesise_results"
    return [
        Send(
            "followup_researcher_worker",
            ResearcherState(
                config=state["config"],
                sub_question=q,
                search_results=[],
                scraped_content=[],
                ingested_docs=[],
                evidence_ids=[],
                messages=[],
            ),
        )
        for q in followups
    ]
