import datetime
import json
import os

import structlog
from google.cloud import firestore, pubsub_v1
from langchain_core.messages import HumanMessage
from langgraph.types import Send
from pydantic import BaseModel

from agents.shared.base_agent import get_journalist_doc, log_action
from agents.shared.gemini import get_llm
from agents.shared.state import EditorState, ResearcherState
from agents.editor.prompts import DECOMPOSE_MANDATE_PROMPT, STORY_SELECTION_PROMPT

log = structlog.get_logger()


class StorySelection(BaseModel):
    story_title: str
    story_summary: str
    urgency_score: int
    mandate_alignment_reason: str


async def select_story(state: EditorState) -> dict:
    db = firestore.AsyncClient()

    # Always load mandate from Firestore — never trust the request payload
    journalist_doc = await get_journalist_doc(db, state["config"].journalist_id)
    mandate = journalist_doc["mandate"]
    jurisdiction = journalist_doc["jurisdiction"]

    # Fetch previous story titles to avoid repetition
    stories_ref = (
        db.collection("journalists")
        .document(state["config"].journalist_id)
        .collection("stories")
        .order_by("published_at", direction=firestore.Query.DESCENDING)
        .limit(10)
    )
    previous_stories_snap = await stories_ref.get()
    previous_stories = [s.to_dict().get("title", "") for s in previous_stories_snap]

    llm = get_llm(temperature=0.3).with_structured_output(StorySelection)
    prompt = STORY_SELECTION_PROMPT.format(
        mandate=mandate,
        jurisdiction=jurisdiction,
        today=datetime.date.today().isoformat(),
        previous_stories=previous_stories or "none",
    )
    story: StorySelection = await llm.ainvoke([HumanMessage(content=prompt)])

    await log_action(
        db,
        state["config"].journalist_id,
        state["cycle_id"],
        "story_selected",
        story.model_dump(),
    )
    log.info("story_selected", title=story.story_title, urgency=story.urgency_score)
    return {
        "selected_story": story.story_title,
        "messages": [HumanMessage(content=f"Selected story: {story.story_title}")],
    }


async def decompose_mandate(state: EditorState) -> dict:
    db = firestore.AsyncClient()
    journalist_doc = await get_journalist_doc(db, state["config"].journalist_id)

    llm = get_llm(temperature=0.1)
    prompt = DECOMPOSE_MANDATE_PROMPT.format(
        story_title=state["selected_story"],
        story_summary="",  # populated by select_story in future via state
        mandate=journalist_doc["mandate"],
        jurisdiction=journalist_doc["jurisdiction"],
    )
    response = await llm.ainvoke([HumanMessage(content=prompt)])
    sub_questions: list[str] = json.loads(response.content)

    await log_action(
        db,
        state["config"].journalist_id,
        state["cycle_id"],
        "mandate_decomposed",
        {"sub_questions": sub_questions, "count": len(sub_questions)},
    )
    log.info("mandate_decomposed", count=len(sub_questions))
    return {"sub_questions": sub_questions}


def spawn_researchers(state: EditorState) -> list[Send]:
    """
    Fan-out: one researcher worker per sub-question.
    In local mode, returns Send() calls for LangGraph subgraph execution.
    In pubsub mode, publishes to Pub/Sub and returns empty list (workers run independently).
    """
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
    """Aggregate researcher results. Compliance check wired in MVP 4."""
    db = firestore.AsyncClient()
    total_evidence = sum(
        len(r.get("evidence_ids", [])) for r in state.get("researcher_results", [])
    )
    await log_action(
        db,
        state["config"].journalist_id,
        state["cycle_id"],
        "results_synthesised",
        {"researcher_count": len(state.get("researcher_results", [])), "evidence_count": total_evidence},
    )
    log.info("results_synthesised", evidence_count=total_evidence)
    return {"compliance_passed": True}
