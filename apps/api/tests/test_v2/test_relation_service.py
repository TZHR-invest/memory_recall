import pytest
import sys
import os
from unittest.mock import AsyncMock, patch

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

from src.services.core.relation_service import RelationService, RelationType


class TestRelationService:
    def setup_method(self):
        self.service = RelationService()

    def test_relation_type_enum(self):
        assert RelationType.UPDATES.value == "updates"
        assert RelationType.EXTENDS.value == "extends"
        assert RelationType.DERIVES.value == "derives"

    @pytest.mark.asyncio
    async def test_create_relation(self):
        with patch("src.services.core.relation_service.db") as mock_db:
            mock_db.fetchrow = AsyncMock(
                return_value={
                    "id": "rel_test123",
                    "from_memory_id": "mem_1",
                    "to_memory_id": "mem_2",
                    "relation_type": "updates",
                    "confidence": 0.8,
                    "created_at": None,
                }
            )

            relation = await self.service.create(
                from_memory_id="mem_1",
                to_memory_id="mem_2",
                relation_type="updates",
            )

            assert relation.from_memory_id == "mem_1"
            assert relation.to_memory_id == "mem_2"
            assert relation.relation_type == "updates"

    @pytest.mark.asyncio
    async def test_create_invalid_relation_type(self):
        with pytest.raises(ValueError):
            await self.service.create(
                from_memory_id="mem_1",
                to_memory_id="mem_2",
                relation_type="invalid",
            )

    @pytest.mark.asyncio
    async def test_get_by_memory(self):
        with patch("src.services.core.relation_service.db") as mock_db:
            mock_db.fetch = AsyncMock(
                return_value=[
                    {
                        "id": "rel_1",
                        "from_memory_id": "mem_1",
                        "to_memory_id": "mem_2",
                        "relation_type": "updates",
                        "confidence": 0.8,
                        "created_at": None,
                    },
                ]
            )

            relations = await self.service.get_by_memory("mem_1")

            assert len(relations) == 1
            assert relations[0].relation_type == "updates"

    @pytest.mark.asyncio
    async def test_delete_relation(self):
        with patch("src.services.core.relation_service.db") as mock_db:
            mock_db.execute = AsyncMock(return_value="DELETE 1")

            result = await self.service.delete("rel_test123")

            assert result is True
