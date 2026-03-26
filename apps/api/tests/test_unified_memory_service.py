import pytest
from pathlib import Path
import sys
import os

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

from dotenv import load_dotenv

env_path = Path(__file__).parent.parent.parent / ".env"
load_dotenv(env_path)

from src.services.unified_memory_service import UnifiedMemoryService
from src.database import db


@pytest.mark.asyncio
async def test_store_manual_memory():
    service = UnifiedMemoryService()
    user_id = "test_unified_manual"

    await db.connect()
    try:
        await db.init_user(user_id)

        async with db.user_context(user_id):
            result = await service.store(
                user_id=user_id,
                content="我是素食主义者，不喜欢吃肉",
                source="manual",
                memory_type="preference",
            )

            assert result["raw_message_id"].startswith("raw_")
            assert result["memory_type"] == "preference"
            assert result["agent_id"] is None
            assert result["source"] == "manual"
    finally:
        await db.disconnect()


@pytest.mark.asyncio
async def test_store_agent_message():
    service = UnifiedMemoryService()
    user_id = "test_unified_agent"

    await db.connect()
    try:
        await db.init_user(user_id)

        async with db.user_context(user_id):
            result = await service.store(
                user_id=user_id,
                content="今天天气不错",
                source="agent",
                agent_id="agent_001",
                session_id="session_001",
            )

            assert result["raw_message_id"].startswith("raw_")
            assert result["memory_type"] == "dialogue"
            assert result["agent_id"] == "agent_001"
            assert result["source"] == "agent"
    finally:
        await db.disconnect()


@pytest.mark.asyncio
async def test_store_with_metadata():
    service = UnifiedMemoryService()
    user_id = "test_unified_metadata"

    await db.connect()
    try:
        await db.init_user(user_id)

        async with db.user_context(user_id):
            result = await service.store(
                user_id=user_id,
                content="今天在星巴克遇到了老同学张三",
                source="manual",
                memory_type="note",
                metadata={
                    "location_name": "星巴克",
                    "tags": ["朋友", "聚会"],
                    "people": [{"name": "张三", "relation": "老同学"}],
                },
            )

            assert result["raw_message_id"].startswith("raw_")

            memory = await service.get_memory_by_id(result["raw_message_id"])
            assert memory is not None
            assert memory["location_name"] == "星巴克"
            assert "朋友" in memory["tags"]
    finally:
        await db.disconnect()


@pytest.mark.asyncio
async def test_recall_manual_only():
    service = UnifiedMemoryService()
    user_id = "test_unified_recall_manual"

    await db.connect()
    try:
        await db.init_user(user_id)

        async with db.user_context(user_id):
            await service.store(
                user_id=user_id,
                content="我喜欢喝咖啡",
                source="manual",
            )

            await service.store(
                user_id=user_id,
                content="用户询问天气",
                source="agent",
                agent_id="agent_001",
                session_id="session_001",
            )

            results = await service.recall(
                query="咖啡",
                user_id=user_id,
                scope="manual_only",
                limit=10,
            )

            for r in results:
                assert r["agent_id"] is None
    finally:
        await db.disconnect()


@pytest.mark.asyncio
async def test_get_user_memories():
    service = UnifiedMemoryService()
    user_id = "test_unified_get_all"

    await db.connect()
    try:
        await db.init_user(user_id)

        async with db.user_context(user_id):
            await service.store(
                user_id=user_id,
                content="偏好1",
                source="manual",
            )

            await service.store(
                user_id=user_id,
                content="偏好2",
                source="manual",
            )

            memories = await service.get_user_memories(user_id)

            assert len(memories) >= 2
    finally:
        await db.disconnect()


@pytest.mark.asyncio
async def test_delete_memory():
    service = UnifiedMemoryService()
    user_id = "test_unified_delete"

    await db.connect()
    try:
        await db.init_user(user_id)

        async with db.user_context(user_id):
            result = await service.store(
                user_id=user_id,
                content="待删除的记忆",
                source="manual",
            )

            memory_id = result["raw_message_id"]

            deleted = await service.delete_memory(memory_id)
            assert deleted == True

            memory = await service.get_memory_by_id(memory_id)
            assert memory is None
    finally:
        await db.disconnect()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
