"""
Profile service for managing user static/dynamic memory profiles.
"""

from typing import Optional, List, Dict, Any
from datetime import datetime
import json

from src.database import db
from src.services.core.memory_store import memory_store


class ProfileService:
    def __init__(self):
        self.static_limit = 50
        self.dynamic_limit = 20

    async def get_profile(
        self,
        container_tag: str,
        query: Optional[str] = None,
        max_static: int = 10,
        max_dynamic: int = 10,
    ) -> Dict[str, Any]:
        cached = await self._get_cached_profile(container_tag)
        if cached and self._is_cache_valid(cached):
            profile = cached
        else:
            profile = await self._build_profile(container_tag)
            await self._cache_profile(container_tag, profile)

        static = profile.get("static_memories", [])[:max_static]
        dynamic = profile.get("dynamic_memories", [])[:max_dynamic]

        search_results = []
        if query:
            search_results = await memory_store.search(
                query=query,
                container_tag=container_tag,
                limit=max_static,
            )

        return {
            "profile": {
                "static": static,
                "dynamic": dynamic,
            },
            "searchResults": search_results,
        }

    async def get_static_facts(
        self,
        container_tag: str,
        limit: int = 10,
    ) -> List[str]:
        memories = await memory_store.get_static_memories(
            container_tag=container_tag,
            limit=limit,
        )
        return [m.content for m in memories]

    async def get_dynamic_facts(
        self,
        container_tag: str,
        limit: int = 10,
    ) -> List[str]:
        memories = await memory_store.get_dynamic_memories(
            container_tag=container_tag,
            limit=limit,
        )
        return [m.content for m in memories]

    async def invalidate_cache(self, container_tag: str) -> None:
        await db.execute(
            """
            UPDATE memory_profiles 
            SET last_updated = '1970-01-01'::timestamp
            WHERE container_tag = $1
            """,
            container_tag,
        )

    async def _build_profile(self, container_tag: str) -> Dict[str, Any]:
        static_memories = await memory_store.get_static_memories(
            container_tag=container_tag,
            limit=self.static_limit,
        )
        dynamic_memories = await memory_store.get_dynamic_memories(
            container_tag=container_tag,
            limit=self.dynamic_limit,
        )

        return {
            "static_memories": [m.content for m in static_memories],
            "dynamic_memories": [m.content for m in dynamic_memories],
        }

    async def _get_cached_profile(self, container_tag: str) -> Optional[Dict[str, Any]]:
        row = await db.fetchrow(
            """
            SELECT static_memories, dynamic_memories, last_updated
            FROM memory_profiles
            WHERE container_tag = $1
            """,
            container_tag,
        )

        if not row:
            return None

        return {
            "static_memories": row["static_memories"] or [],
            "dynamic_memories": row["dynamic_memories"] or [],
            "last_updated": row["last_updated"],
        }

    async def _cache_profile(
        self,
        container_tag: str,
        profile: Dict[str, Any],
    ) -> None:
        await db.execute(
            """
            INSERT INTO memory_profiles (container_tag, static_memories, dynamic_memories, last_updated)
            VALUES ($1, $2, $3, NOW())
            ON CONFLICT (container_tag)
            DO UPDATE SET
                static_memories = EXCLUDED.static_memories,
                dynamic_memories = EXCLUDED.dynamic_memories,
                last_updated = NOW()
            """,
            container_tag,
            json.dumps(profile.get("static_memories", [])),
            json.dumps(profile.get("dynamic_memories", [])),
        )

    def _is_cache_valid(self, cached: Dict[str, Any], max_age_minutes: int = 5) -> bool:
        last_updated = cached.get("last_updated")
        if not last_updated:
            return False

        age = (datetime.now(last_updated.tzinfo) - last_updated).total_seconds() / 60
        return age < max_age_minutes


profile_service = ProfileService()
