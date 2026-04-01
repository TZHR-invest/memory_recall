"""Core types for chunking module."""

import re
import warnings
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
    """Configuration for chunking behavior.

    The relationship between max_chunk_size and max_chunk_tokens:
    - max_chunk_size (chars) is the PRIMARY limit for chunking
    - max_chunk_tokens serves as a SAFETY BOUND for tokenization
    - For Chinese: 1 char ≈ 1 token, so max_chunk_tokens should be >= max_chunk_size
    - For English: ~4 chars ≈ 1 token, so max_chunk_tokens should be >= max_chunk_size / 4

    Priority: max_chunk_size > max_chunk_tokens (code uses max_chunk_size if both set)

    min_section_size: For Markdown, sections smaller than this are merged into previous chunk.
                      Set to 0 to disable merging. Default 300 chars.
    """

    # Primary chunking parameters (optimized for Chinese + English)
    max_chunk_size: int = 3000
    min_chunk_size: int = 200
    min_section_size: int = 300
    overlap_lines: int = 5
    enable_context: bool = True
    context_max_chars: int = 200
    content_type: Optional[ContentType] = None

    # Legacy fields for backward compatibility
    max_chunk_tokens: int = 800
    min_chunk_tokens: int = 50
    overlap_tokens: int = 50
    respect_sentence_boundary: bool = True
    enable_contextual_retrieval: bool = True
    semantic_similarity_threshold: float = 0.5
    context_max_tokens: int = 150

    def __post_init__(self):
        min_tokens_for_english = self.max_chunk_size // 4
        if self.max_chunk_tokens < min_tokens_for_english:
            warnings.warn(
                f"max_chunk_tokens ({self.max_chunk_tokens}) may be too small for "
                f"max_chunk_size ({self.max_chunk_size}). For English text, "
                f"recommend max_chunk_tokens >= {min_tokens_for_english}. "
                f"For Chinese text, recommend max_chunk_tokens >= {self.max_chunk_size}.",
                UserWarning,
            )


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
