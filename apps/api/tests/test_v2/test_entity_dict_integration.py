"""
Integration tests for entity dictionary with memory store and profile service.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from src.services.core.simplified_entity_dict import get_entity_dict, ContainerScopedEntityDict
from src.services.core.memory_store import memory_store
from src.services.core.profile_service import profile_service
from src.config import settings


class TestMemoryStoreIntegration:
    """Integration tests for memory store with entity dictionary."""

    @pytest.mark.asyncio
    async def test_memory_creation_updates_entity_dict(self):
        """Test that creating a memory updates the entity dictionary."""
        from src.services.core.simplified_entity_dict import ContainerScopedEntityDict

        entity_dict = ContainerScopedEntityDict()
        entity_dict._dicts.clear()

        with patch("src.services.core.memory_store.db") as mock_db:
            mock_db.fetchrow = AsyncMock(return_value={
                "id": "mem_new",
                "container_tag": "test_container",
                "content": "我在字节跳动工作",
                "embedding": "[0.1,0.2,0.3]",
                "is_static": True,
                "metadata": {"entities": {"organization": ["字节跳动"]}},
                "confidence": 0.8,
                "created_at": None,
                "is_forgotten": False,
                "version": 1,
                "root_memory_id": None,
                "source_count": 1,
                "is_inference": False,
                "valid_from": None,
                "valid_until": None,
                "is_latest": True,
                "updated_at": None,
            })
            mock_db.execute = AsyncMock(return_value="INSERT 1")
            mock_db.fetch = AsyncMock(return_value=[])

            with patch("src.services.core.memory_store.get_entity_dict", return_value=entity_dict):
                memory = await memory_store.create(
                    content="我在字节跳动工作",
                    container_tag="test_container",
                    extract_entities=False,
                    auto_relations=False,
                    generate_embedding=False,
                    check_merge=False,
                    metadata={"entities": {"organization": ["字节跳动"]}},
                )

                assert "test_container" in entity_dict._dicts
                assert "字节跳动" in entity_dict._dicts["test_container"]


class TestProfileServiceIntegration:
    """Integration tests for profile service with entity dictionary."""

    @pytest.mark.asyncio
    async def test_profile_returns_matched_entities(self):
        """Test that get_profile returns matched entities."""
        entity_dict = get_entity_dict()
        entity_dict._dicts["test_container"] = {
            "字节跳动": type('EntityInfo', (), {'type': 'organization', 'memory_ids': ['mem_1']})(),
            "张三": type('EntityInfo', (), {'type': 'person', 'memory_ids': ['mem_2']})(),
        }

        with patch.object(profile_service, '_get_cached_profile', return_value=None):
            with patch.object(profile_service, '_build_profile', return_value={
                "static_memories": ["静态记忆"],
                "dynamic_memories": ["动态记忆"],
            }):
                with patch.object(profile_service, '_cache_profile', return_value=None):
                    with patch.object(memory_store, 'search', return_value=[]):
                        result = await profile_service.get_profile(
                            container_tag="test_container",
                            query="张三在字节跳动工作",
                        )

                        assert "matchedEntities" in result
                        assert result["matchedEntities"] is not None


class TestEntityDictConfig:
    """Tests for entity dictionary configuration."""

    def test_use_entity_dict_config(self):
        """Test that USE_ENTITY_DICT config exists."""
        assert hasattr(settings, 'USE_ENTITY_DICT')
        assert settings.USE_ENTITY_DICT is True

    def test_entity_dict_lazy_load_config(self):
        """Test that ENTITY_DICT_LAZY_LOAD config exists."""
        assert hasattr(settings, 'ENTITY_DICT_LAZY_LOAD')
        assert settings.ENTITY_DICT_LAZY_LOAD is True

    def test_entity_dict_max_containers_config(self):
        """Test that ENTITY_DICT_MAX_CONTAINERS config exists."""
        assert hasattr(settings, 'ENTITY_DICT_MAX_CONTAINERS')
        assert settings.ENTITY_DICT_MAX_CONTAINERS == 1000
