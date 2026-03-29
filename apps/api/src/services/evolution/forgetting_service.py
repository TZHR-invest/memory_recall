"""
Forgetting Service

Automatic memory expiration and cleanup.
"""

from typing import List, Dict, Any
from datetime import datetime
import uuid

from src.database import db


class ForgettingService:
    """Auto-forgetting management"""

    async def check_and_expire(self, user_id: str) -> List[str]:
        """Check and expire memories past their expiration date"""
        async with db.user_context(user_id):
            rows = await db.fetch(
                """
                UPDATE raw_messages
                SET is_expired = TRUE
                WHERE is_expired = FALSE
                  AND expiration_date IS NOT NULL
                  AND expiration_date <= NOW()
                RETURNING id, content
                """
            )

            expired_ids = [row["id"] for row in rows]

            for row in rows:
                await self._create_expiration_notification(
                    user_id, row["id"], row["content"]
                )

            return expired_ids

    async def get_expiring_soon(
        self,
        user_id: str,
        days: int = 7,
    ) -> List[Dict[str, Any]]:
        """Get memories expiring within specified days"""
        async with db.user_context(user_id):
            rows = await db.fetch(
                """
                SELECT id, content, expiration_date, memory_type
                FROM raw_messages
                WHERE is_expired = FALSE
                  AND expiration_date IS NOT NULL
                  AND expiration_date BETWEEN NOW() AND NOW() + make_interval(days => $1)
                ORDER BY expiration_date
                LIMIT 20
                """,
                days,
            )

            return [dict(row) for row in rows]

    async def extend_expiration(
        self,
        user_id: str,
        memory_id: str,
        days: int,
    ) -> bool:
        """Extend expiration date by specified days"""
        async with db.user_context(user_id):
            result = await db.execute(
                """
                UPDATE raw_messages
                SET expiration_date = expiration_date + make_interval(days => $1),
                    is_expired = FALSE
                WHERE id = $2
                """,
                days,
                memory_id,
            )

            return result == "UPDATE 1"

    async def set_permanent(
        self,
        user_id: str,
        memory_id: str,
    ) -> bool:
        """Mark memory as permanent (never expire)"""
        async with db.user_context(user_id):
            result = await db.execute(
                """
                UPDATE raw_messages
                SET memory_lifespan = 'permanent',
                    expiration_date = NULL,
                    is_expired = FALSE
                WHERE id = $1
                """,
                memory_id,
            )

            return result == "UPDATE 1"

    async def batch_cleanup(
        self,
        user_id: str,
        days_after_expiration: int = 30,
    ) -> int:
        """Clean up memories expired for more than N days"""
        async with db.user_context(user_id):
            result = await db.execute(
                """
                DELETE FROM raw_messages
                WHERE is_expired = TRUE
                  AND expiration_date < NOW() - make_interval(days => $1)
                """,
                days_after_expiration,
            )

            # Parse "DELETE N" to get count
            if result and result.startswith("DELETE "):
                return int(result.split()[1])
            return 0

    async def _create_expiration_notification(
        self,
        user_id: str,
        memory_id: str,
        content: str,
    ) -> None:
        """Create notification for expired memory"""
        async with db.user_context(user_id):
            await db.execute(
                """
                INSERT INTO notifications (id, user_id, notification_type, memory_id, message, created_at)
                VALUES ($1, $2, 'expiration', $3, $4, $5)
                """,
                str(uuid.uuid4()),
                user_id,
                memory_id,
                f"Memory expired: {content[:50]}...",
                datetime.utcnow(),
            )

    async def get_forget_statistics(self, user_id: str) -> Dict[str, Any]:
        """Get forgetting statistics for user"""
        async with db.user_context(user_id):
            stats = await db.fetchrow(
                """
                SELECT
                    COUNT(*) FILTER (WHERE is_expired = FALSE) as active_count,
                    COUNT(*) FILTER (WHERE is_expired = TRUE) as expired_count,
                    COUNT(*) FILTER (WHERE expiration_date BETWEEN NOW() AND NOW() + INTERVAL '7 days') as expiring_soon_count,
                    AVG(importance_score) as avg_importance
                FROM raw_messages
                """
            )

            return {
                "active_count": stats["active_count"] or 0,
                "expired_count": stats["expired_count"] or 0,
                "expiring_soon_count": stats["expiring_soon_count"] or 0,
                "avg_importance": float(stats["avg_importance"] or 0.5),
            }


forgetting_service = ForgettingService()
