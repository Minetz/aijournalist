"""
LangGraph node: draft_records_requests

Runs after update_case_state (end of a successful publish cycle).

Identifies and drafts public records requests that would strengthen the
next cycle's evidence base. Drafts are saved to Firestore with status='draft'
and emitted as an SSE event for dashboard display.

This node always succeeds (errors are logged and swallowed) so a failure
here never blocks the cycle.
"""
import datetime

import structlog
from google.cloud import firestore

from agents.editor.events import emit
from agents.shared.base_agent import log_action
from agents.shared.state import EditorState
from tools.records_requests.drafter import draft_records_requests
from tools.records_requests.tracker import save_draft

log = structlog.get_logger()

# Build evidence summary from researcher_results for the drafter prompt
_MAX_EVIDENCE_CHARS = 3_000


def _build_evidence_summary(researcher_results: list[dict]) -> str:
    lines: list[str] = []
    for r in researcher_results:
        sq = r.get("sub_question", "")
        eids = r.get("evidence_ids", [])
        if sq:
            lines.append(f"Sub-question: {sq} ({len(eids)} sources)")
    return "\n".join(lines)[:_MAX_EVIDENCE_CHARS]


async def draft_records_requests_node(state: EditorState) -> dict:
    """
    After case state is updated, draft records requests for the published story.
    Returns an empty dict — this node only has side effects (Firestore + SSE).
    """
    journalist_id = state["config"].journalist_id
    cycle_id = state["cycle_id"]
    jurisdiction = state["config"].jurisdiction
    story_title = state.get("selected_story", "")

    if not story_title:
        return {}

    today = datetime.date.today().isoformat()
    evidence_summary = _build_evidence_summary(state.get("researcher_results", []))

    try:
        drafts = await draft_records_requests(
            story_title=story_title,
            sub_questions=state.get("sub_questions", []),
            evidence_summary=evidence_summary,
            jurisdiction=jurisdiction,
            today=today,
            max_requests=2,
        )
    except Exception as exc:
        log.warning("records_request_drafting_failed", journalist_id=journalist_id,
                    error=str(exc))
        return {}

    if not drafts:
        return {}

    db = firestore.AsyncClient()
    request_ids: list[str] = []
    for draft in drafts:
        try:
            request_id = await save_draft(
                db=db,
                journalist_id=journalist_id,
                cycle_id=cycle_id,
                story_title=story_title,
                draft=draft,
            )
            request_ids.append(request_id)
        except Exception as exc:
            log.warning("records_request_save_failed", journalist_id=journalist_id,
                        title=draft.title, error=str(exc))

    if request_ids:
        await log_action(db, journalist_id, cycle_id, "records_requests_drafted", {
            "count": len(request_ids),
            "request_ids": request_ids,
            "jurisdiction": jurisdiction,
        })
        emit(journalist_id, "records_requests_drafted", {
            "count": len(request_ids),
            "cycle_id": cycle_id,
            "jurisdiction": jurisdiction,
        })
        log.info("records_requests_drafted", count=len(request_ids),
                 journalist_id=journalist_id, jurisdiction=jurisdiction)

    return {}
