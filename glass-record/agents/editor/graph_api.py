"""
GET /graph/{journalist_id}

Queries Neo4j for all nodes and relationships connected to a journalist
and returns them in a format consumed by react-force-graph-2d:
  { nodes: [{id, label, group}], links: [{source, target, label}] }

Node groups map to Neo4j labels:
  Journalist=0, Story=1, Evidence=2, Entity=3, Claim=4
"""

from fastapi import APIRouter, HTTPException

from graph.client import get_driver

router = APIRouter(tags=["graph"])

_GROUP = {
    "Journalist": 0,
    "Story": 1,
    "Evidence": 2,
    "Entity": 3,
    "Claim": 4,
}

_CYPHER = """
MATCH path = (j:Journalist {journalist_id: $journalist_id})-[*1..3]-(n)
WITH collect(path) AS paths
CALL apoc.convert.toTree(paths) YIELD value
WITH paths
UNWIND paths AS p
UNWIND relationships(p) AS r
WITH
  startNode(r) AS src,
  endNode(r)   AS dst,
  type(r)      AS rel_type
RETURN
  id(src) AS src_id,
  labels(src)[0] AS src_label,
  coalesce(src.title, src.name, src.journalist_id, src.evidence_id, src.claim_id, toString(id(src))) AS src_name,
  id(dst) AS dst_id,
  labels(dst)[0] AS dst_label,
  coalesce(dst.title, dst.name, dst.journalist_id, dst.evidence_id, dst.claim_id, toString(id(dst))) AS dst_name,
  rel_type
"""

# Simpler fallback that doesn't require APOC
_CYPHER_SIMPLE = """
MATCH (j:Journalist {journalist_id: $journalist_id})
OPTIONAL MATCH (j)-[r1]->(s:Story)
OPTIONAL MATCH (s)-[r2]->(e:Evidence)
OPTIONAL MATCH (e)-[r3]->(c:Claim)
OPTIONAL MATCH (e)-[r4]->(ent:Entity)
WITH
  collect({src: j, dst: s, rel: r1}) +
  collect({src: s, dst: e, rel: r2}) +
  collect({src: e, dst: c, rel: r3}) +
  collect({src: e, dst: ent, rel: r4}) AS rels
UNWIND rels AS row
WITH row WHERE row.rel IS NOT NULL
RETURN
  id(row.src) AS src_id,
  labels(row.src)[0] AS src_label,
  coalesce(row.src.title, row.src.name, row.src.journalist_id,
           row.src.evidence_id, toString(id(row.src))) AS src_name,
  id(row.dst) AS dst_id,
  labels(row.dst)[0] AS dst_label,
  coalesce(row.dst.title, row.dst.name, row.dst.journalist_id,
           row.dst.evidence_id, toString(id(row.dst))) AS dst_name,
  type(row.rel) AS rel_type
"""


@router.get("/graph/{journalist_id}")
async def get_graph(journalist_id: str) -> dict:
    """Return Neo4j subgraph for a journalist as nodes + links."""
    driver = get_driver()
    try:
        async with driver.session() as session:
            result = await session.run(_CYPHER_SIMPLE, journalist_id=journalist_id)
            rows = await result.data()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Neo4j unavailable: {exc}") from exc

    node_map: dict[int, dict] = {}
    links: list[dict] = []

    for row in rows:
        for nid, nlabel, nname in [
            (row["src_id"], row["src_label"], row["src_name"]),
            (row["dst_id"], row["dst_label"], row["dst_name"]),
        ]:
            if nid not in node_map:
                node_map[nid] = {
                    "id": nid,
                    "label": nname or nlabel,
                    "group": _GROUP.get(nlabel, 5),
                }
        links.append({
            "source": row["src_id"],
            "target": row["dst_id"],
            "label": row["rel_type"].replace("_", " ").title(),
        })

    # If the journalist node itself has no relationships, return it alone
    if not rows:
        try:
            async with driver.session() as session:
                r = await session.run(
                    "MATCH (j:Journalist {journalist_id: $id}) RETURN id(j) AS nid",
                    id=journalist_id,
                )
                rec = await r.single()
                if rec:
                    node_map[rec["nid"]] = {
                        "id": rec["nid"],
                        "label": journalist_id,
                        "group": 0,
                    }
        except Exception:
            pass

    return {"nodes": list(node_map.values()), "links": links}
