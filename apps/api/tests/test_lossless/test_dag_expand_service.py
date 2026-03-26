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

from src.services.lossless.dag_expand_service import DAGExpandService
from src.services.lossless.raw_message_store import RawMessageStore
from src.services.lossless.summary_store import SummaryStore
from src.database import db


@pytest.mark.asyncio
async def test_expand_node():
    service = DAGExpandService()
    raw_store = RawMessageStore()
    summary_store = SummaryStore()
    user_id = "test_dag_expand"

    await db.connect()
    try:
        await db.init_user(user_id)

        async with db.user_context(user_id):
            msg1_id = await raw_store.store(user_id, "消息1", "dialogue")
            msg2_id = await raw_store.store(user_id, "消息2", "dialogue")

            summary_id = await summary_store.create_summary(
                user_id=user_id,
                content="叶摘要",
                kind="leaf",
                token_count=50,
            )

            await summary_store.link_messages(summary_id, [msg1_id, msg2_id])

            result = await service.expand_node(summary_id, max_tokens=10000)

            assert "nodes" in result
            assert result["total_nodes"] >= 1
            assert result["root_summary_id"] == summary_id
    finally:
        await db.disconnect()


@pytest.mark.asyncio
async def test_expand_to_messages():
    service = DAGExpandService()
    raw_store = RawMessageStore()
    summary_store = SummaryStore()
    user_id = "test_dag_messages"

    await db.connect()
    try:
        await db.init_user(user_id)

        async with db.user_context(user_id):
            msg1_id = await raw_store.store(user_id, "消息1内容", "dialogue")
            msg2_id = await raw_store.store(user_id, "消息2内容", "dialogue")

            summary_id = await summary_store.create_summary(
                user_id=user_id,
                content="摘要",
                kind="leaf",
                token_count=50,
            )

            await summary_store.link_messages(summary_id, [msg1_id, msg2_id])

            result = await service.expand_to_messages(summary_id)

            assert "messages" in result
            assert result["total_messages"] == 2
            assert result["summary_id"] == summary_id
    finally:
        await db.disconnect()


@pytest.mark.asyncio
async def test_get_summary_tree():
    service = DAGExpandService()
    raw_store = RawMessageStore()
    summary_store = SummaryStore()
    user_id = "test_dag_tree"

    await db.connect()
    try:
        await db.init_user(user_id)

        async with db.user_context(user_id):
            msg1_id = await raw_store.store(user_id, "消息1", "dialogue")
            msg2_id = await raw_store.store(user_id, "消息2", "dialogue")

            leaf_id = await summary_store.create_summary(
                user_id=user_id,
                content="叶摘要",
                kind="leaf",
                token_count=50,
            )
            await summary_store.link_messages(leaf_id, [msg1_id, msg2_id])

            condensed_id = await summary_store.create_summary(
                user_id=user_id,
                content="高层摘要",
                kind="condensed",
                depth=1,
                token_count=30,
            )
            await summary_store.link_parents(condensed_id, [leaf_id])

            tree = await service.get_summary_tree(condensed_id, max_depth=3)

            assert "summary_id" in tree
            assert tree["summary_id"] == condensed_id
            assert "children" in tree
            assert len(tree["children"]) >= 1
    finally:
        await db.disconnect()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
