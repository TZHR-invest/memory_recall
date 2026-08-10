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
    status: str = "queued"
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: Optional[datetime] = None
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
        async_process: bool = False,
    ) -> Tuple[Document, bool]:
        word_count = len(content.split())
        content_hash = compute_content_hash(content)

        # Priority 1: Deduplicate by source + title (3-key: container_tag, source, title)
        # If title provided, match on all three keys; otherwise legacy 2-key (container_tag, source)
        if source:
            existing = await self.find_by_source(container_tag, source, title=title)
            if existing:
                # Content changed → update document and chunks
                if existing.content_hash != content_hash:
                    updated, unchanged = await self.update(
                        existing.id,
                        content,
                        title=title,
                        metadata=metadata,
                        auto_chunk=auto_chunk,
                        chunk_config=chunk_config,
                        generate_embeddings=generate_embeddings,
                    )
                    if updated is None:
                        raise RuntimeError(f"Failed to update document {existing.id}")
                    return updated, unchanged
                # Content unchanged → return existing
                return existing, True

        # Priority 2: Deduplicate by URL (same URL, regardless of content)
        if url:
            existing = await self.find_by_url(container_tag, url)
            if existing:
                return existing, True

        # Priority 3: Deduplicate by content hash (same content, no source)
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

        # 异步模式：跳过 LLM 提取，后续在 process_document_async 中完成
        if not async_process and auto_extract and (not title or not document_summary):
            try:
                doc_metadata = await document_processor.process_document(content)
                if not title:
                    extracted_title = doc_metadata.title
                if not document_summary:
                    extracted_summary = doc_metadata.summary
            except Exception:
                pass

        initial_status = "queued" if async_process else "done"

        row = await db.fetchrow(
            """
            INSERT INTO documents (
                container_tag, title, url, source, doc_type,
                token_count, word_count, chunk_count, metadata, content_hash, status
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
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
            initial_status,
        )

        document = self._row_to_document(row)

        # 异步模式：只创建记录，后续处理交给 process_document_async
        if async_process:
            # 存储 content 供后续处理（documents 表不存原文，临时放在 metadata）
            meta = metadata or {}
            meta["_pending_content"] = content
            meta["_pending_auto_chunk"] = auto_chunk
            meta["_pending_auto_extract"] = auto_extract
            meta["_pending_generate_embeddings"] = generate_embeddings
            meta["_pending_document_summary"] = document_summary
            if chunk_config:
                meta["_pending_chunk_config"] = {
                    "max_chunk_tokens": chunk_config.max_chunk_tokens,
                    "overlap_tokens": chunk_config.overlap_tokens,
                    "min_chunk_tokens": chunk_config.min_chunk_tokens,
                }
            await db.execute(
                "UPDATE documents SET metadata = $1 WHERE id = $2",
                json.dumps(meta),
                document.id,
            )
            return document, False

        # ── 同步模式：原有的完整处理流程 ──

        if chunks:
            # 批量生成 embedding（一次 API 调用替代 N 次串行调用）
            chunk_embeddings = [None] * len(chunks)
            if generate_embeddings and self.embedding_client:
                texts_to_embed = [
                    chunk_data.get("embedded_content") or chunk_data.get("content", "")
                    for chunk_data in chunks
                    if not chunk_data.get("embedding")  # 跳过已有 embedding 的
                ]
                if texts_to_embed:
                    batch_result = await self.embedding_client.embed_batch(texts_to_embed)
                    if batch_result:
                        ei = 0
                        for i, chunk_data in enumerate(chunks):
                            if not chunk_data.get("embedding"):
                                chunk_embeddings[i] = batch_result[ei] if ei < len(batch_result) else None
                                ei += 1

            for i, chunk_data in enumerate(chunks):
                await self.create_chunk(
                    document_id=document.id,
                    content=chunk_data.get("content", ""),
                    position=i,
                    chunk_type=chunk_data.get("type", "text"),
                    embedding=chunk_data.get("embedding") or chunk_embeddings[i],
                    embedding_model=chunk_data.get("embedding_model") or (settings.VOLC_EMBEDDING_MODEL if chunk_embeddings[i] else None),
                    generate_embedding=False,  # 已批量生成，跳过
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

            # 批量生成 embedding（一次 API 调用替代 N 次串行调用）
            chunk_embeddings = [None] * len(text_chunks)
            if generate_embeddings and self.embedding_client:
                texts_to_embed = [
                    chunk.embedded_content or chunk.content
                    for chunk in text_chunks
                ]
                if texts_to_embed:
                    batch_result = await self.embedding_client.embed_batch(texts_to_embed)
                    if batch_result:
                        chunk_embeddings = [
                            batch_result[i] if i < len(batch_result) else None
                            for i in range(len(text_chunks))
                        ]

            for i, chunk in enumerate(text_chunks):
                await self.create_chunk(
                    document_id=document.id,
                    content=chunk.content,
                    embedded_content=chunk.embedded_content,
                    position=chunk.position,
                    chunk_type="text",
                    metadata=chunk.metadata,
                    embedding=chunk_embeddings[i],
                    embedding_model=settings.VOLC_EMBEDDING_MODEL if chunk_embeddings[i] else None,
                    generate_embedding=False,  # 已批量生成，跳过
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

        if extracted_summary and auto_chunk:
            try:
                await self._extract_and_map_entities_to_chunks(
                    document_id=document.id,
                    summary=extracted_summary,
                    container_tag=container_tag,
                )
            except Exception as e:
                import logging

                logging.warning(f"Failed to extract entities from summary: {e}")

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

    async def find_by_source(
        self, container_tag: str, source: str, title: Optional[str] = None
    ) -> Optional[Document]:
        """Find document by source path within a container.
        
        If title is provided, match on container_tag + source + title (3-key dedup).
        If title is None, match on container_tag + source only (legacy behavior).
        """
        if title:
            row = await db.fetchrow(
                """
                SELECT * FROM documents
                WHERE container_tag = $1 AND source = $2 AND title = $3
                """,
                container_tag,
                source,
                title,
            )
        else:
            row = await db.fetchrow(
                """
                SELECT * FROM documents
                WHERE container_tag = $1 AND source = $2
                """,
                container_tag,
                source,
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
        document_summary: Optional[str] = None,
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

        updated_doc = self._row_to_document(row) if row else None

        if updated_doc and auto_chunk:
            try:
                summary = document_summary
                if not summary:
                    try:
                        doc_metadata = await document_processor.process_document(
                            content
                        )
                        summary = doc_metadata.summary
                    except Exception:
                        pass

                if summary:
                    await db.execute(
                        "DELETE FROM chunk_entities WHERE chunk_id IN (SELECT id FROM chunks WHERE document_id = $1)",
                        document_id,
                    )
                    await self._extract_and_map_entities_to_chunks(
                        document_id=document_id,
                        summary=summary,
                        container_tag=document.container_tag,
                    )
            except Exception:
                pass

        return updated_doc, False

    async def update_chunks(
        self,
        document_id: str,
        new_chunks: List[Any],
        generate_embeddings: bool = True,
    ) -> None:
        existing_chunks = await self.get_chunks(document_id)
        existing_by_position = {c.position: c for c in existing_chunks}

        # 批量生成需要更新的 embedding
        chunks_need_embed = []  # (index, chunk_or_existing_id)
        for i, chunk in enumerate(new_chunks):
            if i in existing_by_position:
                existing = existing_by_position[i]
                new_hash = compute_content_hash(chunk.content)
                if existing.content_hash != new_hash and generate_embeddings and self.embedding_client:
                    chunks_need_embed.append((i, "update", chunk.embedded_content or chunk.content))
            else:
                if generate_embeddings and self.embedding_client:
                    chunks_need_embed.append((i, "create", chunk.embedded_content or chunk.content))

        # 批量 embed
        batch_embeddings = {}
        if chunks_need_embed:
            texts = [text for _, _, text in chunks_need_embed]
            batch_result = await self.embedding_client.embed_batch(texts)
            if batch_result:
                for j, (idx, action, _) in enumerate(chunks_need_embed):
                    if j < len(batch_result):
                        batch_embeddings[idx] = batch_result[j]

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

                    if i in batch_embeddings:
                        try:
                            embedding = batch_embeddings[i]
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
                    embedding=batch_embeddings.get(i),
                    embedding_model=settings.VOLC_EMBEDDING_MODEL if i in batch_embeddings else None,
                    generate_embedding=False,  # 已批量生成
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

    async def process_document_async(self, document_id: str) -> None:
        """异步处理文档：标题/摘要提取 → chunking → embedding → 实体提取。
        由 FastAPI BackgroundTasks 调用，处理完成后 status=done。"""
        import logging as _logging
        _logger = _logging.getLogger("document_store.async")

        try:
            # 读取 pending 信息
            row = await db.fetchrow(
                "SELECT metadata, container_tag FROM documents WHERE id = $1",
                document_id,
            )
            if not row:
                _logger.error(f"Document {document_id} not found for async processing")
                return

            meta = row["metadata"] if isinstance(row["metadata"], dict) else json.loads(row["metadata"] or "{}")
            container_tag = row["container_tag"]
            content = meta.pop("_pending_content", None)
            auto_chunk = meta.pop("_pending_auto_chunk", True)
            auto_extract = meta.pop("_pending_auto_extract", True)
            generate_embeddings = meta.pop("_pending_generate_embeddings", True)
            document_summary = meta.pop("_pending_document_summary", None)
            chunk_config_dict = meta.pop("_pending_chunk_config", None)

            if not content:
                await self.update_status(document_id, "failed")
                _logger.error(f"Document {document_id}: no pending content found")
                return

            # Step 1: LLM 提取标题/摘要
            await self.update_status(document_id, "extracting")
            extracted_title = None
            extracted_summary = document_summary
            if auto_extract:
                try:
                    doc_metadata = await document_processor.process_document(content)
                    extracted_title = doc_metadata.title
                    if not document_summary:
                        extracted_summary = doc_metadata.summary
                except Exception as e:
                    _logger.warning(f"Document {document_id}: extract failed: {e}")

            # 更新标题
            if extracted_title:
                await db.execute(
                    "UPDATE documents SET title = $1 WHERE id = $2",
                    extracted_title,
                    document_id,
                )

            # Step 2: Chunking
            await self.update_status(document_id, "chunking")
            if chunk_config_dict:
                chunk_config = ChunkConfig(
                    max_chunk_tokens=chunk_config_dict.get("max_chunk_tokens", 800),
                    overlap_tokens=chunk_config_dict.get("overlap_tokens", 50),
                    min_chunk_tokens=chunk_config_dict.get("min_chunk_tokens", 50),
                )
                chunker = document_chunker.__class__(config=chunk_config)
            else:
                chunker = document_chunker

            if auto_chunk:
                text_chunks = chunker.chunk(
                    content,
                    metadata=meta,
                    document_title=extracted_title,
                    document_summary=extracted_summary,
                )

                # Step 3: 批量 Embedding
                await self.update_status(document_id, "embedding")
                chunk_embeddings = [None] * len(text_chunks)
                if generate_embeddings and self.embedding_client:
                    texts_to_embed = [
                        chunk.embedded_content or chunk.content
                        for chunk in text_chunks
                    ]
                    if texts_to_embed:
                        batch_result = await self.embedding_client.embed_batch(texts_to_embed)
                        if batch_result:
                            chunk_embeddings = [
                                batch_result[i] if i < len(batch_result) else None
                                for i in range(len(text_chunks))
                            ]

                # Step 4: 写入 chunks
                await self.update_status(document_id, "indexing")
                for i, chunk in enumerate(text_chunks):
                    await self.create_chunk(
                        document_id=document_id,
                        content=chunk.content,
                        embedded_content=chunk.embedded_content,
                        position=chunk.position,
                        chunk_type="text",
                        metadata=chunk.metadata,
                        embedding=chunk_embeddings[i],
                        embedding_model=settings.VOLC_EMBEDDING_MODEL if chunk_embeddings[i] else None,
                        generate_embedding=False,
                    )

                await db.execute(
                    "UPDATE documents SET chunk_count = $1, token_count = $2 WHERE id = $3",
                    len(text_chunks),
                    sum(c.token_count for c in text_chunks),
                    document_id,
                )

            # Step 5: 实体提取
            if extracted_summary and auto_chunk:
                try:
                    await self._extract_and_map_entities_to_chunks(
                        document_id=document_id,
                        summary=extracted_summary,
                        container_tag=container_tag,
                    )
                except Exception as e:
                    _logger.warning(f"Document {document_id}: entity extraction failed: {e}")

            # 清理 metadata 中的 pending 字段，更新最终状态
            await db.execute(
                "UPDATE documents SET metadata = $1, status = $2 WHERE id = $3",
                json.dumps(meta),
                "done",
                document_id,
            )
            _logger.info(f"Document {document_id}: async processing complete")

        except Exception as e:
            try:
                await self.update_status(document_id, "failed")
            except Exception:
                pass
            _logger.error(f"Document {document_id}: async processing failed: {e}")

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
            SELECT c.*, d.container_tag, d.title, d.source,
                   1 - (c.embedding <=> $1::vector) as similarity
            FROM chunks c
            JOIN documents d ON c.document_id = d.id
            WHERE d.container_tag = $2
            AND d.status = 'done'
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
                "source": row["source"],
                "similarity": float(row["similarity"]) if row["similarity"] else 0.0,
            }
            for row in rows
        ]

    async def _extract_and_map_entities_to_chunks(
        self,
        document_id: str,
        summary: str,
        container_tag: str,
    ) -> None:
        from src.services.core.entity_extraction import entity_extractor

        ner_entities = entity_extractor.extract(summary)

        if not ner_entities:
            return

        chunks = await self.get_chunks(document_id)

        if not chunks:
            return

        for ner_ent in ner_entities:
            # NER Entity(text, type, ...) → 写入 entities 表拿到 id
            try:
                row = await db.fetchrow(
                    """
                    INSERT INTO entities (name, type, container_tag, confidence)
                    VALUES ($1, $2, $3, $4)
                    ON CONFLICT (name, type, container_tag) DO UPDATE SET mention_count = entities.mention_count + 1
                    RETURNING id
                    """,
                    ner_ent.text,
                    ner_ent.type,
                    container_tag,
                    ner_ent.confidence,
                )
                entity_id = row["id"]
            except Exception:
                continue

            # 关联到包含该实体的 chunk
            for chunk in chunks:
                if ner_ent.text in chunk.content:
                    try:
                        await db.execute(
                            """
                            INSERT INTO chunk_entities (chunk_id, entity_id, entity_type)
                            VALUES ($1, $2, $3)
                            ON CONFLICT (chunk_id, entity_id) DO NOTHING
                            """,
                            chunk.id,
                            entity_id,
                            ner_ent.type,
                        )
                    except Exception:
                        pass

    async def find_chunks_by_entities(
        self,
        entity_ids: List[str],
        container_tag: str,
        limit: int = 5,
    ) -> List[Dict[str, Any]]:
        if not entity_ids:
            return []

        rows = await db.fetch(
            """
            SELECT DISTINCT c.id, c.content, c.document_id, d.title, d.source,
                   c.embedding
            FROM chunks c
            JOIN chunk_entities ce ON c.id = ce.chunk_id
            JOIN documents d ON c.document_id = d.id
            WHERE ce.entity_id = ANY($1)
            AND d.container_tag = $2
            AND d.status = 'done'
            LIMIT $3
            """,
            entity_ids,
            container_tag,
            limit,
        )

        return [
            {
                "id": row["id"],
                "content": row["content"],
                "document_id": row["document_id"],
                "title": row["title"],
                "source": row["source"],
                "embedding": json.loads(row["embedding"])
                if row.get("embedding")
                else None,
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
