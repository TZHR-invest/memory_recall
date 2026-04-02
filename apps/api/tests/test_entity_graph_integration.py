"""
Entity Graph 集成测试

测试完整的实体图谱创建流程
"""

import pytest
import sys
import os
from unittest.mock import AsyncMock, MagicMock, patch
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.services.core.memory_store import MemoryStore


class TestEntityGraphIntegration:
    """Entity Graph 集成测试"""

    def setup_method(self):
        self.store = MemoryStore()

    @pytest.mark.asyncio
    async def test_create_memory_with_entity_and_relations(self):
        """测试创建包含实体和关系的记忆"""
        with patch("src.services.core.memory_store.db") as mock_db:
            with patch.object(
                self.store, "_generate_embedding", new_callable=AsyncMock
            ) as mock_embed:
                mock_embed.return_value = [0.1] * 1024

                mock_db.fetchrow = AsyncMock(
                    side_effect=[
                        MagicMock(
                            id="mem_test123",
                            container_tag="user_001",
                            content="我在字节跳动工作，同事张三也在那",
                            metadata=json.dumps(
                                {
                                    "entities": {
                                        "organization": ["字节跳动"],
                                        "person": ["张三"],
                                    }
                                }
                            ),
                            is_static=True,
                            created_at=None,
                        ),
                        None,
                        MagicMock(id="entity_1"),
                        None,
                        MagicMock(id="entity_2"),
                        None,
                    ]
                )
                mock_db.execute = AsyncMock()
                mock_db.fetch = AsyncMock(return_value=[])

                with patch(
                    "src.services.core.memory_store.relation_service"
                ) as mock_rel:
                    mock_rel.auto_create_relations = AsyncMock(return_value=[])

                    with patch(
                        "src.services.core.memory_store.llm_entity_extractor"
                    ) as mock_extractor:
                        mock_extractor.extract_with_relations = AsyncMock(
                            return_value={
                                "entities": [
                                    {"name": "字节跳动", "type": "organization"},
                                    {"name": "张三", "type": "person"},
                                ],
                                "relations": [
                                    {
                                        "from": "我",
                                        "to": "字节跳动",
                                        "type": "works_at",
                                        "confidence": 0.9,
                                    },
                                    {
                                        "from": "张三",
                                        "to": "字节跳动",
                                        "type": "works_at",
                                        "confidence": 0.85,
                                    },
                                ],
                                "confidence": 0.8,
                            }
                        )

                        memory = await self.store.create(
                            content="我在字节跳动工作，同事张三也在那",
                            container_tag="user_001",
                            extract_entities=True,
                            extract_relations=True,
                            use_llm_extraction=True,
                        )

                        assert memory is not None

    @pytest.mark.asyncio
    async def test_create_memory_entities_table_populated(self):
        """测试 entities 表正确填充"""
        with patch("src.services.core.memory_store.db") as mock_db:
            with patch.object(
                self.store, "_generate_embedding", new_callable=AsyncMock
            ) as mock_embed:
                mock_embed.return_value = [0.1] * 1024

                entity_insert_calls = []

                def track_insert(*args, **kwargs):
                    if "INSERT INTO entities" in str(args[0]) if args else "":
                        entity_insert_calls.append(args)
                    return MagicMock(id="entity_test")

                mock_db.fetchrow = AsyncMock(
                    side_effect=[
                        MagicMock(
                            id="mem_test123",
                            container_tag="user_001",
                            content="测试内容",
                            metadata=json.dumps({}),
                            is_static=True,
                            created_at=None,
                        ),
                        None,
                        track_insert(None, MagicMock(id="entity_1")),
                        None,
                        track_insert(None, MagicMock(id="entity_2")),
                        None,
                    ]
                )
                mock_db.execute = AsyncMock(side_effect=track_insert)
                mock_db.fetch = AsyncMock(return_value=[])

                with patch("src.services.core.memory_store.relation_service"):
                    with patch(
                        "src.services.core.memory_store.llm_entity_extractor"
                    ) as mock_extractor:
                        mock_extractor.extract_with_relations = AsyncMock(
                            return_value={
                                "entities": [
                                    {"name": "张三", "type": "person"},
                                    {"name": "北京", "type": "location"},
                                ],
                                "relations": [],
                                "confidence": 0.8,
                            }
                        )

                        await self.store.create(
                            content="张三在北京",
                            container_tag="user_001",
                            extract_entities=True,
                            extract_relations=True,
                            use_llm_extraction=True,
                        )

    @pytest.mark.asyncio
    async def test_create_memory_relations_table_populated(self):
        """测试 entity_relations 表正确填充"""
        with patch("src.services.core.memory_store.db") as mock_db:
            with patch.object(
                self.store, "_generate_embedding", new_callable=AsyncMock
            ) as mock_embed:
                mock_embed.return_value = [0.1] * 1024

                relation_insert_calls = []

                def track_insert(*args, **kwargs):
                    if "entity_relations" in str(args[0]) if args else "":
                        relation_insert_calls.append(args)
                    return MagicMock()

                mock_db.fetchrow = AsyncMock(
                    side_effect=[
                        MagicMock(
                            id="mem_test123",
                            container_tag="user_001",
                            content="测试内容",
                            metadata=json.dumps({}),
                            is_static=True,
                            created_at=None,
                        ),
                        None,
                        MagicMock(id="entity_1"),
                        None,
                        MagicMock(id="entity_2"),
                        None,
                    ]
                )
                mock_db.execute = AsyncMock(side_effect=track_insert)
                mock_db.fetch = AsyncMock(return_value=[])

                with patch("src.services.core.memory_store.relation_service"):
                    with patch(
                        "src.services.core.memory_store.llm_entity_extractor"
                    ) as mock_extractor:
                        mock_extractor.extract_with_relations = AsyncMock(
                            return_value={
                                "entities": [
                                    {"name": "张三", "type": "person"},
                                    {"name": "字节跳动", "type": "organization"},
                                ],
                                "relations": [
                                    {
                                        "from": "张三",
                                        "to": "字节跳动",
                                        "type": "works_at",
                                        "confidence": 0.9,
                                    }
                                ],
                                "confidence": 0.8,
                            }
                        )

                        await self.store.create(
                            content="张三在字节跳动工作",
                            container_tag="user_001",
                            extract_entities=True,
                            extract_relations=True,
                            use_llm_extraction=True,
                        )
