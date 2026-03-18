"""Unit tests for article revision loop."""
import sys
from unittest.mock import MagicMock

for mod in [
    "google", "google.cloud", "google.cloud.firestore",
    "langchain_core", "langchain_core.messages",
    "agents.shared.gemini",
    "agents.editor.events",
    "agents.shared.base_agent",
]:
    sys.modules.setdefault(mod, MagicMock())

from unittest.mock import AsyncMock, patch, call  # noqa: E402

import pytest  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_config(journalist_id: str = "j-001") -> MagicMock:
    cfg = MagicMock()
    cfg.journalist_id = journalist_id
    cfg.jurisdiction = "UN"
    return cfg


def _make_state(
    compliance_passed: bool = True,
    researcher_results: list | None = None,
    contradictions: list | None = None,
) -> dict:
    return {
        "config": _make_config(),
        "cycle_id": "cycle-new",
        "compliance_passed": compliance_passed,
        "selected_story": "New UN Reform Report",
        "researcher_results": researcher_results or [],
        "contradictions": contradictions or [],
    }


def _make_prior_story(
    story_id: str = "story-old",
    cycle_id: str = "cycle-old",
    article_type: str | None = None,
) -> dict:
    doc = {
        "story_id": story_id,
        "cycle_id": cycle_id,
        "title": "Prior Report on UN Sanctions",
        "standfirst": "Russia vetoed all proposals.",
        "published_at": "2026-02-20T10:00:00",
        "tags": ["un"],
    }
    if article_type:
        doc["article_type"] = article_type
    return doc


def _make_db(prior_stories: list[dict]) -> MagicMock:
    """Mock Firestore db returning prior_stories from the stories query."""
    snaps = []
    for s in prior_stories:
        snap = MagicMock()
        snap.to_dict.return_value = s
        snaps.append(snap)

    # The .where().order_by().limit().get() chain
    query = MagicMock()
    query.get = AsyncMock(return_value=snaps)
    query.order_by = MagicMock(return_value=query)
    query.limit = MagicMock(return_value=query)
    query.where = MagicMock(return_value=query)

    stories_col = MagicMock()
    stories_col.where = MagicMock(return_value=query)

    doc_ref = MagicMock()
    doc_ref.collection = MagicMock(return_value=stories_col)
    # For saving a new story: .collection("stories").document(id).set(...)
    new_doc_ref = MagicMock()
    new_doc_ref.set = AsyncMock()
    stories_col.document = MagicMock(return_value=new_doc_ref)

    db = MagicMock()
    db.collection.return_value.document.return_value = doc_ref
    return db


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_skips_when_compliance_failed():
    from agents.editor.revision_nodes import check_and_revise_prior_stories
    state = _make_state(compliance_passed=False)
    result = await check_and_revise_prior_stories(state)
    assert result == {}


@pytest.mark.asyncio
async def test_skips_when_no_prior_stories():
    from agents.editor.revision_nodes import check_and_revise_prior_stories
    db = _make_db([])
    with patch("agents.editor.revision_nodes.firestore.AsyncClient", return_value=db):
        result = await check_and_revise_prior_stories(_make_state())
    assert result == {}


@pytest.mark.asyncio
async def test_skips_stories_from_current_cycle():
    from agents.editor.revision_nodes import check_and_revise_prior_stories
    # Prior story has same cycle_id as current — should be excluded
    db = _make_db([_make_prior_story(cycle_id="cycle-new")])
    with patch("agents.editor.revision_nodes.firestore.AsyncClient", return_value=db):
        result = await check_and_revise_prior_stories(_make_state())
    assert result == {}


@pytest.mark.asyncio
async def test_skips_correction_articles():
    from agents.editor.revision_nodes import check_and_revise_prior_stories
    db = _make_db([_make_prior_story(article_type="correction")])
    with patch("agents.editor.revision_nodes.firestore.AsyncClient", return_value=db):
        result = await check_and_revise_prior_stories(_make_state())
    assert result == {}


@pytest.mark.asyncio
async def test_no_revisions_when_llm_returns_empty():
    from agents.editor.revision_nodes import check_and_revise_prior_stories
    db = _make_db([_make_prior_story()])

    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock(return_value=MagicMock(content='{"revisions": []}'))

    with patch("agents.editor.revision_nodes.firestore.AsyncClient", return_value=db), \
         patch("agents.editor.revision_nodes.get_llm", return_value=mock_llm):
        result = await check_and_revise_prior_stories(_make_state())

    assert result == {}


@pytest.mark.asyncio
async def test_correction_saved_when_llm_detects_contradiction():
    from agents.editor.revision_nodes import check_and_revise_prior_stories

    prior = _make_prior_story()
    db = _make_db([prior])

    revision_payload = {
        "revisions": [{
            "story_id": "story-old",
            "story_title": "Prior Report on UN Sanctions",
            "revision_type": "correction",
            "reason": "New evidence shows China also vetoed, not just Russia.",
            "new_headline": "Correction: Both Russia and China Vetoed UN Sanctions",
            "new_standfirst": "New documents reveal China's previously unreported veto.",
            "new_body_html": "<p>Updated investigation...</p>",
        }]
    }
    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock(return_value=MagicMock(
        content=__import__("json").dumps(revision_payload)
    ))

    saved_docs = []

    async def capture_set(doc):
        saved_docs.append(doc)

    # Intercept the .set() call on the new story doc ref
    new_doc_ref = MagicMock()
    new_doc_ref.set = AsyncMock(side_effect=capture_set)
    db.collection.return_value.document.return_value.collection.return_value.document.return_value = new_doc_ref

    with patch("agents.editor.revision_nodes.firestore.AsyncClient", return_value=db), \
         patch("agents.editor.revision_nodes.get_llm", return_value=mock_llm), \
         patch("agents.editor.revision_nodes.log_action", new=AsyncMock()), \
         patch("agents.editor.revision_nodes.emit"):
        result = await check_and_revise_prior_stories(_make_state())

    assert result == {}
    assert new_doc_ref.set.called
    saved = new_doc_ref.set.call_args[0][0]
    assert saved["article_type"] == "correction"
    assert saved["related_story_id"] == "story-old"
    assert "Correction:" in saved["title"]


@pytest.mark.asyncio
async def test_llm_failure_returns_empty_gracefully():
    from agents.editor.revision_nodes import check_and_revise_prior_stories
    db = _make_db([_make_prior_story()])

    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock(side_effect=Exception("LLM timeout"))

    with patch("agents.editor.revision_nodes.firestore.AsyncClient", return_value=db), \
         patch("agents.editor.revision_nodes.get_llm", return_value=mock_llm):
        result = await check_and_revise_prior_stories(_make_state())

    assert result == {}


@pytest.mark.asyncio
async def test_revisions_capped_at_max():
    from agents.editor.revision_nodes import check_and_revise_prior_stories, MAX_REVISIONS

    prior = _make_prior_story()
    db = _make_db([prior])

    # LLM returns more revisions than MAX_REVISIONS
    many_revisions = [
        {
            "story_id": f"story-{i}",
            "story_title": f"Prior story {i}",
            "revision_type": "update",
            "reason": f"New info {i}",
            "new_headline": f"Update {i}",
            "new_standfirst": f"Standfirst {i}",
            "new_body_html": f"<p>Body {i}</p>",
        }
        for i in range(MAX_REVISIONS + 2)
    ]
    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock(return_value=MagicMock(
        content=__import__("json").dumps({"revisions": many_revisions})
    ))

    set_call_count = 0

    async def count_set(doc):
        nonlocal set_call_count
        set_call_count += 1

    new_doc_ref = MagicMock()
    new_doc_ref.set = AsyncMock(side_effect=count_set)
    db.collection.return_value.document.return_value.collection.return_value.document.return_value = new_doc_ref

    with patch("agents.editor.revision_nodes.firestore.AsyncClient", return_value=db), \
         patch("agents.editor.revision_nodes.get_llm", return_value=mock_llm), \
         patch("agents.editor.revision_nodes.log_action", new=AsyncMock()), \
         patch("agents.editor.revision_nodes.emit"):
        await check_and_revise_prior_stories(_make_state())

    assert set_call_count <= MAX_REVISIONS


def test_build_evidence_summary():
    from agents.editor.revision_nodes import _build_evidence_summary
    results = [
        {"sub_question": "Who voted?", "evidence_ids": ["e1", "e2"]},
        {"sub_question": "When?", "evidence_ids": []},
    ]
    summary = _build_evidence_summary(results)
    assert "Who voted?" in summary
    assert "2 sources" in summary


def test_build_contradictions_summary_empty():
    from agents.editor.revision_nodes import _build_contradictions_summary
    assert "None" in _build_contradictions_summary([])


def test_build_contradictions_summary_with_items():
    from agents.editor.revision_nodes import _build_contradictions_summary
    c = [{
        "severity": "high",
        "description": "Vote count mismatch",
        "claim_a": "12 votes for",
        "claim_b": "10 votes for",
    }]
    summary = _build_contradictions_summary(c)
    assert "HIGH" in summary
    assert "Vote count mismatch" in summary
