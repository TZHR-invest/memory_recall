import pytest
from pathlib import Path
import sys
import os
import time
from datetime import datetime

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

from dotenv import load_dotenv

env_path = Path(__file__).parent.parent.parent / ".env"
load_dotenv(env_path)

from src.services.lossless.compaction_engine import (
    CompactionEngine,
    estimate_tokens,
    format_timestamp,
)
from src.services.lossless.raw_message_store import RawMessageStore
from src.services.lossless.summary_store import SummaryStore
from src.services.lossless.context_store import ContextStore
from src.database import db


def unique_user_id(base: str) -> str:
    return f"{base}_{int(time.time() * 1000000)}"


def test_estimate_tokens():
    short_text = "Hello"
    long_text = "这是一段很长的文本" * 100

    short_tokens = estimate_tokens(short_text)
    long_tokens = estimate_tokens(long_text)

    assert short_tokens >= 1
    assert long_tokens > short_tokens


def test_format_timestamp():
    dt = datetime(2026, 3, 26, 14, 30, 0)
    formatted = format_timestamp(dt)

    assert "2026-03-26" in formatted
    assert "14:30" in formatted


@pytest.mark.asyncio
async def test_compaction_evaluate():
    engine = CompactionEngine()
    raw_store = RawMessageStore()
    context_store = ContextStore()
    user_id = unique_user_id("test_compaction_eval")
    session_id = "session_eval"

    await db.connect()
    try:
        await db.init_user(user_id)

        async with db.user_context(user_id):
            result = await engine.evaluate(user_id, session_id, token_budget=100000)

            assert "should_compact" in result
            assert "current_tokens" in result
            assert "threshold" in result
            assert result["should_compact"] == False

            for i in range(20):
                msg_id = await raw_store.store(
                    user_id, f"长消息内容{i}" * 5000, "dialogue"
                )
                await context_store.append_message(user_id, session_id, msg_id)

            result_after = await engine.evaluate(user_id, session_id, token_budget=1000)
            assert result_after["should_compact"] == True
    finally:
        await db.disconnect()


@pytest.mark.asyncio
async def test_leaf_compact():
    engine = CompactionEngine()
    raw_store = RawMessageStore()
    context_store = ContextStore()
    user_id = unique_user_id("test_compaction_leaf")
    session_id = "session_leaf"

    def mock_summarize(text: str, aggressive: bool = False) -> str:
        return f"这是对 {len(text)} 字符内容的摘要"

    await db.connect()
    try:
        await db.init_user(user_id)

        async with db.user_context(user_id):
            for i in range(15):
                msg_id = await raw_store.store(
                    user_id, f"消息{i}: 今天发生了一些事情，需要记录下来。", "dialogue"
                )
                await context_store.append_message(user_id, session_id, msg_id)

            tokens_before = await context_store.get_token_count(user_id, session_id)

            result = await engine.leaf_compact(
                user_id=user_id,
                agent_id=None,
                session_id=session_id,
                summarize_fn=mock_summarize,
                token_budget=100,
                force=True,
            )

            assert result is not None
            assert result.action_taken == True
            assert result.summary_id is not None
            assert result.summary_id.startswith("sum_")

            tokens_after = await context_store.get_token_count(user_id, session_id)
            assert tokens_after < tokens_before

            items = await context_store.get_context_items(user_id, session_id)
            summary_items = [i for i in items if i.item_type == "summary"]
            assert len(summary_items) >= 1
    finally:
        await db.disconnect()


@pytest.mark.asyncio
async def test_fresh_tail_protection():
    engine = CompactionEngine({"fresh_tail_count": 5})
    raw_store = RawMessageStore()
    context_store = ContextStore()
    user_id = unique_user_id("test_fresh_tail")
    session_id = "session_fresh"

    def mock_summarize(text: str, aggressive: bool = False) -> str:
        return f"摘要"

    await db.connect()
    try:
        await db.init_user(user_id)

        async with db.user_context(user_id):
            for i in range(10):
                msg_id = await raw_store.store(user_id, f"消息{i}", "dialogue")
                await context_store.append_message(user_id, session_id, msg_id)

            await engine.leaf_compact(
                user_id=user_id,
                agent_id=None,
                session_id=session_id,
                summarize_fn=mock_summarize,
                token_budget=100,
                force=True,
            )

            items = await context_store.get_context_items(user_id, session_id)
            message_items = [i for i in items if i.item_type == "message"]

            assert len(message_items) >= 5
    finally:
        await db.disconnect()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
