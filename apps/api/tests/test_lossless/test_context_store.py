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

from src.services.lossless.context_store import ContextStore
from src.services.lossless.raw_message_store import RawMessageStore
from src.services.lossless.summary_store import SummaryStore
from src.database import db


@pytest.mark.asyncio
async def test_append_message():
    store = ContextStore()
    raw_store = RawMessageStore()
    user_id = "test_user_ctx_append_pytest"

    await db.connect()
    try:
        await db.init_user(user_id)

        async with db.user_context(user_id):
            msg1_id = await raw_store.store(user_id, "消息1", "dialogue")
            msg2_id = await raw_store.store(user_id, "消息2", "dialogue")

            ordinal1 = await store.append_message(user_id, "session_001", msg1_id)
            ordinal2 = await store.append_message(user_id, "session_001", msg2_id)

            assert ordinal1 == 0
            assert ordinal2 == 1

            items = await store.get_context_items(user_id, "session_001")

            assert len(items) == 2
            assert items[0].ordinal == 0
            assert items[1].ordinal == 1
            assert items[0].message_id == msg1_id
            assert items[1].message_id == msg2_id
    finally:
        await db.disconnect()


@pytest.mark.asyncio
async def test_append_summary():
    store = ContextStore()
    summary_store = SummaryStore()
    user_id = "test_user_ctx_summary_pytest"

    await db.connect()
    try:
        await db.init_user(user_id)

        async with db.user_context(user_id):
            summary_id = await summary_store.create_summary(
                user_id=user_id, content="测试摘要", kind="leaf"
            )

            ordinal = await store.append_summary(user_id, "session_002", summary_id)

            assert ordinal == 0

            items = await store.get_context_items(user_id, "session_002")

            assert len(items) == 1
            assert items[0].item_type == "summary"
            assert items[0].summary_id == summary_id
    finally:
        await db.disconnect()


@pytest.mark.asyncio
async def test_replace_range_with_summary():
    store = ContextStore()
    raw_store = RawMessageStore()
    summary_store = SummaryStore()
    user_id = "test_user_ctx_replace_pytest"

    await db.connect()
    try:
        await db.init_user(user_id)

        async with db.user_context(user_id):
            msg1_id = await raw_store.store(user_id, "消息1", "dialogue")
            msg2_id = await raw_store.store(user_id, "消息2", "dialogue")
            msg3_id = await raw_store.store(user_id, "消息3", "dialogue")
            msg4_id = await raw_store.store(user_id, "消息4", "dialogue")

            await store.append_message(user_id, "session_003", msg1_id)
            await store.append_message(user_id, "session_003", msg2_id)
            await store.append_message(user_id, "session_003", msg3_id)
            await store.append_message(user_id, "session_003", msg4_id)

            summary_id = await summary_store.create_summary(
                user_id=user_id, content="消息1-3的摘要", kind="leaf"
            )

            await store.replace_range_with_summary(
                user_id, "session_003", 0, 2, summary_id
            )

            items = await store.get_context_items(user_id, "session_003")

            assert len(items) == 2

            assert items[0].item_type == "summary"
            assert items[0].summary_id == summary_id

            assert items[1].item_type == "message"
            assert items[1].message_id == msg4_id
    finally:
        await db.disconnect()


@pytest.mark.asyncio
async def test_get_token_count():
    store = ContextStore()
    raw_store = RawMessageStore()
    user_id = "test_user_ctx_tokens_pytest"

    await db.connect()
    try:
        await db.init_user(user_id)

        async with db.user_context(user_id):
            msg1_id = await raw_store.store(
                user_id, "这是一条测试消息" * 10, "dialogue"
            )
            msg2_id = await raw_store.store(user_id, "另一条消息" * 10, "dialogue")

            await store.append_message(user_id, "session_004", msg1_id)
            await store.append_message(user_id, "session_004", msg2_id)

            token_count = await store.get_token_count(user_id, "session_004")

            assert token_count > 0
    finally:
        await db.disconnect()


@pytest.mark.asyncio
async def test_exists():
    store = ContextStore()
    raw_store = RawMessageStore()
    user_id = "test_user_ctx_exists_pytest"

    await db.connect()
    try:
        await db.init_user(user_id)

        async with db.user_context(user_id):
            exists_before = await store.exists(user_id, "session_005")
            assert exists_before == False

            msg_id = await raw_store.store(user_id, "测试", "dialogue")
            await store.append_message(user_id, "session_005", msg_id)

            exists_after = await store.exists(user_id, "session_005")
            assert exists_after == True
    finally:
        await db.disconnect()


@pytest.mark.asyncio
async def test_clear():
    store = ContextStore()
    raw_store = RawMessageStore()
    user_id = "test_user_ctx_clear_pytest"

    await db.connect()
    try:
        await db.init_user(user_id)

        async with db.user_context(user_id):
            msg1_id = await raw_store.store(user_id, "消息1", "dialogue")
            msg2_id = await raw_store.store(user_id, "消息2", "dialogue")

            await store.append_message(user_id, "session_006", msg1_id)
            await store.append_message(user_id, "session_006", msg2_id)

            count_before = await store.get_item_count(user_id, "session_006")
            assert count_before == 2

            deleted = await store.clear(user_id, "session_006")
            assert deleted == 2

            count_after = await store.get_item_count(user_id, "session_006")
            assert count_after == 0
    finally:
        await db.disconnect()


@pytest.mark.asyncio
async def test_get_last_n_items():
    store = ContextStore()
    raw_store = RawMessageStore()
    user_id = "test_user_ctx_last_n_pytest"

    await db.connect()
    try:
        await db.init_user(user_id)

        async with db.user_context(user_id):
            for i in range(10):
                msg_id = await raw_store.store(user_id, f"消息{i}", "dialogue")
                await store.append_message(user_id, "session_007", msg_id)

            last_3 = await store.get_last_n_items(user_id, "session_007", 3)

            assert len(last_3) == 3

            assert last_3[0].ordinal == 7
            assert last_3[1].ordinal == 8
            assert last_3[2].ordinal == 9
    finally:
        await db.disconnect()


@pytest.mark.asyncio
async def test_mixed_message_and_summary():
    store = ContextStore()
    raw_store = RawMessageStore()
    summary_store = SummaryStore()
    user_id = "test_user_ctx_mixed_pytest"

    await db.connect()
    try:
        await db.init_user(user_id)

        async with db.user_context(user_id):
            msg1_id = await raw_store.store(user_id, "消息1", "dialogue")
            msg2_id = await raw_store.store(user_id, "消息2", "dialogue")
            msg3_id = await raw_store.store(user_id, "消息3", "dialogue")

            await store.append_message(user_id, "session_008", msg1_id)
            await store.append_message(user_id, "session_008", msg2_id)

            summary_id = await summary_store.create_summary(
                user_id=user_id, content="摘要", kind="leaf"
            )
            await store.append_summary(user_id, "session_008", summary_id)

            await store.append_message(user_id, "session_008", msg3_id)

            items = await store.get_context_items(user_id, "session_008")

            assert len(items) == 4
            assert items[0].item_type == "message"
            assert items[1].item_type == "message"
            assert items[2].item_type == "summary"
            assert items[3].item_type == "message"

            msg_count = await store.get_message_count(user_id, "session_008")
            summary_count = await store.get_summary_count(user_id, "session_008")

            assert msg_count == 3
            assert summary_count == 1
    finally:
        await db.disconnect()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
