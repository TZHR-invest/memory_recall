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

from src.services.lossless.memory_recall_engine import (
    MemoryRecallEngine,
    memory_recall_engine,
    ContextEngineInfo,
)
from src.services.lossless.raw_message_store import RawMessageStore
from src.services.lossless.context_store import ContextStore
from src.database import db


def test_engine_info():
    info = ContextEngineInfo()

    assert info.id == "memory-recall"
    assert info.name == "Memory Recall Engine"
    assert info.version == "3.0.0"
    assert info.owns_compaction == True


@pytest.mark.asyncio
async def test_bootstrap():
    engine = MemoryRecallEngine()
    user_id = "test_engine_bootstrap"
    session_id = "session_bootstrap"

    await db.connect()
    try:
        await db.init_user(user_id)

        async with db.user_context(user_id):
            result = await engine.bootstrap(
                {
                    "user_id": user_id,
                    "session_id": session_id,
                }
            )

            assert result["status"] == "ready"
    finally:
        await db.disconnect()


@pytest.mark.asyncio
async def test_ingest_user_memory():
    engine = MemoryRecallEngine()
    user_id = "test_engine_ingest"

    await db.connect()
    try:
        await db.init_user(user_id)

        async with db.user_context(user_id):
            result = await engine.ingest(
                {
                    "user_id": user_id,
                    "message": {"role": "user", "content": "我是素食主义者"},
                }
            )

            assert "raw_message_id" in result
            assert result["raw_message_id"].startswith("raw_")
    finally:
        await db.disconnect()


@pytest.mark.asyncio
async def test_ingest_agent_message():
    engine = MemoryRecallEngine()
    user_id = "test_engine_agent"
    session_id = "session_agent"

    await db.connect()
    try:
        await db.init_user(user_id)

        async with db.user_context(user_id):
            await engine.bootstrap(
                {
                    "user_id": user_id,
                    "agent_id": "agent_001",
                    "session_id": session_id,
                }
            )

            result = await engine.ingest(
                {
                    "user_id": user_id,
                    "agent_id": "agent_001",
                    "session_id": session_id,
                    "message": {"role": "user", "content": "今天天气不错"},
                }
            )

            assert "raw_message_id" in result

            assemble_result = await engine.assemble(
                {
                    "user_id": user_id,
                    "agent_id": "agent_001",
                    "session_id": session_id,
                }
            )

            assert "messages" in assemble_result
            assert "estimated_tokens" in assemble_result
    finally:
        await db.disconnect()


@pytest.mark.asyncio
async def test_recall():
    engine = MemoryRecallEngine()
    user_id = "test_engine_recall"

    await db.connect()
    try:
        await db.init_user(user_id)

        async with db.user_context(user_id):
            await engine.ingest(
                {
                    "user_id": user_id,
                    "message": {"role": "user", "content": "我喜欢喝咖啡"},
                }
            )

            await engine.ingest(
                {
                    "user_id": user_id,
                    "message": {"role": "user", "content": "我是素食主义者"},
                }
            )

            results = await engine.recall(
                query="咖啡",
                user_id=user_id,
                scope="manual_only",
                limit=10,
            )

            assert len(results) >= 1
            assert results[0]["type"] == "raw_message"
    finally:
        await db.disconnect()


@pytest.mark.asyncio
async def test_compact():
    engine = MemoryRecallEngine()
    raw_store = RawMessageStore()
    context_store = ContextStore()
    user_id = "test_engine_compact"
    session_id = "session_compact"

    def mock_summarize(text: str, aggressive: bool = False) -> str:
        return "这是摘要"

    await db.connect()
    try:
        await db.init_user(user_id)

        async with db.user_context(user_id):
            await engine.bootstrap(
                {
                    "user_id": user_id,
                    "session_id": session_id,
                }
            )

            for i in range(15):
                msg_id = await raw_store.store(user_id, f"消息{i}" * 100, "dialogue")
                await context_store.append_message(user_id, session_id, msg_id)

            result = await engine.compact(
                {
                    "user_id": user_id,
                    "session_id": session_id,
                    "token_budget": 100,
                    "force": True,
                    "summarize_fn": mock_summarize,
                }
            )

            assert result["action_taken"] == True
            assert result["summary_id"] is not None
    finally:
        await db.disconnect()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
