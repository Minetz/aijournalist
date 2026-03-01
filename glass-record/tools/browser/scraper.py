import asyncio

import structlog
from playwright.async_api import async_playwright

log = structlog.get_logger()

_MAX_TEXT_CHARS = 50_000
_TIMEOUT_MS = 20_000


async def scrape_url(url: str) -> dict:
    """
    Extract visible text and page title from a URL using headless Chromium.
    Returns {url, title, text, error}. error is None on success.
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (compatible; GlassRecord/1.0; +https://glassrecord.org)"
        )
        page = await context.new_page()
        try:
            await page.goto(url, wait_until="networkidle", timeout=_TIMEOUT_MS)
            title = await page.title()
            body_text = await page.inner_text("body")
            log.info("scraped", url=url, chars=len(body_text))
            return {"url": url, "title": title, "text": body_text[:_MAX_TEXT_CHARS], "error": None}
        except Exception as exc:
            log.warning("scrape_failed", url=url, error=str(exc))
            return {"url": url, "title": "", "text": "", "error": str(exc)}
        finally:
            await browser.close()


async def scrape_urls(urls: list[str]) -> list[dict]:
    """Scrape multiple URLs concurrently."""
    tasks = [scrape_url(url) for url in urls]
    return await asyncio.gather(*tasks)
