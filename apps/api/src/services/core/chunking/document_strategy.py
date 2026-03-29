"""Document chunking strategy using semantic boundaries."""

import re
from typing import Dict, Any, List, Optional

from .types import ChunkingStrategy, TextChunk, ContentType, ChunkConfig


class DocumentChunkerStrategy(ChunkingStrategy):
    """Semantic document chunker based on paragraphs and sentences."""

    def __init__(self, config: Optional[ChunkConfig] = None):
        super().__init__(config)
        self._sentence_endings = re.compile(r"[。！？\.!?]\s*")
        self._paragraph_breaks = re.compile(r"\n\s*\n")
        self._chinese_sentence = re.compile(r"[^。！？]+[。！？]")

    def chunk(
        self,
        text: str,
        metadata: Optional[Dict[str, Any]] = None,
        document_title: Optional[str] = None,
        document_summary: Optional[str] = None,
    ) -> List[TextChunk]:
        if not text or not text.strip():
            return []

        max_size = self.config.max_chunk_size or self.config.max_chunk_tokens

        total_size = self.estimate_tokens_nws(text)

        if total_size <= max_size:
            return [
                self._create_chunk(
                    text.strip(),
                    0,
                    0,
                    len(text),
                    metadata,
                    document_title,
                    document_summary,
                )
            ]

        boundaries = self._find_semantic_boundaries(text)
        chunks = []
        current_chunk = []
        current_size = 0
        position = 0
        last_boundary = 0

        for boundary in boundaries:
            segment = text[last_boundary:boundary].strip()
            if not segment:
                last_boundary = boundary
                continue

            segment_size = self.estimate_tokens_nws(segment)

            if current_size + segment_size > max_size:
                if current_chunk:
                    chunk_text = "".join(current_chunk)
                    chunks.append(
                        self._create_chunk(
                            chunk_text,
                            position,
                            last_boundary - len(chunk_text),
                            last_boundary,
                            metadata,
                            document_title,
                            document_summary,
                        )
                    )
                    position += 1

                current_chunk = [segment]
                current_size = segment_size
            else:
                current_chunk.append(segment)
                current_size += segment_size

            last_boundary = boundary

        if current_chunk:
            chunk_text = "".join(current_chunk)
            min_size = self.config.min_chunk_size or self.config.min_chunk_tokens
            if current_size >= min_size:
                chunks.append(
                    self._create_chunk(
                        chunk_text,
                        position,
                        last_boundary - len(chunk_text),
                        len(text),
                        metadata,
                        document_title,
                        document_summary,
                    )
                )
            elif chunks:
                chunks[-1].content += "\n" + chunk_text
                chunks[-1].token_count += current_size

        if self.config.overlap_lines > 0 and len(chunks) > 1:
            chunks = self._add_overlap(chunks)

        return chunks

    def _find_semantic_boundaries(self, text: str) -> List[int]:
        boundaries = [0]

        para_matches = list(self._paragraph_breaks.finditer(text))
        for match in para_matches:
            boundaries.append(match.end())

        sentence_endings = list(self._sentence_endings.finditer(text))
        for match in sentence_endings:
            boundaries.append(match.end())

        boundaries.append(len(text))
        return sorted(set(boundaries))

    def _create_chunk(
        self,
        content: str,
        position: int,
        start_offset: int,
        end_offset: int,
        metadata: Optional[Dict[str, Any]] = None,
        document_title: Optional[str] = None,
        document_summary: Optional[str] = None,
    ) -> TextChunk:
        embedded_content = None
        if self.config.enable_contextual_retrieval:
            context_parts = []
            if document_title:
                context_parts.append(f"文档主题: {document_title}")
            if document_summary:
                max_tokens = self.config.context_max_tokens
                if self.estimate_tokens_nws(document_summary) <= max_tokens:
                    context_parts.append(f"文档摘要: {document_summary}")
                else:
                    truncated = document_summary[: max_tokens * 4]
                    context_parts.append(f"文档摘要: {truncated}...")

            if context_parts:
                embedded_content = "\n".join(context_parts) + "\n\n" + content
            else:
                embedded_content = content

        return TextChunk(
            content=content,
            embedded_content=embedded_content,
            position=position,
            token_count=self.estimate_tokens_nws(content),
            start_offset=start_offset,
            end_offset=end_offset,
            metadata=metadata or {},
            content_type=ContentType.DOCUMENT,
        )

    def _add_overlap(self, chunks: List[TextChunk]) -> List[TextChunk]:
        overlap_lines = self.config.overlap_lines

        for i in range(1, len(chunks)):
            prev_chunk = chunks[i - 1]
            curr_chunk = chunks[i]

            prev_lines = prev_chunk.content.split("\n")
            overlap_text = "\n".join(prev_lines[-overlap_lines:])

            if overlap_text.strip():
                curr_chunk.content = overlap_text + "\n" + curr_chunk.content
                curr_chunk.token_count = self.estimate_tokens_nws(curr_chunk.content)

        return chunks


document_strategy = DocumentChunkerStrategy()
