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
                        auto_relations=False,
                        entity_context="",
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
                            "embedding": None,
                        },
                        {
                            "id": "mem_test2",
                            "content": "Test content 2",
                            "metadata": {},
                            "confidence": 0.7,
                            "created_at": None,
                            "similarity": 0.8,
                            "embedding": None,
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
                    {
                        "id": "mem_1",
                        "container_tag": "user_001",
                        "content": "旧记忆",
                        "metadata": {"relations": {"updates": ["mem_2"]}},
                        "is_static": True,
                        "created_at": None,
                        "embedding": None,
                        "is_latest": True,
                        "valid_from": None,
                        "valid_until": None,
                        "confidence": 0.8,
                        "is_forgotten": False,
                        "version": 1,
                        "root_memory_id": None,
                        "source_count": 1,
                        "is_inference": False,
                    },
                    {
                        "id": "mem_2",
                        "container_tag": "user_001",
                        "content": "新记忆",
                        "metadata": {"relations": {}},
                        "is_static": True,
                        "created_at": None,
                        "embedding": None,
                        "is_latest": True,
                        "valid_from": None,
                        "valid_until": None,
                        "confidence": 0.8,
                        "is_forgotten": False,
                        "version": 1,
                        "root_memory_id": None,
                        "source_count": 1,
                        "is_inference": False,
                    },
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
                    {
                        "id": "mem_1",
                        "container_tag": "user_001",
                        "content": "记忆1",
                        "metadata": {"relations": {"updates": ["mem_2"]}},
                        "is_static": True,
                        "created_at": None,
                        "embedding": None,
                        "is_latest": True,
                        "valid_from": None,
                        "valid_until": None,
                        "confidence": 0.8,
                        "is_forgotten": False,
                        "version": 1,
                        "root_memory_id": None,
                        "source_count": 1,
                        "is_inference": False,
                    },
                    {
                        "id": "mem_2",
                        "container_tag": "user_001",
                        "content": "记忆2",
                        "metadata": {"relations": {"extends": ["mem_3"]}},
                        "is_static": True,
                        "created_at": None,
                        "embedding": None,
                        "is_latest": True,
                        "valid_from": None,
                        "valid_until": None,
                        "confidence": 0.8,
                        "is_forgotten": False,
                        "version": 1,
                        "root_memory_id": None,
                        "source_count": 1,
                        "is_inference": False,
                    },
                    {
                        "id": "mem_3",
                        "container_tag": "user_001",
                        "content": "记忆3",
                        "metadata": {"relations": {}},
                        "is_static": True,
                        "created_at": None,
                        "embedding": None,
                        "is_latest": True,
                        "valid_from": None,
                        "valid_until": None,
                        "confidence": 0.8,
                        "is_forgotten": False,
                        "version": 1,
                        "root_memory_id": None,
                        "source_count": 1,
                        "is_inference": False,
                    },
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
                    {
                        "id": "mem_1",
                        "container_tag": "user_001",
                        "content": "记忆1",
                        "metadata": {"relations": {"updates": ["mem_2"]}},
                        "is_static": True,
                        "created_at": None,
                        "embedding": None,
                        "is_latest": True,
                        "valid_from": None,
                        "valid_until": None,
                        "confidence": 0.8,
                        "is_forgotten": False,
                        "version": 1,
                        "root_memory_id": None,
                        "source_count": 1,
                        "is_inference": False,
                    },
                    {
                        "id": "mem_2",
                        "container_tag": "user_001",
                        "content": "记忆2",
                        "metadata": {"relations": {"extends": ["mem_3"]}},
                        "is_static": True,
                        "created_at": None,
                        "embedding": None,
                        "is_latest": True,
                        "valid_from": None,
                        "valid_until": None,
                        "confidence": 0.8,
                        "is_forgotten": False,
                        "version": 1,
                        "root_memory_id": None,
                        "source_count": 1,
                        "is_inference": False,
                    },
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
                    {
                        "id": "mem_1",
                        "container_tag": "user_001",
                        "content": "记忆1",
                        "metadata": {"relations": {"updates": ["mem_2", "mem_3"]}},
                        "is_static": True,
                        "created_at": None,
                        "embedding": None,
                        "is_latest": True,
                        "valid_from": None,
                        "valid_until": None,
                        "confidence": 0.8,
                        "is_forgotten": False,
                        "version": 1,
                        "root_memory_id": None,
                        "source_count": 1,
                        "is_inference": False,
                    },
                    {
                        "id": "mem_2",
                        "container_tag": "user_001",
                        "content": "记忆2",
                        "metadata": {"relations": {}},
                        "is_static": True,
                        "created_at": None,
                        "embedding": None,
                        "is_latest": True,
                        "valid_from": None,
                        "valid_until": None,
                        "confidence": 0.8,
                        "is_forgotten": False,
                        "version": 1,
                        "root_memory_id": None,
                        "source_count": 1,
                        "is_inference": False,
                    },
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
                    {
                        "id": "mem_1",
                        "container_tag": "user_001",
                        "content": "记忆1",
                        "metadata": {
                            "relations": {
                                "updates": ["mem_2"],
                                "extends": ["mem_3"],
                            }
                        },
                        "is_static": True,
                        "created_at": None,
                        "embedding": None,
                        "is_latest": True,
                        "valid_from": None,
                        "valid_until": None,
                        "confidence": 0.8,
                        "is_forgotten": False,
                        "version": 1,
                        "root_memory_id": None,
                        "source_count": 1,
                        "is_inference": False,
                    },
                    {
                        "id": "mem_2",
                        "container_tag": "user_001",
                        "content": "记忆2",
                        "metadata": {"relations": {}},
                        "is_static": True,
                        "created_at": None,
                        "embedding": None,
                        "is_latest": True,
                        "valid_from": None,
                        "valid_until": None,
                        "confidence": 0.8,
                        "is_forgotten": False,
                        "version": 1,
                        "root_memory_id": None,
                        "source_count": 1,
                        "is_inference": False,
                    },
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
                    {
                        "id": "mem_1",
                        "container_tag": "user_001",
                        "content": "记忆1",
                        "metadata": {"relations": {"updates": ["mem_2"]}},
                        "is_static": True,
                        "created_at": None,
                        "embedding": None,
                        "is_latest": True,
                        "valid_from": None,
                        "valid_until": None,
                        "confidence": 0.8,
                        "is_forgotten": False,
                        "version": 1,
                        "root_memory_id": None,
                        "source_count": 1,
                        "is_inference": False,
                    },
                    {
                        "id": "mem_2",
                        "container_tag": "user_001",
                        "content": "记忆2",
                        "metadata": {"relations": {"updates": ["mem_1"]}},
                        "is_static": True,
                        "created_at": None,
                        "embedding": None,
                        "is_latest": True,
                        "valid_from": None,
                        "valid_until": None,
                        "confidence": 0.8,
                        "is_forgotten": False,
                        "version": 1,
                        "root_memory_id": None,
                        "source_count": 1,
                        "is_inference": False,
                    },
                ]
            )

            results = await self.store.traverse_memory_relations("mem_1", max_depth=5)

            assert len(results) == 2

    @pytest.mark.asyncio
    async def test_traverse_excludes_forgotten_memories(self):
        """测试 Memory Graph 召回时排除 forgotten 的记忆"""
        with patch("src.services.core.memory_store.db") as mock_db:
            mock_db.fetchrow = AsyncMock(
                side_effect=[
                    {
                        "id": "mem_1",
                        "container_tag": "user_001",
                        "content": "旧记忆",
                        "metadata": {"relations": {"updates": ["mem_2"]}},
                        "is_static": True,
                        "created_at": None,
                        "embedding": None,
                        "is_latest": True,
                        "valid_from": None,
                        "valid_until": None,
                        "confidence": 0.8,
                        "is_forgotten": False,
                        "version": 1,
                        "root_memory_id": None,
                        "source_count": 1,
                        "is_inference": False,
                    },
                    None,  # mem_2 是 forgotten，get_by_id 返回 None
                ]
            )

            results = await self.store.traverse_memory_relations("mem_1", max_depth=1)

            assert len(results) == 1
            assert results[0].id == "mem_1"

    @pytest.mark.asyncio
    async def test_get_by_id_excludes_forgotten_by_default(self):
        """测试 get_by_id 默认排除 forgotten 记忆"""
        with patch("src.services.core.memory_store.db") as mock_db:
            mock_db.fetchrow = AsyncMock(
                return_value={
                    "id": "mem_1",
                    "container_tag": "user_001",
                    "content": "正常记忆",
                    "metadata": {},
                    "is_static": True,
                    "created_at": None,
                    "embedding": None,
                    "is_latest": True,
                    "valid_from": None,
                    "valid_until": None,
                    "confidence": 0.8,
                    "is_forgotten": False,
                    "version": 1,
                    "root_memory_id": None,
                    "source_count": 1,
                    "is_inference": False,
                }
            )

            result = await self.store.get_by_id("mem_1")
            assert result is not None
            assert result.id == "mem_1"

            call_args = mock_db.fetchrow.call_args
            query = call_args[0][0]
            assert "is_forgotten = FALSE" in query

    @pytest.mark.asyncio
    async def test_get_by_id_includes_forgotten_when_requested(self):
        """测试 get_by_id 在 include_forgotten=True 时包含 forgotten 记忆"""
        with patch("src.services.core.memory_store.db") as mock_db:
            mock_db.fetchrow = AsyncMock(
                return_value={
                    "id": "mem_1",
                    "container_tag": "user_001",
                    "content": "已遗忘的记忆",
                    "metadata": {},
                    "is_static": True,
                    "created_at": None,
                    "embedding": None,
                    "is_latest": True,
                    "valid_from": None,
                    "valid_until": None,
                    "confidence": 0.8,
                    "is_forgotten": True,
                    "version": 1,
                    "root_memory_id": None,
                    "source_count": 1,
                    "is_inference": False,
                }
            )

            result = await self.store.get_by_id("mem_1", include_forgotten=True)
            assert result is not None
            assert result.id == "mem_1"

            call_args = mock_db.fetchrow.call_args
            query = call_args[0][0]
            assert "is_forgotten" not in query


class TestTraverseEntityRelations:
    """测试 traverse_entity_relations() 方法"""

    def setup_method(self):
        self.store = MemoryStore()

    @pytest.mark.asyncio
    async def test_traverse_entity_relations_single_hop(self):
        """测试实体关系单跳遍历"""
        entity_id = "00000000-0000-0000-0000-000000000001"

        with patch("src.services.core.memory_store.db") as mock_db:
            mock_db.fetchrow = AsyncMock(
                return_value={
                    "id": entity_id,
                    "name": "张三",
                    "type": "person",
                    "container_tag": "user_001",
                    "mention_count": 1,
                    "confidence": 0.9,
                    "created_at": None,
                    "updated_at": None,
                }
            )
            mock_db.fetch = AsyncMock(return_value=[])

            results = await self.store.traverse_entity_relations(entity_id)

            assert len(results) == 1
            assert results[0].name == "张三"

    @pytest.mark.asyncio
    async def test_traverse_entity_relations_multi_hop(self):
        """测试实体关系多跳遍历"""
        entity_id_1 = "00000000-0000-0000-0000-000000000001"
        entity_id_2 = "00000000-0000-0000-0000-000000000002"

        with patch("src.services.core.memory_store.db") as mock_db:
            mock_db.fetchrow = AsyncMock(
                side_effect=[
                    {
                        "id": entity_id_1,
                        "name": "张三",
                        "type": "person",
                        "container_tag": "user_001",
                        "mention_count": 1,
                        "confidence": 0.9,
                        "created_at": None,
                        "updated_at": None,
                    },
                    {
                        "id": entity_id_2,
                        "name": "字节跳动",
                        "type": "organization",
                        "container_tag": "user_001",
                        "mention_count": 1,
                        "confidence": 0.8,
                        "created_at": None,
                        "updated_at": None,
                    },
                ]
            )
            mock_db.fetch = AsyncMock(
                side_effect=[
                    [{"entity_id": entity_id_2}],
                    [],
                    [],
                    [],
                ]
            )

            results = await self.store.traverse_entity_relations(
                entity_id_1, max_depth=2
            )

            assert len(results) == 2

    @pytest.mark.asyncio
    async def test_traverse_entity_relations_depth_limit(self):
        """测试实体关系遍历深度限制"""
        entity_id = "00000000-0000-0000-0000-000000000001"

        with patch("src.services.core.memory_store.db") as mock_db:
            mock_db.fetchrow = AsyncMock(
                return_value={
                    "id": entity_id,
                    "name": "张三",
                    "type": "person",
                    "container_tag": "user_001",
                    "mention_count": 1,
                    "confidence": 0.9,
                    "created_at": None,
                    "updated_at": None,
                }
            )
            mock_db.fetch = AsyncMock(return_value=[])

            results = await self.store.traverse_entity_relations(entity_id, max_depth=1)

            assert len(results) == 1

    @pytest.mark.asyncio
    async def test_traverse_entity_relations_type_filter(self):
        """测试实体关系类型过滤"""
        entity_id = "00000000-0000-0000-0000-000000000001"

        with patch("src.services.core.memory_store.db") as mock_db:
            mock_db.fetchrow = AsyncMock(
                return_value={
                    "id": entity_id,
                    "name": "张三",
                    "type": "person",
                    "container_tag": "user_001",
                    "mention_count": 1,
                    "confidence": 0.9,
                    "created_at": None,
                    "updated_at": None,
                }
            )
            mock_db.fetch = AsyncMock(return_value=[])

            results = await self.store.traverse_entity_relations(
                entity_id, relation_types=["works_at", "friend"]
            )

            assert len(results) == 1


class TestGetEntitiesForMemories:
    """测试 get_entities_for_memories() 方法"""

    def setup_method(self):
        self.store = MemoryStore()

    @pytest.mark.asyncio
    async def test_get_entities_for_memories_empty_list(self):
        """测试空记忆列表"""
        results = await self.store.get_entities_for_memories([])
        assert results == []

    @pytest.mark.asyncio
    async def test_get_entities_for_memories_single_memory(self):
        """测试单个记忆的实体获取"""
        entity_id = "00000000-0000-0000-0000-000000000001"

        with patch("src.services.core.memory_store.db") as mock_db:
            mock_db.fetch = AsyncMock(
                return_value=[
                    {
                        "id": entity_id,
                        "name": "张三",
                        "type": "person",
                        "container_tag": "user_001",
                        "mention_count": 2,
                        "confidence": 0.9,
                        "created_at": None,
                        "updated_at": None,
                    }
                ]
            )

            results = await self.store.get_entities_for_memories(["mem_1"])

            assert len(results) == 1
            assert results[0].name == "张三"
            assert results[0].type == "person"

    @pytest.mark.asyncio
    async def test_get_entities_for_memories_multiple_memories(self):
        """测试多个记忆的实体获取"""
        with patch("src.services.core.memory_store.db") as mock_db:
            mock_db.fetch = AsyncMock(
                return_value=[
                    {
                        "id": "00000000-0000-0000-0000-000000000001",
                        "name": "张三",
                        "type": "person",
                        "container_tag": "user_001",
                        "mention_count": 2,
                        "confidence": 0.9,
                        "created_at": None,
                        "updated_at": None,
                    },
                    {
                        "id": "00000000-0000-0000-0000-000000000002",
                        "name": "北京",
                        "type": "location",
                        "container_tag": "user_001",
                        "mention_count": 1,
                        "confidence": 0.8,
                        "created_at": None,
                        "updated_at": None,
                    },
                ]
            )

            results = await self.store.get_entities_for_memories(["mem_1", "mem_2"])

            assert len(results) == 2


class TestFindMemoriesByEntities:
    """测试 find_memories_by_entities() 方法"""

    def setup_method(self):
        self.store = MemoryStore()

    @pytest.mark.asyncio
    async def test_find_memories_by_entities_empty_list(self):
        """测试空实体列表"""
        results = await self.store.find_memories_by_entities([], "user_001")
        assert results == []

    @pytest.mark.asyncio
    async def test_find_memories_by_entities_single_entity(self):
        """测试单个实体的记忆查找"""
        entity_id = "00000000-0000-0000-0000-000000000001"

        with patch("src.services.core.memory_store.db") as mock_db:
            mock_db.fetch = AsyncMock(
                return_value=[
                    {
                        "id": "mem_1",
                        "container_tag": "user_001",
                        "content": "张三在北京工作",
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
                ]
            )

            results = await self.store.find_memories_by_entities(
                [entity_id], "user_001"
            )

            assert len(results) == 1
            assert "张三" in results[0].content

    @pytest.mark.asyncio
    async def test_find_memories_by_entities_multiple_entities(self):
        """测试多个实体的记忆查找"""
        entity_id_1 = "00000000-0000-0000-0000-000000000001"
        entity_id_2 = "00000000-0000-0000-0000-000000000002"

        with patch("src.services.core.memory_store.db") as mock_db:
            mock_db.fetch = AsyncMock(
                return_value=[
                    {
                        "id": "mem_1",
                        "container_tag": "user_001",
                        "content": "张三在字节跳动工作",
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
                ]
            )

            results = await self.store.find_memories_by_entities(
                [entity_id_1, entity_id_2], "user_001"
            )

            assert len(results) == 1

    @pytest.mark.asyncio
    async def test_find_memories_by_entities_limit(self):
        """测试记忆数量限制"""
        entity_id = "00000000-0000-0000-0000-000000000001"

        with patch("src.services.core.memory_store.db") as mock_db:
            mock_db.fetch = AsyncMock(
                return_value=[
                    {
                        "id": f"mem_{i}",
                        "container_tag": "user_001",
                        "content": f"记忆{i}",
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
                    for i in range(3)
                ]
            )

            results = await self.store.find_memories_by_entities(
                [entity_id], "user_001", limit=3
            )

            assert len(results) == 3

    @pytest.mark.asyncio
    async def test_find_memories_by_entities_container_isolation(self):
        """测试容器隔离"""
        entity_id = "00000000-0000-0000-0000-000000000001"

        with patch("src.services.core.memory_store.db") as mock_db:
            mock_db.fetch = AsyncMock(return_value=[])

            results = await self.store.find_memories_by_entities(
                [entity_id], "user_002"
            )

    @pytest.mark.asyncio
    async def test_find_memories_by_entities_container_isolation(self):
        """测试容器隔离"""
        entity_id = "00000000-0000-0000-0000-000000000001"

        with patch("src.services.core.memory_store.db") as mock_db:
            mock_db.fetch = AsyncMock(return_value=[])

            results = await self.store.find_memories_by_entities(
                [entity_id], "user_002"
            )

            assert results == []
            call_args = mock_db.fetch.call_args
            assert "user_002" in str(call_args)

    @pytest.mark.asyncio
    async def test_create_update_version_strips_capture_flag(self):
        """显式修订（update）不应继承 _capture 标记，避免异步处理时被 capture 低阈值
        去重（0.80）物理删除新版本导致版本链断裂（2026-08-18 观测：4 条 update 中
        2 条新版本被 capture-dedup DELETE，旧版 is_latest=false 成死链）。"""
        old_memory = Memory(
            id="mem_old_capture",
            container_tag="user_001",
            content="旧内容",
            is_static=True,
            is_latest=True,
            metadata={"_capture": True, "_status": "processing", "type": "learned-pattern"},
        )
        new_memory = Memory(
            id="mem_new_version",
            container_tag="user_001",
            content="新内容（修订）",
            is_static=True,
            is_latest=True,
            metadata={"_status": "completed", "type": "learned-pattern"},
        )

        with patch.object(
            self.store, "get_by_id", new_callable=AsyncMock, return_value=old_memory
        ) as mock_get:
            with patch.object(
                self.store, "create", new_callable=AsyncMock, return_value=new_memory
            ) as mock_create:
                with patch.object(
                    self.store, "add_relation", new_callable=AsyncMock
                ) as mock_relation:
                    with patch(
                        "src.services.core.memory_store.db"
                    ) as mock_db:
                        mock_db.execute = AsyncMock(return_value=None)

                        result = await self.store.create_update_version(
                            memory_id="mem_old_capture",
                            new_content="新内容（修订）",
                        )

                        assert result.id == "mem_new_version"
                        # create 收到的 metadata 必须剥离 _capture 和 processing 状态
                        call_kwargs = mock_create.call_args.kwargs
                        assert "_capture" not in call_kwargs["metadata"]
                        assert call_kwargs["metadata"]["_status"] == "completed"
                        assert call_kwargs["metadata"]["type"] == "learned-pattern"
                        assert mock_relation.called

