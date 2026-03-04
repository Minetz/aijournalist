import uuid

import structlog
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from agents.editor.events import emit, subscribe
from agents.editor.graph import build_graph
from agents.editor.graph_api import router as graph_router
from agents.editor.spawn import router as spawn_router
from agents.shared.base_agent import register_journalist
from agents.shared.cost import CostCallbackHandler
from agents.shared.gemini import get_settings
from agents.shared.state import EditorState, JournalistConfig
from agents.verification.main import router as tips_router
from google.cloud import firestore

app = FastAPI(title="glass-record-editor", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)
app.include_router(spawn_router)
app.include_router(tips_router)
app.include_router(graph_router)
log = structlog.get_logger()


async def _load_resume_state(db: firestore.AsyncClient, journalist_id: str) -> dict:
    """Return pre-computed story/sub_questions from the most recent activity log cycle."""
    entries_snap = await (
        db.collection("journalists")
        .document(journalist_id)
        .collection("activity_log")
        .order_by("timestamp", direction=firestore.Query.DESCENDING)
        .limit(50)
        .get()
    )
    entries = [e.to_dict() for e in entries_snap]

    story_entry = next((e for e in entries if e["action"] == "story_selected"), None)
    if not story_entry:
        return {}

    cycle_id = story_entry["cycle_id"]
    mandate_entry = next(
        (e for e in entries
         if e["action"] == "mandate_decomposed" and e["cycle_id"] == cycle_id),
        None,
    )

    result: dict = {"selected_story": story_entry["data"]["story_title"]}
    if mandate_entry:
        result["sub_questions"] = mandate_entry["data"]["sub_questions"]
    return result


@app.post("/run")
async def run_cycle(config: JournalistConfig, resume: bool = False) -> dict:
    """Trigger one investigation cycle for a journalist.

    Pass ?resume=true to skip story selection and mandate decomposition,
    reusing the outputs from the most recent cycle logged in Firestore.
    """
    cycle_id = str(uuid.uuid4())
    log.info("cycle_start", journalist_id=config.journalist_id, cycle_id=cycle_id,
             resume=resume)

    db = firestore.AsyncClient()
    await register_journalist(
        db,
        journalist_id=config.journalist_id,
        mandate=config.mandate,
        jurisdiction=config.jurisdiction,
        tier=config.tier,
    )

    resume_state: dict = {}
    if resume:
        resume_state = await _load_resume_state(db, config.journalist_id)
        log.info("cycle_resuming", journalist_id=config.journalist_id,
                 has_story=bool(resume_state.get("selected_story")),
                 has_sub_questions=bool(resume_state.get("sub_questions")))

    settings = get_settings()
    cost_cb = CostCallbackHandler(
        journalist_id=config.journalist_id,
        cycle_id=cycle_id,
        model=settings.gemini_model,
    )

    graph = build_graph()
    initial_state = EditorState(
        config=config,
        selected_story=resume_state.get("selected_story", ""),
        sub_questions=resume_state.get("sub_questions", []),
        researcher_results=[],
        compliance_passed=False,
        cycle_id=cycle_id,
        messages=[],
    )

    try:
        final_state = await graph.ainvoke(
            initial_state,
            config={"callbacks": [cost_cb]},
        )
        await cost_cb.flush_to_firestore(db)
        cost = cost_cb.summary()
        emit(config.journalist_id, "cycle_complete", {
            "cycle_id": cycle_id,
            "cost_usd": cost["cost_usd"],
            "total_tokens": cost["total_tokens"],
        })
        log.info("cycle_complete", journalist_id=config.journalist_id,
                 cycle_id=cycle_id, cost_usd=cost["cost_usd"])
        return {
            "status": "ok",
            "cycle_id": cycle_id,
            "story": final_state["selected_story"],
            "sub_questions": final_state["sub_questions"],
            "compliance_passed": final_state["compliance_passed"],
            "cost": cost,
        }
    except Exception as exc:
        # Still flush partial cost on failure
        try:
            await cost_cb.flush_to_firestore(db)
        except Exception:
            pass
        emit(config.journalist_id, "cycle_error", {"cycle_id": cycle_id, "error": str(exc)})
        log.error("cycle_failed", error=str(exc), cycle_id=cycle_id)
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/stream/{journalist_id}")
async def stream_events(journalist_id: str) -> StreamingResponse:
    """
    Server-Sent Events stream for a journalist's live cycle events.

    Events emitted (JSON in `data` field):
      cycle_start, llm_call, story_selected, mandate_decomposed,
      researchers_spawned, researcher_search, researcher_scraping,
      evidence_stored, research_complete, compliance_result,
      building_legal_tree, legal_tree_ready, story_published,
      cycle_complete, cycle_error

    A heartbeat comment (`: heartbeat`) keeps the connection alive
    through load balancers and proxies.
    """
    return StreamingResponse(
        subscribe(journalist_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
