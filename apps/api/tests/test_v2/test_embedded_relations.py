import pytest
import sys
import os
from unittest.mock import AsyncMock, patch

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

from src.services.core.memory_store import MemoryStore, Memory


class TestEmbeddedRelations:
    def setup_method(self):
        self.store = MemoryStore()

    @pytest.mark.asyncio
    async def test_get_relations(self):
        with patch("src.services.core.memory_store.db") as mock_db:
            mock_db.fetchrow = AsyncMock(
                return_value={
                    "id": "mem_test123",
                    "container_tag": "user_001",
                    "content": "Test content",
                    "embedding": None,
                    "is_static": False,
                    "is_latest": True,
                    "valid_from": None,
                    "valid_until": None,
                    "metadata": {
                        "relations": {
                            "updates": ["mem_old1"],
                            "extends": ["mem_ext1"],
                            "derives": [],
                        }
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

            relations = await self.store.get_relations("mem_test123")

            assert relations["updates"] == ["mem_old1"]
            assert relations["extends"] == ["mem_ext1"]
            assert relations["derives"] == []

    @pytest.mark.asyncio
    async def test_get_relations_empty(self):
        with patch("src.services.core.memory_store.db") as mock_db:
            mock_db.fetchrow = AsyncMock(return_value=None)

            relations = await self.store.get_relations("mem_notfound")

            assert relations == {"updates": [], "extends": [], "derives": []}

    @pytest.mark.asyncio
    async def test_add_relation(self):
        with patch("src.services.core.memory_store.db") as mock_db:
            mock_db.fetchrow = AsyncMock(
                return_value={
                    "id": "mem_test123",
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

            result = await self.store.add_relation(
                memory_id="mem_test123",
                target_id="mem_target",
                relation_type="updates",
            )

            assert result is True

    @pytest.mark.asyncio
    async def test_remove_relation(self):
        with patch("src.services.core.memory_store.db") as mock_db:
            mock_db.fetchrow = AsyncMock(
                return_value={
                    "id": "mem_test123",
                    "container_tag": "user_001",
                    "content": "Test content",
                    "embedding": None,
                    "is_static": False,
                    "is_latest": True,
                    "valid_from": None,
                    "valid_until": None,
                    "metadata": {
                        "relations": {
                            "updates": ["mem_target"],
                            "extends": [],
                            "derives": [],
                        }
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

            result = await self.store.remove_relation(
                memory_id="mem_test123",
                target_id="mem_target",
                relation_type="updates",
            )

            assert result is True

    @pytest.mark.asyncio
    async def test_update_embedded_relations(self):
        from src.services.core.relation_service import MemoryRelation
        from datetime import datetime

        with patch("src.services.core.memory_store.db") as mock_db:
            mock_db.fetchrow = AsyncMock(
                return_value={
                    "id": "mem_test123",
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

            relations = [
                MemoryRelation(
                    id="rel_1",
                    from_memory_id="mem_test123",
                    to_memory_id="mem_target",
                    relation_type="updates",
                    confidence=0.9,
                    created_at=datetime.now(),
                )
            ]

            await self.store._update_embedded_relations("mem_test123", relations)

    def test_memory_dataclass_has_relations_in_metadata(self):
        memory = Memory(
            id="mem_test",
            container_tag="user_001",
            content="Test",
            metadata={
                "relations": {
                    "updates": ["mem_old"],
                    "extends": [],
                    "derives": [],
                }
            },
        )
        assert "relations" in memory.metadata
        assert memory.metadata["relations"]["updates"] == ["mem_old"]
