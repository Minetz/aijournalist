"""Unit tests for monthly budget enforcement."""
import sys
from unittest.mock import MagicMock

# Stub out google.cloud.firestore before any module under test imports it,
# so these unit tests run without GCP credentials or native crypto libs.
_firestore_stub = MagicMock()
sys.modules.setdefault("google", MagicMock())
sys.modules.setdefault("google.cloud", MagicMock())
sys.modules["google.cloud.firestore"] = _firestore_stub

from unittest.mock import AsyncMock  # noqa: E402

import pytest  # noqa: E402

from agents.shared.cost import BudgetExceededError, check_monthly_budget  # noqa: E402


def _make_db(cost_usd_values: list[float]) -> AsyncMock:
    """Return a mock Firestore AsyncClient whose cost_ledger query returns the given costs."""
    docs = []
    for val in cost_usd_values:
        doc = MagicMock()
        doc.to_dict.return_value = {"cost_usd": val}
        docs.append(doc)

    query = AsyncMock()
    query.get = AsyncMock(return_value=docs)

    collection_ref = MagicMock()
    collection_ref.where = MagicMock(return_value=query)

    doc_ref = MagicMock()
    doc_ref.collection = MagicMock(return_value=collection_ref)

    db = MagicMock()
    db.collection.return_value.document.return_value = doc_ref
    return db


@pytest.mark.asyncio
async def test_under_budget_returns_spend():
    db = _make_db([5.0, 10.0, 3.50])
    spent = await check_monthly_budget(db, "journalist-001", limit_usd=50.0)
    assert spent == pytest.approx(18.5)


@pytest.mark.asyncio
async def test_exactly_at_limit_raises():
    db = _make_db([25.0, 25.0])
    with pytest.raises(BudgetExceededError) as exc_info:
        await check_monthly_budget(db, "journalist-001", limit_usd=50.0)
    err = exc_info.value
    assert err.spent_usd == pytest.approx(50.0)
    assert err.limit_usd == 50.0
    assert "journalist-001" in str(err)


@pytest.mark.asyncio
async def test_over_budget_raises():
    db = _make_db([40.0, 15.0])
    with pytest.raises(BudgetExceededError):
        await check_monthly_budget(db, "journalist-002", limit_usd=50.0)


@pytest.mark.asyncio
async def test_zero_spend_passes():
    db = _make_db([])
    spent = await check_monthly_budget(db, "journalist-003", limit_usd=10.0)
    assert spent == 0.0


def test_budget_exceeded_error_message():
    err = BudgetExceededError("test-journalist", 55.1234, 50.0)
    assert "test-journalist" in str(err)
    assert "55.1234" in str(err)
    assert "50.00" in str(err)
