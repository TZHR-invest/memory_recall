from typing import Optional, List, Dict, Any

from src.database import db
from src.models.lossless import ContextItem, ItemType


class ContextStore:
    async def append_message(
        self,
        user_id: str,
        session_id: str,
        message_id: str,
        agent_id: Optional[str] = None,
    ) -> int:
        ordinal = await db.fetchval(
            """
            SELECT COALESCE(MAX(ordinal), -1) + 1
            FROM context_items
            WHERE user_id = $1 AND session_id = $2
        """,
            user_id,
            session_id,
        )

        await db.execute(
            """
            INSERT INTO context_items (user_id, agent_id, session_id, ordinal, item_type, message_id)
            VALUES ($1, $2, $3, $4, 'message', $5)
        """,
            user_id,
            agent_id,
            session_id,
            ordinal,
            message_id,
        )

        return ordinal

    async def append_summary(
        self,
        user_id: str,
        session_id: str,
        summary_id: str,
        agent_id: Optional[str] = None,
    ) -> int:
        ordinal = await db.fetchval(
            """
            SELECT COALESCE(MAX(ordinal), -1) + 1
            FROM context_items
            WHERE user_id = $1 AND session_id = $2
        """,
            user_id,
            session_id,
        )

        await db.execute(
            """
            INSERT INTO context_items (user_id, agent_id, session_id, ordinal, item_type, summary_id)
            VALUES ($1, $2, $3, $4, 'summary', $5)
        """,
            user_id,
            agent_id,
            session_id,
            ordinal,
            summary_id,
        )

        return ordinal

    async def get_context_items(
        self, user_id: str, session_id: str, agent_id: Optional[str] = None
    ) -> List[ContextItem]:
        if agent_id:
            rows = await db.fetch(
                """
                SELECT * FROM context_items
                WHERE user_id = $1 AND session_id = $2 AND agent_id = $3
                ORDER BY ordinal
            """,
                user_id,
                session_id,
                agent_id,
            )
        else:
            rows = await db.fetch(
                """
                SELECT * FROM context_items
                WHERE user_id = $1 AND session_id = $2
                ORDER BY ordinal
            """,
                user_id,
                session_id,
            )

        return [self._row_to_model(row) for row in rows]

    async def replace_range_with_summary(
        self,
        user_id: str,
        session_id: str,
        start_ordinal: int,
        end_ordinal: int,
        summary_id: str,
        agent_id: Optional[str] = None,
    ) -> None:
        await db.execute(
            """
            DELETE FROM context_items
            WHERE user_id = $1 AND session_id = $2
              AND ordinal >= $3 AND ordinal <= $4
        """,
            user_id,
            session_id,
            start_ordinal,
            end_ordinal,
        )

        await db.execute(
            """
            INSERT INTO context_items (user_id, agent_id, session_id, ordinal, item_type, summary_id)
            VALUES ($1, $2, $3, $4, 'summary', $5)
        """,
            user_id,
            agent_id,
            session_id,
            start_ordinal,
            summary_id,
        )

        await self._renumber_ordinals(user_id, session_id)

    async def _renumber_ordinals(self, user_id: str, session_id: str) -> None:
        await db.execute(
            """
            WITH ordered_items AS (
                SELECT user_id, session_id, ordinal, item_type, message_id, summary_id, agent_id, created_at,
                       ROW_NUMBER() OVER (ORDER BY ordinal) - 1 AS new_ordinal
                FROM context_items
                WHERE user_id = $1 AND session_id = $2
            )
            UPDATE context_items ci
            SET ordinal = oi.new_ordinal
            FROM ordered_items oi
            WHERE ci.user_id = oi.user_id 
              AND ci.session_id = oi.session_id
              AND ci.ordinal = oi.ordinal
        """,
            user_id,
            session_id,
        )

    async def get_token_count(self, user_id: str, session_id: str) -> int:
        total = await db.fetchval(
            """
            SELECT COALESCE(SUM(
                CASE 
                    WHEN ci.item_type = 'message' THEN rm.token_count
                    WHEN ci.item_type = 'summary' THEN s.token_count
                    ELSE 0
                END
            ), 0)
            FROM context_items ci
            LEFT JOIN raw_messages rm ON ci.message_id = rm.id
            LEFT JOIN summaries s ON ci.summary_id = s.summary_id
            WHERE ci.user_id = $1 AND ci.session_id = $2
        """,
            user_id,
            session_id,
        )

        return total or 0

    async def exists(self, user_id: str, session_id: str) -> bool:
        count = await db.fetchval(
            """
            SELECT COUNT(*) FROM context_items
            WHERE user_id = $1 AND session_id = $2
        """,
            user_id,
            session_id,
        )

        return count > 0

    async def clear(self, user_id: str, session_id: str) -> int:
        result = await db.execute(
            """
            DELETE FROM context_items
            WHERE user_id = $1 AND session_id = $2
        """,
            user_id,
            session_id,
        )

        return int(result.split()[-1]) if result else 0

    async def get_item_count(self, user_id: str, session_id: str) -> int:
        count = await db.fetchval(
            """
            SELECT COUNT(*) FROM context_items
            WHERE user_id = $1 AND session_id = $2
        """,
            user_id,
            session_id,
        )

        return count or 0

    async def get_message_count(self, user_id: str, session_id: str) -> int:
        count = await db.fetchval(
            """
            SELECT COUNT(*) FROM context_items
            WHERE user_id = $1 AND session_id = $2 AND item_type = 'message'
        """,
            user_id,
            session_id,
        )

        return count or 0

    async def get_summary_count(self, user_id: str, session_id: str) -> int:
        count = await db.fetchval(
            """
            SELECT COUNT(*) FROM context_items
            WHERE user_id = $1 AND session_id = $2 AND item_type = 'summary'
        """,
            user_id,
            session_id,
        )

        return count or 0

    async def get_items_by_range(
        self, user_id: str, session_id: str, start_ordinal: int, end_ordinal: int
    ) -> List[ContextItem]:
        rows = await db.fetch(
            """
            SELECT * FROM context_items
            WHERE user_id = $1 AND session_id = $2
              AND ordinal >= $3 AND ordinal <= $4
            ORDER BY ordinal
        """,
            user_id,
            session_id,
            start_ordinal,
            end_ordinal,
        )

        return [self._row_to_model(row) for row in rows]

    async def get_last_n_items(
        self, user_id: str, session_id: str, n: int
    ) -> List[ContextItem]:
        rows = await db.fetch(
            """
            SELECT * FROM context_items
            WHERE user_id = $1 AND session_id = $2
            ORDER BY ordinal DESC
            LIMIT $3
        """,
            user_id,
            session_id,
            n,
        )

        return [self._row_to_model(row) for row in reversed(rows)]

    def _row_to_model(self, row: Dict[str, Any]) -> ContextItem:
        return ContextItem(
            user_id=row["user_id"],
            session_id=row["session_id"],
            ordinal=row["ordinal"],
            item_type=row["item_type"],
            message_id=row["message_id"],
            summary_id=row["summary_id"],
            agent_id=row["agent_id"],
            created_at=row["created_at"],
        )


context_store = ContextStore()
