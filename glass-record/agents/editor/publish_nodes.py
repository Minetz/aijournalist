import datetime
import json
import uuid

import structlog
from google.cloud import firestore
from langchain_core.messages import HumanMessage
from pydantic import BaseModel

from agents.editor.events import emit
from agents.editor.publish_prompts import STORY_SYNTHESIS_PROMPT, TIMELINE_EXTRACTION_PROMPT
from agents.legal_tree.nodes import build_legal_tree
from agents.shared.base_agent import get_journalist_doc, log_action
from agents.shared.gemini import get_llm
from agents.shared.state import EditorState

log = structlog.get_logger()


async def _set_cycle_status(
    db: firestore.AsyncClient,
    journalist_id: str,
    status: str,
    cycle_id: str = "",
    extra: dict | None = None,
) -> None:
    doc = {
        "status": status,
        "cycle_id": cycle_id,
        "updated_at": datetime.datetime.utcnow().isoformat(),
        **(extra or {}),
    }
    await db.collection("journalists").document(journalist_id).set(
        {"cycle_status": doc}, merge=True
    )


class ArticleDraft(BaseModel):
    headline: str
    standfirst: str
    body_html: str
    tags: list[str]


async def _fetch_evidence_summary(
    db: firestore.AsyncClient,
    journalist_id: str,
    max_items: int = 15,
) -> tuple[str, list[dict]]:
    """Returns (formatted summary string, raw evidence dicts)."""
    evidence_ref = (
        db.collection("journalists")
        .document(journalist_id)
        .collection("evidence_locker")
        .order_by("credibility_score", direction=firestore.Query.DESCENDING)
        .limit(max_items)
    )
    docs = await evidence_ref.get()
    lines: list[str] = []
    evidence_dicts: list[dict] = []
    for doc in docs:
        e = doc.to_dict()
        evidence_dicts.append(e)
        claims = "; ".join(e.get("claims", []))
        lines.append(
            f"[{e['evidence_id']}] {e['source_title']} "
            f"(credibility {e.get('credibility_score', 0):.2f})\n"
            f"  Source: {e['source_url']}\n"
            f"  Claims: {claims}"
        )
    summary = "\n\n".join(lines) if lines else "No evidence collected."
    return summary, evidence_dicts


async def _extract_and_store_timeline(
    db: firestore.AsyncClient,
    journalist_id: str,
    story_id: str,
    cycle_id: str,
    evidence_docs: list[dict],
) -> None:
    """
    Extract dateable events from evidence claims via LLM and write them to
    /journalists/{id}/timeline_events/{event_id} for the timeline API.
    """
    if not evidence_docs:
        return

    # Build compact input: evidence_id → claims
    claims_lines: list[str] = []
    url_map: dict[str, str] = {}
    for e in evidence_docs:
        eid = e.get("evidence_id", "")
        url = e.get("source_url", "")
        claims = e.get("claims", [])
        url_map[eid] = url
        if claims:
            claims_lines.append(f'{eid} ({url}): {" | ".join(claims[:4])}')

    if not claims_lines:
        return

    try:
        llm = get_llm(temperature=0.0)
        prompt = TIMELINE_EXTRACTION_PROMPT.format(
            evidence_claims="\n".join(claims_lines[:40])
        )
        response = await llm.ainvoke([HumanMessage(content=prompt)])
        raw = response.content
        if isinstance(raw, list):
            raw = "".join(p["text"] if isinstance(p, dict) else str(p) for p in raw)
        data = json.loads(raw)
    except Exception:
        log.warning("timeline_extraction_failed", journalist_id=journalist_id)
        return

    batch = db.batch()
    for event in data.get("events", []):
        event_id = str(uuid.uuid4())
        doc_ref = (
            db.collection("journalists")
            .document(journalist_id)
            .collection("timeline_events")
            .document(event_id)
        )
        batch.set(doc_ref, {
            "event_id": event_id,
            "journalist_id": journalist_id,
            "story_id": story_id,
            "cycle_id": cycle_id,
            "event_date": event.get("event_date", ""),
            "description": event.get("description", "")[:250],
            "entities": event.get("entities", []),
            "evidence_id": event.get("evidence_id", ""),
            "source_url": event.get("source_url", ""),
            "created_at": datetime.datetime.utcnow().isoformat(),
        })
    await batch.commit()
    log.info("timeline_events_stored",
             journalist_id=journalist_id, count=len(data.get("events", [])))


async def synthesise_and_publish(state: EditorState) -> dict:
    """
    1. Build the legal tree from gathered evidence.
    2. Synthesise a news article using Gemini.
    3. Store the article (including full HTML) in Firestore.
    4. The dashboard renders the article at /{journalist_id}/stories/{story_id}.

    Only runs when compliance_passed is True.
    """
    if not state.get("compliance_passed", False):
        log.warning("publish_skipped_compliance_failed",
                    journalist_id=state["config"].journalist_id)
        return {}

    journalist_id = state["config"].journalist_id
    cycle_id = state["cycle_id"]
    story_title = state["selected_story"]

    db = firestore.AsyncClient()
    journalist_doc = await get_journalist_doc(db, journalist_id)

    emit(journalist_id, "building_legal_tree", {"cycle_id": cycle_id})
    await _set_cycle_status(db, journalist_id, "building_legal_tree", cycle_id)

    # Build legal tree
    tree = await build_legal_tree(journalist_id, cycle_id, story_title)
    emit(journalist_id, "legal_tree_ready", {
        "tree_id": tree.tree_id,
        "strength": tree.overall_strength,
        "root_nodes": len(tree.root_nodes),
    })
    legal_summary_lines = [f"Summary: {tree.summary}"]
    for node in tree.root_nodes:
        legal_summary_lines.append(
            f"- [{node.node_type}] {node.title} (strength: {node.strength})"
        )
        for child in node.children:
            legal_summary_lines.append(
                f"    - [{child.node_type}] {child.title} (strength: {child.strength})"
            )
    legal_summary = "\n".join(legal_summary_lines)

    evidence_summary, evidence_docs = await _fetch_evidence_summary(db, journalist_id)

    # Build contradictions section for the synthesis prompt
    contradictions = state.get("contradictions") or []
    if contradictions:
        c_lines = ["CONTRADICTIONS DETECTED (must be addressed in article):"]
        for c in contradictions:
            severity = c.get("severity", "unknown").upper()
            c_lines.append(
                f"- [{severity}] {c.get('description', '')}: "
                f'"{c.get("claim_a", "")}" vs "{c.get("claim_b", "")}" — '
                f"Suggested resolution: {c.get('resolution_suggestion', '')}"
            )
        contradictions_section = "\n".join(c_lines)
    else:
        contradictions_section = ""

    # Synthesise article
    llm = get_llm(temperature=0.3).with_structured_output(ArticleDraft)
    prompt = STORY_SYNTHESIS_PROMPT.format(
        story_title=story_title,
        mandate=journalist_doc["mandate"],
        jurisdiction=journalist_doc["jurisdiction"],
        evidence_summary=evidence_summary,
        legal_strength=tree.overall_strength,
        legal_summary=legal_summary,
        contradictions_section=contradictions_section,
    )
    draft: ArticleDraft = await llm.ainvoke([HumanMessage(content=prompt)])

    story_id = str(uuid.uuid4())

    # Build transparency footer (links are relative to the dashboard)
    footer_html = _build_footer(journalist_id, cycle_id, tree.tree_id)
    full_html = draft.body_html + footer_html

    # Store story (including full article HTML) in Firestore
    story_doc = {
        "story_id": story_id,
        "journalist_id": journalist_id,
        "cycle_id": cycle_id,
        "title": draft.headline,
        "standfirst": draft.standfirst,
        "body_html": full_html,
        "legal_tree_id": tree.tree_id,
        "published_at": datetime.datetime.utcnow().isoformat(),
        "tags": draft.tags + ["glass-record", journalist_doc["jurisdiction"].lower()],
    }
    await (
        db.collection("journalists")
        .document(journalist_id)
        .collection("stories")
        .document(story_id)
        .set(story_doc)
    )

    story_path = f"/{journalist_id}/stories/{story_id}"

    # Extract and persist timeline events from this cycle's evidence
    await _extract_and_store_timeline(db, journalist_id, story_id, cycle_id, evidence_docs)

    await log_action(db, journalist_id, cycle_id, "story_published", {
        "story_id": story_id,
        "story_path": story_path,
        "headline": draft.headline,
    })
    emit(journalist_id, "story_published", {
        "headline": draft.headline,
        "story_path": story_path,
        "cycle_id": cycle_id,
    })
    await _set_cycle_status(db, journalist_id, "idle", cycle_id,
                            {"last_published": draft.headline, "last_story_path": story_path})

    log.info("story_published", journalist_id=journalist_id,
             story_id=story_id, path=story_path)

    return {"messages": [HumanMessage(content=f"Published: {draft.headline} — {story_path}")]}


def _build_footer(journalist_id: str, cycle_id: str, tree_id: str) -> str:
    return f"""
<hr>
<section class="glass-record-footer">
  <h4>About this investigation</h4>
  <p>
    This article was produced autonomously by The Glass Record.
    Every source, evidence item, compliance decision, and reasoning step is
    publicly logged.
  </p>
  <ul>
    <li><a href="/{journalist_id}?tab=activity">Activity log</a></li>
    <li><a href="/{journalist_id}?tab=evidence">Evidence locker</a></li>
    <li><a href="/{journalist_id}?tab=compliance">Compliance log</a></li>
    <li><a href="/{journalist_id}?tab=graph">Knowledge graph</a></li>
    <li><a href="/{journalist_id}?tab=timeline">Timeline of events</a></li>
  </ul>
  <p><small>Cycle ID: {cycle_id}</small></p>
</section>
""".strip()
