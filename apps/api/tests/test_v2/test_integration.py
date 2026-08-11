"""
Integration tests for end-to-end memory flow.
"""

import pytest
import sys
import os
import asyncio

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

from src.services.core.memory_store import memory_store
from src.services.core.relation_service import relation_service
from src.services.core.profile_service import profile_service
from src.services.core.document_store import document_store
from src.database import db


@pytest.fixture
async def setup_db():
    await db.connect()
    yield
    await db.disconnect()


@pytest.mark.asyncio
async def test_full_memory_lifecycle(setup_db):
    """Test complete memory lifecycle: create, search, update, forget."""
    container = "test_integration_lifecycle"

    memory = await memory_store.create(
        content="我喜欢喝咖啡，特别是美式",
        container_tag=container,
        is_static=True,
    )
    assert memory.id.startswith("mem_")
    assert memory.is_static is True

    results = await memory_store.search(
        query="咖啡偏好",
        container_tag=container,
        limit=5,
    )
    assert len(results) >= 1
    assert any("咖啡" in r["content"] for r in results)

    profile = await profile_service.get_profile(container_tag=container)
    assert "profile" in profile
    assert any("咖啡" in fact for fact in profile["profile"]["static"])

    success = await memory_store.forget(memory.id)
    assert success is True

    # get_by_id 默认过滤已遗忘（include_forgotten=False），直接查询返回 None
    gone = await memory_store.get_by_id(memory.id)
    assert gone is None

    forgotten = await memory_store.get_by_id(memory.id, include_forgotten=True)
    assert forgotten.is_forgotten is True

    success = await memory_store.restore(memory.id)
    assert success is True

    restored = await memory_store.get_by_id(memory.id)
    assert restored.is_forgotten is False


@pytest.mark.asyncio
async def test_temporal_relations(setup_db):
    """Test automatic relation creation for updates and extends."""
    container = "test_integration_relations"

    old_memory = await memory_store.create(
        content="我在 Google 工作",
        container_tag=container,
        is_static=True,
    )

    await asyncio.sleep(0.1)

    new_memory = await memory_store.create(
        content="我现在在 Supermemory 工作",
        container_tag=container,
        is_static=True,
    )

    relations = await relation_service.get_by_memory(new_memory.id)
    updates_relations = [r for r in relations if r.relation_type == "updates"]

    if updates_relations:
        assert updates_relations[0].to_memory_id == old_memory.id

        old_check = await memory_store.get_by_id(old_memory.id)
        assert old_check.is_latest is False


@pytest.mark.asyncio
async def test_profile_caching(setup_db):
    """Test profile caching and invalidation."""
    container = "test_integration_cache"

    await memory_store.create(
        content="我是张三",
        container_tag=container,
        is_static=True,
    )

    profile1 = await profile_service.get_profile(container_tag=container)

    await memory_store.create(
        content="我喜欢编程",
        container_tag=container,
        is_static=True,
    )

    await profile_service.invalidate_cache(container)

    profile2 = await profile_service.get_profile(container_tag=container)

    assert len(profile2["profile"]["static"]) >= len(profile1["profile"]["static"])


@pytest.mark.asyncio
async def test_entity_extraction(setup_db):
    """Test automatic entity extraction."""
    container = "test_integration_entities"

    memory = await memory_store.create(
        content="我在北京工作，喜欢吃火锅",
        container_tag=container,
        is_static=True,
    )

    assert "entities" in memory.metadata
    entities = memory.metadata.get("entities", {})
    assert "location" in entities or "preference" in entities


@pytest.mark.asyncio
async def test_document_lifecycle(setup_db):
    """Test document CRUD operations."""
    container = "test_integration_docs"

    doc, _ = await document_store.create(
        content="This is a test document for integration testing.",
        container_tag=container,
        metadata={"source": "test"},
    )
    assert doc.id.startswith("doc_")

    retrieved = await document_store.get_by_id(doc.id)
    assert retrieved is not None
    assert retrieved.id == doc.id
    assert retrieved.container_tag == doc.container_tag

    docs = await document_store.get_by_container(container)
    assert len(docs) >= 1

    success = await document_store.delete(doc.id)
    assert success is True

    deleted = await document_store.get_by_id(doc.id)
    assert deleted is None


@pytest.mark.asyncio
async def test_search_with_threshold(setup_db):
    """Test search with different similarity thresholds."""
    container = "test_integration_search"

    await memory_store.create(
        content="我喜欢运动，特别是跑步",
        container_tag=container,
        is_static=True,
    )

    high_threshold_results = await memory_store.search(
        query="运动爱好",
        container_tag=container,
        threshold=0.8,
    )

    low_threshold_results = await memory_store.search(
        query="运动爱好",
        container_tag=container,
        threshold=0.3,
    )

    assert len(low_threshold_results) >= len(high_threshold_results)


@pytest.mark.asyncio
async def test_version_history(setup_db):
    """Test memory version history tracking."""
    container = "test_integration_history"

    v1 = await memory_store.create(
        content="项目使用 Python 3.8",
        container_tag=container,
        is_static=False,
    )

    v2 = await memory_store.create_update_version(
        memory_id=v1.id,
        new_content="项目升级到 Python 3.11",
    )

    assert v2.id != v1.id

    history = await relation_service.get_version_history(v2.id)
    assert len(history) >= 1
