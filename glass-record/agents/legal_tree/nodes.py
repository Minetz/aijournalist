import datetime
import uuid

import structlog
from google.cloud import firestore
from langchain_core.messages import HumanMessage

from agents.shared.base_agent import get_journalist_doc, log_action
from agents.shared.gemini import get_llm
from agents.legal_tree.prompts import LEGAL_TREE_PROMPT
from agents.legal_tree.schemas import LegalTree

log = structlog.get_logger()


async def _fetch_evidence_summary(
    db: firestore.AsyncClient,
    journalist_id: str,
    max_items: int = 20,
) -> str:
    """Pull evidence from Firestore and format as a text summary for the prompt."""
    evidence_ref = (
        db.collection("journalists")
        .document(journalist_id)
        .collection("evidence_locker")
        .order_by("credibility_score", direction=firestore.Query.DESCENDING)
        .limit(max_items)
    )
    docs = await evidence_ref.get()
    lines: list[str] = []
    for doc in docs:
        e = doc.to_dict()
        claims_text = "; ".join(e.get("claims", []))
        lines.append(
            f"[{e['evidence_id']}] {e['source_title']} ({e['source_url']})\n"
            f"  Credibility: {e.get('credibility_score', 0):.2f}\n"
            f"  Claims: {claims_text}"
        )
    return "\n\n".join(lines) if lines else "No evidence collected yet."


async def build_legal_tree(
    journalist_id: str,
    cycle_id: str,
    story_title: str,
) -> LegalTree:
    """
    Fetch evidence from Firestore, invoke Gemini to build the legal tree,
    persist the result, and return it.
    """
    db = firestore.AsyncClient()
    journalist_doc = await get_journalist_doc(db, journalist_id)

    evidence_summary = await _fetch_evidence_summary(db, journalist_id)

    llm = get_llm(temperature=0.1).with_structured_output(LegalTree)
    prompt = LEGAL_TREE_PROMPT.format(
        story_title=story_title,
        mandate=journalist_doc["mandate"],
        jurisdiction=journalist_doc["jurisdiction"],
        evidence_summary=evidence_summary,
    )

    tree: LegalTree = await llm.ainvoke([HumanMessage(content=prompt)])
    tree.tree_id = str(uuid.uuid4())
    tree.journalist_id = journalist_id
    tree.cycle_id = cycle_id
    tree.story_title = story_title

    # Persist to Firestore
    tree_doc = tree.model_dump()
    tree_doc["built_at"] = datetime.datetime.utcnow().isoformat()

    await (
        db.collection("journalists")
        .document(journalist_id)
        .collection("legal_trees")
        .document(tree.tree_id)
        .set(tree_doc)
    )

    await log_action(
        db,
        journalist_id,
        cycle_id,
        "legal_tree_built",
        {
            "tree_id": tree.tree_id,
            "overall_strength": tree.overall_strength,
            "root_node_count": len(tree.root_nodes),
        },
    )
    log.info(
        "legal_tree_built",
        journalist_id=journalist_id,
        tree_id=tree.tree_id,
        strength=tree.overall_strength,
    )
    return tree
