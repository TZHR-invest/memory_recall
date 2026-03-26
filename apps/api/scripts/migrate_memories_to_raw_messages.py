import asyncio
import json
from pathlib import Path
import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path)

from src.database import db
from src.embedding.client import get_embedding_client


async def migrate_memories_to_raw_messages():
    embedding_client = get_embedding_client()

    await db.connect()

    try:
        users = await db.fetch("""
            SELECT DISTINCT user_id FROM (
                SELECT user_id FROM public.memories
                UNION
                SELECT schema_name REPLACE(schema_name, 'user_', '') as user_id 
                FROM information_schema.schemata 
                WHERE schema_name LIKE 'user_%'
            ) u
        """)

        print(f"Found {len(users)} users to migrate")

        total_migrated = 0
        total_skipped = 0

        for user_row in users:
            user_id = user_row["user_id"]
            print(f"\nProcessing user: {user_id}")

            try:
                await db.init_user(user_id)
            except Exception as e:
                print(f"  Failed to init user: {e}")
                continue

            async with db.user_context(user_id):
                memories = await db.fetch("""
                    SELECT id, content, input_type, created_at,
                           time_value, location_name, location_address,
                           location_latitude, location_longitude,
                           people, emotion, tags, embedding,
                           importance_score, status
                    FROM memories
                    WHERE status = 'active'
                    ORDER BY created_at ASC
                """)

                print(f"  Found {len(memories)} memories")

                for mem in memories:
                    mem_id = mem["id"]

                    exists = await db.fetchval(
                        "SELECT 1 FROM raw_messages WHERE id = $1", mem_id
                    )

                    if exists:
                        total_skipped += 1
                        continue

                    content = mem["content"]

                    embedding = None
                    if mem["embedding"]:
                        try:
                            if isinstance(mem["embedding"], str):
                                embedding = json.loads(mem["embedding"])
                            else:
                                embedding = list(mem["embedding"])
                        except:
                            pass

                    if not embedding:
                        try:
                            embedding = embedding_client.embed(content)
                        except Exception as e:
                            print(
                                f"    Warning: Failed to generate embedding for {mem_id}: {e}"
                            )

                    embedding_str = None
                    if embedding:
                        embedding_str = "[" + ",".join(map(str, embedding)) + "]"

                    memory_type = "preference"
                    if mem["input_type"] == "segment":
                        memory_type = "note"

                    await db.execute(
                        """
                        INSERT INTO raw_messages (
                            id, user_id, agent_id, memory_type,
                            role, content, token_count,
                            time_value, location_name, location_address,
                            location_latitude, location_longitude,
                            people, emotion, tags, embedding,
                            source_type, input_type, importance_score,
                            created_at, is_archived
                        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19, $20, $21)
                    """,
                        mem_id,
                        user_id,
                        None,
                        memory_type,
                        "user",
                        content,
                        max(1, len(content) // 4),
                        mem["time_value"],
                        mem["location_name"],
                        mem["location_address"],
                        mem["location_latitude"],
                        mem["location_longitude"],
                        mem["people"] or "[]",
                        mem["emotion"] or "{}",
                        mem["tags"] or "[]",
                        embedding_str,
                        "migrated",
                        mem["input_type"] or "text",
                        mem["importance_score"] or 0.5,
                        mem["created_at"],
                        mem["status"] == "archived",
                    )

                    total_migrated += 1

                    if total_migrated % 100 == 0:
                        print(f"  Migrated {total_migrated} memories...")

        print(f"\n{'=' * 50}")
        print(f"Migration completed!")
        print(f"  Total migrated: {total_migrated}")
        print(f"  Total skipped (already exists): {total_skipped}")

    finally:
        await db.disconnect()


if __name__ == "__main__":
    asyncio.run(migrate_memories_to_raw_messages())
