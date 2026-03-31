import pytest
import sys
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

from src.services.core.memory_store import MemoryStore, Memory


class TestMemoryStore:
    def setup_method(self):
        self.store = MemoryStore()

    def test_memory_dataclass(self):
        memory = Memory(
            id="mem_test123",
            container_tag="user_001",
            content="Test content",
            is_static=True,
            is_latest=True,
            metadata={"key": "value"},
        )
        assert memory.id == "mem_test123"
        assert memory.container_tag == "user_001"
        assert memory.content == "Test content"
        assert memory.is_static is True
        assert memory.is_latest is True
        assert memory.metadata == {"key": "value"}

    def test_embedding_to_str(self):
        embedding = [0.1, 0.2, 0.3]
        result = self.store._embedding_to_str(embedding)
        assert result == "[0.1,0.2,0.3]"

    def test_embedding_to_str_none(self):
        result = self.store._embedding_to_str(None)
        assert result is None

    def test_parse_embedding(self):
        result = self.store._parse_embedding("[0.1,0.2,0.3]")
        assert result == [0.1, 0.2, 0.3]

    def test_parse_embedding_none(self):
        result = self.store._parse_embedding(None)
        assert result is None

    def test_parse_embedding_invalid(self):
        result = self.store._parse_embedding("invalid")
        assert result is None


class TestMemoryStoreAsync:
    def setup_method(self):
        self.store = MemoryStore()

    @pytest.mark.asyncio
    async def test_create_memory_mock(self):
        with patch.object(
            self.store, "_generate_embedding", new_callable=AsyncMock
        ) as mock_embed:
            mock_embed.return_value = [0.1] * 1024

            with patch.object(
                self.store, "_check_similar_memory", new_callable=AsyncMock
            ) as mock_check:
                mock_check.return_value = None

                with patch("src.services.core.memory_store.db") as mock_db:
                    mock_db.fetchrow = AsyncMock(
                        return_value={
                            "id": "mem_test123",
                            "container_tag": "user_001",
                            "content": "Test content",
                            "embedding": "[0.1,0.2]",
                            "is_static": True,
                            "is_latest": True,
                            "valid_from": None,
                            "valid_until": None,
                            "metadata": {},
                            "confidence": 0.8,
                            "created_at": None,
                            "is_forgotten": False,
                        }
                    )

                    memory = await self.store.create(
                        content="Test content",
                        container_tag="user_001",
                        is_static=True,
                    )

                    assert memory.id == "mem_test123"
                    assert memory.container_tag == "user_001"
                    assert memory.content == "Test content"
                    assert memory.is_static is True

    @pytest.mark.asyncio
    async def test_get_by_id_mock(self):
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
                    "metadata": {},
                    "confidence": 0.8,
                    "created_at": None,
                    "is_forgotten": False,
                }
            )

            memory = await self.store.get_by_id("mem_test123")

            assert memory is not None
            assert memory.id == "mem_test123"

    @pytest.mark.asyncio
    async def test_get_by_id_not_found(self):
        with patch("src.services.core.memory_store.db") as mock_db:
            mock_db.fetchrow = AsyncMock(return_value=None)

            memory = await self.store.get_by_id("mem_notfound")

            assert memory is None

    @pytest.mark.asyncio
    async def test_forget_memory(self):
        with patch("src.services.core.memory_store.db") as mock_db:
            mock_db.execute = AsyncMock(return_value="UPDATE 1")

            result = await self.store.forget("mem_test123")

            assert result is True

    @pytest.mark.asyncio
    async def test_restore_memory(self):
        with patch("src.services.core.memory_store.db") as mock_db:
            mock_db.execute = AsyncMock(return_value="UPDATE 1")

            result = await self.store.restore("mem_test123")

            assert result is True

    @pytest.mark.asyncio
    async def test_search_memories(self):
        with patch.object(
            self.store, "_generate_embedding", new_callable=AsyncMock
        ) as mock_embed:
            mock_embed.return_value = [0.1] * 1024

            with patch("src.services.core.memory_store.db") as mock_db:
                mock_db.fetch = AsyncMock(
                    return_value=[
                        {
                            "id": "mem_test1",
                            "content": "Test content 1",
                            "metadata": {},
                            "confidence": 0.8,
                            "created_at": None,
                            "similarity": 0.9,
                        },
                        {
                            "id": "mem_test2",
                            "content": "Test content 2",
                            "metadata": {},
                            "confidence": 0.7,
                            "created_at": None,
                            "similarity": 0.8,
                        },
                    ]
                )

                results = await self.store.search(
                    query="test query",
                    container_tag="user_001",
                    limit=10,
                    threshold=0.6,
                )

                assert len(results) == 2
                assert results[0]["id"] == "mem_test1"
                assert results[0]["similarity"] == 0.9
