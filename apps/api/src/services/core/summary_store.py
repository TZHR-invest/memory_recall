import uuid
import json
from typing import Optional, List, Dict, Any
from datetime import datetime

from src.database import db
from src.models.lossless import Summary, SummaryKind, CompressionLevel


class SummaryStore:
    def generate_id(self) -> str:
        return f"sum_{uuid.uuid4().hex[:16]}"

    async def create_summary(
        self,
        user_id: str,
        content: str,
        kind: SummaryKind = "leaf",
        agent_id: Optional[str] = None,
        depth: int = 0,
        token_count: int = 0,
        earliest_at: Optional[datetime] = None,
        latest_at: Optional[datetime] = None,
        descendant_count: int = 0,
        descendant_token_count: int = 0,
        source_message_token_count: int = 0,
        document_id: Optional[str] = None,
        model: str = "unknown",
        compression_level: CompressionLevel = "normal",
        embedding: Optional[List[float]] = None,
    ) -> str:
        summary_id = self.generate_id()

        embedding_str = None
        if embedding:
            embedding_str = "[" + ",".join(map(str, embedding)) + "]"

        await db.execute(
            """
            INSERT INTO summaries (
                summary_id, user_id, agent_id, kind, depth, content, token_count,
                embedding, earliest_at, latest_at, descendant_count,
                descendant_token_count, source_message_token_count,
                document_id, model, compression_level
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16)
        """,
            summary_id,
            user_id,
            agent_id,
            kind,
            depth,
            content,
            token_count,
            embedding_str,
            earliest_at,
            latest_at,
            descendant_count,
            descendant_token_count,
            source_message_token_count,
            document_id,
            model,
            compression_level,
        )

        return summary_id

    async def get_summary(self, summary_id: str) -> Optional[Summary]:
        row = await db.fetchrow(
            "SELECT * FROM summaries WHERE summary_id = $1", summary_id
        )

        if not row:
            return None

        return self._row_to_model(row)

    async def link_message(
        self, summary_id: str, message_id: str, ordinal: int
    ) -> None:
        await db.execute(
            """
            INSERT INTO summary_messages (summary_id, message_id, ordinal)
            VALUES ($1, $2, $3)
            ON CONFLICT (summary_id, message_id) DO UPDATE SET ordinal = $3
        """,
            summary_id,
            message_id,
            ordinal,
        )

    async def link_messages(self, summary_id: str, message_ids: List[str]) -> None:
        for idx, message_id in enumerate(message_ids):
            await self.link_message(summary_id, message_id, idx)

    async def link_parent(
        self, summary_id: str, parent_summary_id: str, ordinal: int
    ) -> None:
        await db.execute(
            """
            INSERT INTO summary_parents (summary_id, parent_summary_id, ordinal)
            VALUES ($1, $2, $3)
            ON CONFLICT (summary_id, parent_summary_id) DO UPDATE SET ordinal = $3
        """,
            summary_id,
            parent_summary_id,
            ordinal,
        )

    async def link_parents(self, summary_id: str, parent_ids: List[str]) -> None:
        for idx, parent_id in enumerate(parent_ids):
            await self.link_parent(summary_id, parent_id, idx)

    async def link_entity(
        self,
        summary_id: str,
        entity_id: str,
        role: str = "mentioned",
        confidence: float = 0.8,
    ) -> None:
        await db.execute(
            """
            INSERT INTO summary_entities (summary_id, entity_id, role, confidence)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (summary_id, entity_id) DO UPDATE SET role = $3, confidence = $4
        """,
            summary_id,
            entity_id,
            role,
            confidence,
        )

    async def get_summary_messages(self, summary_id: str) -> List[str]:
        rows = await db.fetch(
            """
            SELECT message_id FROM summary_messages
            WHERE summary_id = $1
            ORDER BY ordinal
        """,
            summary_id,
        )

        return [row["message_id"] for row in rows]

    async def get_summary_parents(self, summary_id: str) -> List[Summary]:
        rows = await db.fetch(
            """
            SELECT s.* FROM summaries s
            JOIN summary_parents sp ON sp.parent_summary_id = s.summary_id
            WHERE sp.summary_id = $1
            ORDER BY sp.ordinal
        """,
            summary_id,
        )

        return [self._row_to_model(row) for row in rows]

    async def get_summary_children(self, parent_summary_id: str) -> List[Summary]:
        rows = await db.fetch(
            """
            SELECT s.* FROM summaries s
            JOIN summary_parents sp ON sp.summary_id = s.summary_id
            WHERE sp.parent_summary_id = $1
            ORDER BY sp.ordinal
        """,
            parent_summary_id,
        )

        return [self._row_to_model(row) for row in rows]

    async def get_summary_subtree(self, summary_id: str) -> List[Dict[str, Any]]:
        rows = await db.fetch(
            """
            WITH RECURSIVE subtree(summary_id, parent_summary_id, depth_from_root, path) AS (
                SELECT $1, NULL, 0, ''
                
                UNION ALL
                
                SELECT
                    sp.summary_id,
                    sp.parent_summary_id,
                    subtree.depth_from_root + 1,
                    CASE
                        WHEN subtree.path = '' THEN printf('%04d', sp.ordinal)
                        ELSE subtree.path || '.' || printf('%04d', sp.ordinal)
                    END
                FROM summary_parents sp
                JOIN subtree ON sp.parent_summary_id = subtree.summary_id
            )
            SELECT
                s.*,
                subtree.depth_from_root,
                subtree.parent_summary_id,
                subtree.path
            FROM subtree
            JOIN summaries s ON s.summary_id = subtree.summary_id
            ORDER BY subtree.depth_from_root ASC, subtree.path ASC, s.created_at ASC
        """,
            summary_id,
        )

        seen = set()
        result = []
        for row in rows:
            if row["summary_id"] in seen:
                continue
            seen.add(row["summary_id"])

            summary = self._row_to_model(row)
            result.append(
                {
                    "summary": summary,
                    "depth_from_root": row["depth_from_root"],
                    "parent_summary_id": row["parent_summary_id"],
                    "path": row["path"],
                }
            )

        return result

    async def update_embedding(self, summary_id: str, embedding: List[float]) -> None:
        embedding_str = "[" + ",".join(map(str, embedding)) + "]"

        await db.execute(
            """
            UPDATE summaries SET embedding = $1 WHERE summary_id = $2
        """,
            embedding_str,
            summary_id,
        )

    async def get_by_agent(
        self,
        user_id: str,
        agent_id: str,
        kind: Optional[SummaryKind] = None,
        limit: int = 50,
    ) -> List[Summary]:
        if kind:
            rows = await db.fetch(
                """
                SELECT * FROM summaries
                WHERE user_id = $1 AND agent_id = $2 AND kind = $3
                ORDER BY created_at DESC
                LIMIT $4
            """,
                user_id,
                agent_id,
                kind,
                limit,
            )
        else:
            rows = await db.fetch(
                """
                SELECT * FROM summaries
                WHERE user_id = $1 AND agent_id = $2
                ORDER BY created_at DESC
                LIMIT $3
            """,
                user_id,
                agent_id,
                limit,
            )

        return [self._row_to_model(row) for row in rows]

    async def get_user_summaries(self, user_id: str, limit: int = 50) -> List[Summary]:
        rows = await db.fetch(
            """
            SELECT * FROM summaries
            WHERE user_id = $1 AND agent_id IS NULL
            ORDER BY created_at DESC
            LIMIT $2
        """,
            user_id,
            limit,
        )

        return [self._row_to_model(row) for row in rows]

    async def delete(self, summary_id: str) -> bool:
        result = await db.execute(
            "DELETE FROM summaries WHERE summary_id = $1", summary_id
        )
        return result == "DELETE 1"

    def _row_to_model(self, row: Dict[str, Any]) -> Summary:
        embedding = row.get("embedding")
        if embedding and isinstance(embedding, str):
            embedding = json.loads(embedding)

        return Summary(
            summary_id=row["summary_id"],
            user_id=row["user_id"],
            agent_id=row["agent_id"],
            kind=row["kind"],
            depth=row["depth"],
            content=row["content"],
            token_count=row["token_count"],
            embedding=embedding,
            earliest_at=row["earliest_at"],
            latest_at=row["latest_at"],
            descendant_count=row["descendant_count"],
            descendant_token_count=row["descendant_token_count"],
            source_message_token_count=row["source_message_token_count"],
            document_id=row["document_id"],
            model=row["model"],
            compression_level=row["compression_level"],
            created_at=row["created_at"],
        )


summary_store = SummaryStore()
