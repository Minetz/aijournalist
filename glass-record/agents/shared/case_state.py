"""
Cumulative case state — persists the journalist's accumulated findings across cycles.

Firestore path: journalists/{journalist_id}/case_state/current

Provides:
  load_case_context       — inject into prompts for story selection + mandate decomposition
  persist_case_state_update — called after publish to synthesise proven facts / open questions
"""
import datetime
import json

import structlog
from google.cloud import firestore
from langchain_core.messages import HumanMessage

log = structlog.get_logger()

CASE_STATE_UPDATE_PROMPT = """
You are managing the cumulative investigation state for an autonomous journalist.

Mandate: {mandate}
Story just published: {story_title}

New evidence collected this cycle:
{evidence_summary}

Existing case state:
{existing_state}

Based on all of the above, update the investigation's cumulative state.
Return ONLY valid JSON — no markdown, no commentary:
{{
  "proven_facts": [
    "Specific fact established with high confidence across multiple sources",
    "..."
  ],
  "open_questions": [
    "Question that still needs investigation or lacks sufficient evidence",
    "..."
  ],
  "key_entities": [
    "Name of key person, organization, or statute central to the investigation",
    "..."
  ],
  "investigation_threads": [
    "Specific angle or sub-topic worth pursuing in future cycles",
    "..."
  ]
}}

Rules:
- proven_facts: max 20 items, only include claims confirmed by multiple high-credibility sources
- open_questions: max 10 items, specific enough to guide future research sub-questions
- key_entities: max 15 items
- investigation_threads: max 5 items, actionable angles not yet fully explored
- Merge and deduplicate with the existing state — carry forward what remains relevant
- Prioritise recency: if a prior fact is contradicted by new evidence, update or remove it
""".strip()


async def load_case_context(db: firestore.AsyncClient, journalist_id: str) -> str:
    """
    Load accumulated case state and return a formatted string for prompt injection.
    Returns empty string if no case state exists yet (first cycle).
    """
    try:
        snap = await (
            db.collection("journalists")
            .document(journalist_id)
            .collection("case_state")
            .document("current")
            .get()
        )
        if not snap.exists:
            return ""

        data = snap.to_dict() or {}
        lines = ["## Prior Investigation Context\n"]

        if data.get("proven_facts"):
            lines.append("### Established Facts (do not re-investigate these):")
            for f in data["proven_facts"][:15]:
                lines.append(f"- {f}")

        if data.get("open_questions"):
            lines.append("\n### Open Questions (prioritise stories that address these):")
            for q in data["open_questions"][:8]:
                lines.append(f"- {q}")

        if data.get("key_entities"):
            lines.append("\n### Key Entities Under Investigation:")
            lines.append(", ".join(data["key_entities"][:12]))

        if data.get("investigation_threads"):
            lines.append("\n### Recommended Next Investigation Threads:")
            for t in data["investigation_threads"][:5]:
                lines.append(f"- {t}")

        return "\n".join(lines) + "\n"
    except Exception:
        log.warning("case_context_load_failed", journalist_id=journalist_id)
        return ""


async def persist_case_state_update(
    db: firestore.AsyncClient,
    journalist_id: str,
    cycle_id: str,
    llm,
    mandate: str,
    story_title: str,
    evidence_docs: list[dict],
) -> None:
    """
    Run Gemini to synthesise the updated case state and write it to Firestore.
    Called after a story is successfully published.
    """
    # Load existing state to merge with
    ref = (
        db.collection("journalists")
        .document(journalist_id)
        .collection("case_state")
        .document("current")
    )
    snap = await ref.get()
    existing_state = json.dumps(snap.to_dict() or {}, ensure_ascii=False, indent=2)

    # Build evidence summary (top 20 by credibility)
    sorted_docs = sorted(
        evidence_docs,
        key=lambda x: x.get("credibility_score", 0),
        reverse=True,
    )
    evidence_lines = []
    for e in sorted_docs[:20]:
        claims = "; ".join(e.get("claims", [])[:3])
        title = e.get("source_title", e.get("source_url", ""))
        score = e.get("credibility_score", 0)
        evidence_lines.append(f"- [{score:.2f}] {title}: {claims}")
    evidence_summary = "\n".join(evidence_lines) or "No evidence collected."

    prompt = CASE_STATE_UPDATE_PROMPT.format(
        mandate=mandate,
        story_title=story_title,
        evidence_summary=evidence_summary,
        existing_state=existing_state,
    )

    try:
        response = await llm.ainvoke([HumanMessage(content=prompt)])
        raw = response.content
        if isinstance(raw, list):
            raw = "".join(p["text"] if isinstance(p, dict) else str(p) for p in raw)
        new_state: dict = json.loads(raw)
    except Exception:
        log.warning("case_state_update_failed", journalist_id=journalist_id)
        return

    new_state["updated_at"] = datetime.datetime.utcnow().isoformat()
    new_state["last_cycle_id"] = cycle_id
    new_state["last_story"] = story_title

    await ref.set(new_state)
    log.info(
        "case_state_updated",
        journalist_id=journalist_id,
        proven_facts=len(new_state.get("proven_facts", [])),
        open_questions=len(new_state.get("open_questions", [])),
    )
