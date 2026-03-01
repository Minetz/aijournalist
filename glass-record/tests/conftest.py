"""
Shared pytest fixtures.

Set FIRESTORE_EMULATOR_HOST=localhost:8080 before running integration tests:
  FIRESTORE_EMULATOR_HOST=localhost:8080 uv run pytest tests/ -v
"""
import os

import pytest
from unittest.mock import AsyncMock, MagicMock

from agents.shared.state import JournalistConfig


@pytest.fixture
def journalist_config() -> JournalistConfig:
    return JournalistConfig(
        journalist_id="test-journalist-001",
        mandate="Investigate human rights implications of UN Security Council decisions.",
        jurisdiction="UN",
        tier="free",
    )


@pytest.fixture
def mock_llm():
    """Return a mock LLM that yields a configurable response."""
    llm = MagicMock()
    llm.ainvoke = AsyncMock()
    return llm


@pytest.fixture
def mock_firestore_client():
    """Return a mock Firestore AsyncClient."""
    client = MagicMock()
    client.collection.return_value.document.return_value.get = AsyncMock(
        return_value=MagicMock(exists=True, to_dict=lambda: {
            "journalist_id": "test-journalist-001",
            "mandate": "Investigate human rights implications of UN Security Council decisions.",
            "jurisdiction": "UN",
            "tier": "free",
        })
    )
    client.collection.return_value.document.return_value.collection.return_value.add = AsyncMock()
    return client
