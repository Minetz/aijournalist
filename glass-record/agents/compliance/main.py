import uuid

import structlog
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from agents.compliance.graph import build_compliance_graph
from agents.shared.state import ComplianceState, JournalistConfig

app = FastAPI(title="glass-record-compliance", version="0.1.0")
log = structlog.get_logger()


class ComplianceRequest(BaseModel):
    config: JournalistConfig
    selected_story: str
    sub_questions: list[str]
    cycle_id: str


@app.post("/check")
async def compliance_check(req: ComplianceRequest) -> dict:
    log.info("compliance_check_start", journalist_id=req.config.journalist_id, cycle_id=req.cycle_id)

    graph = build_compliance_graph()
    initial_state = ComplianceState(
        config=req.config,
        selected_story=req.selected_story,
        sub_questions=req.sub_questions,
        passed=True,
        reasoning="",
        cycle_id=req.cycle_id,
        messages=[],
    )

    try:
        final_state = await graph.ainvoke(initial_state)
        return {
            "passed": final_state["passed"],
            "reasoning": final_state.get("reasoning", ""),
        }
    except Exception as exc:
        log.error("compliance_check_failed", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
