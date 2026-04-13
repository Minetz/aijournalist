import sys
from unittest.mock import AsyncMock, MagicMock, patch

# Stub out google-cloud and other transitive deps before any module-under-test is imported
for mod in [
    "google", "google.cloud", "google.cloud.firestore",
    "langchain_core", "langchain_core.messages",
    "agents.editor.events", "agents.editor.publish_prompts",
    "agents.legal_tree", "agents.legal_tree.nodes",
    "agents.legal_tree.prompts",
    "agents.shared.base_agent", "agents.shared.gemini",
]:
    sys.modules.setdefault(mod, MagicMock())

import pytest  # noqa: E402
from agents.shared.state import EditorState, JournalistConfig  # noqa: E402


def _make_state(compliance_passed: bool = True) -> EditorState:
    return EditorState(
        config=JournalistConfig(
            journalist_id="test-j-001",
            mandate="Investigate human rights implications of UN Security Council decisions.",
            jurisdiction="UN",
        ),
        selected_story="UN Security Council veto blocks Gaza ceasefire",
        sub_questions=["How many vetoes since October 2023?"],
        researcher_results=[{"evidence_ids": ["abc", "def"]}],
        compliance_passed=compliance_passed,
        cycle_id="cycle-xyz",
        messages=[],
    )


@pytest.mark.asyncio
async def test_publish_skipped_when_compliance_failed():
    """synthesise_and_publish is a no-op when compliance_passed is False."""
    from agents.editor.publish_nodes import synthesise_and_publish

    state = _make_state(compliance_passed=False)
    result = await synthesise_and_publish(state)
    assert result == {}


@pytest.mark.asyncio
async def test_publish_stores_to_firestore(mock_firestore_client):
    """synthesise_and_publish stores body_html in Firestore (no external CMS)."""
    from pydantic import BaseModel

    class ArticleDraft(BaseModel):
        headline: str = "UN Security Council Veto Blocked Gaza Ceasefire"
        standfirst: str = "A P5 veto prevented a humanitarian ceasefire resolution."
        body_html: str = "<p>Full article body.</p>"
        tags: list[str] = ["un", "human-rights"]

    mock_tree = MagicMock()
    mock_tree.tree_id = "tree-001"
    mock_tree.overall_strength = "moderate"
    mock_tree.summary = "Case for veto accountability under international law."
    mock_tree.root_nodes = []

    with (
        patch("agents.editor.publish_nodes.firestore.AsyncClient",
              return_value=mock_firestore_client),
        patch("agents.editor.publish_nodes.get_journalist_doc", AsyncMock(return_value={
            "mandate": "Investigate UN Security Council decisions.",
            "jurisdiction": "UN",
        })),
        patch("agents.editor.publish_nodes.build_legal_tree",
              AsyncMock(return_value=mock_tree)),
        patch("agents.editor.publish_nodes._fetch_evidence_summary",
              AsyncMock(return_value=("Evidence item 1: credibility 0.9", []))),
        patch("agents.editor.publish_nodes._extract_and_store_timeline", AsyncMock()),
        patch("agents.editor.publish_nodes.log_action", new=AsyncMock()),
        patch("agents.editor.publish_nodes.get_llm") as mock_get_llm,
    ):
        mock_llm = MagicMock()
        mock_llm.with_structured_output.return_value.ainvoke = AsyncMock(
            return_value=ArticleDraft()
        )
        mock_get_llm.return_value = mock_llm

        from agents.editor.publish_nodes import synthesise_and_publish
        result = await synthesise_and_publish(_make_state(compliance_passed=True))

    # Story was stored in Firestore (set called on stories subcollection)
    stories_col = (
        mock_firestore_client
        .collection.return_value
        .document.return_value
        .collection.return_value
    )
    stories_col.document.return_value.set.assert_called_once()
    stored = stories_col.document.return_value.set.call_args[0][0]
    assert "body_html" in stored
    assert "UN Security Council Veto" in stored["title"]
    assert len(result["messages"]) == 1
