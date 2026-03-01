// The Glass Record — Neo4j Schema
// Run once on a fresh database: cypher-shell -f graph/schema.cypher

// ── Constraints (uniqueness + implicit index) ────────────────────────────────

CREATE CONSTRAINT journalist_id_unique IF NOT EXISTS
  FOR (j:Journalist) REQUIRE j.journalist_id IS UNIQUE;

CREATE CONSTRAINT story_id_unique IF NOT EXISTS
  FOR (s:Story) REQUIRE s.story_id IS UNIQUE;

CREATE CONSTRAINT evidence_id_unique IF NOT EXISTS
  FOR (e:Evidence) REQUIRE e.evidence_id IS UNIQUE;

CREATE CONSTRAINT entity_id_unique IF NOT EXISTS
  FOR (n:Entity) REQUIRE n.entity_id IS UNIQUE;

CREATE CONSTRAINT claim_id_unique IF NOT EXISTS
  FOR (c:Claim) REQUIRE c.claim_id IS UNIQUE;

// ── Node labels and properties (documentation) ──────────────────────────────
//
// (:Journalist {journalist_id, mandate, jurisdiction, tier, created_at})
// (:Story      {story_id, title, cycle_id, published_at, ghost_post_id})
// (:Evidence   {evidence_id, source_url, source_title, credibility_score, gcs_path, collected_at})
// (:Claim      {claim_id, text, confidence})
// (:Entity     {entity_id, name, type})
//   Entity types: PERSON | ORGANIZATION | LOCATION | STATUTE | DATE | AMOUNT
//
// ── Relationships ────────────────────────────────────────────────────────────
//
// (:Journalist)-[:INVESTIGATED {cycle_id}]->(:Story)
// (:Story)-[:SUPPORTED_BY]->(:Evidence)
// (:Evidence)-[:CONTAINS]->(:Claim)
// (:Claim)-[:MENTIONS]->(:Entity)
// (:Entity)-[:RELATED_TO {relationship_type}]->(:Entity)
