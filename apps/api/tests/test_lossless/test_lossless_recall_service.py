import pytest
from pathlib import Path
import sys
import os
from datetime import datetime, timedelta

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

from dotenv import load_dotenv

env_path = Path(__file__).parent.parent.parent / ".env"
load_dotenv(env_path)

from src.services.lossless.lossless_recall_service import LosslessRecallService
from src.services.lossless.raw_message_store import RawMessageStore
from src.services.lossless.summary_store import SummaryStore
from src.database import db


@pytest.mark.asyncio
async def test_vector_recall():
    service = LosslessRecallService()
    raw_store = RawMessageStore()
    user_id = "test_recall_vector"

    await db.connect()
    try:
        await db.init_user(user_id)

        async with db.user_context(user_id):
            raw_id = await raw_store.store(
                user_id=user_id,
                content="我喜欢喝咖啡，尤其是美式咖啡",
                memory_type="preference",
            )

            embedding_client = None
            try:
                from src.embedding.client import get_embedding_client

                embedding_client = get_embedding_client()
            except Exception:
                pass

            if embedding_client:
                embedding = embedding_client.embed("我喜欢喝咖啡，尤其是美式咖啡")
                if embedding:
                    await raw_store.update_embedding(raw_id, embedding)

            results = await service._vector_recall(
                query_embedding=[0.1] * 1024,
                user_id=user_id,
                agent_filter="agent_id IS NULL",
                limit=10,
            )

            assert isinstance(results, list)
    finally:
        await db.disconnect()


@pytest.mark.asyncio
async def test_keyword_recall():
    service = LosslessRecallService()
    raw_store = RawMessageStore()
    user_id = "test_recall_keyword"

    await db.connect()
    try:
        await db.init_user(user_id)

        async with db.user_context(user_id):
            await raw_store.store(
                user_id=user_id,
                content="今天在星巴克遇到了老同学张三",
                memory_type="note",
            )

            results = await service._keyword_recall(
                query="星巴克",
                user_id=user_id,
                agent_filter="agent_id IS NULL",
                limit=10,
            )

            assert isinstance(results, list)
    finally:
        await db.disconnect()


@pytest.mark.asyncio
async def test_extract_keywords():
    service = LosslessRecallService()

    keywords = service._extract_keywords("今天在星巴克遇到了老同学张三")

    assert isinstance(keywords, list)
    assert len(keywords) >= 1


@pytest.mark.asyncio
async def test_build_agent_filter():
    service = LosslessRecallService()

    filter1 = service._build_agent_filter("manual_only", None)
    assert filter1 == "agent_id IS NULL"

    filter2 = service._build_agent_filter("agent_only", "agent_001")
    assert filter2 == "agent_id = 'agent_001'"

    filter3 = service._build_agent_filter("all", "agent_001")
    assert "agent_id IS NULL" in filter3
    assert "agent_001" in filter3


@pytest.mark.asyncio
async def test_merge_results():
    service = LosslessRecallService()

    vector_results = [
        {
            "type": "raw_message",
            "id": "raw_001",
            "content": "内容1",
            "similarity": 0.8,
            "source": "vector",
            "expandable": False,
        },
    ]

    keyword_results = [
        {
            "type": "raw_message",
            "id": "raw_001",
            "content": "内容1",
            "similarity": 0.7,
            "source": "keyword",
            "expandable": False,
        },
        {
            "type": "summary",
            "id": "sum_001",
            "content": "摘要1",
            "similarity": 0.6,
            "source": "keyword",
            "expandable": True,
        },
    ]

    graph_results = []

    merged = service._merge_results(vector_results, keyword_results, graph_results)

    assert len(merged) == 2
    assert merged[0]["id"] == "raw_001"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
