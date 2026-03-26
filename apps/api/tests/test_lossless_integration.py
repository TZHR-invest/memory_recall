#!/usr/bin/env python3
"""
Lossless stores 集成测试
"""

import sys
import os
import asyncio
import uuid
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path)

from src.services.lossless.raw_message_store import RawMessageStore
from src.services.lossless.summary_store import SummaryStore
from src.services.lossless.context_store import ContextStore
from src.database import db


async def test_raw_message_store():
    print("\n=== Test RawMessageStore ===")
    store = RawMessageStore()
    user_id = "test_lossless_user"

    await db.connect()
    try:
        await db.init_user(user_id)

        async with db.user_context(user_id):
            raw_id = await store.store(
                user_id=user_id,
                content="我是素食主义者，不喜欢吃肉",
                memory_type="preference",
            )
            print(f"  Created raw message: {raw_id}")

            msg = await store.get_by_id(raw_id)
            assert msg is not None
            assert msg.content == "我是素食主义者，不喜欢吃肉"
            assert msg.memory_type == "preference"
            assert msg.agent_id is None
            print(f"  Content: {msg.content}")
            print(f"  Memory type: {msg.memory_type}")
            print(f"  Token count: {msg.token_count}")

            raw_id2 = await store.store(
                user_id=user_id,
                content="今天天气不错",
                memory_type="dialogue",
                agent_id="agent_001",
                session_id="session_001",
            )
            msg2 = await store.get_by_id(raw_id2)
            assert msg2.agent_id == "agent_001"
            assert msg2.session_id == "session_001"
            print(f"  Agent message created: {raw_id2}")

            embedding = [0.1] * 1024
            await store.update_embedding(raw_id, embedding)
            msg_updated = await store.get_by_id(raw_id)
            assert msg_updated.embedding is not None
            assert len(msg_updated.embedding) == 1024
            print(f"  Embedding updated successfully")

            print("  RawMessageStore: PASS")
    finally:
        await db.disconnect()


async def test_summary_store():
    print("\n=== Test SummaryStore ===")
    store = SummaryStore()
    raw_store = RawMessageStore()
    user_id = "test_lossless_summary"

    await db.connect()
    try:
        await db.init_user(user_id)

        async with db.user_context(user_id):
            msg1_id = await raw_store.store(user_id, "消息1", "dialogue")
            msg2_id = await raw_store.store(user_id, "消息2", "dialogue")

            summary_id = await store.create_summary(
                user_id=user_id,
                content="这是摘要内容",
                kind="leaf",
                depth=0,
                token_count=50,
            )
            print(f"  Created summary: {summary_id}")

            await store.link_messages(summary_id, [msg1_id, msg2_id])
            linked_ids = await store.get_summary_messages(summary_id)
            assert len(linked_ids) == 2
            print(f"  Linked messages: {len(linked_ids)}")

            parent_id = await store.create_summary(
                user_id=user_id,
                content="父摘要",
                kind="leaf",
                depth=0,
            )
            child_id = await store.create_summary(
                user_id=user_id,
                content="子摘要",
                kind="condensed",
                depth=1,
            )
            await store.link_parents(child_id, [parent_id])

            parents = await store.get_summary_parents(child_id)
            assert len(parents) == 1
            print(f"  DAG parents: {len(parents)}")

            print("  SummaryStore: PASS")
    finally:
        await db.disconnect()


async def test_context_store():
    print("\n=== Test ContextStore ===")
    store = ContextStore()
    raw_store = RawMessageStore()
    summary_store = SummaryStore()
    user_id = f"test_lossless_context_{uuid.uuid4().hex[:8]}"

    await db.connect()
    try:
        await db.init_user(user_id)

        async with db.user_context(user_id):
            msg1_id = await raw_store.store(user_id, "消息1", "dialogue")
            msg2_id = await raw_store.store(user_id, "消息2", "dialogue")

            ordinal1 = await store.append_message(user_id, "session_001", msg1_id)
            ordinal2 = await store.append_message(user_id, "session_001", msg2_id)

            print(f"  Appended messages: ordinal {ordinal1}, {ordinal2}")

            items = await store.get_context_items(user_id, "session_001")
            assert len(items) == 2, f"Expected 2 items, got {len(items)}"
            print(f"  Context items count: {len(items)}")

            token_count = await store.get_token_count(user_id, "session_001")
            assert token_count > 0
            print(f"  Token count: {token_count}")

            summary_id = await summary_store.create_summary(
                user_id=user_id,
                content="摘要",
                kind="leaf",
                token_count=30,
            )

            await store.replace_range_with_summary(
                user_id, "session_001", ordinal1, ordinal2, summary_id
            )

            items_after = await store.get_context_items(user_id, "session_001")
            assert items_after[0].item_type == "summary"
            assert items_after[0].summary_id == summary_id
            print(f"  After replace: {len(items_after)} items, first is summary")

            print("  ContextStore: PASS")
    finally:
        await db.disconnect()


async def main():
    print("Lossless Stores Integration Tests")
    print("=" * 50)

    try:
        await test_raw_message_store()
        await test_summary_store()
        await test_context_store()

        print("\n" + "=" * 50)
        print("ALL TESTS PASSED!")
    except Exception as e:
        print(f"\nTEST FAILED: {e}")
        import traceback

        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    exit(asyncio.run(main()))
