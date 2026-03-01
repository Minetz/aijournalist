"""
Researcher Agent — Cloud Run entry point.

In local mode, this is invoked as a LangGraph subgraph inside the Editor process.
In pubsub mode, this runs as an independent Cloud Run service consuming Pub/Sub messages.
"""
import json

import structlog
from fastapi import FastAPI, HTTPException, Request

from agents.researcher.graph import build_researcher_graph
from agents.shared.state import JournalistConfig, ResearcherState

app = FastAPI(title="glass-record-researcher", version="0.1.0")
log = structlog.get_logger()


@app.post("/run")
async def run_researcher(request: Request) -> dict:
    """
    Accepts either:
    - Direct JSON body: {journalist_id, mandate, jurisdiction, tier, sub_question, cycle_id}
    - Pub/Sub push message envelope wrapping the same payload
    """
    body = await request.json()

    # Unwrap Pub/Sub push envelope if present
    if "message" in body:
        import base64
        payload = json.loads(base64.b64decode(body["message"]["data"]).decode())
    else:
        payload = body

    config = JournalistConfig(
        journalist_id=payload["journalist_id"],
        mandate=payload["mandate"],
        jurisdiction=payload["jurisdiction"],
        tier=payload.get("tier", "free"),
    )
    sub_question = payload["sub_question"]
    log.info("researcher_start", journalist_id=config.journalist_id, sub_question=sub_question[:60])

    graph = build_researcher_graph()
    initial_state = ResearcherState(
        config=config,
        sub_question=sub_question,
        search_results=[],
        scraped_content=[],
        ingested_docs=[],
        evidence_ids=[],
        messages=[],
    )

    try:
        final_state = await graph.ainvoke(initial_state)
        return {"status": "ok", "evidence_ids": final_state["evidence_ids"]}
    except Exception as exc:
        log.error("researcher_failed", error=str(exc), sub_question=sub_question[:60])
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
