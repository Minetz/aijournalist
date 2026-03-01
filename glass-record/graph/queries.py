"""Cypher query library for The Glass Record knowledge graph."""

from neo4j import AsyncDriver


async def upsert_journalist(driver: AsyncDriver, journalist_id: str, mandate: str,
                             jurisdiction: str, tier: str) -> None:
    async with driver.session() as session:
        await session.run(
            """
            MERGE (j:Journalist {journalist_id: $journalist_id})
            ON CREATE SET j.mandate = $mandate,
                          j.jurisdiction = $jurisdiction,
                          j.tier = $tier,
                          j.created_at = datetime()
            """,
            journalist_id=journalist_id, mandate=mandate,
            jurisdiction=jurisdiction, tier=tier,
        )


async def upsert_story(driver: AsyncDriver, journalist_id: str, story_id: str,
                        title: str, cycle_id: str) -> None:
    async with driver.session() as session:
        await session.run(
            """
            MERGE (s:Story {story_id: $story_id})
            ON CREATE SET s.title = $title, s.cycle_id = $cycle_id, s.created_at = datetime()
            WITH s
            MATCH (j:Journalist {journalist_id: $journalist_id})
            MERGE (j)-[:INVESTIGATED {cycle_id: $cycle_id}]->(s)
            """,
            journalist_id=journalist_id, story_id=story_id,
            title=title, cycle_id=cycle_id,
        )


async def upsert_evidence(driver: AsyncDriver, story_id: str, evidence_id: str,
                           source_url: str, source_title: str,
                           credibility_score: float, gcs_path: str) -> None:
    async with driver.session() as session:
        await session.run(
            """
            MERGE (e:Evidence {evidence_id: $evidence_id})
            ON CREATE SET e.source_url = $source_url,
                          e.source_title = $source_title,
                          e.credibility_score = $credibility_score,
                          e.gcs_path = $gcs_path,
                          e.collected_at = datetime()
            WITH e
            MATCH (s:Story {story_id: $story_id})
            MERGE (s)-[:SUPPORTED_BY]->(e)
            """,
            evidence_id=evidence_id, story_id=story_id,
            source_url=source_url, source_title=source_title,
            credibility_score=credibility_score, gcs_path=gcs_path,
        )


async def upsert_entity(driver: AsyncDriver, entity_id: str, name: str,
                         entity_type: str) -> None:
    async with driver.session() as session:
        await session.run(
            """
            MERGE (n:Entity {entity_id: $entity_id})
            ON CREATE SET n.name = $name, n.type = $entity_type
            """,
            entity_id=entity_id, name=name, entity_type=entity_type,
        )
