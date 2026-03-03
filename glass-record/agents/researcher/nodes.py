import datetime
import hashlib
import json

import structlog
from google import genai
from google.cloud import firestore, storage
from google.genai.types import GenerateContentConfig, GoogleSearch, Tool
from langchain_core.messages import HumanMessage
from pydantic_settings import BaseSettings

from agents.researcher.prompts import EVIDENCE_EXTRACTION_PROMPT
from agents.shared.base_agent import log_action
from agents.shared.events import emit
from agents.shared.gemini import get_llm
from agents.shared.state import ResearcherState

log = structlog.get_logger()


class ResearchSettings(BaseSettings):
    gcs_evidence_bucket: str = "glass-record-evidence-dev"
    google_cloud_project: str = "glass-record-dev"
    gemini_model: str = "gemini-3.1-pro-preview"
    google_genai_use_vertexai: bool = True


async def grounded_research(state: ResearcherState) -> dict:
    """
    Single node: uses Gemini with Google Search grounding to research a
    sub-question, then extracts structured evidence (claims, entities,
    credibility) and stores it in Firestore + GCS.

    Replaces the old search → scrape → analyse_store three-node pipeline.
    No external API keys or Playwright required.
    """
    settings = ResearchSettings()
    journalist_id = state["config"].journalist_id
    sub_question = state["sub_question"]
    mandate = state["config"].mandate

    emit(journalist_id, "researcher_searching", {"sub_question": sub_question[:80]})

    # ── Step 1: Gemini with Google Search grounding ──────────────────────────
    client = genai.Client(
        vertexai=settings.google_genai_use_vertexai,
        project=settings.google_cloud_project,
        location="us-central1",
    )

    search_prompt = (
        f"You are an investigative journalist researcher.\n"
        f"Mandate: {mandate}\n"
        f"Research this sub-question using the web: {sub_question}\n"
        f"Summarise what you find, citing specific facts, dates, and sources."
    )

    grounded = await client.aio.models.generate_content(
        model=settings.gemini_model,
        contents=search_prompt,
        config=GenerateContentConfig(
            tools=[Tool(google_search=GoogleSearch())],
        ),
    )

    grounded_text = grounded.text or ""
    sources: list[dict] = []
    meta = grounded.candidates[0].grounding_metadata if grounded.candidates else None
    if meta and meta.grounding_chunks:
        for chunk in meta.grounding_chunks:
            if chunk.web:
                sources.append({
                    "url": chunk.web.uri,
                    "title": chunk.web.title or chunk.web.uri,
                })

    emit(journalist_id, "researcher_analysing", {
        "sub_question": sub_question[:80],
        "sources_found": len(sources),
    })
    log.info("grounded_search_done", journalist_id=journalist_id,
             sub_question=sub_question[:60], sources=len(sources))

    # ── Step 2: Extract structured claims from grounded text ─────────────────
    extract_prompt = EVIDENCE_EXTRACTION_PROMPT.format(
        sub_question=sub_question,
        grounded_summary=grounded_text[:8_000],
        sources_json=json.dumps(sources[:10], ensure_ascii=False),
    )
    llm = get_llm(temperature=0.0)
    extraction = await llm.ainvoke([HumanMessage(content=extract_prompt)])

    try:
        findings = json.loads(extraction.content)
    except json.JSONDecodeError:
        log.warning("evidence_extraction_failed", sub_question=sub_question)
        findings = {"findings": []}

    # ── Step 3: Store evidence in Firestore + GCS ────────────────────────────
    db = firestore.AsyncClient()
    gcs = storage.Client(project=settings.google_cloud_project)
    bucket = gcs.bucket(settings.gcs_evidence_bucket)

    evidence_ids: list[str] = []

    for finding in findings.get("findings", []):
        url = finding.get("source_url", "")
        if not url:
            continue

        evidence_id = hashlib.sha256(url.encode()).hexdigest()[:16]

        # Upload the grounded research text to GCS as the raw evidence
        blob = bucket.blob(f"{journalist_id}/evidence/{evidence_id}.txt")
        blob.upload_from_string(grounded_text, content_type="text/plain")

        evidence_doc = {
            "evidence_id": evidence_id,
            "journalist_id": journalist_id,
            "sub_question": sub_question,
            "source_url": url,
            "source_title": finding.get("source_title", url),
            "claims": finding.get("claims", []),
            "credibility_score": finding.get("credibility_score", 0.5),
            "credibility_notes": finding.get("credibility_notes", ""),
            "entities": finding.get("entities", []),
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

    await log_action(db, journalist_id, sub_question[:40], "evidence_stored", {
        "count": len(evidence_ids),
        "sources_found": len(sources),
    })
    emit(journalist_id, "evidence_stored", {
        "count": len(evidence_ids),
        "sub_question": sub_question[:80],
    })
    log.info("evidence_stored", count=len(evidence_ids), journalist_id=journalist_id)

    return {
        "evidence_ids": evidence_ids,
        "researcher_results": [{"sub_question": sub_question, "evidence_ids": evidence_ids}],
    }
