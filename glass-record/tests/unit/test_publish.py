import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from agents.shared.state import EditorState, JournalistConfig


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
async def test_publish_calls_ghost_on_success(mock_firestore_client):
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

    mock_ghost_post = {"id": "ghost-post-001", "url": "https://ghost.local/un-veto"}

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
              AsyncMock(return_value="Evidence item 1: credibility 0.9")),
        patch("agents.editor.publish_nodes.get_llm") as mock_get_llm,
        patch("agents.editor.publish_nodes.GhostClient") as mock_ghost_cls,
    ):
        mock_llm = MagicMock()
        mock_llm.with_structured_output.return_value.ainvoke = AsyncMock(
            return_value=ArticleDraft()
        )
        mock_get_llm.return_value = mock_llm

        mock_ghost = AsyncMock()
        mock_ghost.create_post = AsyncMock(return_value=mock_ghost_post)
        mock_ghost_cls.return_value = mock_ghost

        from agents.editor.publish_nodes import synthesise_and_publish
        result = await synthesise_and_publish(_make_state(compliance_passed=True))

    mock_ghost.create_post.assert_called_once()
    call_kwargs = mock_ghost.create_post.call_args.kwargs
    assert "UN Security Council Veto" in call_kwargs["title"]
    assert "glass-record" in call_kwargs["tags"]
    assert len(result["messages"]) == 1
