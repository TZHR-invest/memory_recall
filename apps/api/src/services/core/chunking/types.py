"""Core types for chunking module."""

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Any, List, Optional


class ContentType(Enum):
    """Content type enumeration for chunking strategy selection."""

    CODE = "code"
    DOCUMENT = "document"
    MARKDOWN = "markdown"
    CONVERSATION = "conversation"
    UNKNOWN = "unknown"


@dataclass
class ChunkContext:
    """Context information for a code chunk."""

    scope_chain: List[str] = field(default_factory=list)
    signatures: List[str] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)
    language: Optional[str] = None
    file_path: Optional[str] = None

    def to_comment_header(self, max_chars: int = 200) -> str:
        lines = []

        if self.scope_chain:
            lines.append(f"# Scope: {' > '.join(self.scope_chain)}")

        if self.signatures:
            signatures_str = ", ".join(self.signatures[:3])
            if len(self.signatures) > 3:
                signatures_str += ", ..."
            lines.append(f"# Defines: {signatures_str}")

        if self.dependencies:
            deps_str = ", ".join(self.dependencies[:5])
            if len(self.dependencies) > 5:
                deps_str += ", ..."
            lines.append(f"# Uses: {deps_str}")

        header = "\n".join(lines)
        if len(header) > max_chars:
            header = header[:max_chars].rsplit("\n", 1)[0]

        return header


@dataclass
class ChunkConfig:
    """Configuration for chunking behavior."""

    max_chunk_size: int = 1500
    min_chunk_size: int = 100
    overlap_lines: int = 10
    enable_context: bool = True
    context_max_chars: int = 200
    content_type: Optional[ContentType] = None

    # Legacy fields for backward compatibility
    max_chunk_tokens: int = 512
    min_chunk_tokens: int = 50
    overlap_tokens: int = 50
    respect_sentence_boundary: bool = True
    enable_contextual_retrieval: bool = True
    semantic_similarity_threshold: float = 0.5
    context_max_tokens: int = 100


@dataclass
class TextChunk:
    """A chunk of text with metadata."""

    content: str
    embedded_content: Optional[str] = None
    position: int = 0
    token_count: int = 0
    start_offset: int = 0
    end_offset: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
    context: Optional[ChunkContext] = None
    content_type: ContentType = ContentType.UNKNOWN


class ChunkingStrategy(ABC):
    """Abstract base class for chunking strategies."""

    def __init__(self, config: Optional[ChunkConfig] = None):
        self.config = config or ChunkConfig()

    @abstractmethod
    def chunk(
        self,
        text: str,
        metadata: Optional[Dict[str, Any]] = None,
        document_title: Optional[str] = None,
        document_summary: Optional[str] = None,
    ) -> List[TextChunk]:
        """Chunk the given text into semantic units."""
        pass

    def estimate_tokens_nws(self, text: str) -> int:
        non_whitespace = len(re.findall(r"\S", text))
        chinese_chars = len(re.findall(r"[\u4e00-\u9fff]", text))
        total_chars = max(len(text), 1)
        chinese_ratio = chinese_chars / total_chars

        if chinese_ratio > 0.3:
            return non_whitespace
        return max(non_whitespace // 4, 1)
