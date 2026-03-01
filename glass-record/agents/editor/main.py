import uuid

import structlog
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse

from agents.editor.events import emit, subscribe
from agents.editor.graph import build_graph
from agents.editor.spawn import router as spawn_router
from agents.shared.base_agent import register_journalist
from agents.shared.state import EditorState, JournalistConfig
from google.cloud import firestore

app = FastAPI(title="glass-record-editor", version="0.1.0")
app.include_router(spawn_router)
log = structlog.get_logger()


@app.post("/run")
async def run_cycle(config: JournalistConfig) -> dict:
    """Trigger one investigation cycle for a journalist."""
    cycle_id = str(uuid.uuid4())
    log.info("cycle_start", journalist_id=config.journalist_id, cycle_id=cycle_id)

    # Ensure journalist is registered in Firestore (mandate immutability enforced inside)
    db = firestore.AsyncClient()
    await register_journalist(
        db,
        journalist_id=config.journalist_id,
        mandate=config.mandate,
        jurisdiction=config.jurisdiction,
        tier=config.tier,
    )

    graph = build_graph()
    initial_state = EditorState(
        config=config,
        selected_story="",
        sub_questions=[],
        researcher_results=[],
        compliance_passed=False,
        cycle_id=cycle_id,
        messages=[],
    )

    try:
        final_state = await graph.ainvoke(initial_state)
        emit(config.journalist_id, "cycle_complete", {"cycle_id": cycle_id})
        log.info("cycle_complete", journalist_id=config.journalist_id, cycle_id=cycle_id)
        return {
            "status": "ok",
            "cycle_id": cycle_id,
            "story": final_state["selected_story"],
            "sub_questions": final_state["sub_questions"],
            "compliance_passed": final_state["compliance_passed"],
        }
    except Exception as exc:
        emit(config.journalist_id, "cycle_error", {"cycle_id": cycle_id, "error": str(exc)})
        log.error("cycle_failed", error=str(exc), cycle_id=cycle_id)
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/stream/{journalist_id}")
async def stream_events(journalist_id: str) -> StreamingResponse:
    """
    Server-Sent Events stream for a journalist's live cycle events.

    The dashboard connects here to receive real-time progress updates
    during an active investigation cycle.

    Events emitted (JSON in `data` field):
      cycle_start, llm_call, story_selected, mandate_decomposed,
      researchers_spawned, research_complete, compliance_result,
      building_legal_tree, legal_tree_ready, story_published,
      cycle_complete, cycle_error

    A heartbeat comment (`: heartbeat`) is sent every 15 s to keep
    the connection alive through load balancers and proxies.
    """
    return StreamingResponse(
        subscribe(journalist_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",   # disable nginx buffering
            "Connection": "keep-alive",
        },
    )


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
