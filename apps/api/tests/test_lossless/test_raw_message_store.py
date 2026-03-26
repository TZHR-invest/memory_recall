import pytest
from datetime import datetime
from pathlib import Path
import sys
import os

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

from dotenv import load_dotenv

env_path = Path(__file__).parent.parent.parent / ".env"
load_dotenv(env_path)

from src.services.lossless.raw_message_store import RawMessageStore
from src.database import db


@pytest.mark.asyncio
async def test_store_raw_message():
    store = RawMessageStore()
    user_id = "test_user_store_pytest"

    await db.connect()
    try:
        await db.init_user(user_id)

        async with db.user_context(user_id):
            raw_id = await store.store(
                user_id=user_id,
                content="我是素食主义者，不喜欢吃肉",
                memory_type="preference",
            )

            assert raw_id.startswith("raw_")

            msg = await store.get_by_id(raw_id)

            assert msg is not None
            assert msg.content == "我是素食主义者，不喜欢吃肉"
            assert msg.memory_type == "preference"
            assert msg.agent_id is None
            assert msg.token_count > 0
    finally:
        await db.disconnect()


@pytest.mark.asyncio
async def test_store_with_agent_id():
    store = RawMessageStore()
    user_id = "test_user_agent_pytest"

    await db.connect()
    try:
        await db.init_user(user_id)

        async with db.user_context(user_id):
            raw_id = await store.store(
                user_id=user_id,
                content="今天天气不错",
                memory_type="dialogue",
                agent_id="agent_001",
                session_id="session_001",
            )

            msg = await store.get_by_id(raw_id)

            assert msg.agent_id == "agent_001"
            assert msg.session_id == "session_001"
            assert msg.memory_type == "dialogue"
    finally:
        await db.disconnect()


@pytest.mark.asyncio
async def test_estimate_tokens():
    store = RawMessageStore()

    short_text = "Hello"
    long_text = "这是一段很长的文本" * 100

    short_tokens = store.estimate_tokens(short_text)
    long_tokens = store.estimate_tokens(long_text)

    assert short_tokens >= 1
    assert long_tokens > short_tokens


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
