"""
LangGraph node: check_and_revise_prior_stories

Runs after publish, before update_case_state.

Compares the current cycle's evidence and contradictions against recently
published stories. When the LLM identifies a genuine conflict or material
extension, a correction or update article is drafted and stored in Firestore
linked to the original via related_story_id.

Constraints:
  - Only looks back LOOKBACK_DAYS days of stories
  - Skips the story just published this cycle (same cycle_id)
  - Never revises correction/update articles (no cascading revisions)
  - At most MAX_REVISIONS articles generated per cycle
  - Failures are swallowed — this node never blocks the cycle
"""
import datetime
import json
import uuid

import structlog
from google.cloud import firestore
from langchain_core.messages import HumanMessage

from agents.editor.events import emit
from agents.shared.base_agent import log_action
from agents.shared.gemini import get_llm
from agents.shared.state import EditorState

log = structlog.get_logger()

LOOKBACK_DAYS = 30
MAX_REVISIONS = 2

_REVISION_CHECK_PROMPT = """
You are an editorial AI for an investigative journalism platform.

A new investigation cycle has just concluded with the following evidence and findings:

NEW EVIDENCE SUMMARY:
{evidence_summary}

NEW CONTRADICTIONS DETECTED (if any):
{contradictions_summary}

PRIOR PUBLISHED STORIES (last {lookback_days} days):
{prior_stories}

For each prior story, decide:
1. Does the new evidence CONTRADICT a major factual claim in that story? → type: "correction"
2. Does the new evidence MATERIALLY EXTEND that story with significant new facts? → type: "update"
3. No meaningful relationship? → skip it

Be conservative: only flag genuine, substantive conflicts or extensions.
Prefer returning an empty list over flagging weak matches.

Return ONLY valid JSON — no markdown, no commentary:
{{
  "revisions": [
    {{
      "story_id": "the prior story's story_id",
      "story_title": "the prior story's headline",
      "revision_type": "correction",
      "reason": "One sentence explaining what changed or was contradicted",
      "new_headline": "Headline for the correction/update article",
      "new_standfirst": "One sentence standfirst for the correction/update article",
      "new_body_html": "<p>Full correction/update article as valid HTML paragraphs...</p>"
    }}
  ]
}}

Limit to at most {max_revisions} revisions. If no revisions are warranted, return {{"revisions": []}}.
""".strip()


def _build_evidence_summary(researcher_results: list[dict]) -> str:
    lines = [
        f"- {r['sub_question']} ({len(r.get('evidence_ids', []))} sources)"
        for r in researcher_results
        if r.get("sub_question")
    ]
    return "\n".join(lines) or "No evidence summary available."


def _build_contradictions_summary(contradictions: list[dict]) -> str:
    if not contradictions:
        return "None detected."
    lines = [
        f"- [{c.get('severity', '?').upper()}] {c.get('description', '')}: "
        f'"{c.get("claim_a", "")}" vs "{c.get("claim_b", "")}"'
        for c in contradictions[:5]
    ]
    return "\n".join(lines)


async def check_and_revise_prior_stories(state: EditorState) -> dict:
    """
    Post-publish node: detect and draft corrections/updates to recent stories
    when new cycle evidence warrants them.
    """
    if not state.get("compliance_passed", False):
        return {}

    journalist_id = state["config"].journalist_id
    cycle_id = state["cycle_id"]
    db = firestore.AsyncClient()

    # Load prior stories within the lookback window
    cutoff = (
        datetime.datetime.utcnow() - datetime.timedelta(days=LOOKBACK_DAYS)
    ).isoformat()
    try:
        prior_snaps = await (
            db.collection("journalists")
            .document(journalist_id)
            .collection("stories")
            .where("published_at", ">=", cutoff)
            .order_by("published_at", direction=firestore.Query.DESCENDING)
            .limit(5)
            .get()
        )
        prior_stories = [s.to_dict() for s in prior_snaps]
    except Exception as exc:
        log.warning("revision_story_fetch_failed", journalist_id=journalist_id, error=str(exc))
        return {}

    # Exclude: the story just published this cycle; and correction/update articles
    prior_stories = [
        s for s in prior_stories
        if s.get("cycle_id") != cycle_id and not s.get("article_type")
    ]
    if not prior_stories:
        return {}

    evidence_summary = _build_evidence_summary(state.get("researcher_results", []))
    contradictions_summary = _build_contradictions_summary(
        state.get("contradictions") or []
    )
    prior_stories_text = "\n\n".join(
        f"story_id: {s['story_id']}\n"
        f"headline: {s.get('title', '')}\n"
        f"standfirst: {s.get('standfirst', '')}\n"
        f"published: {s.get('published_at', '')[:10]}"
        for s in prior_stories
    )

    llm = get_llm(temperature=0.2)
    prompt = _REVISION_CHECK_PROMPT.format(
        evidence_summary=evidence_summary,
        contradictions_summary=contradictions_summary,
        prior_stories=prior_stories_text,
        lookback_days=LOOKBACK_DAYS,
        max_revisions=MAX_REVISIONS,
    )

    try:
        response = await llm.ainvoke([HumanMessage(content=prompt)])
        raw = response.content
        if isinstance(raw, list):
            raw = "".join(p["text"] if isinstance(p, dict) else str(p) for p in raw)
        revisions: list[dict] = json.loads(raw).get("revisions", [])
    except Exception as exc:
        log.warning("revision_check_failed", journalist_id=journalist_id, error=str(exc))
        return {}

    revisions = revisions[:MAX_REVISIONS]
    if not revisions:
        log.info("no_revisions_needed", journalist_id=journalist_id,
                 prior_stories_checked=len(prior_stories))
        return {}

    now = datetime.datetime.utcnow().isoformat()
    revision_ids: list[str] = []

    for rev in revisions:
        related_story_id = rev.get("story_id", "")
        revision_type = rev.get("revision_type", "update")
        if revision_type not in ("correction", "update"):
            revision_type = "update"

        new_story_id = str(uuid.uuid4())
        footer_note = (
            f'<p><small>This is a <strong>{revision_type}</strong> to '
            f'<a href="/{journalist_id}/stories/{related_story_id}">a prior story</a>. '
            f"Reason: {rev.get('reason', '')} — Cycle: {cycle_id}</small></p>"
        )

        story_doc = {
            "story_id": new_story_id,
            "journalist_id": journalist_id,
            "cycle_id": cycle_id,
            "title": rev.get("new_headline", ""),
            "standfirst": rev.get("new_standfirst", ""),
            "body_html": rev.get("new_body_html", "") + footer_note,
            "published_at": now,
            "tags": [revision_type, "glass-record"],
            "article_type": revision_type,
            "related_story_id": related_story_id,
            "revision_reason": rev.get("reason", ""),
        }

        try:
            await (
                db.collection("journalists")
                .document(journalist_id)
                .collection("stories")
                .document(new_story_id)
                .set(story_doc)
            )
            revision_ids.append(new_story_id)
            emit(journalist_id, "story_revised", {
                "revision_type": revision_type,
                "new_story_id": new_story_id,
                "related_story_id": related_story_id,
                "cycle_id": cycle_id,
            })
            log.info("story_revision_published", journalist_id=journalist_id,
                     revision_type=revision_type, story_id=new_story_id,
                     related=related_story_id)
        except Exception as exc:
            log.warning("revision_save_failed", journalist_id=journalist_id,
                        error=str(exc))

    if revision_ids:
        try:
            await log_action(db, journalist_id, cycle_id, "stories_revised", {
                "count": len(revision_ids),
                "revision_ids": revision_ids,
            })
        except Exception:
            pass

    return {}
