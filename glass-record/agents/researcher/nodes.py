import datetime
import hashlib
import json

import structlog
from google import genai
from google.api_core.exceptions import ResourceExhausted, ServiceUnavailable
from google.cloud import firestore, storage
from google.genai.types import GenerateContentConfig, GoogleSearch, Tool
from langchain_core.messages import HumanMessage
from pydantic_settings import BaseSettings
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from agents.researcher.prompts import EVIDENCE_EXTRACTION_PROMPT
from agents.shared.base_agent import log_action
from agents.shared.events import emit
from agents.shared.gemini import get_llm
from agents.shared.state import ResearcherState

log = structlog.get_logger()


class ResearchSettings(BaseSettings):
    gcs_evidence_bucket: str = "glass-record-evidence-prod"
    google_cloud_project: str = "glass-record-prod"
    gemini_model: str = "gemini-3.1-pro-preview"
    gemini_fallback_model: str = "gemini-3.0-flash-preview"
    google_genai_use_vertexai: bool = True


async def _load_prior_evidence(journalist_id: str, limit: int = 30) -> str:
    """
    Fetch the most recent evidence items from the evidence_locker and return
    a compact summary string to inject into the researcher prompt.
    Returns an empty string if there is no prior evidence.
    """
    try:
        db = firestore.AsyncClient()
        snap = await (
            db.collection("journalists")
            .document(journalist_id)
            .collection("evidence_locker")
            .order_by("collected_at", direction=firestore.Query.DESCENDING)
            .limit(limit)
            .get()
        )
        if not snap:
            return ""

        lines = ["Prior evidence already collected (do not duplicate):\n"]
        for doc in snap:
            e = doc.to_dict()
            date = e.get("collected_at", "")[:10]
            title = e.get("source_title", e.get("source_url", ""))
            claims = e.get("claims", [])
            claim_str = " | ".join(claims[:2])
            lines.append(f"- [{date}] {title}: {claim_str}")
        return "\n".join(lines) + "\n\n"
    except Exception:
        log.warning("prior_evidence_load_failed", journalist_id=journalist_id)
        return ""


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

    # ── Step 0: Load prior evidence for context ───────────────────────────────
    prior_context = await _load_prior_evidence(journalist_id)

    # ── Step 1: Gemini with Google Search grounding ──────────────────────────
    client = genai.Client(
        vertexai=settings.google_genai_use_vertexai,
        project=settings.google_cloud_project,
        location="global",
    )

    search_prompt = (
        f"You are an investigative journalist researcher.\n"
        f"Mandate: {mandate}\n"
        f"{prior_context}"
        f"Research this sub-question using the web: {sub_question}\n"
        f"Prioritise new developments not already covered in prior findings above.\n"
        f"Summarise what you find, citing specific facts, dates, and sources."
    )

    @retry(
        retry=retry_if_exception_type(ServiceUnavailable),
        wait=wait_exponential(multiplier=1, min=4, max=60),
        stop=stop_after_attempt(4),
        reraise=True,
    )
    async def _call_model(model: str) -> genai.types.GenerateContentResponse:
        return await client.aio.models.generate_content(
            model=model,
            contents=search_prompt,
            config=GenerateContentConfig(
                tools=[Tool(google_search=GoogleSearch())],
            ),
        )

    try:
        grounded = await _call_model(settings.gemini_model)
    except ResourceExhausted:
        log.warning(
            "quota_exhausted_falling_back",
            primary_model=settings.gemini_model,
            fallback_model=settings.gemini_fallback_model,
        )
        emit(journalist_id, "researcher_quota_fallback", {
            "primary_model": settings.gemini_model,
            "fallback_model": settings.gemini_fallback_model,
        })
        grounded = await _call_model(settings.gemini_fallback_model)

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

    raw_content = extraction.content
    if isinstance(raw_content, list):
        raw_content = "".join(
            part["text"] if isinstance(part, dict) else str(part)
            for part in raw_content
        )
    try:
        findings = json.loads(raw_content)
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
