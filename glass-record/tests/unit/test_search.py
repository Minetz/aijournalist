import pytest
from unittest.mock import AsyncMock, patch

from tools.search.google_search import web_search


@pytest.mark.asyncio
async def test_web_search_returns_results():
    mock_response = {
        "items": [
            {"title": "UN Report", "link": "https://un.org/report", "snippet": "Key findings..."},
            {"title": "ICJ Ruling", "link": "https://icj.org/ruling", "snippet": "Decision on..."},
        ]
    }
    with patch("tools.search.google_search.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__.return_value = mock_client
        mock_client.get.return_value = AsyncMock(
            status_code=200,
            json=lambda: mock_response,
            raise_for_status=lambda: None,
        )
        results = await web_search("UN Security Council human rights")

    assert len(results) == 2
    assert results[0]["url"] == "https://un.org/report"
    assert results[0]["title"] == "UN Report"


@pytest.mark.asyncio
async def test_web_search_empty_results():
    with patch("tools.search.google_search.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__.return_value = mock_client
        mock_client.get.return_value = AsyncMock(
            status_code=200,
            json=lambda: {},
            raise_for_status=lambda: None,
        )
        results = await web_search("obscure query with no results")

    assert results == []
