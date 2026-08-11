import pytest
from pathlib import Path
import sys
import os
import uuid

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

from dotenv import load_dotenv

env_path = Path(__file__).parent.parent.parent / ".env"
load_dotenv(env_path)

from src.services.core.document_store import (
    document_store,
    compute_content_hash,
)
from src.database import db


def unique_container_tag(prefix: str = "test") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


@pytest.mark.asyncio(loop_scope="module")
class TestSourceDeduplication:
    @pytest.mark.order(1)
    async def test_deduplication_by_source(self):
        """Same source should return existing document."""
        container_tag = unique_container_tag("source_dedup")
        content = "Document content for source dedup test"
        source = "/path/to/document.md"

        doc1, is_dup1 = await document_store.create(
            content=content,
            container_tag=container_tag,
            source=source,
            title="First Document",
        )

        assert is_dup1 is False
        assert doc1.source == source

        doc2, is_dup2 = await document_store.create(
            content=content,
            container_tag=container_tag,
            source=source,
            title="Second Document",
        )

        assert is_dup2 is True
        assert doc2.id == doc1.id

    @pytest.mark.order(2)
    async def test_source_update_on_content_change(self):
        """Same source but different content should update document."""
        container_tag = unique_container_tag("source_update")
        original_content = "Original content for update test"
        new_content = "Updated content for update test"
        source = "/path/to/updatable.md"

        doc1, is_dup1 = await document_store.create(
            content=original_content,
            container_tag=container_tag,
            source=source,
            title="Original Title",
        )

        assert is_dup1 is False
        original_hash = doc1.content_hash
        original_id = doc1.id

        doc2, is_dup2 = await document_store.create(
            content=new_content,
            container_tag=container_tag,
            source=source,
            title="Original Title",
        )

        assert is_dup2 is False
        assert doc2.id == original_id
        assert doc2.content_hash != original_hash

    @pytest.mark.order(3)
    async def test_source_different_container(self):
        """Same source in different containers should create separate documents."""
        container_tag1 = unique_container_tag("container1")
        container_tag2 = unique_container_tag("container2")
        source = "/shared/path/document.md"
        content = "Same content"

        doc1, is_dup1 = await document_store.create(
            content=content,
            container_tag=container_tag1,
            source=source,
        )

        doc2, is_dup2 = await document_store.create(
            content=content,
            container_tag=container_tag2,
            source=source,
        )

        assert is_dup1 is False
        assert is_dup2 is False
        assert doc1.id != doc2.id

    @pytest.mark.order(4)
    async def test_no_source_uses_content_hash(self):
        """Without source, should fallback to content hash deduplication."""
        container_tag = unique_container_tag("no_source")
        content = "Content without source"

        doc1, is_dup1 = await document_store.create(
            content=content,
            container_tag=container_tag,
        )

        doc2, is_dup2 = await document_store.create(
            content=content,
            container_tag=container_tag,
        )

        assert is_dup1 is False
        assert is_dup2 is True
        assert doc2.id == doc1.id

    @pytest.mark.order(5)
    async def test_source_priority_over_content_hash(self):
        """Source should take priority over content hash for deduplication."""
        container_tag = unique_container_tag("source_priority")
        source = "/path/to/priority.md"

        doc1, _ = await document_store.create(
            content="Content 1",
            container_tag=container_tag,
            source=source,
        )

        doc2, is_dup2 = await document_store.create(
            content="Content 2",
            container_tag=container_tag,
            source=source,
        )

        assert is_dup2 is False
        assert doc2.id == doc1.id
        assert doc2.content_hash != doc1.content_hash


@pytest.mark.asyncio(loop_scope="module")
class TestSourceWithChunks:
    @pytest.mark.order(1)
    async def test_update_preserves_chunks_count_on_unchanged(self):
        """Updating with same content should preserve chunks."""
        container_tag = unique_container_tag("preserve_chunks")
        source = "/path/to/chunks.md"
        content = "Content that will not change"

        doc1, _ = await document_store.create(
            content=content,
            container_tag=container_tag,
            source=source,
            auto_chunk=True,
        )

        doc2, is_dup = await document_store.create(
            content=content,
            container_tag=container_tag,
            source=source,
        )

        assert is_dup is True
        assert doc2.chunk_count == doc1.chunk_count

    @pytest.mark.order(2)
    async def test_update_rechunks_on_content_change(self):
        """Updating with different content should re-chunk."""
        container_tag = unique_container_tag("rechunk")
        source = "/path/to/rechunk.md"
        short_content = "Short content"
        long_content = "This is much longer content that will create more chunks. " * 10

        doc1, _ = await document_store.create(
            content=short_content,
            container_tag=container_tag,
            source=source,
            auto_chunk=True,
        )

        original_chunk_count = doc1.chunk_count

        doc2, is_dup = await document_store.create(
            content=long_content,
            container_tag=container_tag,
            source=source,
        )

        assert is_dup is False
        assert doc2.chunk_count >= original_chunk_count

    @pytest.mark.order(3)
    async def test_chunks_linked_to_same_document(self):
        """After update, chunks should still be linked to the same document."""
        container_tag = unique_container_tag("chunk_link")
        source = "/path/to/chunk_link.md"
        content1 = "First content"
        content2 = "Second content that is different"

        doc1, _ = await document_store.create(
            content=content1,
            container_tag=container_tag,
            source=source,
            auto_chunk=True,
        )

        chunks1 = await document_store.get_chunks(doc1.id)

        doc2, _ = await document_store.create(
            content=content2,
            container_tag=container_tag,
            source=source,
        )

        chunks2 = await document_store.get_chunks(doc2.id)

        assert doc2.id == doc1.id
        assert all(c.document_id == doc1.id for c in chunks2)


@pytest.mark.asyncio(loop_scope="module")
class TestFindMethods:
    @pytest.mark.order(1)
    async def test_find_by_source(self):
        """Test find_by_source method."""
        container_tag = unique_container_tag("find_source")
        source = "/path/to/find.md"
        content = "Content to find"

        created, _ = await document_store.create(
            content=content,
            container_tag=container_tag,
            source=source,
        )

        found = await document_store.find_by_source(container_tag, source)

        assert found is not None
        assert found.id == created.id
        assert found.source == source

    @pytest.mark.order(2)
    async def test_find_by_source_not_found(self):
        """Test find_by_source returns None for non-existent source."""
        container_tag = unique_container_tag("not_found")

        found = await document_store.find_by_source(
            container_tag, "/non/existent/path.md"
        )

        assert found is None

    @pytest.mark.order(3)
    async def test_find_by_source_different_container(self):
        """Test find_by_source is container-isolated."""
        container_tag1 = unique_container_tag("container_a")
        container_tag2 = unique_container_tag("container_b")
        source = "/shared/source.md"

        await document_store.create(
            content="Content in A",
            container_tag=container_tag1,
            source=source,
        )

        found = await document_store.find_by_source(container_tag2, source)

        assert found is None
