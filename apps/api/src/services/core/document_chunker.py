"""
Document chunking service with AST-aware code chunking and content-type-based strategies.

Supports:
- AST-aware chunking for Python/JavaScript/TypeScript code
- Content type detection and automatic strategy selection
- Contextual retrieval with document context
- Structure-aware splitting
"""

import re
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field

from .chunking.types import (
    ChunkConfig as NewChunkConfig,
    TextChunk as NewTextChunk,
    ContentType,
    ChunkContext,
)
from .chunking.content_detector import ContentDetector
from .chunking.factory import ChunkingStrategyFactory

# HTML 标记噪音（README 等文档中的 <div>/<table>/<img> 等标签会被切成无意义 chunk，
# 如 "<div align=center>" 曾被注入上下文 37 次）。剥离标签但保留标签内文本。
_HTML_TAG_RE = re.compile(r"<[^>]+>")


@dataclass
class ChunkConfig:
    """Legacy configuration for backward compatibility."""

    max_chunk_tokens: int = 800
    min_chunk_tokens: int = 50
    overlap_tokens: int = 50
    respect_sentence_boundary: bool = True
    enable_contextual_retrieval: bool = True
    semantic_similarity_threshold: float = 0.5
    context_max_tokens: int = 150

    enable_ast: bool = False
    enable_context: bool = True
    max_chunk_size: int = 3000
    overlap_lines: int = 5
    content_type: Optional[ContentType] = None


@dataclass
class TextChunk:
    """Legacy text chunk for backward compatibility."""

    content: str
    embedded_content: Optional[str] = None
    position: int = 0
    token_count: int = 0
    start_offset: int = 0
    end_offset: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


class DocumentChunker:
    """
    Main document chunker with AST-aware and content-type-based strategies.

    Supports two modes:
    1. Legacy mode (enable_ast=False): Uses regex-based paragraph/sentence splitting
    2. AST mode (enable_ast=True): Uses AST-aware chunking for code + content-type detection
    """

    def __init__(self, config: Optional[ChunkConfig] = None):
        self.config = config or ChunkConfig()
        self._detector = ContentDetector()

        self._sentence_endings = re.compile(r"[。！？\.!?]\s*")
        self._paragraph_breaks = re.compile(r"\n\s*\n")
        self._chinese_sentence = re.compile(r"[^。！？]+[。！？]")
        self._code_block = re.compile(r"```[\s\S]*?```")
        self._list_item = re.compile(r"^\s*[-*•]\s+", re.MULTILINE)
        self._numbered_list = re.compile(r"^\s*\d+[.)]\s+", re.MULTILINE)

    def chunk(
        self,
        text: str,
        metadata: Optional[Dict[str, Any]] = None,
        document_title: Optional[str] = None,
        document_summary: Optional[str] = None,
    ) -> List[TextChunk]:
        if not text or not text.strip():
            return []

        text = _HTML_TAG_RE.sub("", text)

        if self.config.enable_ast:
            return self._chunk_with_strategy(
                text, metadata, document_title, document_summary
            )

        return self._chunk_legacy(text, metadata, document_title, document_summary)

    def _chunk_with_strategy(
        self,
        text: str,
        metadata: Optional[Dict[str, Any]] = None,
        document_title: Optional[str] = None,
        document_summary: Optional[str] = None,
    ) -> List[TextChunk]:
        content_type = self.config.content_type
        if content_type is None:
            content_type = self._detector.detect(text, metadata)

        new_config = NewChunkConfig(
            max_chunk_size=self.config.max_chunk_size,
            min_chunk_size=self.config.min_chunk_tokens,
            overlap_lines=self.config.overlap_lines,
            enable_context=self.config.enable_context,
            context_max_chars=self.config.context_max_tokens * 2,
            content_type=content_type,
            max_chunk_tokens=self.config.max_chunk_tokens,
            min_chunk_tokens=self.config.min_chunk_tokens,
            overlap_tokens=self.config.overlap_tokens,
            enable_contextual_retrieval=self.config.enable_contextual_retrieval,
        )

        strategy = ChunkingStrategyFactory.get_strategy(content_type, new_config)
        new_chunks = strategy.chunk(text, metadata, document_title, document_summary)

        return [self._convert_chunk(c) for c in new_chunks]

    def _convert_chunk(self, new_chunk: NewTextChunk) -> TextChunk:
        return TextChunk(
            content=new_chunk.content,
            embedded_content=new_chunk.embedded_content,
            position=new_chunk.position,
            token_count=new_chunk.token_count,
            start_offset=new_chunk.start_offset,
            end_offset=new_chunk.end_offset,
            metadata=new_chunk.metadata,
        )

    def _chunk_legacy(
        self,
        text: str,
        metadata: Optional[Dict[str, Any]] = None,
        document_title: Optional[str] = None,
        document_summary: Optional[str] = None,
    ) -> List[TextChunk]:
        if not text or not text.strip():
            return []

        total_tokens = self._estimate_tokens(text)

        if total_tokens <= self.config.max_chunk_tokens:
            embedded_content = None
            if self.config.enable_contextual_retrieval:
                embedded_content = self._add_context(
                    text.strip(),
                    document_title,
                    document_summary,
                )

            return [
                TextChunk(
                    content=text.strip(),
                    embedded_content=embedded_content,
                    position=0,
                    token_count=total_tokens,
                    start_offset=0,
                    end_offset=len(text),
                    metadata=metadata or {},
                )
            ]

        semantic_boundaries = self._find_semantic_boundaries(text)

        chunks = []
        current_chunk = []
        current_tokens = 0
        position = 0
        last_boundary = 0

        for boundary in semantic_boundaries:
            segment = text[last_boundary:boundary].strip()
            if not segment:
                last_boundary = boundary
                continue

            segment_tokens = self._estimate_tokens(segment)

            if current_tokens + segment_tokens > self.config.max_chunk_tokens:
                if current_chunk:
                    chunk_text = "".join(current_chunk)
                    embedded_content = None
                    if self.config.enable_contextual_retrieval:
                        embedded_content = self._add_context(
                            chunk_text,
                            document_title,
                            document_summary,
                        )

                    chunks.append(
                        TextChunk(
                            content=chunk_text,
                            embedded_content=embedded_content,
                            position=position,
                            token_count=current_tokens,
                            start_offset=last_boundary - len(chunk_text),
                            end_offset=last_boundary,
                            metadata=metadata or {},
                        )
                    )
                    position += 1

                current_chunk = [segment]
                current_tokens = segment_tokens
            else:
                current_chunk.append(segment)
                current_tokens += segment_tokens

            last_boundary = boundary

        if current_chunk:
            chunk_text = "".join(current_chunk)
            if current_tokens >= self.config.min_chunk_tokens:
                embedded_content = None
                if self.config.enable_contextual_retrieval:
                    embedded_content = self._add_context(
                        chunk_text,
                        document_title,
                        document_summary,
                    )

                chunks.append(
                    TextChunk(
                        content=chunk_text,
                        embedded_content=embedded_content,
                        position=position,
                        token_count=current_tokens,
                        start_offset=last_boundary - len(chunk_text),
                        end_offset=len(text),
                        metadata=metadata or {},
                    )
                )
            elif chunks:
                last_chunk = chunks[-1]
                last_chunk.content += "\n" + chunk_text
                last_chunk.token_count += current_tokens
                if last_chunk.embedded_content:
                    last_chunk.embedded_content = self._add_context(
                        last_chunk.content,
                        document_title,
                        document_summary,
                    )

        if self.config.overlap_tokens > 0 and len(chunks) > 1:
            chunks = self._add_overlap(chunks)

        return chunks

    def _find_semantic_boundaries(self, text: str) -> List[int]:
        boundaries = [0]

        code_matches = list(self._code_block.finditer(text))

        for i, match in enumerate(code_matches):
            boundaries.append(match.end())
            if i < len(code_matches) - 1:
                next_start = code_matches[i + 1].start()
                if next_start > match.end():
                    sub_text = text[match.end() : next_start]
                    boundaries.extend(self._find_text_boundaries(sub_text, match.end()))

        last_code_end = code_matches[-1].end() if code_matches else 0
        if last_code_end < len(text):
            boundaries.extend(
                self._find_text_boundaries(text[last_code_end:], last_code_end)
            )

        boundaries.append(len(text))
        boundaries = sorted(set(boundaries))

        return boundaries

    def _find_text_boundaries(self, text: str, offset: int = 0) -> List[int]:
        boundaries = []

        para_matches = list(self._paragraph_breaks.finditer(text))
        for match in para_matches:
            boundaries.append(offset + match.end())

        sentence_endings = list(self._sentence_endings.finditer(text))
        for match in sentence_endings:
            boundaries.append(offset + match.end())

        return boundaries

    def _add_context(
        self,
        chunk_content: str,
        document_title: Optional[str] = None,
        document_summary: Optional[str] = None,
        source: Optional[str] = None,
        doc_type: Optional[str] = None,
    ) -> str:
        context_parts = []

        if source:
            context_parts.append(f"# 文件: {source}")

        if doc_type:
            context_parts.append(f"# 类型: {doc_type}")

        if document_title:
            context_parts.append(f"# 标题: {document_title}")

        if document_summary:
            summary_tokens = self._estimate_tokens(document_summary)
            if summary_tokens <= self.config.context_max_tokens:
                context_parts.append(f"# 摘要: {document_summary}")
            else:
                truncated = document_summary[: self.config.context_max_tokens * 4]
                context_parts.append(f"# 摘要: {truncated}...")

        if context_parts:
            context = "\n".join(context_parts) + "\n\n"
            return context + chunk_content

        return chunk_content

    def _add_overlap(self, chunks: List[TextChunk]) -> List[TextChunk]:
        for i in range(1, len(chunks)):
            prev_chunk = chunks[i - 1]
            curr_chunk = chunks[i]

            overlap_text = self._get_overlap_from_end(prev_chunk.content)

            if overlap_text:
                curr_chunk.content = overlap_text + "\n" + curr_chunk.content
                curr_chunk.token_count = self._estimate_tokens(curr_chunk.content)

                if curr_chunk.embedded_content:
                    document_title = self._extract_title_from_context(
                        curr_chunk.embedded_content
                    )
                    curr_chunk.embedded_content = self._add_context(
                        curr_chunk.content,
                        document_title=document_title,
                    )

        return chunks

    def _get_overlap_from_end(self, text: str) -> str:
        sentences = self._chinese_sentence.findall(text)
        if not sentences:
            sentences = self._sentence_endings.split(text)
            sentences = [s.strip() for s in sentences if s.strip()]

        if not sentences:
            return ""

        overlap_text = ""
        token_count = 0

        for sentence in reversed(sentences):
            sent_tokens = self._estimate_tokens(sentence)
            if token_count + sent_tokens <= self.config.overlap_tokens:
                overlap_text = sentence + overlap_text
                token_count += sent_tokens
            else:
                break

        return overlap_text.strip()

    def _extract_title_from_context(self, embedded_content: str) -> Optional[str]:
        title_match = re.search(r"文档主题: (.+?)(?:\n|$)", embedded_content)
        if title_match:
            return title_match.group(1).strip()
        return None

    def _estimate_tokens(self, text: str) -> int:
        chinese_chars = len(re.findall(r"[\u4e00-\u9fff]", text))
        english_words = len(re.findall(r"[a-zA-Z]+", text))
        numbers = len(re.findall(r"\d+", text))
        symbols = len(re.findall(r"[^\w\s\u4e00-\u9fff]", text))

        return chinese_chars + english_words + numbers + symbols // 2

    def chunk_with_embeddings(
        self,
        text: str,
        get_embedding_func,
        metadata: Optional[Dict[str, Any]] = None,
        document_title: Optional[str] = None,
        document_summary: Optional[str] = None,
    ) -> List[TextChunk]:
        initial_chunks = self.chunk(
            text,
            metadata=metadata,
            document_title=document_title,
            document_summary=document_summary,
        )

        if len(initial_chunks) <= 1:
            return initial_chunks

        return initial_chunks


document_chunker = DocumentChunker()
