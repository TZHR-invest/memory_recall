import logging
import uuid
import hashlib
from typing import Optional, List, Dict, Any
from datetime import datetime

from src.database import db
from src.services.lossless.raw_message_store import RawMessageStore, raw_message_store
from src.services.lossless.summary_store import SummaryStore, summary_store
from src.services.lossless.lossless_recall_service import (
    LosslessRecallService,
    lossless_recall_service,
)
from src.embedding.client import get_embedding_client

logger = logging.getLogger(__name__)

DEFAULT_CHUNK_SIZE = 5000


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
    ):
        self.raw_store = raw_store or raw_message_store
        self.summary_store = summary_store or summary_store
        self.recall_service = recall_service or lossless_recall_service
        self.embedding_client = get_embedding_client()

    async def store(
        self,
        user_id: str,
        content: str,
        source: str = "manual",
        agent_id: Optional[str] = None,
        session_id: Optional[str] = None,
        memory_type: str = "preference",
        metadata: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        actual_agent_id = None if source == "manual" else agent_id

        actual_memory_type = "dialogue" if source == "agent" else memory_type

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

        return {
            "raw_message_id": raw_id,
            "memory_type": actual_memory_type,
            "agent_id": actual_agent_id,
            "source": source,
            "has_embedding": embedding is not None,
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
        memory_type: str = "note",
        metadata: Optional[Dict] = None,
        max_chunk_size: int = DEFAULT_CHUNK_SIZE,
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

        return {
            "document_id": document_id,
            "chunk_count": len(chunks),
            "chunk_ids": chunk_ids,
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


unified_memory_service = UnifiedMemoryService()
