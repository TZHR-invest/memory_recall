"""
Performance benchmark tests for document chunking.

Compares old params (1500/512) vs new params (3000/800).
"""

import pytest
import sys
import os
from pathlib import Path

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

from src.services.core.chunking.types import ChunkConfig, ContentType
from src.services.core.chunking.markdown_strategy import MarkdownChunker
from src.services.core.chunking.document_strategy import DocumentChunkerStrategy


class TestChunkingPerformance:
    """Benchmark tests comparing old vs new chunking parameters."""

    @pytest.fixture
    def sample_chinese_doc(self) -> str:
        """Generate a sample Chinese document."""
        paragraphs = []
        for i in range(50):
            paragraphs.append(f"这是第{i + 1}段内容。" * 20)
        return "\n\n".join(paragraphs)

    @pytest.fixture
    def sample_english_doc(self) -> str:
        """Generate a sample English document."""
        paragraphs = []
        for i in range(50):
            paragraphs.append(f"This is paragraph {i + 1} content. " * 30)
        return "\n\n".join(paragraphs)

    @pytest.fixture
    def sample_markdown_doc(self) -> str:
        """Generate a sample Markdown document."""
        sections = []
        for i in range(5):
            sections.append(f"\n\n## Section {i + 1}\n\n")
            for j in range(10):
                sections.append(
                    f"This is content for section {i + 1}, paragraph {j + 1}. " * 15
                )
                sections.append("\n\n")
        return "".join(sections)

    def test_chinese_chunk_count_reduction(self, sample_chinese_doc):
        """Verify new params reduce chunk count for Chinese documents."""
        old_config = ChunkConfig(
            max_chunk_size=1500,
            max_chunk_tokens=512,
            min_chunk_size=100,
            overlap_lines=10,
        )
        new_config = ChunkConfig(
            max_chunk_size=3000,
            max_chunk_tokens=800,
            min_chunk_size=200,
            overlap_lines=5,
        )

        old_chunker = DocumentChunkerStrategy(old_config)
        new_chunker = DocumentChunkerStrategy(new_config)

        old_chunks = old_chunker.chunk(sample_chinese_doc)
        new_chunks = new_chunker.chunk(sample_chinese_doc)

        assert len(new_chunks) < len(old_chunks), (
            f"New config should produce fewer chunks: "
            f"{len(new_chunks)} vs {len(old_chunks)}"
        )

        reduction = 1 - (len(new_chunks) / len(old_chunks))
        print(
            f"Chinese doc: {len(old_chunks)} -> {len(new_chunks)} chunks "
            f"({reduction:.1%} reduction)"
        )

    def test_english_chunk_count_reduction(self, sample_english_doc):
        """Verify new params reduce chunk count for English documents."""
        old_config = ChunkConfig(
            max_chunk_size=1500,
            max_chunk_tokens=512,
            min_chunk_size=100,
            overlap_lines=10,
        )
        new_config = ChunkConfig(
            max_chunk_size=3000,
            max_chunk_tokens=800,
            min_chunk_size=200,
            overlap_lines=5,
        )

        old_chunker = DocumentChunkerStrategy(old_config)
        new_chunker = DocumentChunkerStrategy(new_config)

        old_chunks = old_chunker.chunk(sample_english_doc)
        new_chunks = new_chunker.chunk(sample_english_doc)

        assert len(new_chunks) < len(old_chunks)

        reduction = 1 - (len(new_chunks) / len(old_chunks))
        print(
            f"English doc: {len(old_chunks)} -> {len(new_chunks)} chunks "
            f"({reduction:.1%} reduction)"
        )

    def test_markdown_chunk_count_reduction(self, sample_markdown_doc):
        """Verify new params reduce chunk count for Markdown documents."""
        old_config = ChunkConfig(
            max_chunk_size=1500,
            max_chunk_tokens=512,
            min_chunk_size=100,
            overlap_lines=10,
            content_type=ContentType.MARKDOWN,
        )
        new_config = ChunkConfig(
            max_chunk_size=3000,
            max_chunk_tokens=800,
            min_chunk_size=200,
            overlap_lines=5,
            content_type=ContentType.MARKDOWN,
        )

        old_chunker = MarkdownChunker(old_config)
        new_chunker = MarkdownChunker(new_config)

        old_chunks = old_chunker.chunk(sample_markdown_doc)
        new_chunks = new_chunker.chunk(sample_markdown_doc)

        assert len(new_chunks) <= len(old_chunks)

        if len(new_chunks) < len(old_chunks):
            reduction = 1 - (len(new_chunks) / len(old_chunks))
            print(
                f"Markdown doc: {len(old_chunks)} -> {len(new_chunks)} chunks "
                f"({reduction:.1%} reduction)"
            )

    def test_average_chunk_size_increases(self, sample_chinese_doc):
        """Verify average chunk size increases with new params."""
        new_config = ChunkConfig(
            max_chunk_size=3000,
            max_chunk_tokens=800,
            min_chunk_size=200,
            overlap_lines=5,
        )

        chunker = DocumentChunkerStrategy(new_config)
        chunks = chunker.chunk(sample_chinese_doc)

        avg_size = sum(len(c.content) for c in chunks) / len(chunks)

        assert avg_size > 500, (
            f"Average chunk size should be > 500 chars, got {avg_size}"
        )
        print(f"Average chunk size: {avg_size:.0f} chars")

    def test_min_chunk_size_respected(self, sample_chinese_doc):
        """Verify minimum chunk size is respected."""
        new_config = ChunkConfig(
            max_chunk_size=3000,
            max_chunk_tokens=800,
            min_chunk_size=200,
            overlap_lines=5,
        )

        chunker = DocumentChunkerStrategy(new_config)
        chunks = chunker.chunk(sample_chinese_doc)

        for chunk in chunks[:-1]:
            assert len(chunk.content) >= 200, (
                f"Chunk too small: {len(chunk.content)} chars"
            )

    def test_markdown_section_merge(self):
        """Verify small sections are merged in Markdown documents."""
        markdown_doc = (
            """
# Main Title

## Section 1
This is a small section with just a few lines.

## Section 2
Another small section.

## Section 3
This is a large section with a lot of content.
"""
            + ("More content here. " * 100)
            + """

## Section 4
Final small section.
"""
        )

        no_merge_config = ChunkConfig(
            max_chunk_size=3000,
            min_section_size=0,
            content_type=ContentType.MARKDOWN,
        )
        merge_config = ChunkConfig(
            max_chunk_size=3000,
            min_section_size=300,
            content_type=ContentType.MARKDOWN,
        )

        no_merge_chunker = MarkdownChunker(no_merge_config)
        merge_chunker = MarkdownChunker(merge_config)

        no_merge_chunks = no_merge_chunker.chunk(markdown_doc)
        merge_chunks = merge_chunker.chunk(markdown_doc)

        assert len(merge_chunks) < len(no_merge_chunks), (
            f"Merge should reduce chunk count: "
            f"{len(merge_chunks)} vs {len(no_merge_chunks)}"
        )
        print(f"Markdown merge: {len(no_merge_chunks)} -> {len(merge_chunks)} chunks")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
