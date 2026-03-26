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

from src.services.unified_memory_service import (
    UnifiedMemoryService,
    split_into_chunks,
    generate_document_id,
)
from src.database import db


def unique_user_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def test_split_into_chunks_short():
    content = "短文本"
    chunks = split_into_chunks(content, max_chars=100)

    assert len(chunks) == 1
    assert chunks[0] == "短文本"


def test_split_into_chunks_long():
    content = "段落1\n\n段落2\n\n段落3"
    chunks = split_into_chunks(content, max_chars=5)

    assert len(chunks) >= 1


def test_generate_document_id():
    doc_id = generate_document_id()

    assert doc_id.startswith("doc_")
    assert len(doc_id) == 20


@pytest.mark.asyncio
async def test_store_long_document():
    service = UnifiedMemoryService()
    user_id = unique_user_id("test_long_doc")

    await db.connect()
    try:
        await db.init_user(user_id)

        async with db.user_context(user_id):
            long_content = "这是一个很长的文档内容。" * 1000

            result = await service.store_long_document(
                user_id=user_id,
                content=long_content,
                memory_type="note",
                metadata={"tags": ["测试", "长文档"]},
                max_chunk_size=5000,
            )

            assert result["document_id"].startswith("doc_")
            assert result["chunk_count"] >= 1
            assert len(result["chunk_ids"]) == result["chunk_count"]
    finally:
        await db.disconnect()


@pytest.mark.asyncio
async def test_store_file():
    service = UnifiedMemoryService()
    user_id = unique_user_id("test_file_upload")

    await db.connect()
    try:
        await db.init_user(user_id)

        async with db.user_context(user_id):
            file_content = f"这是文件内容\n第二行\n第三行 {uuid.uuid4()}".encode(
                "utf-8"
            )

            result = await service.store_file(
                user_id=user_id,
                content=file_content,
                file_name="test.txt",
                metadata={"tags": ["测试文件"]},
            )

            assert result["status"] == "created"
            assert result["document_id"].startswith("doc_")
            assert result["file_name"] == "test.txt"
    finally:
        await db.disconnect()


@pytest.mark.asyncio
async def test_store_file_duplicate():
    service = UnifiedMemoryService()
    user_id = unique_user_id("test_file_dedup")

    await db.connect()
    try:
        await db.init_user(user_id)

        async with db.user_context(user_id):
            file_content = f"重复文件内容 {uuid.uuid4()}".encode("utf-8")

            result1 = await service.store_file(
                user_id=user_id,
                content=file_content,
                file_name="file1.txt",
            )

            assert result1["status"] == "created"

            result2 = await service.store_file(
                user_id=user_id,
                content=file_content,
                file_name="file2.txt",
            )

            assert result2["status"] == "duplicate"
            assert result2["document_id"] == result1["document_id"]
    finally:
        await db.disconnect()


@pytest.mark.asyncio
async def test_get_document_chunks():
    service = UnifiedMemoryService()
    user_id = unique_user_id("test_get_chunks")

    await db.connect()
    try:
        await db.init_user(user_id)

        async with db.user_context(user_id):
            doc_result = await service.store_long_document(
                user_id=user_id,
                content="段落1\n\n段落2\n\n段落3",
                memory_type="note",
                max_chunk_size=10,
            )

            chunks = await service.get_document_chunks(
                document_id=doc_result["document_id"],
                user_id=user_id,
            )

            assert len(chunks) >= 1
            assert chunks[0]["id"].startswith("raw_")
    finally:
        await db.disconnect()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
