"""
Memory Fusion Service

Detects and merges similar memories.
Prevents duplicate storage.
"""

from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
import uuid


class FusionService:
    """Memory fusion and deduplication"""

    SIMILARITY_THRESHOLD = 0.95
    OVERLAP_THRESHOLD = 0.7

    async def detect_similar(
        self,
        user_id: str,
        content: str,
        embedding: List[float],
        exclude_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Find similar memories using embedding similarity"""
        from src.database import db

        embedding_str = "[" + ",".join(map(str, embedding)) + "]"

        async with db.user_context(user_id):
            query = """
                SELECT id, content, embedding <=> $1::vector as distance,
                       created_at, memory_type
                FROM raw_messages
                WHERE user_id = $2 AND is_expired = FALSE
            """
            params = [embedding_str, user_id]

            if exclude_id:
                query += " AND id != $3"
                params.append(exclude_id)

            query += " ORDER BY distance LIMIT 5"

            rows = await db.fetch(query, *params)

        similar = []
        for row in rows:
            similarity = 1 - row["distance"]
            if similarity >= self.SIMILARITY_THRESHOLD:
                similar.append(
                    {
                        "id": row["id"],
                        "content": row["content"],
                        "similarity": similarity,
                        "created_at": row["created_at"],
                        "memory_type": row["memory_type"],
                    }
                )

        return similar

    async def should_fuse(
        self,
        user_id: str,
        content: str,
        embedding: List[float],
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """Determine if new memory should be fused with existing"""
        similar = await self.detect_similar(user_id, content, embedding)

        if not similar:
            return False, None, None

        best_match = similar[0]

        if best_match["similarity"] >= 0.98:
            return True, best_match["id"], "duplicate"

        if best_match["similarity"] >= self.SIMILARITY_THRESHOLD:
            return True, best_match["id"], "extend"

        return False, None, None

    async def create_fusion_relation(
        self,
        user_id: str,
        source_id: str,
        target_id: str,
        relation_type: str,
    ) -> str:
        """Create a relation between fused memories"""
        from src.database import db

        relation_id = str(uuid.uuid4())

        async with db.user_context(user_id):
            await db.execute(
                """
                INSERT INTO memory_relations (
                    id, user_id, source_memory_id, target_memory_id,
                    relation_type, confidence, detected_by, created_at
                ) VALUES ($1, $2, $3, $4, $5, 0.95, 'fusion', NOW())
                """,
                relation_id,
                user_id,
                source_id,
                target_id,
                relation_type,
            )

        return relation_id

    async def merge_memories(
        self,
        user_id: str,
        primary_id: str,
        secondary_id: str,
        strategy: str = "keep_newer",
    ) -> Dict[str, Any]:
        """Merge two similar memories"""
        from src.database import db

        async with db.user_context(user_id):
            primary = await db.fetchrow(
                "SELECT * FROM raw_messages WHERE id = $1",
                primary_id,
            )
            secondary = await db.fetchrow(
                "SELECT * FROM raw_messages WHERE id = $1",
                secondary_id,
            )

            if not primary or not secondary:
                return {"success": False, "error": "Memory not found"}

            if strategy == "keep_newer":
                if primary["created_at"] < secondary["created_at"]:
                    primary, secondary = secondary, primary
                    primary_id, secondary_id = secondary_id, primary_id

                await db.execute(
                    "UPDATE raw_messages SET is_expired = TRUE WHERE id = $1",
                    secondary_id,
                )

                await self.create_fusion_relation(
                    user_id, primary_id, secondary_id, "supersedes"
                )

                return {
                    "success": True,
                    "action": "superseded",
                    "kept_id": primary_id,
                    "expired_id": secondary_id,
                }

            elif strategy == "extend":
                await self.create_fusion_relation(
                    user_id, secondary_id, primary_id, "extends"
                )

                return {
                    "success": True,
                    "action": "extended",
                    "original_id": primary_id,
                    "extending_id": secondary_id,
                }

        return {"success": False, "error": "Unknown strategy"}

    async def find_duplicates(
        self,
        user_id: str,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Find potential duplicate memories for review"""
        from src.database import db

        async with db.user_context(user_id):
            rows = await db.fetch(
                """
                SELECT 
                    m1.id as id1, m1.content as content1,
                    m2.id as id2, m2.content as content2,
                    m1.embedding <=> m2.embedding as distance
                FROM raw_messages m1
                JOIN raw_messages m2 ON m1.id < m2.id AND m1.user_id = m2.user_id
                WHERE m1.user_id = $1
                  AND m1.is_expired = FALSE
                  AND m2.is_expired = FALSE
                  AND m1.embedding <=> m2.embedding < 0.1
                ORDER BY distance
                LIMIT $2
                """,
                user_id,
                limit,
            )

        return [
            {
                "memory1": {"id": row["id1"], "content": row["content1"][:100]},
                "memory2": {"id": row["id2"], "content": row["content2"][:100]},
                "similarity": 1 - row["distance"],
            }
            for row in rows
        ]


fusion_service = FusionService()
