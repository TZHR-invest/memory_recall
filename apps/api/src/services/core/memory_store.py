"""
Core memory storage service for simplified memory architecture.
"""

from typing import Optional, List, Dict, Any
from datetime import datetime
from dataclasses import dataclass, field
import json

from src.database import db
from src.embedding.client import get_embedding_client


@dataclass
class Memory:
    id: str
    container_tag: str
    content: str
    embedding: Optional[List[float]] = None
    is_static: bool = False
    is_latest: bool = True
    valid_from: Optional[datetime] = None
    valid_until: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.8
    created_at: Optional[datetime] = None
    is_forgotten: bool = False


class MemoryStore:
    def __init__(self):
        self.embedding_client = get_embedding_client()

    async def create(
        self,
        content: str,
        container_tag: str,
        is_static: bool = False,
        metadata: Optional[Dict[str, Any]] = None,
        generate_embedding: bool = True,
    ) -> Memory:
        embedding = None
        if generate_embedding:
            embedding = await self._generate_embedding(content)

        row = await db.fetchrow(
            """
            INSERT INTO memories (container_tag, content, embedding, is_static, metadata)
            VALUES ($1, $2, $3, $4, $5)
            RETURNING *
            """,
            container_tag,
            content,
            self._embedding_to_str(embedding) if embedding else None,
            is_static,
            json.dumps(metadata or {}),
        )

        return self._row_to_memory(row)

    async def get_by_id(self, memory_id: str) -> Optional[Memory]:
        row = await db.fetchrow(
            "SELECT * FROM memories WHERE id = $1",
            memory_id,
        )
        return self._row_to_memory(row) if row else None

    async def get_by_container(
        self,
        container_tag: str,
        limit: int = 100,
        include_forgotten: bool = False,
    ) -> List[Memory]:
        query = """
            SELECT * FROM memories 
            WHERE container_tag = $1
            AND is_latest = TRUE
        """
        if not include_forgotten:
            query += " AND is_forgotten = FALSE"
        query += " ORDER BY created_at DESC LIMIT $2"

        rows = await db.fetch(query, container_tag, limit)
        return [self._row_to_memory(row) for row in rows]

    async def get_static_memories(
        self,
        container_tag: str,
        limit: int = 50,
    ) -> List[Memory]:
        rows = await db.fetch(
            """
            SELECT * FROM memories 
            WHERE container_tag = $1 
            AND is_static = TRUE 
            AND is_latest = TRUE
            AND is_forgotten = FALSE
            ORDER BY created_at DESC 
            LIMIT $2
            """,
            container_tag,
            limit,
        )
        return [self._row_to_memory(row) for row in rows]

    async def get_dynamic_memories(
        self,
        container_tag: str,
        limit: int = 20,
    ) -> List[Memory]:
        rows = await db.fetch(
            """
            SELECT * FROM memories 
            WHERE container_tag = $1 
            AND is_static = FALSE 
            AND is_latest = TRUE
            AND is_forgotten = FALSE
            ORDER BY created_at DESC 
            LIMIT $2
            """,
            container_tag,
            limit,
        )
        return [self._row_to_memory(row) for row in rows]

    async def search(
        self,
        query: str,
        container_tag: str,
        limit: int = 10,
        threshold: float = 0.6,
    ) -> List[Dict[str, Any]]:
        query_embedding = await self._generate_embedding(query)

        rows = await db.fetch(
            """
            SELECT 
                id, content, metadata, confidence, created_at,
                1 - (embedding <=> $1::vector) as similarity
            FROM memories
            WHERE container_tag = $2
            AND is_latest = TRUE
            AND is_forgotten = FALSE
            AND 1 - (embedding <=> $1::vector) > $3
            ORDER BY similarity DESC
            LIMIT $4
            """,
            self._embedding_to_str(query_embedding),
            container_tag,
            threshold,
            limit,
        )

        return [
            {
                "id": row["id"],
                "content": row["content"],
                "metadata": row["metadata"],
                "confidence": row["confidence"],
                "created_at": row["created_at"].isoformat()
                if row["created_at"]
                else None,
                "similarity": float(row["similarity"]) if row["similarity"] else 0.0,
            }
            for row in rows
        ]

    async def forget(self, memory_id: str) -> bool:
        result = await db.execute(
            """
            UPDATE memories 
            SET is_forgotten = TRUE, updated_at = NOW()
            WHERE id = $1
            """,
            memory_id,
        )
        return result == "UPDATE 1"

    async def restore(self, memory_id: str) -> bool:
        result = await db.execute(
            """
            UPDATE memories 
            SET is_forgotten = FALSE, updated_at = NOW()
            WHERE id = $1
            """,
            memory_id,
        )
        return result == "UPDATE 1"

    async def update_metadata(
        self,
        memory_id: str,
        metadata: Dict[str, Any],
    ) -> bool:
        result = await db.execute(
            """
            UPDATE memories 
            SET metadata = $1, updated_at = NOW()
            WHERE id = $2
            """,
            json.dumps(metadata),
            memory_id,
        )
        return result == "UPDATE 1"

    async def create_update_version(
        self,
        memory_id: str,
        new_content: str,
    ) -> Optional[Memory]:
        old_memory = await self.get_by_id(memory_id)
        if not old_memory:
            return None

        new_memory = await self.create(
            content=new_content,
            container_tag=old_memory.container_tag,
            is_static=old_memory.is_static,
            metadata=old_memory.metadata,
        )

        await db.execute(
            """
            INSERT INTO memory_relations_new (from_memory_id, to_memory_id, relation_type)
            VALUES ($1, $2, 'updates')
            """,
            new_memory.id,
            memory_id,
        )

        await db.execute(
            """
            UPDATE memories 
            SET is_latest = FALSE, valid_until = NOW(), updated_at = NOW()
            WHERE id = $1
            """,
            memory_id,
        )

        return new_memory

    async def _generate_embedding(self, text: str) -> List[float]:
        if not self.embedding_client:
            return []
        try:
            result = await self.embedding_client.embed(text)
            return result
        except Exception:
            return []

    def _embedding_to_str(self, embedding: Optional[List[float]]) -> Optional[str]:
        if not embedding:
            return None
        return "[" + ",".join(map(str, embedding)) + "]"

    def _row_to_memory(self, row: Dict) -> Memory:
        return Memory(
            id=row["id"],
            container_tag=row["container_tag"],
            content=row["content"],
            embedding=self._parse_embedding(row.get("embedding")),
            is_static=row.get("is_static", False),
            is_latest=row.get("is_latest", True),
            valid_from=row.get("valid_from"),
            valid_until=row.get("valid_until"),
            metadata=row.get("metadata", {}) or {},
            confidence=row.get("confidence", 0.8),
            created_at=row.get("created_at"),
            is_forgotten=row.get("is_forgotten", False),
        )

    def _parse_embedding(self, embedding_str: Optional[str]) -> Optional[List[float]]:
        if not embedding_str:
            return None
        try:
            return [float(x) for x in embedding_str.strip("[]").split(",")]
        except Exception:
            return None


memory_store = MemoryStore()
