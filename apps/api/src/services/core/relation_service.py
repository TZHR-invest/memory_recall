"""
Relation service for memory relationships (updates/extends/derives).
"""

from typing import Optional, List, Dict, Any
from datetime import datetime
from dataclasses import dataclass
from enum import Enum

from src.database import db


class RelationType(Enum):
    UPDATES = "updates"
    EXTENDS = "extends"
    DERIVES = "derives"


@dataclass
class MemoryRelation:
    id: str
    from_memory_id: str
    to_memory_id: str
    relation_type: str
    confidence: float
    created_at: datetime


class RelationService:
    async def create(
        self,
        from_memory_id: str,
        to_memory_id: str,
        relation_type: str,
        confidence: float = 0.8,
    ) -> MemoryRelation:
        if relation_type not in [r.value for r in RelationType]:
            raise ValueError(f"Invalid relation type: {relation_type}")

        row = await db.fetchrow(
            """
            INSERT INTO memory_relations_new (from_memory_id, to_memory_id, relation_type, confidence)
            VALUES ($1, $2, $3, $4)
            RETURNING *
            """,
            from_memory_id,
            to_memory_id,
            relation_type,
            confidence,
        )

        return self._row_to_relation(row)

    async def get_by_memory(self, memory_id: str) -> List[MemoryRelation]:
        rows = await db.fetch(
            """
            SELECT * FROM memory_relations_new
            WHERE from_memory_id = $1 OR to_memory_id = $1
            ORDER BY created_at DESC
            """,
            memory_id,
        )
        return [self._row_to_relation(row) for row in rows]

    async def get_version_history(self, memory_id: str) -> List[Dict[str, Any]]:
        visited = set()
        history = []

        async def traverse(mid: str, depth: int = 0):
            if mid in visited or depth > 10:
                return
            visited.add(mid)

            relations = await db.fetch(
                """
                SELECT r.*, m.content, m.created_at, m.is_latest
                FROM memory_relations_new r
                JOIN memories m ON r.to_memory_id = m.id
                WHERE r.from_memory_id = $1 AND r.relation_type = 'updates'
                """,
                mid,
            )

            for row in relations:
                history.append(
                    {
                        "id": row["to_memory_id"],
                        "content": row["content"],
                        "created_at": row["created_at"].isoformat()
                        if row["created_at"]
                        else None,
                        "is_latest": row["is_latest"],
                        "depth": depth,
                    }
                )
                await traverse(row["to_memory_id"], depth + 1)

        await traverse(memory_id)
        return sorted(history, key=lambda x: x["created_at"], reverse=True)

    async def get_related_memories(
        self,
        memory_id: str,
        relation_types: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        types = relation_types or [r.value for r in RelationType]
        placeholders = ",".join(f"'{t}'" for t in types)

        rows = await db.fetch(
            f"""
            SELECT r.relation_type, r.confidence, m.id, m.content, m.created_at
            FROM memory_relations_new r
            JOIN memories m ON (
                CASE 
                    WHEN r.from_memory_id = $1 THEN r.to_memory_id
                    ELSE r.from_memory_id
                END = m.id
            )
            WHERE (r.from_memory_id = $1 OR r.to_memory_id = $1)
            AND r.relation_type IN ({placeholders})
            AND m.is_forgotten = FALSE
            ORDER BY r.created_at DESC
            """,
            memory_id,
        )

        return [
            {
                "id": row["id"],
                "content": row["content"],
                "relation_type": row["relation_type"],
                "confidence": row["confidence"],
                "created_at": row["created_at"].isoformat()
                if row["created_at"]
                else None,
            }
            for row in rows
        ]

    async def delete(self, relation_id: str) -> bool:
        result = await db.execute(
            "DELETE FROM memory_relations_new WHERE id = $1",
            relation_id,
        )
        return result == "DELETE 1"

    def _row_to_relation(self, row: Dict) -> MemoryRelation:
        return MemoryRelation(
            id=str(row["id"]),
            from_memory_id=row["from_memory_id"],
            to_memory_id=row["to_memory_id"],
            relation_type=row["relation_type"],
            confidence=row["confidence"],
            created_at=row["created_at"],
        )


relation_service = RelationService()
