import pytest
from pathlib import Path
import sys
import os
import uuid
import asyncio

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

from dotenv import load_dotenv

env_path = Path(__file__).parent.parent.parent / ".env"
load_dotenv(env_path)

from src.services.core.document_store import (
    document_store,
    compute_content_hash,
    Document,
    Chunk,
)
from src.database import db


def unique_container_tag(prefix: str = "test") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


class TestComputeContentHash:
    def test_same_content_same_hash(self):
        content = "This is test content"
        hash1 = compute_content_hash(content)
        hash2 = compute_content_hash(content)
        assert hash1 == hash2

    def test_different_content_different_hash(self):
        content1 = "Content 1"
        content2 = "Content 2"
        hash1 = compute_content_hash(content1)
        hash2 = compute_content_hash(content2)
        assert hash1 != hash2

    def test_empty_content(self):
        hash_val = compute_content_hash("")
        assert len(hash_val) == 64

    def test_hash_is_hex_string(self):
        content = "Test content"
        hash_val = compute_content_hash(content)
        assert len(hash_val) == 64
        assert all(c in "0123456789abcdef" for c in hash_val)

    def test_unicode_content(self):
        content = "中文内容测试 🎉"
        hash_val = compute_content_hash(content)
        assert len(hash_val) == 64


@pytest.mark.asyncio(loop_scope="module")
class TestDocumentDeduplication:
    @pytest.mark.order(1)
    async def test_deduplication_by_url(self):
        container_tag = unique_container_tag("url_dedup")
        content = "Document content for URL dedup test"
        url = "https://example.com/test-doc"

        doc1, is_dup1 = await document_store.create(
            content=content,
            container_tag=container_tag,
            url=url,
            title="First Document",
        )

        assert is_dup1 is False
        assert doc1.url == url

        doc2, is_dup2 = await document_store.create(
            content=content,
            container_tag=container_tag,
            url=url,
            title="Second Document",
        )

        assert is_dup2 is True
        assert doc2.id == doc1.id

    @pytest.mark.order(2)
    async def test_deduplication_by_content_hash(self):
        container_tag = unique_container_tag("hash_dedup")
        content = "Identical content for hash test"

        doc1, is_dup1 = await document_store.create(
            content=content,
            container_tag=container_tag,
            title="First Document",
        )

        assert is_dup1 is False

        doc2, is_dup2 = await document_store.create(
            content=content,
            container_tag=container_tag,
            title="Second Document",
        )

        assert is_dup2 is True
        assert doc2.id == doc1.id
        assert doc2.content_hash == doc1.content_hash

    @pytest.mark.order(3)
    async def test_no_deduplication_different_container(self):
        container_tag1 = unique_container_tag("container1")
        container_tag2 = unique_container_tag("container2")
        content = "Same content, different containers"

        doc1, is_dup1 = await document_store.create(
            content=content,
            container_tag=container_tag1,
        )

        doc2, is_dup2 = await document_store.create(
            content=content,
            container_tag=container_tag2,
        )

        assert is_dup1 is False
        assert is_dup2 is False
        assert doc1.id != doc2.id

    @pytest.mark.order(4)
    async def test_url_takes_priority_over_content_hash(self):
        container_tag = unique_container_tag("priority")
        url = "https://example.com/priority-test"

        doc1, _ = await document_store.create(
            content="Content 1",
            container_tag=container_tag,
            url=url,
        )

        doc2, is_dup2 = await document_store.create(
            content="Content 2",
            container_tag=container_tag,
            url=url,
        )

        assert is_dup2 is True
        assert doc2.id == doc1.id


@pytest.mark.asyncio(loop_scope="module")
class TestIncrementalChunkUpdate:
    @pytest.mark.order(1)
    async def test_update_unchanged_content(self):
        container_tag = unique_container_tag("unchanged")
        content = "Original content that won't change"

        doc, _ = await document_store.create(
            content=content,
            container_tag=container_tag,
            auto_chunk=True,
        )

        updated_doc, unchanged = await document_store.update(
            document_id=doc.id,
            content=content,
        )

        assert unchanged is True
        assert updated_doc.content_hash == doc.content_hash

    @pytest.mark.order(2)
    async def test_update_changed_content(self):
        container_tag = unique_container_tag("changed")
        original_content = "Original content here"
        new_content = "Updated content here"

        doc, _ = await document_store.create(
            content=original_content,
            container_tag=container_tag,
            auto_chunk=True,
        )

        original_hash = doc.content_hash

        updated_doc, unchanged = await document_store.update(
            document_id=doc.id,
            content=new_content,
        )

        assert unchanged is False
        assert updated_doc.content_hash != original_hash

    @pytest.mark.order(3)
    async def test_update_with_more_chunks(self):
        container_tag = unique_container_tag("more_chunks")
        short_content = "Short"
        long_content = (
            "This is a much longer content that will create more chunks. " * 10
        )

        doc, _ = await document_store.create(
            content=short_content,
            container_tag=container_tag,
            auto_chunk=True,
        )

        original_chunk_count = doc.chunk_count

        updated_doc, unchanged = await document_store.update(
            document_id=doc.id,
            content=long_content,
        )

        assert unchanged is False
        assert updated_doc.chunk_count >= original_chunk_count

    @pytest.mark.order(4)
    async def test_update_with_fewer_chunks(self):
        container_tag = unique_container_tag("fewer_chunks")
        long_content = "This is a long content. " * 20
        short_content = "Short"

        doc, _ = await document_store.create(
            content=long_content,
            container_tag=container_tag,
            auto_chunk=True,
        )

        original_chunk_count = doc.chunk_count

        updated_doc, unchanged = await document_store.update(
            document_id=doc.id,
            content=short_content,
        )

        assert unchanged is False
        assert updated_doc.chunk_count <= original_chunk_count

    @pytest.mark.order(5)
    async def test_update_preserves_metadata(self):
        container_tag = unique_container_tag("preserve_meta")
        content = "Content"
        original_title = "Original Title"
        original_metadata = {"key": "value"}

        doc, _ = await document_store.create(
            content=content,
            container_tag=container_tag,
            title=original_title,
            metadata=original_metadata,
        )

        updated_doc, unchanged = await document_store.update(
            document_id=doc.id,
            content="New content",
        )

        assert updated_doc.title == original_title


@pytest.mark.asyncio(loop_scope="module")
class TestIntegration:
    @pytest.mark.order(1)
    async def test_full_document_lifecycle(self):
        container_tag = unique_container_tag("lifecycle")

        doc, is_dup = await document_store.create(
            content="Initial content",
            container_tag=container_tag,
            url="https://example.com/lifecycle",
            title="Lifecycle Test",
            auto_chunk=True,
        )

        assert is_dup is False
        assert doc.url is not None

        updated_doc, unchanged = await document_store.update(
            document_id=doc.id,
            content="Updated content with more text to ensure changes",
        )

        assert unchanged is False
        assert updated_doc.content_hash != doc.content_hash

        duplicate_doc, is_dup2 = await document_store.create(
            content="Initial content",
            container_tag=container_tag,
            url="https://example.com/lifecycle",
        )

        assert is_dup2 is True
        assert duplicate_doc.id == doc.id
