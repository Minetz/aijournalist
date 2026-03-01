import datetime
import hashlib
import json

import structlog
from google.cloud import firestore, storage
from langchain_core.messages import HumanMessage
from pydantic_settings import BaseSettings

from agents.shared.base_agent import log_action
from agents.shared.gemini import get_llm
from agents.shared.state import ResearcherState
from agents.researcher.prompts import EVIDENCE_ANALYSIS_PROMPT
from tools.browser.scraper import scrape_urls
from tools.search.google_search import web_search

log = structlog.get_logger()


class StorageSettings(BaseSettings):
    gcs_evidence_bucket: str = "glass-record-evidence-dev"
    google_cloud_project: str = "glass-record-dev"


async def search_node(state: ResearcherState) -> dict:
    results = await web_search(state["sub_question"])
    db = firestore.AsyncClient()
    await log_action(
        db,
        state["config"].journalist_id,
        state["sub_question"][:40],
        "search_complete",
        {"query": state["sub_question"], "result_count": len(results)},
    )
    return {"search_results": results}


async def scrape_node(state: ResearcherState) -> dict:
    urls = [r["url"] for r in state["search_results"][:5]]
    scraped = await scrape_urls(urls)
    successful = [s for s in scraped if not s["error"]]
    log.info("scrape_complete", total=len(urls), successful=len(successful))
    return {"scraped_content": successful}


async def analyse_and_store_evidence(state: ResearcherState) -> dict:
    """
    For each scraped page:
    1. Run Gemini to extract relevant factual claims.
    2. Store structured evidence in Firestore (content-addressed by URL SHA256).
    3. Upload raw text to Cloud Storage.
    """
    llm = get_llm(temperature=0.0)
    ss = StorageSettings()
    db = firestore.AsyncClient()
    gcs = storage.Client(project=ss.google_cloud_project)
    bucket = gcs.bucket(ss.gcs_evidence_bucket)

    evidence_ids: list[str] = []
    journalist_id = state["config"].journalist_id

    for page in state["scraped_content"]:
        prompt = EVIDENCE_ANALYSIS_PROMPT.format(
            sub_question=state["sub_question"],
            url=page["url"],
            text=page["text"][:8_000],
        )
        response = await llm.ainvoke([HumanMessage(content=prompt)])

        try:
            analysis = json.loads(response.content)
        except json.JSONDecodeError:
            log.warning("analysis_parse_failed", url=page["url"])
            continue

        if not analysis.get("relevant", False):
            continue

        # Content-addressed ID — same URL always maps to same evidence_id
        evidence_id = hashlib.sha256(page["url"].encode()).hexdigest()[:16]

        # Upload raw text to Cloud Storage
        blob = bucket.blob(f"{journalist_id}/evidence/{evidence_id}.txt")
        blob.upload_from_string(page["text"], content_type="text/plain")

        # Write structured evidence to Firestore
        evidence_doc = {
            "evidence_id": evidence_id,
            "journalist_id": journalist_id,
            "sub_question": state["sub_question"],
            "source_url": page["url"],
            "source_title": page["title"],
            "claims": analysis.get("claims", []),
            "credibility_score": analysis.get("credibility_score", 0.5),
            "credibility_notes": analysis.get("credibility_notes", ""),
            "gcs_path": f"{journalist_id}/evidence/{evidence_id}.txt",
            "collected_at": datetime.datetime.utcnow().isoformat(),
        }
        await (
            db.collection("journalists")
            .document(journalist_id)
            .collection("evidence_locker")
            .document(evidence_id)
            .set(evidence_doc)
        )
        evidence_ids.append(evidence_id)

    await log_action(
        db,
        journalist_id,
        state["sub_question"][:40],
        "evidence_stored",
        {"count": len(evidence_ids)},
    )
    log.info("evidence_stored", count=len(evidence_ids), journalist_id=journalist_id)
    return {
        "evidence_ids": evidence_ids,
        "researcher_results": [{"sub_question": state["sub_question"], "evidence_ids": evidence_ids}],
    }
