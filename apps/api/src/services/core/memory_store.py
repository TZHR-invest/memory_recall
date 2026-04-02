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
from src.services.graph_tools import normalize_entity_name
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


@dataclass
class Entity:
    """实体数据类"""

    id: str
    name: str
    type: str
    container_tag: str
    mention_count: int = 1
    confidence: float = 0.8
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


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
        extract_entities: Optional[bool] = None,
        extract_relations: Optional[bool] = None,
        use_llm_extraction: Optional[bool] = None,
        entity_context: Optional[str] = None,
        parent_memory_id: Optional[str] = None,
        is_inference: bool = False,
        check_merge: bool = True,
    ) -> Memory:
        if extract_entities is None:
            extract_entities = settings.ENABLE_ENTITY_EXTRACTION
        if extract_relations is None:
            extract_relations = settings.ENABLE_ENTITY_RELATION_EXTRACTION
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

                    if extract_relations:
                        extraction = await extractor.extract_with_relations(
                            content, entity_context
                        )
                        entities_to_store = extraction.get("entities", [])
                        relations_to_store = extraction.get("relations", [])

                        if entities_to_store:
                            entities_dict = {}
                            for entity in entities_to_store:
                                etype = entity.get("type", "unknown")
                                if etype not in entities_dict:
                                    entities_dict[etype] = []
                                entities_dict[etype].append(entity.get("name"))
                            final_metadata["entities"] = entities_dict
                            final_metadata["_entities_to_store"] = entities_to_store
                            final_metadata["_relations_to_store"] = relations_to_store
                    else:
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

        if (
            "_entities_to_store" in final_metadata
            or "_relations_to_store" in final_metadata
        ):
            entities_to_store = final_metadata.pop("_entities_to_store", [])
            relations_to_store = final_metadata.pop("_relations_to_store", [])

            if entities_to_store or relations_to_store:
                try:
                    await self._store_entity_graph(
                        memory.id, entities_to_store, relations_to_store, container_tag
                    )
                except Exception as e:
                    logger.warning(f"Failed to store entity graph: {e}")

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
                id, content, metadata, confidence, created_at, embedding,
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
                "embedding": self._parse_embedding(row["embedding"]),
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

    async def _store_entity_graph(
        self,
        memory_id: str,
        entities: List[Dict[str, Any]],
        relations: List[Dict[str, Any]],
        container_tag: str,
    ) -> None:
        """
        存储 Entity Graph 到数据库

        使用归一化实体名 + 类型的去重逻辑

        Args:
            memory_id: 记忆 ID
            entities: 实体列表 [{"name": "实体名", "type": "person/location/..."}]
            relations: 关系列表 [{"from": "实体1", "to": "实体2", "type": "关系类型", "confidence": 0.9}]
            container_tag: 容器标签
        """
        entity_ids = {}

        for entity in entities:
            name = entity.get("name")
            entity_type = entity.get("type", "unknown")
            confidence = entity.get("confidence", 0.8)

            if not name:
                continue

            normalized_name = normalize_entity_name(name)
            existing = await db.fetchrow(
                """
                SELECT id FROM entities 
                WHERE LOWER(TRIM(name)) = $1 AND type = $2 AND container_tag = $3
                """,
                normalized_name,
                entity_type,
                container_tag,
            )

            if existing:
                await db.execute(
                    "UPDATE entities SET mention_count = mention_count + 1, updated_at = NOW() WHERE id = $1",
                    str(existing["id"]),
                )
                entity_ids[name] = str(existing["id"])
            else:
                result = await db.fetchrow(
                    """
                    INSERT INTO entities (name, type, container_tag, confidence)
                    VALUES ($1, $2, $3, $4)
                    RETURNING id
                    """,
                    name.strip(),
                    entity_type,
                    container_tag,
                    confidence,
                )
                entity_ids[name] = str(result["id"]) if result else None

        for relation in relations:
            from_entity = relation.get("from")
            to_entity = relation.get("to")
            relation_type = relation.get("type")
            confidence = relation.get("confidence", 0.8)

            if not all([from_entity, to_entity, relation_type]):
                continue

            from_id = entity_ids.get(from_entity)
            to_id = entity_ids.get(to_entity)

            if not from_id or not to_id:
                continue

            existing = await db.fetchrow(
                """
                SELECT id FROM entity_relations 
                WHERE from_entity_id = $1 AND to_entity_id = $2 AND relation_type = $3
                """,
                from_id,
                to_id,
                relation_type,
            )

            if existing:
                await db.execute(
                    "UPDATE entity_relations SET weight = LEAST(weight + 0.1, 1.0) WHERE id = $1",
                    str(existing["id"]),
                )
            else:
                await db.execute(
                    """
                    INSERT INTO entity_relations 
                    (from_entity_id, to_entity_id, relation_type, container_tag, source_memory_id, confidence)
                    VALUES ($1, $2, $3, $4, $5, $6)
                    """,
                    from_id,
                    to_id,
                    relation_type,
                    container_tag,
                    memory_id,
                    confidence,
                )

        for entity_name, entity_id in entity_ids.items():
            if entity_id:
                await db.execute(
                    """
                    INSERT INTO memory_entities (memory_id, entity_id)
                    VALUES ($1, $2)
                    ON CONFLICT DO NOTHING
                    """,
                    memory_id,
                    entity_id,
                )

    async def traverse_memory_relations(
        self,
        memory_id: str,
        max_depth: int = 2,
        max_nodes: int = 5,
        relation_types: Optional[List[str]] = None,
    ) -> List[Memory]:
        """
        从 metadata->'relations' 遍历记忆演进关系

        关系类型:
        - updates: 更新关系（新记忆取代旧记忆）
        - extends: 扩展关系（新记忆补充旧记忆）
        - derives: 推导关系（从旧记忆推导出新记忆）

        Args:
            memory_id: 起始记忆 ID
            max_depth: 最大遍历深度（默认 2）
            max_nodes: 最大返回节点数（默认 5）
            relation_types: 关系类型过滤（默认所有类型）

        Returns:
            相关记忆列表
        """
        visited = set()
        results = []

        async def _traverse(current_id: str, depth: int):
            if depth > max_depth or len(results) >= max_nodes:
                return

            if current_id in visited:
                return
            visited.add(current_id)

            memory = await self.get_by_id(current_id)
            if not memory:
                return

            results.append(memory)

            relations = memory.metadata.get("relations", {})
            for rel_type, target_ids in relations.items():
                if relation_types and rel_type not in relation_types:
                    continue

                if not isinstance(target_ids, list):
                    continue

                for target_id in target_ids:
                    if len(results) >= max_nodes:
                        return
                    await _traverse(target_id, depth + 1)

        await _traverse(memory_id, 0)
        return results[:max_nodes]

    async def traverse_entity_relations(
        self,
        entity_id: str,
        max_depth: int = 2,
        max_nodes: int = 5,
        relation_types: Optional[List[str]] = None,
        container_tag: Optional[str] = None,
    ) -> List[Entity]:
        visited = set()
        results = []

        async def _traverse(current_id: str, depth: int):
            if depth > max_depth or len(results) >= max_nodes:
                return

            if current_id in visited:
                return
            visited.add(current_id)

            row = await db.fetchrow(
                "SELECT * FROM entities WHERE id = $1",
                current_id,
            )
            if not row:
                return

            results.append(
                Entity(
                    id=str(row["id"]),
                    name=row["name"],
                    type=row["type"],
                    container_tag=row["container_tag"],
                    mention_count=row["mention_count"],
                    confidence=row["confidence"],
                    created_at=row["created_at"],
                    updated_at=row["updated_at"],
                )
            )

            query = """
                SELECT to_entity_id as entity_id FROM entity_relations
                WHERE from_entity_id = $1
            """
            params: List[Any] = [current_id]

            if relation_types:
                query += " AND relation_type = ANY($2)"
                params.append(list(relation_types))

            if container_tag:
                param_idx = len(params) + 1
                query += f" AND container_tag = ${param_idx}"
                params.append(container_tag)

            related = await db.fetch(query, *params)

            for rel in related:
                if len(results) >= max_nodes:
                    return
                await _traverse(str(rel["entity_id"]), depth + 1)

            reverse_query = """
                SELECT from_entity_id as entity_id FROM entity_relations
                WHERE to_entity_id = $1
            """
            reverse_params: List[Any] = [current_id]

            if relation_types:
                reverse_query += " AND relation_type = ANY($2)"
                reverse_params.append(list(relation_types))

            if container_tag:
                param_idx = len(reverse_params) + 1
                reverse_query += f" AND container_tag = ${param_idx}"
                reverse_params.append(container_tag)

            reverse_related = await db.fetch(reverse_query, *reverse_params)

            for rel in reverse_related:
                if len(results) >= max_nodes:
                    return
                await _traverse(str(rel["entity_id"]), depth + 1)

        await _traverse(entity_id, 0)
        return results[:max_nodes]

    async def get_entities_for_memories(
        self,
        memory_ids: List[str],
    ) -> List[Entity]:
        if not memory_ids:
            return []

        rows = await db.fetch(
            """
            SELECT DISTINCT e.* FROM entities e
            JOIN memory_entities me ON e.id = me.entity_id
            WHERE me.memory_id = ANY($1)
            """,
            memory_ids,
        )

        return [
            Entity(
                id=str(row["id"]),
                name=row["name"],
                type=row["type"],
                container_tag=row["container_tag"],
                mention_count=row["mention_count"],
                confidence=row["confidence"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )
            for row in rows
        ]

    async def find_memories_by_entities(
        self,
        entity_ids: List[str],
        container_tag: str,
        limit: int = 10,
    ) -> List[Memory]:
        if not entity_ids:
            return []

        rows = await db.fetch(
            """
            SELECT m.*, COUNT(me.entity_id) as entity_match_count
            FROM memories m
            JOIN memory_entities me ON m.id = me.memory_id
            WHERE me.entity_id = ANY($1)
            AND m.container_tag = $2
            AND m.is_latest = TRUE
            AND m.is_forgotten = FALSE
            GROUP BY m.id
            ORDER BY entity_match_count DESC, m.created_at DESC
            LIMIT $3
            """,
            entity_ids,
            container_tag,
            limit,
        )

        return [self._row_to_memory(row) for row in rows]


memory_store = MemoryStore()
