"""
User Profile Service

Aggregates user facts and preferences from memories.
Target: ~50ms retrieval.
"""

import json
from typing import Dict, Any, Optional
from datetime import datetime
from dataclasses import dataclass, asdict
from functools import lru_cache
import hashlib


@dataclass
class UserProfile:
    user_id: str
    static_facts: Dict[str, Any]
    dynamic_facts: Dict[str, Any]
    preferences: Dict[str, Any]
    source_memory_count: int
    last_rebuilt_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime


class ProfileCache:
    """In-memory LRU cache for user profiles"""

    def __init__(self, max_size: int = 1000):
        self._cache: Dict[str, UserProfile] = {}
        self._max_size = max_size
        self._dirty_flags: Dict[str, bool] = {}
        self._hits = 0
        self._misses = 0

    def get(self, user_id: str) -> Optional[UserProfile]:
        if user_id in self._cache and not self._dirty_flags.get(user_id, False):
            self._hits += 1
            return self._cache[user_id]
        self._misses += 1
        return None

    def set(self, user_id: str, profile: UserProfile) -> None:
        if len(self._cache) >= self._max_size and user_id not in self._cache:
            oldest_key = next(iter(self._cache))
            del self._cache[oldest_key]
            self._dirty_flags.pop(oldest_key, None)

        self._cache[user_id] = profile
        self._dirty_flags[user_id] = False

    def invalidate(self, user_id: str) -> None:
        self._dirty_flags[user_id] = True

    def remove(self, user_id: str) -> None:
        self._cache.pop(user_id, None)
        self._dirty_flags.pop(user_id, None)

    def get_stats(self) -> Dict[str, Any]:
        return {
            "size": len(self._cache),
            "max_size": self._max_size,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": self._hits / (self._hits + self._misses)
            if (self._hits + self._misses) > 0
            else 0,
        }


profile_cache = ProfileCache()


class UserProfileService:
    async def get_or_create(self, user_id: str) -> UserProfile:
        cached = profile_cache.get(user_id)
        if cached:
            return cached

        from src.database import db

        async with db.user_context(user_id):
            row = await db.fetchrow(
                "SELECT * FROM user_profiles WHERE user_id = $1",
                user_id,
            )

            if row:
                profile = UserProfile(
                    user_id=row["user_id"],
                    static_facts=row["static_facts"] or {},
                    dynamic_facts=row["dynamic_facts"] or {},
                    preferences=row["preferences"] or {},
                    source_memory_count=row["source_memory_count"] or 0,
                    last_rebuilt_at=row["last_rebuilt_at"],
                    created_at=row["created_at"],
                    updated_at=row["updated_at"],
                )
                profile_cache.set(user_id, profile)
                return profile

        now = datetime.utcnow()

        profile = UserProfile(
            user_id=user_id,
            static_facts={},
            dynamic_facts={},
            preferences={},
            source_memory_count=0,
            last_rebuilt_at=None,
            created_at=now,
            updated_at=now,
        )

        profile_cache.set(user_id, profile)
        return profile

    async def rebuild(self, user_id: str) -> UserProfile:
        """
        Rebuild profile from all user memories.

        This aggregates all user memories and categorizes them into:
        - static_facts: Permanent facts about the user (memory_behavior='fact')
        - dynamic_facts: Time-based events/episodes
        - preferences: User preferences (memory_behavior='preference')

        Args:
            user_id: User ID

        Returns:
            Rebuilt UserProfile instance
        """
        from src.database import db
        from src.services.core.lossless_recall_service import lossless_recall_service

        memories = await lossless_recall_service.hybrid_recall(
            query="",
            user_id=user_id,
            scope="manual_only",
            limit=1000,
            min_similarity=0.0,
        )

        static_facts = {}
        dynamic_facts = {}
        preferences = {}

        for i, memory in enumerate(memories):
            content = memory.get("content", "")
            memory_behavior = memory.get("memory_behavior", "episode")
            memory_id = memory.get("id", "")
            created_at = memory.get("created_at")

            created_at_str = (
                created_at.isoformat() if created_at else datetime.utcnow().isoformat()
            )

            if memory_behavior == "fact":
                static_facts[f"fact_{i}"] = {
                    "content": content,
                    "source_id": memory_id,
                    "created_at": created_at_str,
                }
            elif memory_behavior == "preference":
                preferences[f"pref_{i}"] = {
                    "content": content,
                    "source_id": memory_id,
                    "created_at": created_at_str,
                }
            else:
                dynamic_facts[f"event_{i}"] = {
                    "content": content[:200],
                    "source_id": memory_id,
                    "created_at": created_at_str,
                }

        now = datetime.utcnow()

        async with db.user_context(user_id):
            await db.execute(
                """
                INSERT INTO user_profiles 
                    (user_id, static_facts, dynamic_facts, preferences, source_memory_count, last_rebuilt_at, updated_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                ON CONFLICT (user_id) DO UPDATE SET
                    static_facts = $2,
                    dynamic_facts = $3,
                    preferences = $4,
                    source_memory_count = $5,
                    last_rebuilt_at = $6,
                    updated_at = $7,
                    is_dirty = FALSE
                """,
                user_id,
                json.dumps(static_facts),
                json.dumps(dynamic_facts),
                json.dumps(preferences),
                len(memories),
                now,
                now,
            )

        profile = UserProfile(
            user_id=user_id,
            static_facts=static_facts,
            dynamic_facts=dynamic_facts,
            preferences=preferences,
            source_memory_count=len(memories),
            last_rebuilt_at=now,
            created_at=now,
            updated_at=now,
        )

        profile_cache.set(user_id, profile)
        return profile

    async def incremental_update(
        self,
        user_id: str,
        memory_id: str,
        content: str,
        memory_behavior: str,
    ) -> None:
        """
        Incrementally update profile with new memory.

        This adds a new memory entry to the appropriate category without
        rebuilding the entire profile. The profile will be marked as dirty.

        Args:
            user_id: User ID
            memory_id: Memory ID
            content: Memory content
            memory_behavior: One of 'fact', 'preference', or 'episode'
        """
        from src.database import db

        profile = await self.get_or_create(user_id)

        now = datetime.utcnow()
        idx = profile.source_memory_count

        if memory_behavior == "fact":
            key = f"fact_{idx}"
            json_column = "static_facts"
        elif memory_behavior == "preference":
            key = f"pref_{idx}"
            json_column = "preferences"
        else:
            key = f"event_{idx}"
            json_column = "dynamic_facts"

        entry = {
            "content": content[:500],
            "source_id": memory_id,
            "created_at": now.isoformat(),
        }

        # jsonb_build_object merges new entry into existing JSONB column
        async with db.user_context(user_id):
            await db.execute(
                f"""
                UPDATE user_profiles
                SET {json_column} = {json_column} || jsonb_build_object($1, $2::jsonb),
                    source_memory_count = source_memory_count + 1,
                    is_dirty = TRUE,
                    updated_at = $3
                WHERE user_id = $4
                """,
                key,
                json.dumps(entry),
                now,
                user_id,
            )

    async def mark_dirty(self, user_id: str) -> None:
        """Mark profile as needing rebuild"""
        from src.database import db

        profile_cache.invalidate(user_id)

        async with db.user_context(user_id):
            await db.execute(
                "UPDATE user_profiles SET is_dirty = TRUE, updated_at = $1 WHERE user_id = $2",
                datetime.utcnow(),
                user_id,
            )

    async def get_profile_summary(self, user_id: str) -> Dict[str, Any]:
        """
        Get a summary of the user profile.

        Returns a lightweight summary suitable for quick access.

        Args:
            user_id: User ID

        Returns:
            Dictionary with profile summary
        """
        profile = await self.get_or_create(user_id)

        return {
            "user_id": profile.user_id,
            "total_memories": profile.source_memory_count,
            "static_facts_count": len(profile.static_facts),
            "dynamic_facts_count": len(profile.dynamic_facts),
            "preferences_count": len(profile.preferences),
            "is_dirty": await self._is_dirty(user_id),
            "last_rebuilt_at": profile.last_rebuilt_at.isoformat()
            if profile.last_rebuilt_at
            else None,
        }

    async def _is_dirty(self, user_id: str) -> bool:
        """Check if profile needs rebuild"""
        from src.database import db

        async with db.user_context(user_id):
            row = await db.fetchrow(
                "SELECT is_dirty FROM user_profiles WHERE user_id = $1",
                user_id,
            )
            return row["is_dirty"] if row else False


user_profile_service = UserProfileService()
