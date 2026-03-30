"""
Document storage service with chunking support.

Architecture:
- documents: metadata (title, url, source, stats)
- chunks: content blocks with embeddings
"""

from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime
from dataclasses import dataclass, field
import json
import hashlib

from src.database import db
from src.services.core.document_chunker import document_chunker, ChunkConfig
from src.services.core.document_processor import document_processor
from src.embedding.client import get_embedding_client
from src.config import settings


def compute_content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


@dataclass
class Document:
    id: str
    container_tag: str
    title: Optional[str] = None
    url: Optional[str] = None
    source: Optional[str] = None
    doc_type: str = "text"
    token_count: int = 0
    word_count: int = 0
    chunk_count: int = 0
    content_hash: Optional[str] = None
    status: str = "done"
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


@dataclass
class Chunk:
    id: str
    document_id: str
    content: str
    embedded_content: Optional[str] = None
    position: int = 0
    chunk_type: str = "text"
    content_hash: Optional[str] = None
    embedding: Optional[List[float]] = None
    embedding_model: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: Optional[datetime] = None


class DocumentStore:
    """Document storage with chunking support"""

    def __init__(self):
        self.embedding_client = get_embedding_client()

    async def create(
        self,
        content: str,
        container_tag: str,
        title: Optional[str] = None,
        url: Optional[str] = None,
        source: Optional[str] = None,
        doc_type: str = "text",
        metadata: Optional[Dict[str, Any]] = None,
        chunks: Optional[List[Dict[str, Any]]] = None,
        auto_chunk: bool = True,
        chunk_config: Optional[ChunkConfig] = None,
        document_summary: Optional[str] = None,
        auto_extract: bool = True,
        generate_embeddings: bool = True,
    ) -> Tuple[Document, bool]:
        word_count = len(content.split())
        content_hash = compute_content_hash(content)

        if url:
            existing = await self.find_by_url(container_tag, url)
            if existing:
                return existing, True

        existing = await self.find_by_content_hash(container_tag, content_hash)
        if existing:
            return existing, True

        if chunk_config:
            chunker = document_chunker.__class__(config=chunk_config)
        else:
            chunker = document_chunker

        token_count = chunker._estimate_tokens(content)

        extracted_title = title
        extracted_summary = document_summary

        if auto_extract and (not title or not document_summary):
            try:
                doc_metadata = await document_processor.process_document(content)
                if not title:
                    extracted_title = doc_metadata.title
                if not document_summary:
                    extracted_summary = doc_metadata.summary
            except Exception:
                pass

        row = await db.fetchrow(
            """
            INSERT INTO documents (
                container_tag, title, url, source, doc_type,
                token_count, word_count, chunk_count, metadata, content_hash
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            RETURNING *
            """,
            container_tag,
            extracted_title,
            url,
            source,
            doc_type,
            token_count,
            word_count,
            0,
            json.dumps(metadata or {}),
            content_hash,
        )

        document = self._row_to_document(row)

        if chunks:
            for i, chunk_data in enumerate(chunks):
                await self.create_chunk(
                    document_id=document.id,
                    content=chunk_data.get("content", ""),
                    position=i,
                    chunk_type=chunk_data.get("type", "text"),
                    embedding=chunk_data.get("embedding"),
                    embedding_model=chunk_data.get("embedding_model"),
                    generate_embedding=generate_embeddings,
                )

            await db.execute(
                "UPDATE documents SET chunk_count = $1 WHERE id = $2",
                len(chunks),
                document.id,
            )
            document.chunk_count = len(chunks)

        elif auto_chunk:
            text_chunks = chunker.chunk(
                content,
                metadata=metadata,
                document_title=extracted_title,
                document_summary=extracted_summary,
            )

            for chunk in text_chunks:
                await self.create_chunk(
                    document_id=document.id,
                    content=chunk.content,
                    embedded_content=chunk.embedded_content,
                    position=chunk.position,
                    chunk_type="text",
                    metadata=chunk.metadata,
                    generate_embedding=generate_embeddings,
                )

            if text_chunks:
                await db.execute(
                    "UPDATE documents SET chunk_count = $1, token_count = $2 WHERE id = $3",
                    len(text_chunks),
                    sum(c.token_count for c in text_chunks),
                    document.id,
                )
                document.chunk_count = len(text_chunks)
                document.token_count = sum(c.token_count for c in text_chunks)

        return document, False

    async def create_chunk(
        self,
        document_id: str,
        content: str,
        embedded_content: Optional[str] = None,
        position: int = 0,
        chunk_type: str = "text",
        embedding: Optional[List[float]] = None,
        embedding_model: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        generate_embedding: bool = True,
    ) -> Chunk:
        content_hash = compute_content_hash(content)

        if embedding is None and generate_embedding and self.embedding_client:
            try:
                text_to_embed = embedded_content if embedded_content else content
                embedding = await self.embedding_client.embed(text_to_embed)
                embedding_model = settings.VOLC_EMBEDDING_MODEL
            except Exception:
                pass

        embedding_str = None
        if embedding:
            embedding_str = "[" + ",".join(map(str, embedding)) + "]"

        row = await db.fetchrow(
            """
            INSERT INTO chunks (
                document_id, content, embedded_content, position, chunk_type,
                embedding, embedding_model, metadata, content_hash
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            RETURNING *
            """,
            document_id,
            content,
            embedded_content,
            position,
            chunk_type,
            embedding_str,
            embedding_model,
            json.dumps(metadata or {}),
            content_hash,
        )

        return self._row_to_chunk(row)

    async def get_by_id(self, document_id: str) -> Optional[Document]:
        row = await db.fetchrow(
            "SELECT * FROM documents WHERE id = $1",
            document_id,
        )
        return self._row_to_document(row) if row else None

    async def get_by_container(
        self,
        container_tag: str,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Document]:
        rows = await db.fetch(
            """
            SELECT * FROM documents
            WHERE container_tag = $1
            ORDER BY created_at DESC
            LIMIT $2 OFFSET $3
            """,
            container_tag,
            limit,
            offset,
        )
        return [self._row_to_document(row) for row in rows]

    async def find_by_url(self, container_tag: str, url: str) -> Optional[Document]:
        row = await db.fetchrow(
            """
            SELECT * FROM documents
            WHERE container_tag = $1 AND url = $2
            """,
            container_tag,
            url,
        )
        return self._row_to_document(row) if row else None

    async def find_by_content_hash(
        self, container_tag: str, content_hash: str
    ) -> Optional[Document]:
        row = await db.fetchrow(
            """
            SELECT * FROM documents
            WHERE container_tag = $1 AND content_hash = $2
            """,
            container_tag,
            content_hash,
        )
        return self._row_to_document(row) if row else None

    async def update(
        self,
        document_id: str,
        content: str,
        title: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        auto_chunk: bool = True,
        chunk_config: Optional[ChunkConfig] = None,
        generate_embeddings: bool = True,
    ) -> Tuple[Optional[Document], bool]:
        document = await self.get_by_id(document_id)
        if not document:
            return None, False

        new_content_hash = compute_content_hash(content)

        if document.content_hash == new_content_hash:
            return document, True

        if chunk_config:
            chunker = document_chunker.__class__(config=chunk_config)
        else:
            chunker = document_chunker

        token_count = chunker._estimate_tokens(content)
        word_count = len(content.split())

        if auto_chunk:
            text_chunks = chunker.chunk(content)
            await self.update_chunks(document_id, text_chunks, generate_embeddings)
            chunk_count = len(text_chunks)
        else:
            chunk_count = document.chunk_count

        row = await db.fetchrow(
            """
            UPDATE documents
            SET content_hash = $1, token_count = $2, word_count = $3,
                chunk_count = $4, title = COALESCE($5, title),
                metadata = COALESCE($6, metadata), updated_at = NOW()
            WHERE id = $7
            RETURNING *
            """,
            new_content_hash,
            token_count,
            word_count,
            chunk_count,
            title,
            json.dumps(metadata) if metadata else None,
            document_id,
        )

        return self._row_to_document(row) if row else None, False

    async def update_chunks(
        self,
        document_id: str,
        new_chunks: List[Any],
        generate_embeddings: bool = True,
    ) -> None:
        existing_chunks = await self.get_chunks(document_id)
        existing_by_position = {c.position: c for c in existing_chunks}

        for i, chunk in enumerate(new_chunks):
            new_hash = compute_content_hash(chunk.content)

            if i in existing_by_position:
                existing = existing_by_position[i]
                if existing.content_hash != new_hash:
                    await db.execute(
                        """
                        UPDATE chunks
                        SET content = $1, content_hash = $2,
                            embedded_content = $3, metadata = $4
                        WHERE id = $5
                        """,
                        chunk.content,
                        new_hash,
                        chunk.embedded_content,
                        json.dumps(chunk.metadata)
                        if hasattr(chunk, "metadata")
                        else "{}",
                        existing.id,
                    )

                    if generate_embeddings and self.embedding_client:
                        try:
                            text_to_embed = chunk.embedded_content or chunk.content
                            embedding = await self.embedding_client.embed(text_to_embed)
                            embedding_str = "[" + ",".join(map(str, embedding)) + "]"
                            await db.execute(
                                "UPDATE chunks SET embedding = $1 WHERE id = $2",
                                embedding_str,
                                existing.id,
                            )
                        except Exception:
                            pass
            else:
                await self.create_chunk(
                    document_id=document_id,
                    content=chunk.content,
                    embedded_content=chunk.embedded_content,
                    position=i,
                    chunk_type="text",
                    metadata=chunk.metadata if hasattr(chunk, "metadata") else None,
                    generate_embedding=generate_embeddings,
                )

        if len(existing_chunks) > len(new_chunks):
            positions_to_delete = [c.id for c in existing_chunks[len(new_chunks) :]]
            if positions_to_delete:
                await db.execute(
                    "DELETE FROM chunks WHERE id = ANY($1)",
                    positions_to_delete,
                )

    async def get_chunks(self, document_id: str) -> List[Chunk]:
        rows = await db.fetch(
            """
            SELECT * FROM chunks
            WHERE document_id = $1
            ORDER BY position
            """,
            document_id,
        )
        return [self._row_to_chunk(row) for row in rows]

    async def delete(self, document_id: str) -> bool:
        result = await db.execute(
            "DELETE FROM documents WHERE id = $1",
            document_id,
        )
        return result == "DELETE 1"

    async def update_status(
        self,
        document_id: str,
        status: str,
    ) -> bool:
        valid_statuses = [
            "queued",
            "extracting",
            "chunking",
            "embedding",
            "indexing",
            "done",
            "failed",
        ]
        if status not in valid_statuses:
            raise ValueError(f"Invalid status: {status}")

        result = await db.execute(
            """
            UPDATE documents SET status = $1, updated_at = NOW()
            WHERE id = $2
            """,
            status,
            document_id,
        )
        return result == "UPDATE 1"

    async def count(self, container_tag: str) -> int:
        return await db.fetchval(
            "SELECT COUNT(*) FROM documents WHERE container_tag = $1",
            container_tag,
        )

    async def search_chunks(
        self,
        query_embedding: List[float],
        container_tag: str,
        limit: int = 10,
        threshold: float = 0.5,
    ) -> List[Dict[str, Any]]:
        embedding_str = "[" + ",".join(map(str, query_embedding)) + "]"

        rows = await db.fetch(
            """
            SELECT c.*, d.container_tag, d.title,
                   1 - (c.embedding <=> $1::vector) as similarity
            FROM chunks c
            JOIN documents d ON c.document_id = d.id
            WHERE d.container_tag = $2
            AND 1 - (c.embedding <=> $1::vector) > $3
            ORDER BY similarity DESC
            LIMIT $4
            """,
            embedding_str,
            container_tag,
            threshold,
            limit,
        )

        return [
            {
                "chunk": self._row_to_chunk(row),
                "document_id": row["document_id"],
                "title": row["title"],
                "similarity": float(row["similarity"]) if row["similarity"] else 0.0,
            }
            for row in rows
        ]

    def _row_to_document(self, row: Dict) -> Document:
        return Document(
            id=row["id"],
            container_tag=row["container_tag"],
            title=row.get("title"),
            url=row.get("url"),
            source=row.get("source"),
            doc_type=row.get("doc_type", "text"),
            token_count=row.get("token_count", 0),
            word_count=row.get("word_count", 0),
            chunk_count=row.get("chunk_count", 0),
            content_hash=row.get("content_hash"),
            status=row.get("status", "done"),
            metadata=row.get("metadata", {}) or {},
            created_at=row.get("created_at"),
            updated_at=row.get("updated_at"),
        )

    def _row_to_chunk(self, row: Dict) -> Chunk:
        embedding = None
        if row.get("embedding"):
            emb_str = row["embedding"]
            if isinstance(emb_str, str) and emb_str.startswith("["):
                embedding = json.loads(emb_str)

        return Chunk(
            id=row["id"],
            document_id=row["document_id"],
            content=row["content"],
            embedded_content=row.get("embedded_content"),
            position=row.get("position", 0),
            chunk_type=row.get("chunk_type", "text"),
            content_hash=row.get("content_hash"),
            embedding=embedding,
            embedding_model=row.get("embedding_model"),
            metadata=row.get("metadata", {}) or {},
            created_at=row.get("created_at"),
        )


document_store = DocumentStore()
