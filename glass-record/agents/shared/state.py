import operator
from typing import Annotated, TypedDict

from langgraph.graph.message import add_messages
from pydantic import BaseModel


class JournalistConfig(BaseModel):
    journalist_id: str
    mandate: str       # immutable — set at spawn, never overwritten
    jurisdiction: str  # e.g. "UN", "EU", "US_FEDERAL"
    tier: str = "free"  # "free" | "paid"


def _keep_last(a, b):
    return b


class EditorState(TypedDict):
    config: Annotated[JournalistConfig, _keep_last]
    selected_story: str
    sub_questions: list[str]
    researcher_results: Annotated[list[dict], operator.add]  # reduced from parallel workers
    compliance_passed: bool
    cycle_id: str
    messages: Annotated[list, add_messages]


class ResearcherState(TypedDict):
    config: JournalistConfig
    sub_question: str
    search_results: list[dict]
    scraped_content: list[dict]
    ingested_docs: list[dict]
    evidence_ids: list[str]
    messages: Annotated[list, add_messages]


class ComplianceState(TypedDict):
    config: JournalistConfig
    selected_story: str
    sub_questions: list[str]
    passed: bool
    reasoning: str
    cycle_id: str
    messages: Annotated[list, add_messages]
