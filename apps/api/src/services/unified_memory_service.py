import logging
import uuid
import hashlib
import re
from typing import Optional, List, Dict, Any, cast
from datetime import datetime

from src.database import db
from src.models.lossless import MemoryType
from src.services.core.raw_message_store import (
    RawMessageStore,
    raw_message_store as default_raw_store,
)
from src.services.core.summary_store import (
    SummaryStore,
    summary_store as default_summary_store,
)
from src.services.core.lossless_recall_service import (
    LosslessRecallService,
    lossless_recall_service as default_recall_service,
)
from src.embedding.client import get_embedding_client

logger = logging.getLogger(__name__)

DEFAULT_CHUNK_SIZE = 5000
MAX_TOKENS_PER_MESSAGE = 1000  # Long document threshold (~4000 Chinese characters)


def generate_document_id() -> str:
    return f"doc_{uuid.uuid4().hex[:16]}"


def split_into_chunks(content: str, max_chars: int = DEFAULT_CHUNK_SIZE) -> List[str]:
    if len(content) <= max_chars:
        return [content]

    chunks = []
    paragraphs = content.split("\n\n")
    current_chunk = ""

    for para in paragraphs:
        if len(current_chunk) + len(para) + 2 <= max_chars:
            current_chunk += ("\n\n" if current_chunk else "") + para
        else:
            if current_chunk:
                chunks.append(current_chunk)

            if len(para) > max_chars:
                for i in range(0, len(para), max_chars):
                    chunks.append(para[i : i + max_chars])
                current_chunk = ""
            else:
                current_chunk = para

    if current_chunk:
        chunks.append(current_chunk)

    return chunks


class UnifiedMemoryService:
    def __init__(
        self,
        raw_store: Optional[RawMessageStore] = None,
        summary_store: Optional[SummaryStore] = None,
        recall_service: Optional[LosslessRecallService] = None,
        entity_extractor: Optional[Any] = None,
        graph_builder: Optional[Any] = None,
    ):
        self.raw_store = raw_store or default_raw_store
        self.summary_store = summary_store or default_summary_store
        self.recall_service = recall_service or default_recall_service
        self.embedding_client = get_embedding_client()

        # Entity extraction services (lazy initialization)
        self._entity_extractor = entity_extractor
        self._graph_builder = graph_builder

    @property
    def entity_extractor(self):
        if self._entity_extractor is None:
            from src.services.memory_extraction_service import (
                get_memory_extraction_service,
            )

            self._entity_extractor = get_memory_extraction_service()
        return self._entity_extractor

    @property
    def graph_builder(self):
        if self._graph_builder is None:
            from src.services.graph_builder_service import get_graph_builder_service

            self._graph_builder = get_graph_builder_service()
        return self._graph_builder

    async def store(
        self,
        user_id: str,
        content: str,
        source: str = "manual",
        agent_id: Optional[str] = None,
        session_id: Optional[str] = None,
        memory_type: str = "preference",
        metadata: Optional[Dict] = None,
        enable_graph: bool = True,
    ) -> Dict[str, Any]:
        actual_agent_id = None if source == "manual" else agent_id

        actual_memory_type: MemoryType = (
            "dialogue" if source == "agent" else cast(MemoryType, memory_type)
        )

        is_long = self._is_long_document(content, source, metadata or {})

        location_name = metadata.get("location_name") if metadata else None
        location_address = metadata.get("location_address") if metadata else None
        location_latitude = metadata.get("location_latitude") if metadata else None
        location_longitude = metadata.get("location_longitude") if metadata else None
        people = metadata.get("people") if metadata else None
        emotion = metadata.get("emotion") if metadata else None
        tags = metadata.get("tags") if metadata else None
        time_value = metadata.get("time_value") if metadata else None
        importance_score = metadata.get("importance_score", 0.5) if metadata else 0.5

        raw_id = await self.raw_store.store(
            user_id=user_id,
            content=content,
            memory_type=actual_memory_type,
            agent_id=actual_agent_id,
            session_id=session_id,
            location_name=location_name,
            location_address=location_address,
            location_latitude=location_latitude,
            location_longitude=location_longitude,
            people=people,
            emotion=emotion,
            tags=tags,
            metadata=metadata or {},
            source_type=source,
            importance_score=importance_score,
            time_value=time_value,
        )

        embedding = None
        try:
            embedding = self.embedding_client.embed(content)
            if embedding:
                await self.raw_store.update_embedding(raw_id, embedding)
        except Exception as e:
            logger.warning(f"Failed to generate embedding: {e}")

        entities_result = {"entities": [], "entities_count": 0}

        if enable_graph:
            if source == "manual" and not is_long:
                entities_result = await self._extract_and_store_entities_for_user(
                    content=content,
                    user_id=user_id,
                    memory_id=raw_id,
                )

        return {
            "raw_message_id": raw_id,
            "memory_type": actual_memory_type,
            "agent_id": actual_agent_id,
            "source": source,
            "is_long_document": is_long,
            "has_embedding": embedding is not None,
            "entities": entities_result.get("entities", []),
            "entities_count": entities_result.get("entities_count", 0),
        }

    async def store_agent_message(
        self,
        user_id: str,
        agent_id: str,
        session_id: str,
        role: str,
        content: str,
    ) -> Dict[str, Any]:
        return await self.store(
            user_id=user_id,
            content=content,
            source="agent",
            agent_id=agent_id,
            session_id=session_id,
            memory_type="dialogue",
            metadata={"role": role},
        )

    async def recall(
        self,
        query: str,
        user_id: str,
        scope: str = "all",
        agent_id: Optional[str] = None,
        limit: int = 20,
        min_similarity: float = 0.3,
    ) -> List[Dict[str, Any]]:
        return await self.recall_service.hybrid_recall(
            query=query,
            user_id=user_id,
            agent_id=agent_id,
            scope=scope,
            limit=limit,
            min_similarity=min_similarity,
        )

    async def get_user_memories(
        self,
        user_id: str,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        messages = await self.raw_store.get_user_preferences(user_id, limit)

        return [
            {
                "id": msg.id,
                "content": msg.content,
                "memory_type": msg.memory_type,
                "agent_id": msg.agent_id,
                "tags": msg.tags,
                "created_at": msg.created_at.isoformat() if msg.created_at else None,
            }
            for msg in messages
        ]

    async def get_memory_by_id(
        self,
        memory_id: str,
    ) -> Optional[Dict[str, Any]]:
        msg = await self.raw_store.get_by_id(memory_id)

        if not msg:
            return None

        return {
            "id": msg.id,
            "content": msg.content,
            "memory_type": msg.memory_type,
            "agent_id": msg.agent_id,
            "session_id": msg.session_id,
            "role": msg.role,
            "location_name": msg.location_name,
            "location_address": msg.location_address,
            "people": msg.people,
            "emotion": msg.emotion,
            "tags": msg.tags,
            "source_type": msg.source_type,
            "importance_score": msg.importance_score,
            "created_at": msg.created_at.isoformat() if msg.created_at else None,
        }

    async def delete_memory(
        self,
        memory_id: str,
    ) -> bool:
        return await self.raw_store.delete(memory_id)

    async def archive_memory(
        self,
        memory_id: str,
    ) -> bool:
        return await self.raw_store.archive(memory_id)

    async def store_long_document(
        self,
        user_id: str,
        content: str,
        memory_type: MemoryType = "note",
        metadata: Optional[Dict] = None,
        max_chunk_size: int = DEFAULT_CHUNK_SIZE,
        auto_compress: bool = True,
    ) -> Dict[str, Any]:
        document_id = generate_document_id()

        chunks = split_into_chunks(content, max_chunk_size)

        chunk_ids = []
        total_tokens = 0

        for i, chunk_content in enumerate(chunks):
            chunk_metadata = {
                **(metadata or {}),
                "chunk_index": i,
                "total_chunks": len(chunks),
            }

            raw_id = await self.raw_store.store(
                user_id=user_id,
                content=chunk_content,
                memory_type=memory_type,
                agent_id=None,
                document_id=document_id,
                tags=metadata.get("tags") if metadata else None,
                metadata=chunk_metadata,
                source_type="manual",
                input_type="text",
            )

            try:
                embedding = self.embedding_client.embed(chunk_content)
                if embedding:
                    await self.raw_store.update_embedding(raw_id, embedding)
            except Exception as e:
                logger.warning(f"Failed to generate embedding for chunk {i}: {e}")

            chunk_ids.append(raw_id)
            total_tokens += len(chunk_content) // 4

        summary_id = None

        if auto_compress and len(chunks) > 1:
            summary_id = await self._compress_document_chunks(
                document_id=document_id,
                user_id=user_id,
                chunk_ids=chunk_ids,
                content=content,
            )

        return {
            "document_id": document_id,
            "chunk_count": len(chunks),
            "chunk_ids": chunk_ids,
            "summary_id": summary_id,
            "memory_type": memory_type,
            "source": "manual",
            "total_tokens": total_tokens,
        }

    async def store_file(
        self,
        user_id: str,
        content: bytes,
        file_name: str,
        metadata: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        content_hash = hashlib.sha256(content).hexdigest()

        existing = await db.fetchrow(
            "SELECT document_id FROM raw_messages WHERE metadata->>'content_hash' = $1 AND user_id = $2 LIMIT 1",
            content_hash,
            user_id,
        )

        if existing:
            return {
                "status": "duplicate",
                "document_id": existing["document_id"],
                "message": "File already exists",
            }

        try:
            text_content = content.decode("utf-8")
        except UnicodeDecodeError:
            try:
                text_content = content.decode("gbk")
            except:
                text_content = content.decode("utf-8", errors="ignore")

        file_metadata = {
            **(metadata or {}),
            "file_name": file_name,
            "file_size": len(content),
            "content_hash": content_hash,
        }

        result = await self.store_long_document(
            user_id=user_id,
            content=text_content,
            memory_type="note",
            metadata=file_metadata,
        )

        return {
            "status": "created",
            "document_id": result["document_id"],
            "chunk_count": result["chunk_count"],
            "file_name": file_name,
            "file_size": len(content),
        }

    async def get_document_chunks(
        self,
        document_id: str,
        user_id: str,
    ) -> List[Dict[str, Any]]:
        rows = await db.fetch(
            """
            SELECT id, content, metadata->>'chunk_index' as chunk_index,
                   token_count, created_at
            FROM raw_messages
            WHERE document_id = $1 AND user_id = $2
            ORDER BY (metadata->>'chunk_index')::int ASC
            """,
            document_id,
            user_id,
        )

        return [
            {
                "id": row["id"],
                "content": row["content"],
                "chunk_index": int(row["chunk_index"]) if row["chunk_index"] else 0,
                "token_count": row["token_count"],
                "created_at": row["created_at"].isoformat()
                if row["created_at"]
                else None,
            }
            for row in rows
        ]

    def _is_long_document(self, content: str, source: str, metadata: Dict) -> bool:
        token_count = len(content) // 4  # Rough estimate
        if token_count > MAX_TOKENS_PER_MESSAGE:
            return True
        if len(content) > 5000:
            return True
        if source == "file":
            return True
        if metadata.get("is_document"):
            return True
        return False

    def _deduplicate_entities(self, entities: List[Dict]) -> List[Dict]:
        seen = set()
        unique = []
        for e in entities:
            key = (e.get("name"), e.get("type"))
            if key not in seen:
                seen.add(key)
                unique.append(e)
        return unique

    def _deduplicate_relations(self, relations: List[Dict]) -> List[Dict]:
        seen = set()
        unique = []
        for r in relations:
            key = (r.get("source"), r.get("target"), r.get("relation_type"))
            if key not in seen:
                seen.add(key)
                unique.append(r)
        return unique

    async def _link_message_entity(self, message_id: str, entity_id: str):
        await db.execute(
            """
            INSERT INTO memory_entities (memory_id, entity_id)
            VALUES ($1, $2)
            ON CONFLICT DO NOTHING
        """,
            message_id,
            entity_id,
        )

    async def _extract_and_store_entities_for_user(
        self,
        content: str,
        user_id: str,
        memory_id: str,
    ) -> Dict[str, Any]:
        try:
            extraction_result = await self.entity_extractor.extract_memories(content)

            if not extraction_result or not extraction_result.get("success"):
                return {"entities": [], "relations": [], "entities_count": 0}

            memories = extraction_result.get("memories", [])
            all_entities = []
            all_relations = []

            for memory in memories:
                entities = memory.get("entities", [])
                relations = memory.get("relations", [])
                all_entities.extend(entities)
                all_relations.extend(relations)

            unique_entities = self._deduplicate_entities(all_entities)
            unique_relations = self._deduplicate_relations(all_relations)

            entity_ids = {}
            for entity in unique_entities:
                entity_name = entity.get("name")
                entity_type = entity.get("type", "unknown")
                confidence = entity.get("confidence", 0.8)

                if not entity_name or entity_name == "我":
                    continue

                entity_id = await self.graph_builder._upsert_entity(
                    name=entity_name,
                    entity_type=entity_type,
                    user_id=user_id,
                    agent_id=None,
                    confidence=confidence,
                )

                if entity_id:
                    entity_ids[entity_name] = entity_id
                    await self._link_message_entity(memory_id, entity_id)

            for relation in unique_relations:
                source = relation.get("source")
                target = relation.get("target")
                rel_type = relation.get("relation_type")
                confidence = relation.get("confidence", 0.8)

                if not source or not target or not rel_type or target == "我":
                    continue

                await self.graph_builder._upsert_relation(
                    from_entity=source,
                    to_entity=target,
                    relation_type=rel_type,
                    confidence=confidence,
                    user_id=user_id,
                )

            return {
                "entities": unique_entities,
                "relations": unique_relations,
                "entities_count": len(unique_entities),
            }

        except Exception as e:
            logger.warning(f"Entity extraction failed: {e}")
            return {"entities": [], "relations": [], "entities_count": 0}

    async def _compress_document_chunks(
        self,
        document_id: str,
        user_id: str,
        chunk_ids: List[str],
        content: str,
    ) -> Optional[str]:
        try:
            from src.llm.client import get_llm_client

            llm_client = get_llm_client()

            max_summary_input = 15000
            summary_input = content[:max_summary_input]
            if len(content) > max_summary_input:
                summary_input += "\n...[内容已截断]"

            prompt = (
                f"请总结以下文档的主要内容，保留关键信息和要点：\n\n{summary_input}"
            )
            summary_content = llm_client.chat([{"role": "user", "content": prompt}])

            if not summary_content or not summary_content.strip():
                logger.warning(f"Empty summary generated for document {document_id}")
                return None

            summary_content = summary_content.strip()

            summary_embedding = None
            try:
                summary_embedding = self.embedding_client.embed(summary_content)
            except Exception as e:
                logger.warning(f"Failed to generate summary embedding: {e}")

            summary_token_count = len(summary_content) // 4
            source_token_count = len(content) // 4

            summary_id = await self.summary_store.create_summary(
                user_id=user_id,
                agent_id=None,
                content=summary_content,
                kind="leaf",
                depth=0,
                token_count=summary_token_count,
                document_id=document_id,
                source_message_token_count=source_token_count,
                embedding=summary_embedding,
                model="llm",
                compression_level="normal",
            )

            await self.summary_store.link_messages(summary_id, chunk_ids)

            await self._extract_and_store_entities_for_user(
                content=summary_content,
                user_id=user_id,
                memory_id=summary_id,
            )

            logger.info(
                f"Document compressed: {document_id} -> {summary_id}, "
                f"tokens: {source_token_count} -> {summary_token_count}"
            )

            return summary_id

        except Exception as e:
            logger.warning(f"Document compression failed for {document_id}: {e}")
            return None


unified_memory_service = UnifiedMemoryService()
