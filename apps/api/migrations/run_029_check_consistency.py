"""
Data Consistency Check Script

This script verifies:
1. entities table consistency with memories.metadata->'entities'
2. memory_entities association integrity
3. entity_relations referential integrity
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.database import db


async def check_entity_consistency():
    """Check if entities in metadata match entities table"""

    rows = await db.fetch(
        """
        SELECT m.id, m.container_tag, m.metadata->'entities' as metadata_entities
        FROM memories m
        WHERE m.metadata->'entities' IS NOT NULL
        AND m.is_latest = TRUE
        LIMIT 1000
        """
    )

    consistent = 0
    inconsistent = 0

    for row in rows:
        memory_id = row["id"]
        container_tag = row["container_tag"]
        metadata_entities = row["metadata_entities"] or {}

        db_entities = await db.fetch(
            """
            SELECT e.name, e.type
            FROM entities e
            JOIN memory_entities me ON e.id = me.entity_id
            WHERE me.memory_id = $1
            """,
            memory_id,
        )

        db_entity_map = {}
        for e in db_entities:
            etype = e["type"]
            if etype not in db_entity_map:
                db_entity_map[etype] = set()
            db_entity_map[etype].add(e["name"])

        is_consistent = True
        for etype, names in metadata_entities.items():
            if not isinstance(names, list):
                continue
            db_names = db_entity_map.get(etype, set())
            meta_names = set(names)
            if db_names != meta_names:
                is_consistent = False
                break

        if is_consistent:
            consistent += 1
        else:
            inconsistent += 1

    return {"consistent": consistent, "inconsistent": inconsistent}


async def check_memory_entities_integrity():
    """Check if all memory_entities point to valid memories and entities"""

    orphan_links = await db.fetch(
        """
        SELECT me.id, me.memory_id, me.entity_id
        FROM memory_entities me
        WHERE NOT EXISTS (SELECT 1 FROM memories m WHERE m.id = me.memory_id)
        OR NOT EXISTS (SELECT 1 FROM entities e WHERE e.id = me.entity_id)
        """
    )

    return {"orphan_links": len(orphan_links)}


async def check_entity_relations_integrity():
    """Check if all entity_relations point to valid entities"""

    orphan_relations = await db.fetch(
        """
        SELECT er.id, er.from_entity_id, er.to_entity_id
        FROM entity_relations er
        WHERE NOT EXISTS (SELECT 1 FROM entities e WHERE e.id = er.from_entity_id)
        OR NOT EXISTS (SELECT 1 FROM entities e WHERE e.id = er.to_entity_id)
        """
    )

    return {"orphan_relations": len(orphan_relations)}


async def generate_report():
    """Generate data quality report"""

    print("Data Consistency Check")
    print("=" * 50)

    total_memories = await db.fetchval(
        "SELECT COUNT(*) FROM memories WHERE is_latest = TRUE"
    )
    total_entities = await db.fetchval("SELECT COUNT(*) FROM entities")
    total_relations = await db.fetchval("SELECT COUNT(*) FROM entity_relations")
    total_links = await db.fetchval("SELECT COUNT(*) FROM memory_entities")

    print(f"\nStatistics:")
    print(f"  Total memories: {total_memories}")
    print(f"  Total entities: {total_entities}")
    print(f"  Total relations: {total_relations}")
    print(f"  Total memory-entity links: {total_links}")

    print(f"\nChecking entity consistency...")
    entity_check = await check_entity_consistency()
    print(f"  Consistent: {entity_check['consistent']}")
    print(f"  Inconsistent: {entity_check['inconsistent']}")

    print(f"\nChecking memory_entities integrity...")
    me_check = await check_memory_entities_integrity()
    print(f"  Orphan links: {me_check['orphan_links']}")

    print(f"\nChecking entity_relations integrity...")
    er_check = await check_entity_relations_integrity()
    print(f"  Orphan relations: {er_check['orphan_relations']}")

    print("\n" + "=" * 50)

    if (
        entity_check["inconsistent"] == 0
        and me_check["orphan_links"] == 0
        and er_check["orphan_relations"] == 0
    ):
        print("✅ All checks passed!")
    else:
        print("⚠️  Some issues found, review above.")


async def main():
    await generate_report()


if __name__ == "__main__":
    asyncio.run(main())
