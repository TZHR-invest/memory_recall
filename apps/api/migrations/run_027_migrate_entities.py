"""
Migration 027: Migrate entities from memories.metadata->'entities' to entities table

This script:
1. Extracts entities from existing memories.metadata->'entities' JSONB field
2. Populates the entities table
3. Creates memory_entities associations
"""

import asyncio
import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.database import db


async def migrate_entities(batch_size: int = 100):
    """Migrate entities from metadata to entities table"""

    offset = 0
    total_migrated = 0
    total_entities = 0
    total_relations = 0

    while True:
        rows = await db.fetch(
            """
            SELECT id, container_tag, metadata 
            FROM memories 
            WHERE metadata->'entities' IS NOT NULL
            AND is_latest = TRUE
            ORDER BY created_at DESC
            LIMIT $1 OFFSET $2
            """,
            batch_size,
            offset,
        )

        if not rows:
            break

        for row in rows:
            memory_id = row["id"]
            container_tag = row["container_tag"]
            metadata = row["metadata"] or {}
            entities = metadata.get("entities", {})

            if not entities:
                continue

            for entity_type, names in entities.items():
                if not isinstance(names, list):
                    continue

                for name in names:
                    if not name:
                        continue

                    existing = await db.fetchrow(
                        """
                        SELECT id FROM entities 
                        WHERE name = $1 AND container_tag = $2
                        """,
                        name,
                        container_tag,
                    )

                    if existing:
                        await db.execute(
                            """
                            UPDATE entities 
                            SET mention_count = mention_count + 1, updated_at = NOW()
                            WHERE id = $1
                            """,
                            existing["id"],
                        )
                        entity_id = existing["id"]
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
                        entity_id = result["id"]
                        total_entities += 1

                    await db.execute(
                        """
                        INSERT INTO memory_entities (memory_id, entity_id, entity_type)
                        VALUES ($1, $2, $3)
                        ON CONFLICT DO NOTHING
                        """,
                        memory_id,
                        entity_id,
                        entity_type,
                    )

            total_migrated += 1

        offset += batch_size
        print(f"Migrated {total_migrated} memories, {total_entities} new entities...")

    return {
        "memories_migrated": total_migrated,
        "entities_created": total_entities,
        "relations_created": total_relations,
    }


async def main():
    print("Starting entity migration...")
    print("=" * 50)

    result = await migrate_entities()

    print("=" * 50)
    print("Migration completed!")
    print(f"Memories migrated: {result['memories_migrated']}")
    print(f"Entities created: {result['entities_created']}")


if __name__ == "__main__":
    asyncio.run(main())
