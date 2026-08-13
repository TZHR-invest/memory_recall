"""
Performance tests for profile API and core operations.
Target: < 100ms for profile retrieval.
"""

import pytest
import sys
import os
import time
import asyncio

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

from src.services.core.memory_store import memory_store
from src.services.core.profile_service import profile_service
from src.database import db


@pytest.fixture
async def setup_db():
    await db.connect()
    yield
    await db.disconnect()


@pytest.fixture
async def populated_container(setup_db):
    """Create a container with multiple memories for testing."""
    container = "test_perf_container"

    for i in range(20):
        await memory_store.create(
            content=f"静态记忆 {i}: 我喜欢技术{i}",
            container_tag=container,
            is_static=True,
        )

    for i in range(30):
        await memory_store.create(
            content=f"动态记忆 {i}: 最近在项目{i}上工作",
            container_tag=container,
            is_static=False,
        )

    yield container


@pytest.mark.asyncio
async def test_profile_retrieval_latency(populated_container):
    """Profile retrieval should be < 100ms."""
    container = populated_container

    latencies = []
    for _ in range(10):
        start = time.perf_counter()
        profile = await profile_service.get_profile(container_tag=container)
        end = time.perf_counter()
        latencies.append((end - start) * 1000)

    avg_latency = sum(latencies) / len(latencies)
    max_latency = max(latencies)
    min_latency = min(latencies)

    print(f"\nProfile Retrieval Latency:")
    print(f"  Average: {avg_latency:.2f}ms")
    print(f"  Min: {min_latency:.2f}ms")
    print(f"  Max: {max_latency:.2f}ms")

    assert avg_latency < 100, (
        f"Average latency {avg_latency:.2f}ms exceeds 100ms target"
    )
    assert "profile" in profile
    assert "static" in profile["profile"]
    assert "dynamic" in profile["profile"]


@pytest.mark.asyncio
async def test_cached_profile_latency(populated_container):
    """Cached profile retrieval should be < 50ms."""
    container = populated_container

    await profile_service.get_profile(container_tag=container)

    latencies = []
    for _ in range(10):
        start = time.perf_counter()
        await profile_service.get_profile(container_tag=container)
        end = time.perf_counter()
        latencies.append((end - start) * 1000)

    avg_latency = sum(latencies) / len(latencies)

    print(f"\nCached Profile Latency: {avg_latency:.2f}ms")

    assert avg_latency < 50, f"Cached latency {avg_latency:.2f}ms exceeds 50ms target"


@pytest.mark.asyncio
async def test_search_latency(populated_container):
    """Search should complete within reasonable time."""
    container = populated_container

    latencies = []
    for _ in range(5):
        start = time.perf_counter()
        results = await memory_store.search(
            query="技术偏好",
            container_tag=container,
            limit=10,
        )
        end = time.perf_counter()
        latencies.append((end - start) * 1000)

    avg_latency = sum(latencies) / len(latencies)

    print(f"\nSearch Latency: {avg_latency:.2f}ms")

    assert avg_latency < 500, f"Search latency {avg_latency:.2f}ms is too high"


@pytest.mark.asyncio
async def test_create_memory_latency(setup_db):
    """Memory creation should be < 200ms (excluding embedding generation)."""
    container = "test_perf_create"

    latencies = []
    for i in range(10):
        start = time.perf_counter()
        await memory_store.create(
            content=f"测试记忆 {i}",
            container_tag=container,
            is_static=True,
            generate_embedding=False,
            extract_entities=False,
            extract_relations=False,
        )
        end = time.perf_counter()
        latencies.append((end - start) * 1000)

    avg_latency = sum(latencies) / len(latencies)

    print(f"\nCreate Memory Latency (no embedding): {avg_latency:.2f}ms")

    assert avg_latency < 200, f"Create latency {avg_latency:.2f}ms exceeds 200ms"


@pytest.mark.asyncio
async def test_concurrent_profile_requests(populated_container):
    """Handle concurrent profile requests efficiently."""
    container = populated_container

    async def get_profile_task():
        return await profile_service.get_profile(container_tag=container)

    start = time.perf_counter()
    results = await asyncio.gather(*[get_profile_task() for _ in range(10)])
    end = time.perf_counter()

    total_latency = (end - start) * 1000

    print(f"\n10 Concurrent Profile Requests: {total_latency:.2f}ms")

    assert len(results) == 10
    assert total_latency < 500, f"Concurrent requests took {total_latency:.2f}ms"
