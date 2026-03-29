"""
Temporal Service

Handles time-based memory lifecycle management.
"""

from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
from dataclasses import dataclass

from src.database import db


LIFESPAN_DAYS = {
    "temporary": 1,
    "short_term": 30,
    "long_term": 365,
    "permanent": 36500,  # 100 years
}


@dataclass
class TemporalInfo:
    """Temporal information for a memory"""

    event_date: Optional[datetime]
    document_date: Optional[datetime]
    expiration_date: Optional[datetime]
    memory_lifespan: str
    days_remaining: Optional[int]


class TemporalService:
    """Temporal awareness and lifecycle management"""

    def calculate_expiration(
        self,
        memory_lifespan: str,
        created_at: datetime,
    ) -> datetime:
        """Calculate expiration date based on lifespan"""
        days = LIFESPAN_DAYS.get(memory_lifespan, 365)
        return created_at + timedelta(days=days)

    async def set_expiration(
        self,
        user_id: str,
        memory_id: str,
        expiration_date: Optional[datetime] = None,
        memory_lifespan: Optional[str] = None,
    ) -> bool:
        """
        Set or update expiration for a memory

        Args:
            user_id: User ID for schema isolation
            memory_id: Memory ID to update
            expiration_date: Explicit expiration date (optional)
            memory_lifespan: Lifespan category (optional, used if no explicit date)

        Returns:
            True if update succeeded
        """
        async with db.user_context(user_id):
            if expiration_date is None and memory_lifespan:
                row = await db.fetchrow(
                    "SELECT created_at FROM raw_messages WHERE id = $1",
                    memory_id,
                )
                if row:
                    expiration_date = self.calculate_expiration(
                        memory_lifespan, row["created_at"]
                    )

            if expiration_date:
                result = await db.execute(
                    """
                    UPDATE raw_messages
                    SET expiration_date = $1, memory_lifespan = $2
                    WHERE id = $3
                    """,
                    expiration_date,
                    memory_lifespan,
                    memory_id,
                )
                return "UPDATE" in result

        return False

    async def filter_expired(
        self,
        user_id: str,
        memory_ids: List[str],
        include_expired: bool = False,
    ) -> List[str]:
        """
        Filter out expired memories unless requested

        Args:
            user_id: User ID for schema isolation
            memory_ids: List of memory IDs to filter
            include_expired: Whether to include expired memories

        Returns:
            Filtered list of memory IDs
        """
        if include_expired or not memory_ids:
            return memory_ids

        async with db.user_context(user_id):
            rows = await db.fetch(
                """
                SELECT id FROM raw_messages
                WHERE id = ANY($1)
                  AND (expiration_date IS NULL OR expiration_date > NOW())
                  AND is_expired = FALSE
                """,
                memory_ids,
            )

        return [row["id"] for row in rows]

    async def mark_expired(self, user_id: str, memory_id: str) -> bool:
        """
        Mark a memory as expired

        Args:
            user_id: User ID for schema isolation
            memory_id: Memory ID to mark

        Returns:
            True if memory was marked as expired
        """
        async with db.user_context(user_id):
            result = await db.execute(
                """
                UPDATE raw_messages
                SET is_expired = TRUE
                WHERE id = $1 AND expiration_date <= NOW() AND is_expired = FALSE
                """,
                memory_id,
            )
            return "UPDATE" in result

        return False

    async def check_expiration_warnings(self, user_id: str) -> List[Dict[str, Any]]:
        """
        Get memories expiring soon for warning notifications

        Args:
            user_id: User ID for schema isolation

        Returns:
            List of memories expiring within 7 days
        """
        async with db.user_context(user_id):
            rows = await db.fetch(
                """
                SELECT id, content, expiration_date
                FROM raw_messages
                WHERE user_id = $1
                  AND is_expired = FALSE
                  AND expiration_date IS NOT NULL
                  AND expiration_date BETWEEN NOW() AND NOW() + INTERVAL '7 days'
                ORDER BY expiration_date
                LIMIT 10
                """,
                user_id,
            )

        return [dict(row) for row in rows]

    async def cleanup_expired(self, user_id: str, days_old: int = 30) -> int:
        """
        Delete long-expired memories

        Args:
            user_id: User ID for schema isolation
            days_old: Delete memories expired more than this many days ago

        Returns:
            Number of deleted memories
        """
        async with db.user_context(user_id):
            result = await db.fetchval(
                """
                SELECT COUNT(*) FROM raw_messages
                WHERE is_expired = TRUE
                  AND expiration_date < NOW() - INTERVAL '%s days'
                """
                % days_old,
            )

            if result and result > 0:
                await db.execute(
                    """
                    DELETE FROM raw_messages
                    WHERE is_expired = TRUE
                      AND expiration_date < NOW() - INTERVAL '%s days'
                    """
                    % days_old,
                )

            return result or 0

    async def get_temporal_info(
        self,
        user_id: str,
        memory_id: str,
    ) -> Optional[TemporalInfo]:
        """
        Get temporal info for a specific memory

        Args:
            user_id: User ID for schema isolation
            memory_id: Memory ID to query

        Returns:
            TemporalInfo or None if memory not found
        """
        async with db.user_context(user_id):
            row = await db.fetchrow(
                """
                SELECT event_date, document_date, expiration_date, memory_lifespan
                FROM raw_messages
                WHERE id = $1
                """,
                memory_id,
            )

        if not row:
            return None

        expiration = row.get("expiration_date")
        now = datetime.utcnow()

        days_remaining = None
        if expiration:
            days_remaining = (expiration - now).days

        return TemporalInfo(
            event_date=row.get("event_date"),
            document_date=row.get("document_date"),
            expiration_date=expiration,
            memory_lifespan=row.get("memory_lifespan", "long_term"),
            days_remaining=days_remaining,
        )

    def get_temporal_info_from_dict(
        self,
        memory: Dict[str, Any],
    ) -> TemporalInfo:
        """
        Extract temporal info from memory dict

        Args:
            memory: Memory dict with temporal fields

        Returns:
            TemporalInfo object
        """
        expiration = memory.get("expiration_date")
        now = datetime.utcnow()

        days_remaining = None
        if expiration:
            if isinstance(expiration, str):
                expiration = datetime.fromisoformat(expiration.replace("Z", "+00:00"))
            days_remaining = (expiration - now).days

        return TemporalInfo(
            event_date=memory.get("event_date"),
            document_date=memory.get("document_date"),
            expiration_date=expiration,
            memory_lifespan=memory.get("memory_lifespan", "long_term"),
            days_remaining=days_remaining,
        )

    async def batch_update_lifespan(
        self,
        user_id: str,
        memory_ids: List[str],
        memory_lifespan: str,
    ) -> int:
        """
        Update lifespan for multiple memories

        Args:
            user_id: User ID for schema isolation
            memory_ids: List of memory IDs to update
            memory_lifespan: New lifespan category

        Returns:
            Number of updated memories
        """
        if not memory_ids:
            return 0

        async with db.user_context(user_id):
            rows = await db.fetch(
                """
                SELECT id, created_at FROM raw_messages
                WHERE id = ANY($1)
                """,
                memory_ids,
            )

            count = 0
            for row in rows:
                expiration = self.calculate_expiration(
                    memory_lifespan, row["created_at"]
                )
                await db.execute(
                    """
                    UPDATE raw_messages
                    SET memory_lifespan = $1, expiration_date = $2
                    WHERE id = $3
                    """,
                    memory_lifespan,
                    expiration,
                    row["id"],
                )
                count += 1

        return count

    async def get_expired_memories(
        self,
        user_id: str,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        Get all expired memories for a user

        Args:
            user_id: User ID for schema isolation
            limit: Maximum number to return

        Returns:
            List of expired memories
        """
        async with db.user_context(user_id):
            rows = await db.fetch(
                """
                SELECT id, content, expiration_date, memory_lifespan, created_at
                FROM raw_messages
                WHERE user_id = $1
                  AND is_expired = TRUE
                ORDER BY expiration_date DESC
                LIMIT $2
                """,
                user_id,
                limit,
            )

        return [dict(row) for row in rows]


# Singleton instance
temporal_service = TemporalService()
