import datetime
import json
import uuid

import structlog
from google.cloud import firestore
from langchain_core.messages import HumanMessage
from pydantic import BaseModel

from agents.editor.events import emit
from agents.editor.publish_prompts import STORY_SYNTHESIS_PROMPT
from agents.legal_tree.nodes import build_legal_tree
from agents.shared.base_agent import get_journalist_doc, log_action
from agents.shared.gemini import get_llm
from agents.shared.state import EditorState
from cms.ghost import GhostClient

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
    await db.collection("journalists").document(journalist_id).update(
        {"cycle_status": doc}
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
) -> str:
    evidence_ref = (
        db.collection("journalists")
        .document(journalist_id)
        .collection("evidence_locker")
        .order_by("credibility_score", direction=firestore.Query.DESCENDING)
        .limit(max_items)
    )
    docs = await evidence_ref.get()
    lines: list[str] = []
    for doc in docs:
        e = doc.to_dict()
        claims = "; ".join(e.get("claims", []))
        lines.append(
            f"[{e['evidence_id']}] {e['source_title']} "
            f"(credibility {e.get('credibility_score', 0):.2f})\n"
            f"  Source: {e['source_url']}\n"
            f"  Claims: {claims}"
        )
    return "\n\n".join(lines) if lines else "No evidence collected."


async def synthesise_and_publish(state: EditorState) -> dict:
    """
    1. Build the legal tree from gathered evidence.
    2. Synthesise a news article using Gemini.
    3. Publish to Ghost CMS.
    4. Log the post ID and cost metadata to Firestore.

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

    evidence_summary = await _fetch_evidence_summary(db, journalist_id)

    # Synthesise article
    llm = get_llm(temperature=0.3).with_structured_output(ArticleDraft)
    prompt = STORY_SYNTHESIS_PROMPT.format(
        story_title=story_title,
        mandate=journalist_doc["mandate"],
        jurisdiction=journalist_doc["jurisdiction"],
        evidence_summary=evidence_summary,
        legal_strength=tree.overall_strength,
        legal_summary=legal_summary,
    )
    draft: ArticleDraft = await llm.ainvoke([HumanMessage(content=prompt)])

    # Append transparency footer
    footer_html = _build_footer(journalist_id, cycle_id, tree.tree_id)
    full_html = draft.body_html + footer_html

    # Publish to Ghost
    ghost = GhostClient()
    post = await ghost.create_post(
        title=draft.headline,
        html=full_html,
        status="published",
        tags=draft.tags + ["glass-record", journalist_doc["jurisdiction"].lower()],
    )
    ghost_post_id = post["id"]
    ghost_url = post.get("url", "")

    # Record story in Firestore
    story_id = str(uuid.uuid4())
    story_doc = {
        "story_id": story_id,
        "journalist_id": journalist_id,
        "cycle_id": cycle_id,
        "title": draft.headline,
        "standfirst": draft.standfirst,
        "ghost_post_id": ghost_post_id,
        "ghost_url": ghost_url,
        "legal_tree_id": tree.tree_id,
        "published_at": datetime.datetime.utcnow().isoformat(),
        "tags": draft.tags,
    }
    await (
        db.collection("journalists")
        .document(journalist_id)
        .collection("stories")
        .document(story_id)
        .set(story_doc)
    )

    await log_action(db, journalist_id, cycle_id, "story_published", {
        "ghost_post_id": ghost_post_id,
        "ghost_url": ghost_url,
        "headline": draft.headline,
    })
    emit(journalist_id, "story_published", {
        "headline": draft.headline,
        "ghost_url": ghost_url,
        "cycle_id": cycle_id,
    })
    await _set_cycle_status(db, journalist_id, "idle", cycle_id,
                            {"last_published": draft.headline, "last_url": ghost_url})

    log.info("story_published", journalist_id=journalist_id,
             ghost_post_id=ghost_post_id, url=ghost_url)

    return {"messages": [HumanMessage(content=f"Published: {draft.headline} — {ghost_url}")]}


def _build_footer(journalist_id: str, cycle_id: str, tree_id: str) -> str:
    return f"""
<hr>
<section class="glass-record-footer">
  <h4>About this investigation</h4>
  <p>
    This article was produced autonomously by
    <a href="https://glassrecord.org/{journalist_id}">The Glass Record</a>.
    Every source, evidence item, compliance decision, and reasoning step is
    publicly logged.
  </p>
  <ul>
    <li><a href="https://glassrecord.org/{journalist_id}/activity">Activity log</a></li>
    <li><a href="https://glassrecord.org/{journalist_id}/evidence">Evidence locker</a></li>
    <li><a href="https://glassrecord.org/{journalist_id}/compliance">Compliance log</a></li>
    <li><a href="https://glassrecord.org/{journalist_id}/legal-tree/{tree_id}">Legal case tree</a></li>
  </ul>
  <p><small>Cycle ID: {cycle_id}</small></p>
</section>
""".strip()
