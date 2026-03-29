"""
Importance Scoring Service

Calculates memory importance based on multiple factors.
Score range: 0.0 - 1.0
"""

from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass


@dataclass
class ImportanceFactors:
    repetition_score: float
    access_score: float
    entity_score: float
    recency_score: float
    behavior_score: float


class ImportanceService:
    """Memory importance scoring"""

    BEHAVIOR_WEIGHTS = {
        "fact": 1.0,
        "preference": 0.9,
        "episode": 0.5,
    }

    MAX_ACCESS_BOOST = 0.3
    REPETITION_BOOST = 0.1
    ENTITY_DENSITY_WEIGHT = 0.1
    RECENCY_DECAY_DAYS = 30

    async def calculate_importance(
        self,
        user_id: str,
        memory_id: str,
        content: str,
        memory_behavior: str = "episode",
        entity_count: int = 0,
        created_at: Optional[datetime] = None,
    ) -> float:
        """Calculate importance score for a memory"""
        factors = await self._calculate_factors(
            user_id=user_id,
            memory_id=memory_id,
            content=content,
            memory_behavior=memory_behavior,
            entity_count=entity_count,
            created_at=created_at,
        )

        score = self._combine_factors(factors)
        return min(1.0, max(0.0, score))

    async def _calculate_factors(
        self,
        user_id: str,
        memory_id: str,
        content: str,
        memory_behavior: str,
        entity_count: int,
        created_at: Optional[datetime],
    ) -> ImportanceFactors:
        """Calculate individual scoring factors"""
        from src.database import db

        repetition_score = 0.0
        async with db.user_context(user_id):
            similar_count = await db.fetchval(
                """
                SELECT COUNT(*) FROM raw_messages
                WHERE user_id = $1
                  AND id != $2
                  AND content LIKE '%' || $3 || '%'
                """,
                user_id,
                memory_id,
                content[:50],
            )
            repetition_score = min(0.3, similar_count * self.REPETITION_BOOST)

        access_score = 0.0

        entity_score = min(0.2, entity_count * self.ENTITY_DENSITY_WEIGHT)

        recency_score = 0.5
        if created_at:
            days_old = (datetime.utcnow() - created_at).days
            decay_factor = max(0, 1 - (days_old / self.RECENCY_DECAY_DAYS))
            recency_score = 0.3 + (0.2 * decay_factor)

        behavior_score = self.BEHAVIOR_WEIGHTS.get(memory_behavior, 0.5)

        return ImportanceFactors(
            repetition_score=repetition_score,
            access_score=access_score,
            entity_score=entity_score,
            recency_score=recency_score,
            behavior_score=behavior_score,
        )

    def _combine_factors(self, factors: ImportanceFactors) -> float:
        """Combine factors into final score"""
        weights = {
            "repetition": 0.15,
            "access": 0.20,
            "entity": 0.15,
            "recency": 0.20,
            "behavior": 0.30,
        }

        score = (
            factors.repetition_score * weights["repetition"]
            + factors.access_score * weights["access"]
            + factors.entity_score * weights["entity"]
            + factors.recency_score * weights["recency"]
            + factors.behavior_score * weights["behavior"]
        )

        return score

    async def update_on_access(
        self,
        user_id: str,
        memory_id: str,
    ) -> float:
        """Update importance when memory is accessed"""
        from src.database import db

        async with db.user_context(user_id):
            row = await db.fetchrow(
                "SELECT importance_score, access_count FROM raw_messages WHERE id = $1",
                memory_id,
            )

            if not row:
                return 0.5

            current_score = row["importance_score"] or 0.5
            access_count = row["access_count"] or 0

            access_boost = min(self.MAX_ACCESS_BOOST, (access_count + 1) * 0.02)

            new_score = min(1.0, current_score + access_boost * 0.1)

            await db.execute(
                """
                UPDATE raw_messages
                SET importance_score = $1, access_count = access_count + 1, last_accessed_at = NOW()
                WHERE id = $2
                """,
                new_score,
                memory_id,
            )

            return new_score

    async def batch_recalculate(
        self,
        user_id: str,
        limit: int = 100,
    ) -> int:
        """Recalculate importance for user's memories"""
        from src.database import db

        async with db.user_context(user_id):
            rows = await db.fetch(
                """
                SELECT id, content, memory_behavior, created_at
                FROM raw_messages
                WHERE user_id = $1
                ORDER BY created_at DESC
                LIMIT $2
                """,
                user_id,
                limit,
            )

            updated = 0
            for row in rows:
                score = await self.calculate_importance(
                    user_id=user_id,
                    memory_id=row["id"],
                    content=row["content"],
                    memory_behavior=row.get("memory_behavior", "episode"),
                    entity_count=0,
                    created_at=row.get("created_at"),
                )

                await db.execute(
                    "UPDATE raw_messages SET importance_score = $1 WHERE id = $2",
                    score,
                    row["id"],
                )
                updated += 1

            return updated


importance_service = ImportanceService()
