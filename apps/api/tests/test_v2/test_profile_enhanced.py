"""
Tests for enhanced ProfileService features.
"""

import pytest
import sys
import os
from unittest.mock import AsyncMock, patch, MagicMock

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

from src.services.core.profile_service import ProfileService
from src.services.core.memory_store import Memory


class TestProfileWithEntities:
    @pytest.mark.asyncio
    async def test_get_profile_with_entities(self):
        service = ProfileService()

        mock_memories = [
            Memory(
                id="mem_001",
                container_tag="user_001",
                content="我在北京工作",
                metadata={"entities": {"location": ["北京"]}},
            ),
            Memory(
                id="mem_002",
                container_tag="user_001",
                content="我喜欢喝咖啡",
                metadata={"entities": {"preference": ["咖啡"]}},
            ),
        ]

        with patch.object(service, "_get_cached_profile") as mock_cache:
            with patch("src.services.core.profile_service.memory_store") as mock_store:
                mock_cache.return_value = None
                mock_store.get_by_container = AsyncMock(return_value=mock_memories)
                mock_store.get_static_memories = AsyncMock(return_value=[])
                mock_store.get_dynamic_memories = AsyncMock(return_value=mock_memories)

                result = await service.get_profile_with_entities("user_001")

                assert "entities" in result
                assert "location" in result["entities"]
                assert "preference" in result["entities"]

    @pytest.mark.asyncio
    async def test_get_profile_with_entities_filtered(self):
        service = ProfileService()

        mock_memories = [
            Memory(
                id="mem_001",
                container_tag="user_001",
                content="我在北京工作",
                metadata={"entities": {"location": ["北京"]}},
            ),
            Memory(
                id="mem_002",
                container_tag="user_001",
                content="我喜欢喝咖啡",
                metadata={"entities": {"preference": ["咖啡"]}},
            ),
        ]

        with patch.object(service, "_get_cached_profile") as mock_cache:
            with patch("src.services.core.profile_service.memory_store") as mock_store:
                mock_cache.return_value = None
                mock_store.get_by_container = AsyncMock(return_value=mock_memories)

                result = await service.get_profile_with_entities(
                    "user_001", entity_type="location"
                )

                assert "entities" in result
                assert "location" in result["entities"]
                assert "preference" not in result["entities"]


class TestProfileWithRelations:
    @pytest.mark.asyncio
    async def test_get_profile_with_relations(self):
        service = ProfileService()

        mock_memories = [
            Memory(
                id="mem_001",
                container_tag="user_001",
                content="原始记忆",
                is_static=True,
                version=1,
                metadata={"relations": {"updates": [], "extends": [], "derives": []}},
            ),
            Memory(
                id="mem_002",
                container_tag="user_001",
                content="更新后的记忆",
                is_static=True,
                version=2,
                metadata={
                    "relations": {"updates": ["mem_001"], "extends": [], "derives": []}
                },
            ),
        ]

        with patch.object(service, "_get_cached_profile") as mock_cache:
            with patch("src.services.core.profile_service.memory_store") as mock_store:
                mock_cache.return_value = None
                mock_store.get_by_container = AsyncMock(return_value=mock_memories)

                result = await service.get_profile_with_relations("user_001")

                assert "nodes" in result
                assert "edges" in result
                assert len(result["nodes"]) == 2
                assert any(e["type"] == "updates" for e in result["edges"])

    @pytest.mark.asyncio
    async def test_get_profile_with_relations_empty(self):
        service = ProfileService()

        with patch.object(service, "_get_cached_profile") as mock_cache:
            with patch("src.services.core.profile_service.memory_store") as mock_store:
                mock_cache.return_value = None
                mock_store.get_by_container = AsyncMock(return_value=[])

                result = await service.get_profile_with_relations("user_001")

                assert result["nodes"] == []
                assert result["edges"] == []


class TestProfileWithMetadata:
    @pytest.mark.asyncio
    async def test_get_profile_with_metadata(self):
        service = ProfileService()

        mock_memories = [
            Memory(
                id="mem_001",
                container_tag="user_001",
                content="测试记忆",
                metadata={"entities": {"location": ["北京"]}},
                version=1,
                created_at=None,
            ),
        ]

        with patch.object(service, "_get_cached_profile") as mock_cache:
            with patch("src.services.core.profile_service.memory_store") as mock_store:
                mock_cache.return_value = None
                mock_store.get_static_memories = AsyncMock(return_value=mock_memories)
                mock_store.get_dynamic_memories = AsyncMock(return_value=[])

                result = await service.get_profile(
                    container_tag="user_001",
                    include_metadata=True,
                )

                assert "profile" in result
                assert "static" in result["profile"]
                if result["profile"]["static"]:
                    assert "metadata" in result["profile"]["static"][0]
                    assert "version" in result["profile"]["static"][0]


class TestProfileServiceMethods:
    @pytest.mark.asyncio
    async def test_get_static_facts(self):
        service = ProfileService()

        mock_memories = [
            Memory(id="mem_001", container_tag="user_001", content="Fact 1"),
            Memory(id="mem_002", container_tag="user_001", content="Fact 2"),
        ]

        with patch("src.services.core.profile_service.memory_store") as mock_store:
            mock_store.get_static_memories = AsyncMock(return_value=mock_memories)

            facts = await service.get_static_facts("user_001")

            assert len(facts) == 2
            assert "Fact 1" in facts

    @pytest.mark.asyncio
    async def test_get_dynamic_facts(self):
        service = ProfileService()

        mock_memories = [
            Memory(id="mem_001", container_tag="user_001", content="Dynamic 1"),
        ]

        with patch("src.services.core.profile_service.memory_store") as mock_store:
            mock_store.get_dynamic_memories = AsyncMock(return_value=mock_memories)

            facts = await service.get_dynamic_facts("user_001")

            assert len(facts) == 1
            assert "Dynamic 1" in facts
