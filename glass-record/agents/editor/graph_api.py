"""
GET /graph/{journalist_id}

Builds a journalist → story → evidence → entity knowledge graph directly
from Firestore data and returns it in the format consumed by react-force-graph-2d:
  { nodes: [{id, label, group}], links: [{source, target, label}] }

Node groups:
  0 = Journalist, 1 = Story, 2 = Evidence, 3 = Entity
"""

import hashlib

from fastapi import APIRouter
from google.cloud import firestore

router = APIRouter(tags=["graph"])


@router.get("/graph/{journalist_id}")
async def get_graph(journalist_id: str) -> dict:
    """Return knowledge graph for a journalist derived from Firestore."""
    db = firestore.AsyncClient()
    nodes: list[dict] = []
    links: list[dict] = []
    seen: set[str] = set()

    def add_node(node_id: str, label: str, group: int) -> None:
        if node_id not in seen:
            nodes.append({"id": node_id, "label": label[:40], "group": group})
            seen.add(node_id)

    # ── Journalist node ──────────────────────────────────────────────────────
    j_node = f"j-{journalist_id}"
    add_node(j_node, journalist_id, 0)

    # ── Story nodes ──────────────────────────────────────────────────────────
    stories_snap = await (
        db.collection("journalists")
        .document(journalist_id)
        .collection("stories")
        .order_by("published_at", direction=firestore.Query.DESCENDING)
        .limit(10)
        .get()
    )
    cycle_to_story: dict[str, str] = {}  # cycle_id → story node_id
    for sd in stories_snap:
        s = sd.to_dict()
        s_node = f"s-{s['story_id']}"
        add_node(s_node, s.get("title", s["story_id"]), 1)
        links.append({"source": j_node, "target": s_node, "label": "Investigated"})
        cycle_to_story[s.get("cycle_id", "")] = s_node

    # ── Evidence nodes ───────────────────────────────────────────────────────
    evidence_snap = await (
        db.collection("journalists")
        .document(journalist_id)
        .collection("evidence_locker")
        .order_by("credibility_score", direction=firestore.Query.DESCENDING)
        .limit(40)
        .get()
    )
    entity_seen: dict[str, str] = {}  # stable key → entity node_id

    for ed in evidence_snap:
        e = ed.to_dict()
        e_node = f"e-{e['evidence_id']}"
        add_node(e_node, e.get("source_title", e["evidence_id"]), 2)

        # Link to journalist (fallback) or to the matching story via cycle_id
        parent = cycle_to_story.get(e.get("cycle_id", ""), j_node)
        links.append({"source": parent, "target": e_node, "label": "Supported By"})

        # ── Entity nodes extracted from this evidence ────────────────────────
        for entity in e.get("entities", []):
            name = entity.get("name", "").strip()
            if not name:
                continue
            key = hashlib.md5(name.lower().encode()).hexdigest()[:8]
            ent_node = f"en-{key}"
            if key not in entity_seen:
                entity_seen[key] = ent_node
                add_node(ent_node, name, 3)
            links.append({"source": e_node, "target": ent_node, "label": "Mentions"})

    return {"nodes": nodes, "links": links}
