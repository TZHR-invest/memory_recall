"""
Tests for enhanced MemoryStore features (version control, embedded relations).
"""

import pytest
import sys
import os
from unittest.mock import AsyncMock, patch, MagicMock

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

from src.services.core.memory_store import MemoryStore, Memory


class TestMemoryVersionControl:
    @pytest.mark.asyncio
    async def test_create_memory_with_version(self):
        store = MemoryStore()

        with patch.object(store, "_generate_embedding", return_value=[0.1] * 1024):
            with patch("src.services.core.memory_store.db") as mock_db:
                mock_db.fetchrow = AsyncMock(
                    return_value={
                        "id": "mem_001",
                        "container_tag": "user_001",
                        "content": "Test content",
                        "embedding": None,
                        "is_static": False,
                        "is_latest": True,
                        "valid_from": None,
                        "valid_until": None,
                        "metadata": {
                            "relations": {"updates": [], "extends": [], "derives": []}
                        },
                        "confidence": 0.8,
                        "created_at": None,
                        "is_forgotten": False,
                        "version": 1,
                        "root_memory_id": None,
                        "source_count": 1,
                        "is_inference": False,
                    }
                )
                mock_db.execute = AsyncMock(return_value="UPDATE 1")

                memory = await store.create(
                    content="Test content",
                    container_tag="user_001",
                )

                assert memory.version == 1
                assert memory.root_memory_id is None

    @pytest.mark.asyncio
    async def test_create_memory_with_parent(self):
        store = MemoryStore()

        with patch.object(store, "_generate_embedding", return_value=[0.1] * 1024):
            with patch("src.services.core.memory_store.db") as mock_db:
                mock_db.fetchrow = AsyncMock(
                    return_value={
                        "id": "mem_002",
                        "container_tag": "user_001",
                        "content": "Updated content",
                        "embedding": None,
                        "is_static": False,
                        "is_latest": True,
                        "valid_from": None,
                        "valid_until": None,
                        "metadata": {
                            "relations": {
                                "updates": ["mem_001"],
                                "extends": [],
                                "derives": [],
                            }
                        },
                        "confidence": 0.8,
                        "created_at": None,
                        "is_forgotten": False,
                        "version": 2,
                        "root_memory_id": "mem_001",
                        "source_count": 1,
                        "is_inference": False,
                    }
                )
                mock_db.execute = AsyncMock(return_value="UPDATE 1")

                store.get_by_id = AsyncMock(
                    return_value=Memory(
                        id="mem_001",
                        container_tag="user_001",
                        content="Original content",
                        version=1,
                        root_memory_id=None,
                    )
                )

                memory = await store.create(
                    content="Updated content",
                    container_tag="user_001",
                    parent_memory_id="mem_001",
                )

                assert memory.version == 2
                assert memory.root_memory_id == "mem_001"


class TestMemoryEmbeddedRelations:
    @pytest.mark.asyncio
    async def test_create_initializes_relations(self):
        store = MemoryStore()

        with patch.object(store, "_generate_embedding", return_value=[0.1] * 1024):
            with patch("src.services.core.memory_store.db") as mock_db:
                mock_db.fetchrow = AsyncMock(
                    return_value={
                        "id": "mem_001",
                        "container_tag": "user_001",
                        "content": "Test content",
                        "embedding": None,
                        "is_static": False,
                        "is_latest": True,
                        "valid_from": None,
                        "valid_until": None,
                        "metadata": {
                            "relations": {"updates": [], "extends": [], "derives": []}
                        },
                        "confidence": 0.8,
                        "created_at": None,
                        "is_forgotten": False,
                        "version": 1,
                        "root_memory_id": None,
                        "source_count": 1,
                        "is_inference": False,
                    }
                )
                mock_db.execute = AsyncMock(return_value="UPDATE 1")

                memory = await store.create(
                    content="Test content",
                    container_tag="user_001",
                )

                assert "relations" in memory.metadata
                assert memory.metadata["relations"]["updates"] == []

    @pytest.mark.asyncio
    async def test_add_relation(self):
        store = MemoryStore()

        with patch("src.services.core.memory_store.db") as mock_db:
            mock_db.fetchrow = AsyncMock(
                return_value={
                    "id": "mem_001",
                    "container_tag": "user_001",
                    "content": "Test content",
                    "embedding": None,
                    "is_static": False,
                    "is_latest": True,
                    "valid_from": None,
                    "valid_until": None,
                    "metadata": {
                        "relations": {"updates": [], "extends": [], "derives": []}
                    },
                    "confidence": 0.8,
                    "created_at": None,
                    "is_forgotten": False,
                    "version": 1,
                    "root_memory_id": None,
                    "source_count": 1,
                    "is_inference": False,
                }
            )
            mock_db.execute = AsyncMock(return_value="UPDATE 1")

            result = await store.add_relation(
                memory_id="mem_001",
                target_id="mem_002",
                relation_type="updates",
            )

            assert result is True

    @pytest.mark.asyncio
    async def test_get_relations(self):
        store = MemoryStore()

        with patch.object(store, "get_by_id") as mock_get:
            mock_get.return_value = Memory(
                id="mem_001",
                container_tag="user_001",
                content="Test content",
                metadata={
                    "relations": {
                        "updates": ["mem_002"],
                        "extends": ["mem_003"],
                        "derives": [],
                    }
                },
            )

            relations = await store.get_relations("mem_001")

            assert "updates" in relations
            assert "mem_002" in relations["updates"]
            assert "mem_003" in relations["extends"]


class TestMemoryDataclass:
    def test_memory_creation(self):
        memory = Memory(
            id="mem_001",
            container_tag="user_001",
            content="Test content",
            version=2,
            root_memory_id="mem_000",
        )

        assert memory.id == "mem_001"
        assert memory.version == 2
        assert memory.root_memory_id == "mem_000"

    def test_memory_defaults(self):
        memory = Memory(
            id="mem_001",
            container_tag="user_001",
            content="Test content",
        )

        assert memory.version == 1
        assert memory.root_memory_id is None
        assert memory.is_latest is True
        assert memory.is_forgotten is False
        assert memory.source_count == 1
        assert memory.is_inference is False


class TestLLMExtractionIntegration:
    @pytest.mark.asyncio
    async def test_create_with_llm_extraction(self):
        store = MemoryStore()

        with patch.object(store, "_generate_embedding", return_value=[0.1] * 1024):
            with patch(
                "src.services.core.memory_store.llm_entity_extractor"
            ) as mock_llm:
                mock_llm.extract = AsyncMock(
                    return_value=MagicMock(
                        content="Test",
                        entities={"location": ["北京"]},
                        is_static=True,
                        confidence=0.9,
                    )
                )

                with patch("src.services.core.memory_store.db") as mock_db:
                    mock_db.fetchrow = AsyncMock(
                        return_value={
                            "id": "mem_001",
                            "container_tag": "user_001",
                            "content": "我在北京工作",
                            "embedding": None,
                            "is_static": True,
                            "is_latest": True,
                            "valid_from": None,
                            "valid_until": None,
                            "metadata": {
                                "entities": {"location": ["北京"]},
                                "relations": {
                                    "updates": [],
                                    "extends": [],
                                    "derives": [],
                                },
                            },
                            "confidence": 0.9,
                            "created_at": None,
                            "is_forgotten": False,
                            "version": 1,
                            "root_memory_id": None,
                            "source_count": 1,
                            "is_inference": False,
                        }
                    )
                    mock_db.execute = AsyncMock(return_value="UPDATE 1")

                    memory = await store.create(
                        content="我在北京工作",
                        container_tag="user_001",
                        use_llm_extraction=True,
                    )

                    mock_llm.extract.assert_called_once()
