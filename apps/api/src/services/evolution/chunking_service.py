"""
Chunking Service

Strategies for splitting long documents into chunks.
Supermemory-style: 2-sentence overlap for semantic continuity.
"""

from typing import List, Dict, Any, Optional
from dataclasses import dataclass
import re


@dataclass
class Chunk:
    index: int
    text: str
    start_offset: int
    end_offset: int
    token_estimate: int


class ChunkingService:
    """Long document chunking with multiple strategies"""

    def __init__(self, max_chunk_tokens: int = 500):
        self.max_chunk_tokens = max_chunk_tokens
        self.avg_chars_per_token = 4  # Approximate for Chinese/English mix

    def chunk(
        self,
        content: str,
        strategy: str = "sentence",
        overlap_sentences: int = 2,
    ) -> List[Chunk]:
        """Split content into chunks using specified strategy"""
        if strategy == "semantic":
            return self._semantic_chunk(content)
        elif strategy == "fixed":
            return self._fixed_chunk(content)
        else:
            return self._sentence_chunk(content, overlap_sentences)

    def _sentence_chunk(
        self,
        content: str,
        overlap: int = 2,
    ) -> List[Chunk]:
        """Split by sentences with overlap (Supermemory style)"""
        sentences = self._split_sentences(content)

        if not sentences:
            return []

        chunks = []
        current_sentences = []
        current_tokens = 0
        chunk_start = 0

        for i, sent in enumerate(sentences):
            sent_tokens = len(sent) // self.avg_chars_per_token

            if (
                current_tokens + sent_tokens > self.max_chunk_tokens
                and current_sentences
            ):
                text = " ".join(current_sentences)
                chunks.append(
                    Chunk(
                        index=len(chunks),
                        text=text,
                        start_offset=chunk_start,
                        end_offset=chunk_start + len(text),
                        token_estimate=current_tokens,
                    )
                )

                overlap_sents = (
                    current_sentences[-overlap:]
                    if len(current_sentences) >= overlap
                    else current_sentences
                )
                current_sentences = overlap_sents.copy()
                current_tokens = sum(
                    len(s) // self.avg_chars_per_token for s in current_sentences
                )
                chunk_start = (
                    chunk_start
                    + len(" ".join(current_sentences[: -len(overlap_sents)]))
                    + 1
                    if overlap_sents
                    else chunk_start
                )

            current_sentences.append(sent)
            current_tokens += sent_tokens

        if current_sentences:
            text = " ".join(current_sentences)
            chunks.append(
                Chunk(
                    index=len(chunks),
                    text=text,
                    start_offset=chunk_start,
                    end_offset=len(content),
                    token_estimate=current_tokens,
                )
            )

        return chunks

    def _semantic_chunk(self, content: str) -> List[Chunk]:
        """Split by semantic boundaries (paragraphs, sections)"""
        paragraphs = re.split(r"\n\s*\n", content)

        chunks = []
        current_para = []
        current_tokens = 0
        start = 0

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            para_tokens = len(para) // self.avg_chars_per_token

            if current_tokens + para_tokens > self.max_chunk_tokens and current_para:
                text = "\n\n".join(current_para)
                chunks.append(
                    Chunk(
                        index=len(chunks),
                        text=text,
                        start_offset=start,
                        end_offset=start + len(text),
                        token_estimate=current_tokens,
                    )
                )
                current_para = []
                current_tokens = 0
                start += len(text) + 2

            current_para.append(para)
            current_tokens += para_tokens

        if current_para:
            text = "\n\n".join(current_para)
            chunks.append(
                Chunk(
                    index=len(chunks),
                    text=text,
                    start_offset=start,
                    end_offset=len(content),
                    token_estimate=current_tokens,
                )
            )

        return chunks

    def _fixed_chunk(
        self,
        content: str,
        overlap_chars: int = 200,
    ) -> List[Chunk]:
        """Fixed-size chunks with character overlap"""
        max_chars = self.max_chunk_tokens * self.avg_chars_per_token
        chunks = []
        start = 0

        while start < len(content):
            end = min(start + max_chars, len(content))

            if end < len(content):
                last_space = content.rfind(" ", start, end)
                if last_space > start:
                    end = last_space

            chunk_text = content[start:end].strip()
            if chunk_text:
                chunks.append(
                    Chunk(
                        index=len(chunks),
                        text=chunk_text,
                        start_offset=start,
                        end_offset=end,
                        token_estimate=len(chunk_text) // self.avg_chars_per_token,
                    )
                )

            start = end - overlap_chars if end < len(content) else end

        return chunks

    def _split_sentences(self, text: str) -> List[str]:
        """Split text into sentences (Chinese and English aware)"""
        pattern = r"(?<=[。！？.!?])\s+"
        sentences = re.split(pattern, text)
        return [s.strip() for s in sentences if s.strip()]

    async def store_chunks(
        self,
        memory_id: str,
        user_id: str,
        chunks: List[Chunk],
        generate_embeddings: bool = True,
    ) -> List[str]:
        """Store chunks in database with optional embeddings"""
        from src.database import db
        import uuid

        chunk_ids = []

        for chunk in chunks:
            chunk_id = str(uuid.uuid4())

            embedding = None
            if generate_embeddings:
                try:
                    from src.embedding.client import get_embedding_client

                    client = get_embedding_client()
                    embedding = client.embed(chunk.text)
                except Exception:
                    pass

            embedding_str = (
                "[" + ",".join(map(str, embedding)) + "]" if embedding else None
            )

            await db.execute(
                """
                INSERT INTO content_chunks (id, memory_id, user_id, chunk_index, chunk_text, start_offset, end_offset, embedding)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                """,
                chunk_id,
                memory_id,
                user_id,
                chunk.index,
                chunk.text,
                chunk.start_offset,
                chunk.end_offset,
                embedding_str,
            )

            chunk_ids.append(chunk_id)

        await db.execute(
            "UPDATE raw_messages SET chunk_count = $1 WHERE id = $2",
            len(chunks),
            memory_id,
        )

        return chunk_ids


chunking_service = ChunkingService()
