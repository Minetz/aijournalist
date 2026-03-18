"""Unit tests for public records request automation."""
import sys
from unittest.mock import MagicMock

# Stub GCP and LangChain imports before module-under-test is loaded
for mod in [
    "google", "google.cloud", "google.cloud.firestore",
    "google.cloud.firestore_v1",
    "langchain_core", "langchain_core.messages",
    "agents.shared.gemini",
    "agents.editor.events",
    "agents.shared.base_agent",
]:
    sys.modules.setdefault(mod, MagicMock())

from unittest.mock import AsyncMock, patch  # noqa: E402

import pytest  # noqa: E402


# ---------------------------------------------------------------------------
# Registry tests
# ---------------------------------------------------------------------------

def test_registry_known_jurisdiction():
    from tools.records_requests.registry import get_registry_entry
    entry = get_registry_entry("US_FEDERAL")
    assert entry["response_days"] == 20
    assert "FOIA" in entry["name"]


def test_registry_case_insensitive():
    from tools.records_requests.registry import get_registry_entry
    assert get_registry_entry("eu") == get_registry_entry("EU")


def test_registry_unknown_jurisdiction_returns_fallback():
    from tools.records_requests.registry import get_registry_entry
    entry = get_registry_entry("MARS_COLONY")
    assert entry["response_days"] == 20  # fallback
    assert "Generic" in entry["name"]


def test_registry_un_entry_exists():
    from tools.records_requests.registry import get_registry_entry, REGISTRY
    assert "UN" in REGISTRY
    entry = get_registry_entry("UN")
    assert entry["template"] == "un.txt"


def test_get_template_us_federal_returns_text():
    from tools.records_requests.registry import get_template
    text = get_template("US_FEDERAL")
    assert text is not None
    assert len(text) > 50


def test_get_template_eu_returns_text():
    from tools.records_requests.registry import get_template
    text = get_template("EU")
    assert text is not None
    assert len(text) > 50


def test_get_template_un_returns_text():
    from tools.records_requests.registry import get_template
    text = get_template("UN")
    assert text is not None
    assert "United Nations" in text


# ---------------------------------------------------------------------------
# Drafter tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_drafter_returns_drafts_on_success():
    from tools.records_requests.drafter import draft_records_requests

    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock(side_effect=[
        # Step 1: identify
        MagicMock(content='{"requests": [{"title": "Voting Records", "records_sought": "All voting records from 2024", "holding_body": "UN Secretariat", "investigative_value": "Shows member state positions"}]}'),
        # Step 2: draft letter
        MagicMock(content="Dear UN Secretariat,\n\nI hereby request voting records...\n\nRespectfully,\nThe Glass Record"),
    ])

    with patch("tools.records_requests.drafter.get_llm", return_value=mock_llm):
        drafts = await draft_records_requests(
            story_title="Security Council Reform Stalled",
            sub_questions=["Which countries blocked reform?"],
            evidence_summary="Sources indicate Russia and China voted against.",
            jurisdiction="UN",
            today="2026-03-18",
            max_requests=1,
        )

    assert len(drafts) == 1
    assert drafts[0].title == "Voting Records"
    assert "Dear UN Secretariat" in drafts[0].letter_text
    assert drafts[0].jurisdiction == "UN"


@pytest.mark.asyncio
async def test_drafter_returns_empty_on_llm_failure():
    from tools.records_requests.drafter import draft_records_requests

    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock(side_effect=Exception("LLM unavailable"))

    with patch("tools.records_requests.drafter.get_llm", return_value=mock_llm):
        drafts = await draft_records_requests(
            story_title="Test",
            sub_questions=[],
            evidence_summary="",
            jurisdiction="EU",
            today="2026-03-18",
        )

    assert drafts == []


@pytest.mark.asyncio
async def test_drafter_caps_at_max_requests():
    from tools.records_requests.drafter import draft_records_requests

    # LLM returns 3 requests but max_requests=2
    requests_json = '{"requests": [' + ",".join([
        f'{{"title": "Req{i}", "records_sought": "docs{i}", "holding_body": "Body{i}", "investigative_value": "val{i}"}}'
        for i in range(3)
    ]) + "]}"

    call_count = 0

    async def side_effect(messages):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return MagicMock(content=requests_json)
        return MagicMock(content=f"Dear Body,\n\nRequest {call_count}.\n\nRespectfully,")

    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock(side_effect=side_effect)

    with patch("tools.records_requests.drafter.get_llm", return_value=mock_llm):
        drafts = await draft_records_requests(
            story_title="Test",
            sub_questions=[],
            evidence_summary="",
            jurisdiction="US_FEDERAL",
            today="2026-03-18",
            max_requests=2,
        )

    assert len(drafts) <= 2


# ---------------------------------------------------------------------------
# Tracker tests
# ---------------------------------------------------------------------------

def test_due_date_calculation():
    from tools.records_requests.tracker import _due_date
    due = _due_date("US_FEDERAL", "2026-03-01T00:00:00")
    assert due == "2026-03-21"  # 20 days from March 1


def test_due_date_eu():
    from tools.records_requests.tracker import _due_date
    due = _due_date("EU", "2026-03-01T00:00:00")
    assert due == "2026-03-16"  # 15 days


@pytest.mark.asyncio
async def test_update_status_rejects_invalid_status():
    from tools.records_requests.tracker import update_status
    db = MagicMock()
    with pytest.raises(ValueError, match="Invalid status"):
        await update_status(db, "j-001", "req-001", "in_limbo")


# ---------------------------------------------------------------------------
# Records request node tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_node_skips_when_no_story():
    from agents.editor.records_request_node import draft_records_requests_node

    cfg = MagicMock()
    cfg.journalist_id = "j-001"
    cfg.jurisdiction = "UN"

    state = {
        "config": cfg,
        "cycle_id": "cycle-001",
        "selected_story": "",
        "sub_questions": [],
        "researcher_results": [],
    }
    result = await draft_records_requests_node(state)
    assert result == {}


@pytest.mark.asyncio
async def test_node_saves_drafts_on_success():
    from agents.editor.records_request_node import draft_records_requests_node
    from tools.records_requests.drafter import RecordsRequestDraft

    cfg = MagicMock()
    cfg.journalist_id = "j-001"
    cfg.jurisdiction = "UN"
    cfg.mandate = "investigate"

    state = {
        "config": cfg,
        "cycle_id": "cycle-001",
        "selected_story": "UN Reform Vote",
        "sub_questions": ["Who voted?"],
        "researcher_results": [{"sub_question": "Who voted?", "evidence_ids": ["e1"]}],
    }

    fake_draft = RecordsRequestDraft(
        title="Voting Records",
        records_sought="All 2024 vote records",
        holding_body="UN Secretariat",
        investigative_value="Shows positions",
        letter_text="Dear UN...",
        jurisdiction="UN",
    )

    mock_db = MagicMock()
    mock_save = AsyncMock(return_value="req-abc")

    with patch("agents.editor.records_request_node.draft_records_requests",
               new=AsyncMock(return_value=[fake_draft])), \
         patch("agents.editor.records_request_node.save_draft", new=mock_save), \
         patch("agents.editor.records_request_node.firestore.AsyncClient",
               return_value=mock_db), \
         patch("agents.editor.records_request_node.log_action", new=AsyncMock()), \
         patch("agents.editor.records_request_node.emit"):
        result = await draft_records_requests_node(state)

    assert result == {}
    mock_save.assert_called_once()
