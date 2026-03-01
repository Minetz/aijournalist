import structlog
import httpx
from pydantic_settings import BaseSettings

log = structlog.get_logger()


class SearchSettings(BaseSettings):
    google_search_api_key: str = ""
    google_search_engine_id: str = ""


async def web_search(query: str, num: int = 10) -> list[dict]:
    """
    Query the Google Programmable Search Engine.
    Returns a list of {title, url, snippet} dicts.
    """
    s = SearchSettings()
    params = {
        "key": s.google_search_api_key,
        "cx": s.google_search_engine_id,
        "q": query,
        "num": min(num, 10),  # API max is 10 per request
    }
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get("https://www.googleapis.com/customsearch/v1", params=params)
        r.raise_for_status()

    items = r.json().get("items", [])
    results = [{"title": i["title"], "url": i["link"], "snippet": i.get("snippet", "")} for i in items]
    log.info("search_complete", query=query, result_count=len(results))
    return results
