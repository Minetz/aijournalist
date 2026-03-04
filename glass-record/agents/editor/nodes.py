import datetime
import json
import os

import structlog
from google.cloud import firestore, pubsub_v1
from langchain_core.messages import HumanMessage
from langgraph.types import Send
from pydantic import BaseModel

from agents.editor.events import emit
from agents.shared.base_agent import get_journalist_doc, log_action
from agents.shared.gemini import get_llm
from agents.shared.state import EditorState, ResearcherState
from agents.editor.prompts import DECOMPOSE_MANDATE_PROMPT, STORY_SELECTION_PROMPT

log = structlog.get_logger()


async def _set_cycle_status(
    db: firestore.AsyncClient,
    journalist_id: str,
    status: str,
    cycle_id: str = "",
    extra: dict | None = None,
) -> None:
    """Write the journalist's current cycle status to Firestore for dashboard polling.
    Uses set+merge so this is safe on brand-new journalist documents."""
    doc = {
        "status": status,
        "cycle_id": cycle_id,
        "updated_at": datetime.datetime.utcnow().isoformat(),
        **(extra or {}),
    }
    await (
        db.collection("journalists")
        .document(journalist_id)
        .set({"cycle_status": doc}, merge=True)
    )


class StorySelection(BaseModel):
    story_title: str
    story_summary: str
    urgency_score: int
    mandate_alignment_reason: str


async def select_story(state: EditorState) -> dict:
    journalist_id = state["config"].journalist_id
    cycle_id = state["cycle_id"]
    db = firestore.AsyncClient()

    emit(journalist_id, "cycle_start", {"cycle_id": cycle_id})
    await _set_cycle_status(db, journalist_id, "selecting_story", cycle_id)

    # Resume path: story was pre-loaded from a prior cycle's activity log
    if state.get("selected_story"):
        emit(journalist_id, "story_selected", {
            "title": state["selected_story"],
            "urgency_score": 0,
            "cycle_id": cycle_id,
            "resumed": True,
        })
        await _set_cycle_status(db, journalist_id, "story_selected", cycle_id,
                                {"story_title": state["selected_story"]})
        log.info("story_selection_skipped_resume", title=state["selected_story"])
        return {}

    # Always load mandate from Firestore — never trust the request payload
    journalist_doc = await get_journalist_doc(db, journalist_id)
    mandate = journalist_doc["mandate"]
    jurisdiction = journalist_doc["jurisdiction"]

    # Fetch previous story titles to avoid repetition
    stories_ref = (
        db.collection("journalists")
        .document(journalist_id)
        .collection("stories")
        .order_by("published_at", direction=firestore.Query.DESCENDING)
        .limit(10)
    )
    previous_stories_snap = await stories_ref.get()
    previous_stories = [s.to_dict().get("title", "") for s in previous_stories_snap]

    emit(journalist_id, "llm_call", {"step": "select_story", "model": "gemini"})

    llm = get_llm(temperature=0.3).with_structured_output(StorySelection)
    prompt = STORY_SELECTION_PROMPT.format(
        mandate=mandate,
        jurisdiction=jurisdiction,
        today=datetime.date.today().isoformat(),
        previous_stories=previous_stories or "none",
    )
    story: StorySelection = await llm.ainvoke([HumanMessage(content=prompt)])

    await log_action(db, journalist_id, cycle_id, "story_selected", story.model_dump())
    emit(journalist_id, "story_selected", {
        "title": story.story_title,
        "urgency_score": story.urgency_score,
        "cycle_id": cycle_id,
    })
    await _set_cycle_status(db, journalist_id, "story_selected", cycle_id,
                            {"story_title": story.story_title})

    log.info("story_selected", title=story.story_title, urgency=story.urgency_score)
    return {
        "selected_story": story.story_title,
        "messages": [HumanMessage(content=f"Selected story: {story.story_title}")],
    }


async def decompose_mandate(state: EditorState) -> dict:
    journalist_id = state["config"].journalist_id
    cycle_id = state["cycle_id"]
    db = firestore.AsyncClient()

    # Resume path: sub_questions were pre-loaded from a prior cycle's activity log
    if state.get("sub_questions"):
        emit(journalist_id, "mandate_decomposed", {
            "sub_questions": state["sub_questions"],
            "count": len(state["sub_questions"]),
            "resumed": True,
        })
        await _set_cycle_status(db, journalist_id, "researching", cycle_id,
                                {"sub_question_count": len(state["sub_questions"])})
        log.info("mandate_decomposition_skipped_resume", count=len(state["sub_questions"]))
        return {}

    emit(journalist_id, "llm_call", {"step": "decompose_mandate", "model": "gemini"})
    await _set_cycle_status(db, journalist_id, "decomposing_mandate", cycle_id)

    journalist_doc = await get_journalist_doc(db, journalist_id)

    llm = get_llm(temperature=0.1)
    prompt = DECOMPOSE_MANDATE_PROMPT.format(
        story_title=state["selected_story"],
        story_summary="",
        mandate=journalist_doc["mandate"],
        jurisdiction=journalist_doc["jurisdiction"],
    )
    response = await llm.ainvoke([HumanMessage(content=prompt)])
    content = response.content
    if isinstance(content, list):
        content = "".join(
            part["text"] if isinstance(part, dict) else str(part)
            for part in content
        )
    sub_questions: list[str] = json.loads(content)

    await log_action(db, journalist_id, cycle_id, "mandate_decomposed",
                     {"sub_questions": sub_questions, "count": len(sub_questions)})
    emit(journalist_id, "mandate_decomposed", {
        "sub_questions": sub_questions,
        "count": len(sub_questions),
    })
    await _set_cycle_status(db, journalist_id, "researching", cycle_id,
                            {"sub_question_count": len(sub_questions)})

    log.info("mandate_decomposed", count=len(sub_questions))
    return {"sub_questions": sub_questions}


def spawn_researchers(state: EditorState) -> list[Send]:
    """
    Fan-out: one researcher worker per sub-question.
    In local mode, returns Send() calls for LangGraph subgraph execution.
    In pubsub mode, publishes to Pub/Sub and returns empty list (workers run independently).
    """
    emit(state["config"].journalist_id, "researchers_spawned",
         {"count": len(state["sub_questions"])})

    mode = os.environ.get("RESEARCHER_MODE", "local")

    if mode == "pubsub":
        _publish_researcher_tasks(state)
        return []

    return [
        Send(
            "researcher_worker",
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
        for q in state["sub_questions"]
    ]


def _publish_researcher_tasks(state: EditorState) -> None:
    topic = os.environ.get("PUBSUB_RESEARCHER_TOPIC", "glass-record-researcher-tasks")
    publisher = pubsub_v1.PublisherClient()
    topic_path = publisher.topic_path(state["config"].journalist_id.split("-")[0], topic)

    for q in state["sub_questions"]:
        payload = json.dumps(
            {
                "journalist_id": state["config"].journalist_id,
                "mandate": state["config"].mandate,
                "jurisdiction": state["config"].jurisdiction,
                "tier": state["config"].tier,
                "sub_question": q,
                "cycle_id": state["cycle_id"],
            }
        ).encode()
        publisher.publish(topic_path, payload)
    log.info("researcher_tasks_published", count=len(state["sub_questions"]))


async def synthesise_results(state: EditorState) -> dict:
    """
    Aggregate researcher results, then run the Compliance Agent.
    The cycle proceeds only if compliance passes.
    """
    from agents.compliance.graph import build_compliance_graph
    from agents.shared.state import ComplianceState

    journalist_id = state["config"].journalist_id
    cycle_id = state["cycle_id"]
    db = firestore.AsyncClient()

    total_evidence = sum(
        len(r.get("evidence_ids", [])) for r in state.get("researcher_results", [])
    )
    await log_action(db, journalist_id, cycle_id, "results_synthesised",
                     {"researcher_count": len(state.get("researcher_results", [])),
                      "evidence_count": total_evidence})
    emit(journalist_id, "research_complete", {
        "evidence_count": total_evidence,
        "researcher_count": len(state.get("researcher_results", [])),
    })
    await _set_cycle_status(db, journalist_id, "compliance_check", cycle_id,
                            {"evidence_count": total_evidence})

    # Run compliance check inline
    compliance_graph = build_compliance_graph()
    compliance_state = ComplianceState(
        config=state["config"],
        selected_story=state["selected_story"],
        sub_questions=state["sub_questions"],
        passed=True,
        reasoning="",
        cycle_id=cycle_id,
        messages=[],
    )
    compliance_result = await compliance_graph.ainvoke(compliance_state)
    passed = compliance_result.get("passed", False)

    emit(journalist_id, "compliance_result", {
        "passed": passed,
        "reasoning": compliance_result.get("reasoning", ""),
    })

    if not passed:
        await _set_cycle_status(db, journalist_id, "idle", cycle_id,
                                {"last_result": "compliance_failed"})
        log.error("cycle_blocked_by_compliance", journalist_id=journalist_id,
                  reasoning=compliance_result.get("reasoning", ""))
    else:
        await _set_cycle_status(db, journalist_id, "publishing", cycle_id)

    log.info("results_synthesised", evidence_count=total_evidence)
    return {"compliance_passed": passed}
