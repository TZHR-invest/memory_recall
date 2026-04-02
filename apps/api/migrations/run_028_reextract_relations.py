"""
Migration 028: Re-extract entity relations from memory content using LLM

This script:
1. Finds memories without entity relations
2. Uses LLM to extract entities and relations
3. Populates entity_relations table
"""

import asyncio
import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.database import db
from src.services.core.llm_entity_extraction import llm_entity_extractor


async def extract_relations_for_memory(
    memory_id: str, content: str, container_tag: str
):
    """Extract entities and relations for a single memory"""

    try:
        extraction = await llm_entity_extractor.extract_with_relations(content)

        entities = extraction.get("entities", [])
        relations = extraction.get("relations", [])

        entity_ids = {}

        for entity in entities:
            name = entity.get("name")
            entity_type = entity.get("type", "unknown")

            if not name:
                continue

            existing = await db.fetchrow(
                "SELECT id FROM entities WHERE name = $1 AND container_tag = $2",
                name,
                container_tag,
            )

            if existing:
                await db.execute(
                    "UPDATE entities SET mention_count = mention_count + 1 WHERE id = $1",
                    existing["id"],
                )
                entity_ids[name] = str(existing["id"])
            else:
                result = await db.fetchrow(
                    """
                    INSERT INTO entities (name, type, container_tag)
                    VALUES ($1, $2, $3)
                    RETURNING id
                    """,
                    name,
                    entity_type,
                    container_tag,
                )
                entity_ids[name] = str(result["id"]) if result else None

        relations_created = 0
        for relation in relations:
            from_entity = relation.get("from")
            to_entity = relation.get("to")
            relation_type = relation.get("type")

            if not all([from_entity, to_entity, relation_type]):
                continue

            from_id = entity_ids.get(from_entity)
            to_id = entity_ids.get(to_entity)

            if not from_id or not to_id:
                continue

            await db.execute(
                """
                INSERT INTO entity_relations 
                (from_entity_id, to_entity_id, relation_type, container_tag, source_memory_id)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT DO NOTHING
                """,
                from_id,
                to_id,
                relation_type,
                container_tag,
                memory_id,
            )
            relations_created += 1

        return len(entities), relations_created

    except Exception as e:
        print(f"Error processing memory {memory_id}: {e}")
        return 0, 0


async def reextract_relations(batch_size: int = 50, limit: int = 1000):
    """Re-extract relations for memories that don't have them"""

    offset = 0
    total_processed = 0
    total_entities = 0
    total_relations = 0

    while total_processed < limit:
        rows = await db.fetch(
            """
            SELECT m.id, m.content, m.container_tag
            FROM memories m
            WHERE m.is_latest = TRUE
            AND NOT EXISTS (
                SELECT 1 FROM entity_relations er WHERE er.source_memory_id = m.id
            )
            ORDER BY m.created_at DESC
            LIMIT $1 OFFSET $2
            """,
            batch_size,
            offset,
        )

        if not rows:
            break

        for row in rows:
            entities_count, relations_count = await extract_relations_for_memory(
                row["id"], row["content"], row["container_tag"]
            )
            total_entities += entities_count
            total_relations += relations_count
            total_processed += 1

            if total_processed % 10 == 0:
                print(
                    f"Processed {total_processed} memories, {total_relations} relations..."
                )

        offset += batch_size

    return {
        "memories_processed": total_processed,
        "entities_extracted": total_entities,
        "relations_created": total_relations,
    }


async def main():
    print("Starting relation re-extraction...")
    print("=" * 50)

    result = await reextract_relations()

    print("=" * 50)
    print("Re-extraction completed!")
    print(f"Memories processed: {result['memories_processed']}")
    print(f"Entities extracted: {result['entities_extracted']}")
    print(f"Relations created: {result['relations_created']}")


if __name__ == "__main__":
    asyncio.run(main())
