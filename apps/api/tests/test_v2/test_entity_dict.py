"""
Unit tests for container-scoped entity dictionary service.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import time

from src.services.core.simplified_entity_dict import (
    EntityInfo,
    ContainerScopedEntityDict,
    get_entity_dict,
)


class TestEntityInfo:
    """Tests for EntityInfo dataclass."""

    def test_entity_info_creation(self):
        info = EntityInfo(type="organization", memory_ids=["mem_1", "mem_2"])
        assert info.type == "organization"
        assert info.memory_ids == ["mem_1", "mem_2"]
        assert info.created_at is not None

    def test_entity_info_default_values(self):
        info = EntityInfo(type="person")
        assert info.memory_ids == []


class TestContainerScopedEntityDict:
    """Tests for ContainerScopedEntityDict class."""

    @pytest.fixture
    def entity_dict(self):
        return ContainerScopedEntityDict()

    @pytest.fixture
    def mock_db_data(self):
        return [
            {
                "id": "mem_1",
                "entities": {"organization": ["字节跳动"], "person": ["张三"]},
            },
            {
                "id": "mem_2",
                "entities": {"organization": ["字节跳动北京分公司"], "person": ["李四"]},
            },
            {
                "id": "mem_3",
                "entities": {"location": ["北京"], "preference": ["喜欢吃火锅"]},
            },
        ]

    @pytest.mark.asyncio
    async def test_build(self, entity_dict, mock_db_data):
        """Test building dictionary from memories."""
        with patch("src.services.core.simplified_entity_dict.db") as mock_db:
            mock_db.fetch = AsyncMock(return_value=mock_db_data)

            result = await entity_dict.build("container_1")

            assert "字节跳动" in result
            assert "张三" in result
            assert "李四" in result
            assert "北京" in result
            assert result["字节跳动"].type == "organization"
            assert "mem_1" in result["字节跳动"].memory_ids

    @pytest.mark.asyncio
    async def test_build_container_isolation(self, entity_dict, mock_db_data):
        """Test that dictionaries are isolated by container_tag."""
        with patch("src.services.core.simplified_entity_dict.db") as mock_db:
            mock_db.fetch = AsyncMock(return_value=mock_db_data)

            result1 = await entity_dict.build("container_1")
            result2 = await entity_dict.build("container_2")

            assert "container_1" in entity_dict._dicts
            assert "container_2" in entity_dict._dicts
            assert entity_dict._dicts["container_1"] is not entity_dict._dicts["container_2"]
            assert result1 is not result2

    @pytest.mark.asyncio
    async def test_get_or_build_lazy_loading(self, entity_dict, mock_db_data):
        """Test lazy loading behavior."""
        with patch("src.services.core.simplified_entity_dict.db") as mock_db:
            mock_db.fetch = AsyncMock(return_value=mock_db_data)

            assert not entity_dict.has("container_1")

            result = await entity_dict.get_or_build("container_1")

            assert entity_dict.has("container_1")
            assert "字节跳动" in result

    @pytest.mark.asyncio
    async def test_get_or_build_returns_cached(self, entity_dict, mock_db_data):
        """Test that subsequent calls return cached dictionary."""
        with patch("src.services.core.simplified_entity_dict.db") as mock_db:
            mock_db.fetch = AsyncMock(return_value=mock_db_data)

            result1 = await entity_dict.get_or_build("container_1")
            result2 = await entity_dict.get_or_build("container_1")

            assert mock_db.fetch.call_count == 1
            assert result1 is result2

    def test_match_single_entity(self, entity_dict):
        """Test matching a single entity."""
        entity_dict._dicts["container_1"] = {
            "字节跳动": EntityInfo(type="organization", memory_ids=["mem_1"]),
            "张三": EntityInfo(type="person", memory_ids=["mem_2"]),
        }

        result = entity_dict.match("我在字节跳动工作", "container_1")

        assert result == ["字节跳动"]

    def test_match_multiple_entities(self, entity_dict):
        """Test matching multiple entities."""
        entity_dict._dicts["container_1"] = {
            "字节跳动": EntityInfo(type="organization", memory_ids=["mem_1"]),
            "张三": EntityInfo(type="person", memory_ids=["mem_2"]),
            "北京": EntityInfo(type="location", memory_ids=["mem_3"]),
        }

        result = entity_dict.match("张三在字节跳动北京分公司工作", "container_1")

        assert "字节跳动" in result
        assert "张三" in result

    def test_match_longest_first(self, entity_dict):
        """Test longest-match-first algorithm."""
        entity_dict._dicts["container_1"] = {
            "字节跳动": EntityInfo(type="organization", memory_ids=["mem_1"]),
            "字节跳动北京分公司": EntityInfo(type="organization", memory_ids=["mem_2"]),
        }

        result = entity_dict.match("我在字节跳动北京分公司工作", "container_1")

        assert result == ["字节跳动北京分公司"]
        assert "字节跳动" not in result

    def test_match_no_entities(self, entity_dict):
        """Test query with no matching entities."""
        entity_dict._dicts["container_1"] = {
            "字节跳动": EntityInfo(type="organization", memory_ids=["mem_1"]),
        }

        result = entity_dict.match("今天天气很好", "container_1")

        assert result == []

    def test_match_empty_container(self, entity_dict):
        """Test matching against non-existent container."""
        result = entity_dict.match("测试查询", "nonexistent_container")

        assert result == []

    def test_add_entity(self, entity_dict):
        """Test adding entity to dictionary."""
        entity_dict._dicts["container_1"] = {}

        entity_dict.add_entity(
            container_tag="container_1",
            entity_name="阿里巴巴",
            entity_type="organization",
            memory_id="mem_1",
        )

        assert "阿里巴巴" in entity_dict._dicts["container_1"]
        assert entity_dict._dicts["container_1"]["阿里巴巴"].type == "organization"
        assert "mem_1" in entity_dict._dicts["container_1"]["阿里巴巴"].memory_ids

    def test_add_entity_duplicate(self, entity_dict):
        """Test adding duplicate entity appends memory_id."""
        entity_dict._dicts["container_1"] = {
            "阿里巴巴": EntityInfo(type="organization", memory_ids=["mem_1"])
        }

        entity_dict.add_entity(
            container_tag="container_1",
            entity_name="阿里巴巴",
            entity_type="organization",
            memory_id="mem_2",
        )

        assert "mem_1" in entity_dict._dicts["container_1"]["阿里巴巴"].memory_ids
        assert "mem_2" in entity_dict._dicts["container_1"]["阿里巴巴"].memory_ids

    def test_remove_entity(self, entity_dict):
        """Test removing entity from dictionary."""
        entity_dict._dicts["container_1"] = {
            "阿里巴巴": EntityInfo(type="organization", memory_ids=["mem_1", "mem_2"])
        }

        entity_dict.remove_entity(
            container_tag="container_1",
            entity_name="阿里巴巴",
            memory_id="mem_1",
        )

        assert "mem_1" not in entity_dict._dicts["container_1"]["阿里巴巴"].memory_ids
        assert "mem_2" in entity_dict._dicts["container_1"]["阿里巴巴"].memory_ids

    def test_remove_entity_last_memory(self, entity_dict):
        """Test removing last memory_id deletes entity."""
        entity_dict._dicts["container_1"] = {
            "阿里巴巴": EntityInfo(type="organization", memory_ids=["mem_1"])
        }

        entity_dict.remove_entity(
            container_tag="container_1",
            entity_name="阿里巴巴",
            memory_id="mem_1",
        )

        assert "阿里巴巴" not in entity_dict._dicts["container_1"]

    def test_invalidate(self, entity_dict):
        """Test invalidating cached dictionary."""
        entity_dict._dicts["container_1"] = {
            "阿里巴巴": EntityInfo(type="organization", memory_ids=["mem_1"])
        }

        entity_dict.invalidate("container_1")

        assert "container_1" not in entity_dict._dicts

    def test_has(self, entity_dict):
        """Test checking if dictionary exists."""
        entity_dict._dicts["container_1"] = {}

        assert entity_dict.has("container_1") is True
        assert entity_dict.has("container_2") is False

    def test_get_stats(self, entity_dict):
        """Test getting statistics."""
        entity_dict._dicts["container_1"] = {
            "entity1": EntityInfo(type="organization", memory_ids=["mem_1"]),
            "entity2": EntityInfo(type="person", memory_ids=["mem_2"]),
        }
        entity_dict._dicts["container_2"] = {
            "entity3": EntityInfo(type="location", memory_ids=["mem_3"]),
        }

        stats = entity_dict.get_stats()

        assert stats["container_count"] == 2
        assert stats["total_entities"] == 3

    def test_match_performance(self, entity_dict):
        """Test that matching is fast (< 10ms)."""
        for i in range(1000):
            entity_dict._dicts["container_1"] = {
                f"entity_{i}": EntityInfo(type="organization", memory_ids=[f"mem_{i}"])
                for i in range(1000)
            }

        start_time = time.time()
        for _ in range(100):
            result = entity_dict.match("这是 entity_500 测试", "container_1")
        elapsed_ms = (time.time() - start_time) * 1000 / 100

        assert elapsed_ms < 10


class TestGetEntityDict:
    """Tests for get_entity_dict function."""

    def test_returns_singleton(self):
        """Test that get_entity_dict returns the same instance."""
        from src.services.core import simplified_entity_dict

        simplified_entity_dict.entity_dict = None

        dict1 = get_entity_dict()
        dict2 = get_entity_dict()

        assert dict1 is dict2
