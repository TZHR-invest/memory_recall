"""
Container-scoped entity dictionary service for fast entity matching.

Provides in-memory entity dictionaries scoped by container_tag,
supporting lazy loading, incremental updates, and fast string matching.
"""

import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime

from src.database import db

logger = logging.getLogger(__name__)


@dataclass
class EntityInfo:
    """Information about an entity in the dictionary."""

    type: str
    memory_ids: List[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)


class ContainerScopedEntityDict:
    """Container-scoped entity dictionary for fast entity matching."""

    def __init__(self):
        self._dicts: Dict[str, Dict[str, EntityInfo]] = {}
        self._building: Dict[str, bool] = {}

    async def build(self, container_tag: str) -> Dict[str, EntityInfo]:
        """
        Build entity dictionary for a specific container.

        Loads entities from memory.metadata["entities"] JSONB field.

        Args:
            container_tag: Container to build dictionary for

        Returns:
            Entity dictionary for the container
        """
        if container_tag in self._dicts:
            return self._dicts[container_tag]

        if self._building.get(container_tag):
            logger.warning(f"Dictionary already building for {container_tag}")
            return {}

        self._building[container_tag] = True

        try:
            rows = await db.fetch(
                """
                SELECT id, metadata->'entities' as entities
                FROM memories
                WHERE container_tag = $1
                AND is_forgotten = FALSE
                AND is_latest = TRUE
                """,
                container_tag,
            )

            entity_dict: Dict[str, EntityInfo] = {}

            for row in rows:
                memory_id = row["id"]
                entities = row["entities"] or {}

                for entity_type, values in entities.items():
                    if not isinstance(values, list):
                        continue
                    for value in values:
                        if not value:
                            continue
                        if value not in entity_dict:
                            entity_dict[value] = EntityInfo(
                                type=entity_type, memory_ids=[memory_id]
                            )
                        else:
                            if memory_id not in entity_dict[value].memory_ids:
                                entity_dict[value].memory_ids.append(memory_id)

            self._dicts[container_tag] = entity_dict
            logger.info(
                f"Built entity dictionary for {container_tag}: "
                f"{len(entity_dict)} entities from {len(rows)} memories"
            )

            return entity_dict

        except Exception as e:
            logger.error(f"Failed to build entity dictionary for {container_tag}: {e}")
            raise
        finally:
            self._building[container_tag] = False

    async def get_or_build(self, container_tag: str) -> Dict[str, EntityInfo]:
        """
        Get entity dictionary for a container, building if needed.

        Implements lazy loading - dictionary is built on first access.

        Args:
            container_tag: Container to get dictionary for

        Returns:
            Entity dictionary for the container
        """
        if container_tag not in self._dicts:
            return await self.build(container_tag)
        return self._dicts[container_tag]

    def match(self, query: str, container_tag: str) -> List[str]:
        """
        Match entities from query string.

        Uses longest-match-first algorithm to avoid partial matches.

        Args:
            query: Query string to search for entities
            container_tag: Container to search in

        Returns:
            List of matched entity names (longest first)
        """
        entity_dict = self._dicts.get(container_tag, {})
        if not entity_dict:
            return []

        matched = []
        seen = set()

        sorted_names = sorted(entity_dict.keys(), key=len, reverse=True)

        for name in sorted_names:
            if name in query:
                skip = False
                for seen_name in seen:
                    if name in seen_name:
                        skip = True
                        break

                if not skip:
                    matched.append(name)
                    seen.add(name)

        return matched

    def match_with_info(self, query: str, container_tag: str) -> List[Dict[str, Any]]:
        """
        Match entities with full info from query string.

        Args:
            query: Query string to search for entities
            container_tag: Container to search in

        Returns:
            List of dicts with entity name, type, and memory_ids
        """
        entity_dict = self._dicts.get(container_tag, {})
        if not entity_dict:
            return []

        matched_names = self.match(query, container_tag)
        return [
            {
                "name": name,
                "type": entity_dict[name].type,
                "memory_ids": entity_dict[name].memory_ids,
            }
            for name in matched_names
        ]

    def add_entity(
        self,
        container_tag: str,
        entity_name: str,
        entity_type: str,
        memory_id: str,
    ) -> None:
        """
        Add entity to dictionary (incremental update).

        Args:
            container_tag: Container to add entity to
            entity_name: Name of the entity
            entity_type: Type of the entity
            memory_id: Memory ID that contains this entity
        """
        if container_tag not in self._dicts:
            self._dicts[container_tag] = {}

        entity_dict = self._dicts[container_tag]

        if entity_name not in entity_dict:
            entity_dict[entity_name] = EntityInfo(
                type=entity_type, memory_ids=[memory_id]
            )
            logger.debug(f"Added entity '{entity_name}' to {container_tag}")
        else:
            if memory_id not in entity_dict[entity_name].memory_ids:
                entity_dict[entity_name].memory_ids.append(memory_id)
                logger.debug(
                    f"Added memory {memory_id} to entity '{entity_name}' in {container_tag}"
                )

    def remove_entity(
        self,
        container_tag: str,
        entity_name: str,
        memory_id: str,
    ) -> None:
        """
        Remove memory_id from entity (incremental update).

        Args:
            container_tag: Container to remove entity from
            entity_name: Name of the entity
            memory_id: Memory ID to remove
        """
        if container_tag not in self._dicts:
            return

        entity_dict = self._dicts[container_tag]

        if entity_name not in entity_dict:
            return

        if memory_id in entity_dict[entity_name].memory_ids:
            entity_dict[entity_name].memory_ids.remove(memory_id)

        if not entity_dict[entity_name].memory_ids:
            del entity_dict[entity_name]
            logger.debug(f"Removed entity '{entity_name}' from {container_tag}")

    def invalidate(self, container_tag: str) -> None:
        """
        Clear cached dictionary for a container.

        Args:
            container_tag: Container to invalidate
        """
        if container_tag in self._dicts:
            del self._dicts[container_tag]
            logger.info(f"Invalidated entity dictionary for {container_tag}")

    def has(self, container_tag: str) -> bool:
        """
        Check if dictionary exists for a container.

        Args:
            container_tag: Container to check

        Returns:
            True if dictionary exists
        """
        return container_tag in self._dicts

    def get_stats(self) -> Dict[str, Any]:
        """
        Get statistics about entity dictionary usage.

        Returns:
            Statistics dictionary
        """
        total_entities = sum(len(d) for d in self._dicts.values())

        return {
            "container_count": len(self._dicts),
            "total_entities": total_entities,
            "containers": list(self._dicts.keys())[:10],
            "memory_usage_estimate_kb": total_entities * 0.5,
        }


entity_dict: Optional[ContainerScopedEntityDict] = None


def get_entity_dict() -> ContainerScopedEntityDict:
    """Get the global entity dictionary instance."""
    global entity_dict
    if entity_dict is None:
        entity_dict = ContainerScopedEntityDict()
    return entity_dict
