"""
Integration test: full editor cycle against Firestore emulator.

Run with:
  FIRESTORE_EMULATOR_HOST=localhost:8080 uv run pytest tests/integration/ -v

Requires:
  docker compose up -d  (Firestore emulator on :8080)
"""
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from agents.shared.state import EditorState, JournalistConfig

JOURNALIST_ID = "integration-test-journalist"
MANDATE = "Investigate human rights implications of UN Security Council decisions."


@pytest.fixture
def journalist_config() -> JournalistConfig:
    return JournalistConfig(
        journalist_id=JOURNALIST_ID,
        mandate=MANDATE,
        jurisdiction="UN",
        tier="free",
    )


@pytest.mark.asyncio
@pytest.mark.skipif(
    not os.getenv("FIRESTORE_EMULATOR_HOST"),
    reason="Firestore emulator not running (set FIRESTORE_EMULATOR_HOST=localhost:8080)",
)
async def test_editor_selects_story_and_decomposes(journalist_config):
    """
    End-to-end: Editor selects a story and decomposes it into sub-questions.
    Uses mocked Gemini but real Firestore emulator.
    """
    from pydantic import BaseModel

    class StorySelection(BaseModel):
        story_title: str = "UN Security Council veto blocks Gaza ceasefire resolution"
        story_summary: str = "P5 member vetoed a resolution that would have mandated a ceasefire."
        urgency_score: int = 9
        mandate_alignment_reason: str = "Directly concerns a Security Council decision with human rights impact."

    sub_questions = [
        "How many Security Council ceasefire resolutions have been vetoed since October 2023?",
        "What legal obligations does the UN Charter place on Security Council members regarding humanitarian law?",
        "Which UN member states co-sponsored the vetoed resolution?",
    ]

    mock_story_llm = MagicMock()
    mock_story_llm.with_structured_output.return_value.ainvoke = AsyncMock(
        return_value=StorySelection()
    )

    mock_decompose_llm = MagicMock()
    mock_decompose_response = MagicMock()
    mock_decompose_response.content = str(sub_questions).replace("'", '"')
    mock_decompose_llm.ainvoke = AsyncMock(return_value=mock_decompose_response)

    call_count = 0

    def mock_get_llm(temperature=0.2):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return mock_story_llm   # select_story call
        return mock_decompose_llm   # decompose_mandate call

    # Patch Gemini but use real Firestore emulator
    with (
        patch("agents.editor.nodes.get_llm", side_effect=mock_get_llm),
        patch("agents.editor.nodes.get_journalist_doc", AsyncMock(return_value={
            "journalist_id": JOURNALIST_ID,
            "mandate": MANDATE,
            "jurisdiction": "UN",
            "tier": "free",
        })),
        # Skip researcher and compliance for this test scope
        patch("agents.editor.nodes.spawn_researchers", return_value=[]),
        patch("agents.editor.nodes.build_compliance_graph") as mock_compliance,
    ):
        mock_compliance_graph = MagicMock()
        mock_compliance_graph.ainvoke = AsyncMock(return_value={"passed": True, "reasoning": "OK"})
        mock_compliance.return_value = mock_compliance_graph

        from agents.editor.graph import build_graph
        from agents.shared.state import EditorState
        import uuid

        graph = build_graph()
        state = EditorState(
            config=journalist_config,
            selected_story="",
            sub_questions=[],
            researcher_results=[],
            compliance_passed=False,
            cycle_id=str(uuid.uuid4()),
            messages=[],
        )
        result = await graph.ainvoke(state)

    assert result["selected_story"] == "UN Security Council veto blocks Gaza ceasefire resolution"
    assert len(result["sub_questions"]) == 3
    assert result["compliance_passed"] is True
