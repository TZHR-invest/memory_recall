"""
Memory Behavior Service

Implements behavior-specific storage and recall logic:
- fact: Persistent until updated, no decay
- preference: Strengthens with repetition
- episode: Decays unless significant
"""

from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from dataclasses import dataclass
import re


@dataclass
class BehaviorConfig:
    default_lifespan: str
    decay_factor: float
    weight_boost: float
    always_include: bool


BEHAVIOR_CONFIGS = {
    "fact": BehaviorConfig(
        default_lifespan="permanent",
        decay_factor=0.0,
        weight_boost=1.0,
        always_include=True,
    ),
    "preference": BehaviorConfig(
        default_lifespan="long_term",
        decay_factor=0.3,
        weight_boost=0.9,
        always_include=False,
    ),
    "episode": BehaviorConfig(
        default_lifespan="short_term",
        decay_factor=1.0,
        weight_boost=0.6,
        always_include=False,
    ),
}

PREFERENCE_KEYWORDS = [
    "喜欢",
    "爱",
    "讨厌",
    "偏好",
    "倾向",
    "更愿意",
    "不喜欢",
    "favorite",
    "prefer",
    "like",
    "hate",
    "love",
    "best",
]

FACT_KEYWORDS = [
    "是",
    "叫",
    "住在",
    "工作",
    "生日",
    "电话",
    "邮箱",
    "地址",
    "is",
    "name",
    "work",
    "live",
    "born",
    "phone",
    "email",
]

EPISODE_KEYWORDS = [
    "今天",
    "昨天",
    "明天",
    "上周",
    "下周",
    "刚才",
    "刚才",
    "today",
    "yesterday",
    "tomorrow",
    "last week",
    "next week",
]


class MemoryBehaviorService:
    def detect_behavior(self, content: str) -> str:
        """Auto-detect memory behavior from content"""
        content_lower = content.lower()

        preference_score = sum(1 for kw in PREFERENCE_KEYWORDS if kw in content_lower)
        fact_score = sum(1 for kw in FACT_KEYWORDS if kw in content_lower)
        episode_score = sum(1 for kw in EPISODE_KEYWORDS if kw in content_lower)

        if preference_score >= fact_score and preference_score >= episode_score:
            return "preference"
        elif fact_score >= episode_score:
            return "fact"
        else:
            return "episode"

    def get_lifespan_for_behavior(self, behavior: str) -> str:
        """Get default lifespan for behavior type"""
        config = BEHAVIOR_CONFIGS.get(behavior, BEHAVIOR_CONFIGS["episode"])
        return config.default_lifespan

    def calculate_expiration(
        self,
        behavior: str,
        created_at: datetime,
    ) -> Optional[datetime]:
        """Calculate expiration date based on behavior"""
        lifespan = self.get_lifespan_for_behavior(behavior)

        lifespan_days = {
            "temporary": 1,
            "short_term": 30,
            "long_term": 365,
            "permanent": None,
        }

        days = lifespan_days.get(lifespan, 365)
        if days is None:
            return None

        return created_at + timedelta(days=days)

    def apply_behavior_weight(
        self,
        score: float,
        behavior: str,
        age_days: float = 0,
    ) -> float:
        """Apply behavior-specific weighting to recall score"""
        config = BEHAVIOR_CONFIGS.get(behavior, BEHAVIOR_CONFIGS["episode"])

        weighted_score = score * config.weight_boost

        if config.decay_factor > 0 and age_days > 0:
            decay = config.decay_factor * (age_days / 30)
            weighted_score *= max(0.1, 1 - decay)

        return weighted_score

    def should_always_include(self, behavior: str) -> bool:
        """Check if memory should always be included in recall"""
        config = BEHAVIOR_CONFIGS.get(behavior, BEHAVIOR_CONFIGS["episode"])
        return config.always_include

    async def check_preference_repetition(
        self,
        user_id: str,
        content: str,
    ) -> Dict[str, Any]:
        """Check if similar preference exists and boost weight"""
        from src.database import db

        async with db.user_context(user_id):
            similar = await db.fetch(
                """
                SELECT id, content, importance_score, access_count
                FROM raw_messages
                WHERE user_id = $1
                  AND memory_behavior = 'preference'
                  AND is_expired = FALSE
                  AND content % $2
                LIMIT 3
                """,
                user_id,
                content[:100],
            )

            if similar:
                return {
                    "is_repetition": True,
                    "similar_memories": [dict(r) for r in similar],
                    "suggested_boost": min(0.3, len(similar) * 0.1),
                }

        return {"is_repetition": False, "similar_memories": [], "suggested_boost": 0.0}

    async def boost_preference_weight(
        self,
        memory_id: str,
        boost_amount: float,
    ) -> None:
        """Boost importance score for repeated preference"""
        from src.database import db

        await db.execute(
            """
            UPDATE raw_messages
            SET importance_score = LEAST(1.0, importance_score + $1)
            WHERE id = $2
            """,
            boost_amount,
            memory_id,
        )


memory_behavior_service = MemoryBehaviorService()
