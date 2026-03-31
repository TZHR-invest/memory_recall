"""
Core memory storage service for simplified memory architecture.
"""

from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
from dataclasses import dataclass, field
import json
import logging

from src.database import db
from src.embedding.client import get_embedding_client
from src.services.core.relation_service import relation_service
from src.services.core.entity_extraction import entity_extractor
from src.services.core.llm_entity_extraction import (
    llm_entity_extractor,
    LLMEntityExtractor,
    get_default_entity_context,
)
from src.services.core.chinese_prompts import detect_language
from src.config import settings

logger = logging.getLogger(__name__)


@dataclass
class Memory:
    id: str
    container_tag: str
    content: str
    embedding: Optional[List[float]] = None
    is_static: bool = False
    is_latest: bool = True
    valid_from: Optional[datetime] = None
    valid_until: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.8
    created_at: Optional[datetime] = None
    is_forgotten: bool = False
    version: int = 1
    root_memory_id: Optional[str] = None
    source_count: int = 1
    is_inference: bool = False


class MemoryStore:
    def __init__(self):
        self.embedding_client = get_embedding_client()
        self._llm_extractor = None

    def _get_llm_extractor(self) -> LLMEntityExtractor:
        if self._llm_extractor is None:
            self._llm_extractor = LLMEntityExtractor(
                timeout=settings.LLM_EXTRACTION_TIMEOUT
            )
        return self._llm_extractor

    async def _get_entity_context(
        self,
        content: str,
        container_tag: str,
        entity_context: Optional[str] = None,
    ) -> str:
        """
        Get entity context using three-tier priority:
        1. Parameter (highest priority)
        2. Profile storage
        3. Default value (lowest priority)
        """
        if not settings.USE_DEFAULT_ENTITY_CONTEXT:
            return entity_context or ""

        if entity_context:
            return entity_context

        from src.services.core.profile_service import profile_service

        stored = await profile_service.get_entity_context(container_tag)
        if stored:
            return stored

        language = detect_language(content)
        return get_default_entity_context(language)

    async def create(
        self,
        content: str,
        container_tag: str,
        is_static: bool = False,
        metadata: Optional[Dict[str, Any]] = None,
        generate_embedding: bool = True,
        auto_relations: bool = True,
        extract_entities: bool = True,
        use_llm_extraction: Optional[bool] = None,
        entity_context: Optional[str] = None,
        parent_memory_id: Optional[str] = None,
        is_inference: bool = False,
        check_merge: bool = True,
    ) -> Memory:
        if use_llm_extraction is None:
            use_llm_extraction = settings.USE_LLM_EXTRACTION

        embedding = None
        if generate_embedding:
            embedding = await self._generate_embedding(content)

        if check_merge and not parent_memory_id and embedding:
            similar = await self._check_similar_memory(
                content, container_tag, embedding=embedding
            )
            if similar:
                logger.info(
                    f"Memory merge: found similar memory {similar['id']} "
                    f"(similarity={similar['similarity']:.3f}) for container {container_tag}"
                )
                await self.merge_similar_memory(similar["id"], content)
                existing = await self.get_by_id(similar["id"])
                if existing:
                    return existing

        if entity_context is None and extract_entities:
            entity_context = await self._get_entity_context(
                content, container_tag, entity_context
            )

        # Database JSONB may return as string
        final_metadata = metadata or {}
        if isinstance(final_metadata, str):
            try:
                final_metadata = json.loads(final_metadata)
            except Exception:
                final_metadata = {}

        if extract_entities:
            if use_llm_extraction:
                try:
                    extractor = self._get_llm_extractor()
                    llm_fact = await extractor.extract(content, entity_context)
                    if llm_fact.entities:
                        final_metadata["entities"] = llm_fact.entities
                    is_static = llm_fact.is_static
                except Exception:
                    entities = entity_extractor.extract_to_metadata(content)
                    if entities:
                        final_metadata["entities"] = entities
            else:
                try:
                    entities = entity_extractor.extract_to_metadata(content)
                    if entities:
                        final_metadata["entities"] = entities
                except Exception:
                    pass

        final_metadata["relations"] = {"updates": [], "extends": [], "derives": []}

        version = 1
        root_memory_id = None

        if parent_memory_id:
            parent = await self.get_by_id(parent_memory_id)
            if parent:
                version = parent.version + 1
                root_memory_id = parent.root_memory_id or parent.id

        row = await db.fetchrow(
            """
            INSERT INTO memories (
                container_tag, content, embedding, is_static, metadata,
                version, root_memory_id, is_inference
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            RETURNING *
            """,
            container_tag,
            content,
            self._embedding_to_str(embedding) if embedding else None,
            is_static,
            json.dumps(final_metadata),
            version,
            root_memory_id,
            is_inference,
        )

        memory = self._row_to_memory(row)

        if auto_relations:
            try:
                relations = await relation_service.auto_create_relations(
                    new_memory_id=memory.id,
                    new_content=content,
                    container_tag=container_tag,
                    is_static=is_static,
                )
                await self._update_embedded_relations(memory.id, relations)
            except Exception:
                pass

        return memory

    async def _update_embedded_relations(
        self,
        memory_id: str,
        relations: List[Any],
    ) -> None:
        memory = await self.get_by_id(memory_id)
        if not memory:
            return

        metadata = memory.metadata.copy()
        relations_dict = metadata.get(
            "relations", {"updates": [], "extends": [], "derives": []}
        )

        for rel in relations:
            rel_type = rel.relation_type
            target_id = rel.to_memory_id
            if rel_type in relations_dict and target_id not in relations_dict[rel_type]:
                relations_dict[rel_type].append(target_id)

        metadata["relations"] = relations_dict
        await self.update_metadata(memory_id, metadata)

    async def add_relation(
        self,
        memory_id: str,
        target_id: str,
        relation_type: str,
    ) -> bool:
        memory = await self.get_by_id(memory_id)
        if not memory:
            return False

        metadata = memory.metadata.copy()
        relations_dict = metadata.get(
            "relations", {"updates": [], "extends": [], "derives": []}
        )

        if relation_type not in relations_dict:
            relations_dict[relation_type] = []

        if target_id not in relations_dict[relation_type]:
            relations_dict[relation_type].append(target_id)

        metadata["relations"] = relations_dict
        return await self.update_metadata(memory_id, metadata)

    async def get_relations(self, memory_id: str) -> Dict[str, List[str]]:
        memory = await self.get_by_id(memory_id)
        if not memory:
            return {"updates": [], "extends": [], "derives": []}
        return memory.metadata.get(
            "relations", {"updates": [], "extends": [], "derives": []}
        )

    async def remove_relation(
        self,
        memory_id: str,
        target_id: str,
        relation_type: str,
    ) -> bool:
        memory = await self.get_by_id(memory_id)
        if not memory:
            return False

        metadata = memory.metadata.copy()
        relations_dict = metadata.get(
            "relations", {"updates": [], "extends": [], "derives": []}
        )

        if (
            relation_type in relations_dict
            and target_id in relations_dict[relation_type]
        ):
            relations_dict[relation_type].remove(target_id)

        metadata["relations"] = relations_dict
        return await self.update_metadata(memory_id, metadata)

    async def get_by_id(self, memory_id: str) -> Optional[Memory]:
        row = await db.fetchrow(
            "SELECT * FROM memories WHERE id = $1",
            memory_id,
        )
        return self._row_to_memory(row) if row else None

    async def get_by_container(
        self,
        container_tag: str,
        limit: int = 100,
        include_forgotten: bool = False,
    ) -> List[Memory]:
        query = """
            SELECT * FROM memories 
            WHERE container_tag = $1
            AND is_latest = TRUE
        """
        if not include_forgotten:
            query += " AND is_forgotten = FALSE"
        query += " ORDER BY created_at DESC LIMIT $2"

        rows = await db.fetch(query, container_tag, limit)
        return [self._row_to_memory(row) for row in rows]

    async def get_static_memories(
        self,
        container_tag: str,
        limit: int = 50,
    ) -> List[Memory]:
        rows = await db.fetch(
            """
            SELECT * FROM memories 
            WHERE container_tag = $1 
            AND is_static = TRUE 
            AND is_latest = TRUE
            AND is_forgotten = FALSE
            ORDER BY created_at DESC 
            LIMIT $2
            """,
            container_tag,
            limit,
        )
        return [self._row_to_memory(row) for row in rows]

    async def get_dynamic_memories(
        self,
        container_tag: str,
        limit: int = 20,
    ) -> List[Memory]:
        rows = await db.fetch(
            """
            SELECT * FROM memories 
            WHERE container_tag = $1 
            AND is_static = FALSE 
            AND is_latest = TRUE
            AND is_forgotten = FALSE
            ORDER BY created_at DESC 
            LIMIT $2
            """,
            container_tag,
            limit,
        )
        return [self._row_to_memory(row) for row in rows]

    async def get_version_chain(self, memory_id: str) -> List[Memory]:
        memory = await self.get_by_id(memory_id)
        if not memory:
            return []

        root_id = memory.root_memory_id or memory.id

        rows = await db.fetch(
            """
            SELECT * FROM memories 
            WHERE root_memory_id = $1 OR id = $1
            ORDER BY version ASC
            """,
            root_id,
        )
        return [self._row_to_memory(row) for row in rows]

    async def search(
        self,
        query: str,
        container_tag: str,
        limit: int = 10,
        threshold: float = 0.6,
    ) -> List[Dict[str, Any]]:
        query_embedding = await self._generate_embedding(query)

        rows = await db.fetch(
            """
            SELECT 
                id, content, metadata, confidence, created_at,
                1 - (embedding <=> $1::vector) as similarity
            FROM memories
            WHERE container_tag = $2
            AND is_latest = TRUE
            AND is_forgotten = FALSE
            AND 1 - (embedding <=> $1::vector) > $3
            ORDER BY similarity DESC
            LIMIT $4
            """,
            self._embedding_to_str(query_embedding),
            container_tag,
            threshold,
            limit,
        )

        return [
            {
                "id": row["id"],
                "content": row["content"],
                "metadata": row["metadata"],
                "confidence": row["confidence"],
                "created_at": row["created_at"].isoformat()
                if row["created_at"]
                else None,
                "similarity": float(row["similarity"]) if row["similarity"] else 0.0,
            }
            for row in rows
        ]

    async def forget(self, memory_id: str) -> bool:
        result = await db.execute(
            """
            UPDATE memories 
            SET is_forgotten = TRUE, updated_at = NOW()
            WHERE id = $1
            """,
            memory_id,
        )
        return result == "UPDATE 1"

    async def restore(self, memory_id: str) -> bool:
        result = await db.execute(
            """
            UPDATE memories 
            SET is_forgotten = FALSE, updated_at = NOW()
            WHERE id = $1
            """,
            memory_id,
        )
        return result == "UPDATE 1"

    async def update_metadata(
        self,
        memory_id: str,
        metadata: Dict[str, Any],
    ) -> bool:
        result = await db.execute(
            """
            UPDATE memories 
            SET metadata = $1, updated_at = NOW()
            WHERE id = $2
            """,
            json.dumps(metadata),
            memory_id,
        )
        return result == "UPDATE 1"

    async def create_update_version(
        self,
        memory_id: str,
        new_content: str,
    ) -> Optional[Memory]:
        old_memory = await self.get_by_id(memory_id)
        if not old_memory:
            return None

        new_memory = await self.create(
            content=new_content,
            container_tag=old_memory.container_tag,
            is_static=old_memory.is_static,
            metadata=old_memory.metadata,
            parent_memory_id=memory_id,
        )

        await self.add_relation(new_memory.id, memory_id, "updates")

        await db.execute(
            """
            UPDATE memories 
            SET is_latest = FALSE, valid_until = NOW(), updated_at = NOW()
            WHERE id = $1
            """,
            memory_id,
        )

        return new_memory

    async def _generate_embedding(self, text: str) -> Optional[List[float]]:
        if not self.embedding_client:
            return None
        try:
            result = await self.embedding_client.embed(text)
            return result
        except Exception:
            return None

    def _embedding_to_str(self, embedding: Optional[List[float]]) -> Optional[str]:
        if not embedding:
            return None
        return "[" + ",".join(map(str, embedding)) + "]"

    async def _check_similar_memory(
        self,
        content: str,
        container_tag: str,
        threshold: Optional[float] = None,
        embedding: Optional[List[float]] = None,
    ) -> Optional[Dict[str, Any]]:
        if threshold is None:
            threshold = settings.MEMORY_MERGE_THRESHOLD

        if embedding is None:
            query_embedding = await self._generate_embedding(content)
            if not query_embedding:
                return None
        else:
            query_embedding = embedding

        row = await db.fetchrow(
            """
            SELECT id, content, metadata,
                   1 - (embedding <=> $1::vector) as similarity
            FROM memories
            WHERE container_tag = $2
            AND is_latest = TRUE
            AND is_forgotten = FALSE
            AND 1 - (embedding <=> $1::vector) >= $3
            ORDER BY similarity DESC
            LIMIT 1
            """,
            self._embedding_to_str(query_embedding),
            container_tag,
            threshold,
        )

        if row:
            return {
                "id": row["id"],
                "content": row["content"],
                "similarity": float(row["similarity"]),
                "metadata": row["metadata"],
            }
        return None

    async def merge_similar_memory(
        self,
        existing_memory_id: str,
        new_content: Optional[str] = None,
    ) -> bool:
        """
        Merge a new memory into an existing one by updating metadata.

        Args:
            existing_memory_id: ID of the existing memory to merge into
            new_content: Content being merged (not stored, for logging)

        Returns:
            True if merge successful, False otherwise
        """
        memory = await self.get_by_id(existing_memory_id)
        if not memory:
            return False

        metadata = memory.metadata.copy()
        metadata["merged_count"] = metadata.get("merged_count", 0) + 1
        metadata["last_merged_at"] = datetime.now(timezone.utc).isoformat()

        return await self.update_metadata(existing_memory_id, metadata)

    def _row_to_memory(self, row: Dict) -> Memory:
        metadata = row.get("metadata", {}) or {}
        if isinstance(metadata, str):
            try:
                metadata = json.loads(metadata)
            except Exception:
                metadata = {}

        return Memory(
            id=row["id"],
            container_tag=row["container_tag"],
            content=row["content"],
            embedding=self._parse_embedding(row.get("embedding")),
            is_static=row.get("is_static", False),
            is_latest=row.get("is_latest", True),
            valid_from=row.get("valid_from"),
            valid_until=row.get("valid_until"),
            metadata=metadata,
            confidence=row.get("confidence", 0.8),
            created_at=row.get("created_at"),
            is_forgotten=row.get("is_forgotten", False),
            version=row.get("version", 1),
            root_memory_id=row.get("root_memory_id"),
            source_count=row.get("source_count", 1),
            is_inference=row.get("is_inference", False),
        )

    def _parse_embedding(self, embedding_str: Optional[str]) -> Optional[List[float]]:
        if not embedding_str:
            return None
        try:
            return [float(x) for x in embedding_str.strip("[]").split(",")]
        except Exception:
            return None


memory_store = MemoryStore()
