import structlog
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from agents.legal_tree.nodes import build_legal_tree
from agents.legal_tree.schemas import LegalTree

app = FastAPI(title="glass-record-legal-tree", version="0.1.0")
log = structlog.get_logger()


class LegalTreeRequest(BaseModel):
    journalist_id: str
    cycle_id: str
    story_title: str


@app.post("/build", response_model=LegalTree)
async def build_tree(req: LegalTreeRequest) -> LegalTree:
    log.info("legal_tree_start", journalist_id=req.journalist_id, cycle_id=req.cycle_id)
    try:
        tree = await build_legal_tree(
            journalist_id=req.journalist_id,
            cycle_id=req.cycle_id,
            story_title=req.story_title,
        )
        return tree
    except Exception as exc:
        log.error("legal_tree_failed", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
