import pytest
from pathlib import Path
import sys
import os
import time

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

from dotenv import load_dotenv

env_path = Path(__file__).parent.parent.parent / ".env"
load_dotenv(env_path)

from src.services.lossless.summary_store import SummaryStore
from src.services.lossless.raw_message_store import RawMessageStore
from src.database import db


def unique_user_id(base: str) -> str:
    return f"{base}_{int(time.time() * 1000000)}"


@pytest.mark.asyncio
async def test_create_summary():
    store = SummaryStore()
    user_id = unique_user_id("test_user_summary")

    await db.connect()
    try:
        await db.init_user(user_id)

        async with db.user_context(user_id):
            summary_id = await store.create_summary(
                user_id=user_id,
                content="这是一个摘要内容",
                kind="leaf",
                depth=0,
                token_count=50,
            )

            assert summary_id.startswith("sum_")

            summary = await store.get_summary(summary_id)

            assert summary is not None
            assert summary.content == "这是一个摘要内容"
            assert summary.kind == "leaf"
            assert summary.depth == 0
    finally:
        await db.disconnect()


@pytest.mark.asyncio
async def test_link_messages():
    store = SummaryStore()
    raw_store = RawMessageStore()
    user_id = unique_user_id("test_user_link")

    await db.connect()
    try:
        await db.init_user(user_id)

        async with db.user_context(user_id):
            msg1_id = await raw_store.store(user_id, "消息1", "dialogue")
            msg2_id = await raw_store.store(user_id, "消息2", "dialogue")
            msg3_id = await raw_store.store(user_id, "消息3", "dialogue")

            summary_id = await store.create_summary(
                user_id=user_id, content="摘要", kind="leaf"
            )

            await store.link_messages(summary_id, [msg1_id, msg2_id, msg3_id])

            linked_ids = await store.get_summary_messages(summary_id)

            assert len(linked_ids) == 3
            assert linked_ids == [msg1_id, msg2_id, msg3_id]
    finally:
        await db.disconnect()


@pytest.mark.asyncio
async def test_link_parents():
    store = SummaryStore()
    user_id = unique_user_id("test_user_parents")

    await db.connect()
    try:
        await db.init_user(user_id)

        async with db.user_context(user_id):
            parent1_id = await store.create_summary(
                user_id=user_id, content="父摘要1", kind="leaf", depth=0
            )

            parent2_id = await store.create_summary(
                user_id=user_id, content="父摘要2", kind="leaf", depth=0
            )

            child_id = await store.create_summary(
                user_id=user_id, content="子摘要", kind="condensed", depth=1
            )

            await store.link_parents(child_id, [parent1_id, parent2_id])

            parents = await store.get_summary_parents(child_id)

            assert len(parents) == 2
    finally:
        await db.disconnect()


@pytest.mark.asyncio
async def test_get_summary_children():
    store = SummaryStore()
    user_id = unique_user_id("test_user_children")

    await db.connect()
    try:
        await db.init_user(user_id)

        async with db.user_context(user_id):
            parent_id = await store.create_summary(
                user_id=user_id, content="父摘要", kind="leaf", depth=0
            )

            child1_id = await store.create_summary(
                user_id=user_id, content="子摘要1", kind="condensed", depth=1
            )

            child2_id = await store.create_summary(
                user_id=user_id, content="子摘要2", kind="condensed", depth=1
            )

            await store.link_parent(child1_id, parent_id, 0)
            await store.link_parent(child2_id, parent_id, 1)

            children = await store.get_summary_children(parent_id)

            assert len(children) == 2
    finally:
        await db.disconnect()


@pytest.mark.asyncio
async def test_update_embedding():
    store = SummaryStore()
    user_id = unique_user_id("test_user_sum_embedding")

    await db.connect()
    try:
        await db.init_user(user_id)

        async with db.user_context(user_id):
            summary_id = await store.create_summary(
                user_id=user_id, content="测试向量", kind="leaf"
            )

            embedding = [0.5] * 1024

            await store.update_embedding(summary_id, embedding)

            summary = await store.get_summary(summary_id)

            assert summary.embedding is not None
            assert len(summary.embedding) == 1024
    finally:
        await db.disconnect()


@pytest.mark.asyncio
async def test_get_by_agent():
    store = SummaryStore()
    user_id = unique_user_id("test_user_by_agent")

    await db.connect()
    try:
        await db.init_user(user_id)

        async with db.user_context(user_id):
            await store.create_summary(
                user_id=user_id, content="Agent1摘要", kind="leaf", agent_id="agent_001"
            )

            await store.create_summary(
                user_id=user_id, content="Agent2摘要", kind="leaf", agent_id="agent_002"
            )

            await store.create_summary(
                user_id=user_id, content="用户摘要", kind="leaf", agent_id=None
            )

            agent1_summaries = await store.get_by_agent(user_id, "agent_001")
            assert len(agent1_summaries) == 1

            agent2_summaries = await store.get_by_agent(user_id, "agent_002")
            assert len(agent2_summaries) == 1
    finally:
        await db.disconnect()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
