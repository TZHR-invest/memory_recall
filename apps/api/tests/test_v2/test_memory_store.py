import pytest
import sys
import os
import json
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


class TestStoreEntityGraph:
    """测试 _store_entity_graph() 方法"""

    def setup_method(self):
        self.store = MemoryStore()

    @pytest.mark.asyncio
    async def test_store_entity_graph_creates_new_entities(self):
        """测试创建新实体"""
        with patch("src.services.core.memory_store.db") as mock_db:
            mock_db.fetchrow = AsyncMock(
                side_effect=[
                    None,
                    MagicMock(id="entity_1"),
                    None,
                    MagicMock(id="entity_2"),
                ]
            )
            mock_db.execute = AsyncMock()

            entities = [
                {"name": "张三", "type": "person"},
                {"name": "北京", "type": "location"},
            ]
            relations = []

            await self.store._store_entity_graph(
                "mem_test", entities, relations, "user_001"
            )

            assert mock_db.fetchrow.call_count == 4
            assert mock_db.execute.call_count >= 2

    @pytest.mark.asyncio
    async def test_store_entity_graph_deduplicates_entities(self):
        """测试实体去重"""
        with patch("src.services.core.memory_store.db") as mock_db:
            mock_db.fetchrow = AsyncMock(return_value=MagicMock(id="existing_entity_1"))
            mock_db.execute = AsyncMock()

            entities = [{"name": "张三", "type": "person"}]
            relations = []

            await self.store._store_entity_graph(
                "mem_test", entities, relations, "user_001"
            )

            mock_db.execute.assert_called()

    @pytest.mark.asyncio
    async def test_store_entity_graph_creates_relations(self):
        """测试创建关系"""
        with patch("src.services.core.memory_store.db") as mock_db:
            mock_db.fetchrow = AsyncMock(
                side_effect=[
                    None,
                    MagicMock(id="entity_1"),
                    None,
                    MagicMock(id="entity_2"),
                    None,
                ]
            )
            mock_db.execute = AsyncMock()

            entities = [
                {"name": "张三", "type": "person"},
                {"name": "字节跳动", "type": "organization"},
            ]
            relations = [
                {
                    "from": "张三",
                    "to": "字节跳动",
                    "type": "works_at",
                    "confidence": 0.9,
                }
            ]

            await self.store._store_entity_graph(
                "mem_test", entities, relations, "user_001"
            )

            assert mock_db.execute.call_count >= 3

    @pytest.mark.asyncio
    async def test_store_entity_graph_deduplicates_relations(self):
        """测试关系去重"""
        with patch("src.services.core.memory_store.db") as mock_db:
            mock_db.fetchrow = AsyncMock(
                side_effect=[
                    None,
                    MagicMock(id="entity_1"),
                    None,
                    MagicMock(id="entity_2"),
                    MagicMock(id="existing_relation"),
                ]
            )
            mock_db.execute = AsyncMock()

            entities = [
                {"name": "张三", "type": "person"},
                {"name": "字节跳动", "type": "organization"},
            ]
            relations = [
                {
                    "from": "张三",
                    "to": "字节跳动",
                    "type": "works_at",
                    "confidence": 0.9,
                }
            ]

            await self.store._store_entity_graph(
                "mem_test", entities, relations, "user_001"
            )

            update_calls = [
                call
                for call in mock_db.execute.call_args_list
                if "UPDATE entity_relations" in str(call)
            ]
            assert len(update_calls) > 0

    @pytest.mark.asyncio
    async def test_store_entity_graph_container_isolation(self):
        """测试 container_tag 隔离"""
        with patch("src.services.core.memory_store.db") as mock_db:
            mock_db.fetchrow = AsyncMock(
                side_effect=[
                    None,
                    MagicMock(id="entity_1_user1"),
                    None,
                    MagicMock(id="entity_1_user2"),
                ]
            )
            mock_db.execute = AsyncMock()

            entities = [{"name": "张三", "type": "person"}]
            relations = []

            await self.store._store_entity_graph(
                "mem_test1", entities, relations, "user_001"
            )

            await self.store._store_entity_graph(
                "mem_test2", entities, relations, "user_002"
            )

            assert mock_db.fetchrow.call_count == 4

    @pytest.mark.asyncio
    async def test_store_entity_graph_handles_missing_entity_in_relation(self):
        """测试关系中缺失实体的处理"""
        with patch("src.services.core.memory_store.db") as mock_db:
            mock_db.fetchrow = AsyncMock(
                side_effect=[
                    None,
                    MagicMock(id="entity_1"),
                ]
            )
            mock_db.execute = AsyncMock()

            entities = [{"name": "张三", "type": "person"}]
            relations = [
                {
                    "from": "张三",
                    "to": "李四",
                    "type": "friend",
                    "confidence": 0.9,
                }
            ]

            await self.store._store_entity_graph(
                "mem_test", entities, relations, "user_001"
            )

    @pytest.mark.asyncio
    async def test_store_entity_graph_creates_memory_entity_links(self):
        """测试创建记忆-实体关联"""
        with patch("src.services.core.memory_store.db") as mock_db:
            mock_db.fetchrow = AsyncMock(
                side_effect=[
                    None,
                    MagicMock(id="entity_1"),
                ]
            )
            mock_db.execute = AsyncMock()

            entities = [{"name": "张三", "type": "person"}]
            relations = []

            await self.store._store_entity_graph(
                "mem_test", entities, relations, "user_001"
            )

            link_calls = [
                call
                for call in mock_db.execute.call_args_list
                if "memory_entities" in str(call)
            ]
            assert len(link_calls) > 0


class TestTraverseMemoryRelations:
    """测试 traverse_memory_relations() 方法"""

    def setup_method(self):
        self.store = MemoryStore()

    @pytest.mark.asyncio
    async def test_traverse_single_hop(self):
        """测试单跳遍历"""
        with patch("src.services.core.memory_store.db") as mock_db:
            mock_db.fetchrow = AsyncMock(
                side_effect=[
                    MagicMock(
                        id="mem_1",
                        container_tag="user_001",
                        content="旧记忆",
                        metadata=json.dumps({"relations": {"updates": ["mem_2"]}}),
                        is_static=True,
                        created_at=None,
                    ),
                    MagicMock(
                        id="mem_2",
                        container_tag="user_001",
                        content="新记忆",
                        metadata=json.dumps({"relations": {}}),
                        is_static=True,
                        created_at=None,
                    ),
                ]
            )

            results = await self.store.traverse_memory_relations("mem_1", max_depth=1)

            assert len(results) == 2
            assert results[0].id == "mem_1"
            assert results[1].id == "mem_2"

    @pytest.mark.asyncio
    async def test_traverse_multi_hop(self):
        """测试多跳遍历"""
        with patch("src.services.core.memory_store.db") as mock_db:
            mock_db.fetchrow = AsyncMock(
                side_effect=[
                    MagicMock(
                        id="mem_1",
                        container_tag="user_001",
                        content="记忆1",
                        metadata=json.dumps({"relations": {"updates": ["mem_2"]}}),
                        is_static=True,
                        created_at=None,
                    ),
                    MagicMock(
                        id="mem_2",
                        container_tag="user_001",
                        content="记忆2",
                        metadata=json.dumps({"relations": {"extends": ["mem_3"]}}),
                        is_static=True,
                        created_at=None,
                    ),
                    MagicMock(
                        id="mem_3",
                        container_tag="user_001",
                        content="记忆3",
                        metadata=json.dumps({"relations": {}}),
                        is_static=True,
                        created_at=None,
                    ),
                ]
            )

            results = await self.store.traverse_memory_relations("mem_1", max_depth=3)

            assert len(results) == 3

    @pytest.mark.asyncio
    async def test_traverse_depth_limit(self):
        """测试深度限制"""
        with patch("src.services.core.memory_store.db") as mock_db:
            mock_db.fetchrow = AsyncMock(
                side_effect=[
                    MagicMock(
                        id="mem_1",
                        container_tag="user_001",
                        content="记忆1",
                        metadata=json.dumps({"relations": {"updates": ["mem_2"]}}),
                        is_static=True,
                        created_at=None,
                    ),
                    MagicMock(
                        id="mem_2",
                        container_tag="user_001",
                        content="记忆2",
                        metadata=json.dumps({"relations": {"extends": ["mem_3"]}}),
                        is_static=True,
                        created_at=None,
                    ),
                ]
            )

            results = await self.store.traverse_memory_relations("mem_1", max_depth=1)

            assert len(results) == 2

    @pytest.mark.asyncio
    async def test_traverse_max_nodes_limit(self):
        """测试节点数限制"""
        with patch("src.services.core.memory_store.db") as mock_db:
            mock_db.fetchrow = AsyncMock(
                side_effect=[
                    MagicMock(
                        id="mem_1",
                        container_tag="user_001",
                        content="记忆1",
                        metadata=json.dumps(
                            {"relations": {"updates": ["mem_2", "mem_3"]}}
                        ),
                        is_static=True,
                        created_at=None,
                    ),
                    MagicMock(
                        id="mem_2",
                        container_tag="user_001",
                        content="记忆2",
                        metadata=json.dumps({"relations": {}}),
                        is_static=True,
                        created_at=None,
                    ),
                ]
            )

            results = await self.store.traverse_memory_relations(
                "mem_1", max_depth=2, max_nodes=2
            )

            assert len(results) <= 2

    @pytest.mark.asyncio
    async def test_traverse_relation_type_filter(self):
        """测试关系类型过滤"""
        with patch("src.services.core.memory_store.db") as mock_db:
            mock_db.fetchrow = AsyncMock(
                side_effect=[
                    MagicMock(
                        id="mem_1",
                        container_tag="user_001",
                        content="记忆1",
                        metadata=json.dumps(
                            {
                                "relations": {
                                    "updates": ["mem_2"],
                                    "extends": ["mem_3"],
                                }
                            }
                        ),
                        is_static=True,
                        created_at=None,
                    ),
                    MagicMock(
                        id="mem_2",
                        container_tag="user_001",
                        content="记忆2",
                        metadata=json.dumps({"relations": {}}),
                        is_static=True,
                        created_at=None,
                    ),
                ]
            )

            results = await self.store.traverse_memory_relations(
                "mem_1",
                max_depth=2,
                relation_types=["updates"],
            )

            assert len(results) == 2
            assert results[1].id == "mem_2"

    @pytest.mark.asyncio
    async def test_traverse_avoids_cycles(self):
        """测试避免循环"""
        with patch("src.services.core.memory_store.db") as mock_db:
            mock_db.fetchrow = AsyncMock(
                side_effect=[
                    MagicMock(
                        id="mem_1",
                        container_tag="user_001",
                        content="记忆1",
                        metadata=json.dumps({"relations": {"updates": ["mem_2"]}}),
                        is_static=True,
                        created_at=None,
                    ),
                    MagicMock(
                        id="mem_2",
                        container_tag="user_001",
                        content="记忆2",
                        metadata=json.dumps({"relations": {"updates": ["mem_1"]}}),
                        is_static=True,
                        created_at=None,
                    ),
                ]
            )

            results = await self.store.traverse_memory_relations("mem_1", max_depth=5)

            assert len(results) == 2
