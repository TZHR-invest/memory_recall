"""Factory for creating chunking strategies."""

from typing import Optional

from .types import ContentType, ChunkConfig, ChunkingStrategy
from .code_chunker import CodeChunker
from .document_strategy import DocumentChunkerStrategy
from .markdown_strategy import MarkdownChunker
from .conversation_strategy import ConversationChunker


class ChunkingStrategyFactory:
    """Factory for creating chunking strategies based on content type."""

    _strategies = {}

    @classmethod
    def get_strategy(
        cls,
        content_type: ContentType,
        config: Optional[ChunkConfig] = None,
    ) -> ChunkingStrategy:
        cache_key = (content_type, id(config))

        if cache_key not in cls._strategies:
            cls._strategies[cache_key] = cls._create_strategy(content_type, config)

        return cls._strategies[cache_key]

    @classmethod
    def _create_strategy(
        cls,
        content_type: ContentType,
        config: Optional[ChunkConfig] = None,
    ) -> ChunkingStrategy:
        strategy_map = {
            ContentType.CODE: CodeChunker,
            ContentType.DOCUMENT: DocumentChunkerStrategy,
            ContentType.MARKDOWN: MarkdownChunker,
            ContentType.CONVERSATION: ConversationChunker,
        }

        strategy_class = strategy_map.get(content_type, DocumentChunkerStrategy)
        return strategy_class(config)

    @classmethod
    def clear_cache(cls):
        cls._strategies.clear()


def get_chunker(
    content_type: ContentType,
    config: Optional[ChunkConfig] = None,
) -> ChunkingStrategy:
    return ChunkingStrategyFactory.get_strategy(content_type, config)
