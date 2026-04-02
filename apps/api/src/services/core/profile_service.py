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
        include_metadata: bool = False,
    ) -> Dict[str, Any]:
        cached = await self._get_cached_profile(container_tag)
        if cached and self._is_cache_valid(cached):
            profile = cached
        else:
            profile = await self._build_profile(container_tag)
            await self._cache_profile(container_tag, profile)

        static = profile.get("static_memories", [])[:max_static]
        dynamic = profile.get("dynamic_memories", [])[:max_dynamic]

        if include_metadata:
            static_memories = await memory_store.get_static_memories(
                container_tag=container_tag,
                limit=max_static,
            )
            dynamic_memories = await memory_store.get_dynamic_memories(
                container_tag=container_tag,
                limit=max_dynamic,
            )
            static = [
                {
                    "content": m.content,
                    "metadata": m.metadata,
                    "version": m.version,
                    "created_at": m.created_at.isoformat() if m.created_at else None,
                }
                for m in static_memories
            ]
            dynamic = [
                {
                    "content": m.content,
                    "metadata": m.metadata,
                    "version": m.version,
                    "created_at": m.created_at.isoformat() if m.created_at else None,
                }
                for m in dynamic_memories
            ]

        search_results = []
        if query:
            search_results = await memory_store.search(
                query=query,
                container_tag=container_tag,
                limit=max_static,
            )

        matched_entities = []
        if query:
            try:
                matched_entities = await self._match_entities_from_table(
                    query, container_tag
                )
            except Exception:
                pass

        return {
            "profile": {
                "static": static,
                "dynamic": dynamic,
            },
            "searchResults": search_results,
            "entityContext": profile.get("entity_context"),
            "matchedEntities": matched_entities if matched_entities else None,
        }

    async def _match_entities_from_table(
        self,
        query: str,
        container_tag: str,
    ) -> List[Dict[str, Any]]:
        """
        从实体表匹配查询中的实体
        使用最长匹配优先策略
        """
        rows = await db.fetch(
            """
            SELECT id, name, type, mention_count
            FROM entities
            WHERE container_tag = $1
            ORDER BY LENGTH(name) DESC
            """,
            container_tag,
        )

        if not rows:
            return []

        matched = []
        seen_names = set()

        for row in rows:
            name = row["name"]
            if name in query and name not in seen_names:
                memory_ids = await db.fetch(
                    """
                    SELECT memory_id FROM memory_entities
                    WHERE entity_id = $1
                    LIMIT 5
                    """,
                    row["id"],
                )

                matched.append(
                    {
                        "name": name,
                        "type": row["type"],
                        "memory_ids": [str(m["memory_id"]) for m in memory_ids],
                        "mention_count": row["mention_count"],
                    }
                )
                seen_names.add(name)

        return matched

    async def get_profile_with_entities(
        self,
        container_tag: str,
        entity_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        memories = await memory_store.get_by_container(container_tag, limit=100)

        all_entities: Dict[str, List[Dict[str, Any]]] = {}

        for m in memories:
            entities = m.metadata.get("entities", {})
            for etype, values in entities.items():
                if entity_type and etype != entity_type:
                    continue
                if etype not in all_entities:
                    all_entities[etype] = []
                for value in values:
                    all_entities[etype].append(
                        {
                            "value": value,
                            "source_id": m.id,
                            "is_static": m.is_static,
                        }
                    )

        return {
            "container_tag": container_tag,
            "entities": all_entities,
            "total_memories": len(memories),
        }

    async def get_profile_with_relations(
        self,
        container_tag: str,
    ) -> Dict[str, Any]:
        memories = await memory_store.get_by_container(container_tag, limit=50)

        nodes = []
        edges = []

        for m in memories:
            nodes.append(
                {
                    "id": m.id,
                    "content": m.content,
                    "is_static": m.is_static,
                    "version": m.version,
                }
            )

            relations = m.metadata.get("relations", {})
            for rel_type, target_ids in relations.items():
                for target_id in target_ids:
                    edges.append(
                        {
                            "source": m.id,
                            "target": target_id,
                            "type": rel_type,
                        }
                    )

        return {
            "container_tag": container_tag,
            "nodes": nodes,
            "edges": edges,
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

    async def set_entity_context(
        self,
        container_tag: str,
        entity_context: str,
    ) -> bool:
        if len(entity_context) > 1500:
            entity_context = entity_context[:1500]

        await db.execute(
            """
            INSERT INTO memory_profiles (container_tag, entity_context, last_updated)
            VALUES ($1, $2, NOW())
            ON CONFLICT (container_tag)
            DO UPDATE SET
                entity_context = EXCLUDED.entity_context,
                last_updated = NOW()
            """,
            container_tag,
            entity_context,
        )
        return True

    async def get_entity_context(self, container_tag: str) -> Optional[str]:
        row = await db.fetchrow(
            """
            SELECT entity_context FROM memory_profiles
            WHERE container_tag = $1
            """,
            container_tag,
        )
        return row["entity_context"] if row else None

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
            SELECT static_memories, dynamic_memories, last_updated, entity_context
            FROM memory_profiles
            WHERE container_tag = $1
            """,
            container_tag,
        )

        if not row:
            return None

        # Parse JSONB fields (asyncpg returns strings for JSONB when manually serialized)
        static_memories = row["static_memories"]
        dynamic_memories = row["dynamic_memories"]

        # Handle both string and already-parsed formats
        if isinstance(static_memories, str):
            static_memories = json.loads(static_memories) if static_memories else []
        if isinstance(dynamic_memories, str):
            dynamic_memories = json.loads(dynamic_memories) if dynamic_memories else []

        return {
            "static_memories": static_memories or [],
            "dynamic_memories": dynamic_memories or [],
            "last_updated": row["last_updated"],
            "entity_context": row["entity_context"],
        }

    async def _cache_profile(
        self,
        container_tag: str,
        profile: Dict[str, Any],
        entity_context: Optional[str] = None,
    ) -> None:
        await db.execute(
            """
            INSERT INTO memory_profiles (container_tag, static_memories, dynamic_memories, entity_context, last_updated)
            VALUES ($1, $2, $3, $4, NOW())
            ON CONFLICT (container_tag)
            DO UPDATE SET
                static_memories = EXCLUDED.static_memories,
                dynamic_memories = EXCLUDED.dynamic_memories,
                entity_context = COALESCE(EXCLUDED.entity_context, memory_profiles.entity_context),
                last_updated = NOW()
            """,
            container_tag,
            json.dumps(profile.get("static_memories", [])),
            json.dumps(profile.get("dynamic_memories", [])),
            entity_context,
        )

    def _is_cache_valid(self, cached: Dict[str, Any], max_age_minutes: int = 5) -> bool:
        last_updated = cached.get("last_updated")
        if not last_updated:
            return False

        age = (datetime.now(last_updated.tzinfo) - last_updated).total_seconds() / 60
        return age < max_age_minutes


profile_service = ProfileService()
