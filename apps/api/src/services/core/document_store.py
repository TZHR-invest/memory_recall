"""
Document storage service for optional document management.
"""

from typing import Optional, List, Dict, Any
from datetime import datetime
from dataclasses import dataclass, field
import json

from src.database import db


@dataclass
class Document:
    id: str
    container_tag: str
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    status: str = "done"
    created_at: Optional[datetime] = None


class DocumentStore:
    async def create(
        self,
        content: str,
        container_tag: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Document:
        row = await db.fetchrow(
            """
            INSERT INTO documents_new (container_tag, content, metadata)
            VALUES ($1, $2, $3)
            RETURNING *
            """,
            container_tag,
            content,
            json.dumps(metadata or {}),
        )

        return self._row_to_document(row)

    async def get_by_id(self, document_id: str) -> Optional[Document]:
        row = await db.fetchrow(
            "SELECT * FROM documents_new WHERE id = $1",
            document_id,
        )
        return self._row_to_document(row) if row else None

    async def get_by_container(
        self,
        container_tag: str,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Document]:
        rows = await db.fetch(
            """
            SELECT * FROM documents_new
            WHERE container_tag = $1
            ORDER BY created_at DESC
            LIMIT $2 OFFSET $3
            """,
            container_tag,
            limit,
            offset,
        )
        return [self._row_to_document(row) for row in rows]

    async def delete(self, document_id: str) -> bool:
        result = await db.execute(
            "DELETE FROM documents_new WHERE id = $1",
            document_id,
        )
        return result == "DELETE 1"

    async def update_status(
        self,
        document_id: str,
        status: str,
    ) -> bool:
        if status not in ["queued", "processing", "done"]:
            raise ValueError(f"Invalid status: {status}")

        result = await db.execute(
            """
            UPDATE documents_new SET status = $1
            WHERE id = $2
            """,
            status,
            document_id,
        )
        return result == "UPDATE 1"

    async def count(self, container_tag: str) -> int:
        return await db.fetchval(
            "SELECT COUNT(*) FROM documents_new WHERE container_tag = $1",
            container_tag,
        )

    def _row_to_document(self, row: Dict) -> Document:
        return Document(
            id=row["id"],
            container_tag=row["container_tag"],
            content=row["content"],
            metadata=row.get("metadata", {}) or {},
            status=row.get("status", "done"),
            created_at=row.get("created_at"),
        )


document_store = DocumentStore()
