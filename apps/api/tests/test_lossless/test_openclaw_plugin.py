import pytest
from pathlib import Path
import sys
import os
import json

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

from dotenv import load_dotenv

env_path = Path(__file__).parent.parent.parent / ".env"
load_dotenv(env_path)

from src.openclaw_plugin import (
    create_memory_recall_engine,
    get_engine_info,
    MemoryRecallEngine,
)
from src.database import db


def test_plugin_info():
    info = get_engine_info()

    assert info["id"] == "memory-recall"
    assert info["name"] == "Memory Recall Engine"
    assert info["version"] == "3.0.0"
    assert info["owns_compaction"] == True
    assert "ingest" in info["capabilities"]
    assert "assemble" in info["capabilities"]
    assert "compact" in info["capabilities"]


def test_create_engine():
    engine = create_memory_recall_engine({"token_budget": 50000})

    assert isinstance(engine, MemoryRecallEngine)
    assert engine.config.get("token_budget") == 50000


def test_plugin_manifest():
    manifest_path = (
        Path(__file__).parent.parent.parent
        / "src"
        / "openclaw_plugin"
        / "openclaw.plugin.json"
    )

    assert manifest_path.exists()

    with open(manifest_path) as f:
        manifest = json.load(f)

    assert manifest["name"] == "memory-recall"
    assert manifest["version"] == "3.0.0"
    assert "contextEngine" in manifest["provides"]
    assert manifest["provides"]["contextEngine"]["id"] == "memory-recall"


@pytest.mark.asyncio
async def test_engine_context_engine_interface():
    engine = create_memory_recall_engine()
    user_id = "test_plugin_interface"
    session_id = "session_plugin"

    await db.connect()
    try:
        await db.init_user(user_id)

        async with db.user_context(user_id):
            bootstrap_result = await engine.bootstrap(
                {
                    "user_id": user_id,
                    "session_id": session_id,
                }
            )
            assert bootstrap_result["status"] == "ready"

            ingest_result = await engine.ingest(
                {
                    "user_id": user_id,
                    "session_id": session_id,
                    "message": {"role": "user", "content": "测试消息"},
                }
            )
            assert "raw_message_id" in ingest_result

            assemble_result = await engine.assemble(
                {
                    "user_id": user_id,
                    "session_id": session_id,
                    "token_budget": 10000,
                }
            )
            assert "messages" in assemble_result
            assert "estimated_tokens" in assemble_result
    finally:
        await db.disconnect()


@pytest.mark.asyncio
async def test_engine_recall_interface():
    engine = create_memory_recall_engine()
    user_id = "test_plugin_recall"

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

            results = await engine.recall(
                query="咖啡",
                user_id=user_id,
                scope="manual_only",
                limit=10,
            )

            assert isinstance(results, list)
    finally:
        await db.disconnect()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
