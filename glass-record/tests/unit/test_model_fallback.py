"""Unit tests for model fallback strategy."""
import sys
from unittest.mock import MagicMock, patch

# Stub google-cloud and langchain before any imports
for mod in [
    "google", "google.cloud", "google.cloud.firestore",
    "google.api_core", "google.api_core.exceptions",
    "langchain_google_genai",
    "pydantic_settings",
]:
    sys.modules.setdefault(mod, MagicMock())

import pytest  # noqa: E402


# ---------------------------------------------------------------------------
# Settings tests
# ---------------------------------------------------------------------------

def test_settings_has_fallback_model():
    with open("agents/shared/gemini.py") as f:
        src = f.read()
    assert "gemini_fallback_model" in src
    assert "flash" in src  # default value should reference flash model


def test_settings_has_gcs_bucket():
    with open("agents/shared/gemini.py") as f:
        src = f.read()
    assert "gcs_evidence_bucket" in src


# ---------------------------------------------------------------------------
# get_llm_with_fallback tests
# ---------------------------------------------------------------------------

def test_get_llm_with_fallback_returns_runnable():
    """get_llm_with_fallback() should return an object with an ainvoke method."""
    mock_primary = MagicMock()
    mock_fallback = MagicMock()
    mock_with_fallbacks = MagicMock()
    mock_primary.with_fallbacks = MagicMock(return_value=mock_with_fallbacks)

    mock_chat_cls = MagicMock(side_effect=[mock_primary, mock_fallback])

    mock_exceptions = MagicMock()
    mock_exceptions.ResourceExhausted = Exception
    mock_exceptions.ServiceUnavailable = Exception
    sys.modules["google.api_core.exceptions"] = mock_exceptions

    with patch("agents.shared.gemini.ChatGoogleGenerativeAI", mock_chat_cls), \
         patch("agents.shared.gemini.get_settings") as mock_settings:
        mock_settings.return_value = MagicMock(
            gemini_model="gemini-pro",
            gemini_fallback_model="gemini-flash",
            google_cloud_project="test",
            google_genai_use_vertexai=True,
        )
        from agents.shared import gemini as gemini_mod
        result = gemini_mod.get_llm_with_fallback(temperature=0.1)

    # Should call with_fallbacks on the primary model
    mock_primary.with_fallbacks.assert_called_once()
    args, kwargs = mock_primary.with_fallbacks.call_args
    fallbacks_list = args[0]
    assert len(fallbacks_list) == 1
    assert fallbacks_list[0] is mock_fallback
    assert result is mock_with_fallbacks


def test_get_llm_with_fallback_passes_exception_types():
    """The exceptions_to_handle tuple should include ResourceExhausted and ServiceUnavailable."""
    mock_primary = MagicMock()
    mock_fallback = MagicMock()
    mock_primary.with_fallbacks = MagicMock(return_value=MagicMock())

    ResourceExhausted = type("ResourceExhausted", (Exception,), {})
    ServiceUnavailable = type("ServiceUnavailable", (Exception,), {})
    mock_exceptions = MagicMock()
    mock_exceptions.ResourceExhausted = ResourceExhausted
    mock_exceptions.ServiceUnavailable = ServiceUnavailable
    sys.modules["google.api_core.exceptions"] = mock_exceptions

    with patch("agents.shared.gemini.ChatGoogleGenerativeAI",
               MagicMock(side_effect=[mock_primary, mock_fallback])), \
         patch("agents.shared.gemini.get_settings") as mock_settings:
        mock_settings.return_value = MagicMock(
            gemini_model="gemini-pro",
            gemini_fallback_model="gemini-flash",
            google_cloud_project="test",
            google_genai_use_vertexai=True,
        )
        from agents.shared import gemini as gemini_mod
        gemini_mod.get_llm_with_fallback(temperature=0.0)

    _, kwargs = mock_primary.with_fallbacks.call_args
    exc_types = kwargs.get("exceptions_to_handle", ())
    assert ResourceExhausted in exc_types
    assert ServiceUnavailable in exc_types


# ---------------------------------------------------------------------------
# Researcher fallback clause test
# ---------------------------------------------------------------------------

def test_researcher_catches_service_unavailable():
    """The except clause should list both ResourceExhausted and ServiceUnavailable."""
    import ast, textwrap
    with open("agents/researcher/nodes.py") as f:
        src = f.read()

    # Find the except clause that triggers the fallback
    assert "ServiceUnavailable" in src
    # Both exceptions should appear together in one except clause
    assert "(ResourceExhausted, ServiceUnavailable)" in src
