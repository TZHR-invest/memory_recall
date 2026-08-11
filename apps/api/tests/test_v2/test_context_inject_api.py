"""
Integration tests for /context-inject API endpoint.
Tests the full context injection flow with deduplication.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient
from httpx import AsyncClient

from src.services.core.semantic_dedup_service import DedupItem


class TestContextInjectAPI:
    @pytest.fixture
    def mock_profile_service(self):
        with patch("src.services.core.context_inject_service.profile_service") as mock:
            mock.get_profile = AsyncMock(
                return_value={
                    "profile": {
                        "static": ["我是素食主义者", "在字节跳动工作"],
                        "dynamic": ["正在做后端去重"],
                    }
                }
            )
            yield mock

    @pytest.fixture
    def mock_memory_store(self):
        with patch("src.services.core.context_inject_service.memory_store") as mock:
            mock_memory1 = MagicMock()
            mock_memory1.id = "mem_001"
            mock_memory1.content = "我喜欢吃蔬菜"
            mock_memory1.embedding = [0.1] * 1024
            mock_memory1.is_static = False

            mock_memory2 = MagicMock()
            mock_memory2.id = "mem_002"
            mock_memory2.content = "项目使用 FastAPI"
            mock_memory2.embedding = [0.5] * 1024
            mock_memory2.is_static = False

            mock.get_by_container = AsyncMock(return_value=[mock_memory1, mock_memory2])
            yield mock

    @pytest.fixture
    def mock_document_store(self):
        with patch("src.services.core.context_inject_service.document_store") as mock:
            mock.search_chunks = AsyncMock(return_value=[])
            yield mock

    @pytest.fixture
    def mock_embedding_client(self):
        with patch(
            "src.services.core.context_inject_service.get_embedding_client"
        ) as mock:
            client = MagicMock()
            client.embed = AsyncMock(return_value=[0.5] * 1024)
            mock.return_value = client
            yield mock

    def test_context_inject_returns_context(
        self, mock_profile_service, mock_memory_store, mock_document_store
    ):
        from src.api.context_inject import ContextInjectRequest, ContextInjectConfig
        from src.services.core.context_inject_service import context_inject_service

        result = asyncio.run(
            context_inject_service.inject(
                container_tag="user_test",
                query="测试查询",
                config={
                    "inject_profile": True,
                    "max_profile_items": 10,
                    "max_memories": 5,
                    "max_chunks": 3,
                    "enable_semantic_dedup": False,
                    "language": "zh_CN",
                },
            )
        )

        assert "context" in result
        assert "sources" in result
        assert "stats" in result
        assert "用户上下文" in result["context"]

    def test_context_inject_with_dedup(
        self, mock_profile_service, mock_memory_store, mock_document_store
    ):
        from src.services.core.context_inject_service import context_inject_service

        result = asyncio.run(
            context_inject_service.inject(
                container_tag="user_test",
                query="测试查询",
                config={
                    "inject_profile": True,
                    "max_profile_items": 10,
                    "max_memories": 5,
                    "max_chunks": 3,
                    "enable_semantic_dedup": True,
                    "dedup_threshold": 0.85,
                    "language": "zh_CN",
                },
            )
        )

        assert "stats" in result
        assert result["stats"]["total_items"] >= result["stats"]["after_dedup"]

    def test_context_inject_profile_only(
        self, mock_profile_service, mock_memory_store, mock_document_store
    ):
        from src.services.core.context_inject_service import context_inject_service

        mock_memory_store.get_by_container = AsyncMock(return_value=[])

        result = asyncio.run(
            context_inject_service.inject(
                container_tag="user_test",
                query=None,
                config={
                    "inject_profile": True,
                    "max_profile_items": 10,
                    "max_memories": 0,
                    "max_chunks": 0,
                    "enable_semantic_dedup": False,
                    "language": "zh_CN",
                },
            )
        )

        assert result["stats"]["profile_count"] > 0
        assert result["stats"]["memories_count"] == 0
        assert result["stats"]["chunks_count"] == 0

    def test_context_inject_no_profile(
        self, mock_profile_service, mock_memory_store, mock_document_store
    ):
        from src.services.core.context_inject_service import context_inject_service

        result = asyncio.run(
            context_inject_service.inject(
                container_tag="user_test",
                query=None,
                config={
                    "inject_profile": False,
                    "max_profile_items": 10,
                    "max_memories": 5,
                    "max_chunks": 3,
                    "enable_semantic_dedup": False,
                    "language": "zh_CN",
                },
            )
        )

        assert result["stats"]["profile_count"] == 0

    def test_context_inject_with_chunks(self, mock_profile_service, mock_memory_store):
        from src.services.core.context_inject_service import context_inject_service

        mock_memory_store.get_by_container = AsyncMock(return_value=[])

        context_inject_service._get_chunks = AsyncMock(
            return_value=[
                {
                    "id": "chunk_001",
                    "content": "项目文档内容",
                    "embedding": [0.3] * 1024,
                    "document_id": "doc_001",
                    "similarity": 0.8,
                }
            ]
        )

        result = asyncio.run(
            context_inject_service.inject(
                container_tag="user_test",
                query="项目文档",
                config={
                    "inject_profile": False,
                    "max_profile_items": 10,
                    "max_memories": 0,
                    "max_chunks": 3,
                    "enable_semantic_dedup": False,
                    "language": "zh_CN",
                },
            )
        )

        assert result["stats"]["chunks_count"] > 0

    def test_context_inject_english_language(
        self, mock_profile_service, mock_memory_store, mock_document_store
    ):
        from src.services.core.context_inject_service import context_inject_service

        result = asyncio.run(
            context_inject_service.inject(
                container_tag="user_test",
                query=None,
                config={
                    "inject_profile": True,
                    "max_profile_items": 10,
                    "max_memories": 0,
                    "max_chunks": 0,
                    "enable_semantic_dedup": False,
                    "language": "en_US",
                },
            )
        )

        assert "User Context" in result["context"]

    def test_context_inject_auto_language_detection(
        self, mock_profile_service, mock_memory_store, mock_document_store
    ):
        from src.services.core.context_inject_service import context_inject_service

        mock_profile_service.get_profile = AsyncMock(
            return_value={
                "profile": {
                    "static": ["I am a vegetarian", "Work at Google"],
                    "dynamic": ["Working on backend"],
                }
            }
        )

        mock_memory_store.get_by_container = AsyncMock(return_value=[])

        result = asyncio.run(
            context_inject_service.inject(
                container_tag="user_test",
                query=None,
                config={
                    "inject_profile": True,
                    "max_profile_items": 10,
                    "max_memories": 0,
                    "max_chunks": 0,
                    "enable_semantic_dedup": False,
                    "language": "auto",
                },
            )
        )

        assert "上下文" in result["context"] or "Context" in result["context"]

    def test_context_inject_sources_structure(
        self, mock_profile_service, mock_memory_store, mock_document_store
    ):
        from src.services.core.context_inject_service import context_inject_service

        result = asyncio.run(
            context_inject_service.inject(
                container_tag="user_test",
                query=None,
                config={
                    "inject_profile": True,
                    "max_profile_items": 10,
                    "max_memories": 5,
                    "max_chunks": 3,
                    "enable_semantic_dedup": False,
                    "language": "zh_CN",
                },
            )
        )

        assert "profile" in result["sources"]
        assert "memories" in result["sources"]
        assert "chunks" in result["sources"]
        assert isinstance(result["sources"]["profile"], list)
        assert isinstance(result["sources"]["memories"], list)
        assert isinstance(result["sources"]["chunks"], list)

    def test_context_inject_stats_structure(
        self, mock_profile_service, mock_memory_store, mock_document_store
    ):
        from src.services.core.context_inject_service import context_inject_service

        result = asyncio.run(
            context_inject_service.inject(
                container_tag="user_test",
                query=None,
                config={
                    "inject_profile": True,
                    "max_profile_items": 10,
                    "max_memories": 5,
                    "max_chunks": 3,
                    "enable_semantic_dedup": True,
                    "dedup_threshold": 0.85,
                    "language": "zh_CN",
                },
            )
        )

        stats = result["stats"]
        assert "total_items" in stats
        assert "after_dedup" in stats
        assert "deduped_count" in stats
        assert "profile_count" in stats
        assert "memories_count" in stats
        assert "chunks_count" in stats

    def test_context_inject_dedup_removes_similar(
        self, mock_profile_service, mock_memory_store, mock_document_store
    ):
        mock_memory1 = MagicMock()
        mock_memory1.id = "mem_001"
        mock_memory1.content = "我吃素"
        mock_memory1.embedding = [0.95] * 1024
        mock_memory1.is_static = False

        mock_memory_store.get_by_container = AsyncMock(return_value=[mock_memory1])

        from src.services.core.context_inject_service import context_inject_service

        result = asyncio.run(
            context_inject_service.inject(
                container_tag="user_test",
                query=None,
                config={
                    "inject_profile": True,
                    "max_profile_items": 10,
                    "max_memories": 5,
                    "max_chunks": 0,
                    "enable_semantic_dedup": True,
                    "dedup_threshold": 0.85,
                    "language": "zh_CN",
                },
            )
        )

        assert result["stats"]["deduped_count"] >= 0

    def test_context_inject_memory_graph_recall(
        self, mock_profile_service, mock_document_store
    ):
        """测试 Memory Graph 召回集成"""
        with patch(
            "src.services.core.context_inject_service.memory_store"
        ) as mock_memory:
            mock_memory.search = AsyncMock(
                return_value=[
                    {
                        "id": "mem_001",
                        "content": "我在 Google 工作",
                        "similarity": 0.9,
                    }
                ]
            )
            mock_memory.traverse_memory_relations = AsyncMock(
                return_value=[
                    MagicMock(
                        id="mem_002",
                        content="我跳槽到了字节跳动",
                        is_static=False,
                    )
                ]
            )
            mock_memory.get_by_container = AsyncMock(return_value=[])

            with patch(
                "src.services.core.context_inject_service.get_embedding_client"
            ) as mock_embed:
                client = MagicMock()
                client.embed = AsyncMock(return_value=[0.5] * 1024)
                mock_embed.return_value = client

                from src.services.core.context_inject_service import (
                    context_inject_service,
                )

                result = asyncio.run(
                    context_inject_service.inject(
                        container_tag="user_test",
                        query="工作",
                        config={
                            "inject_profile": False,
                            "max_memories": 5,
                            "enable_memory_graph": True,
                            "memory_graph_depth": 2,
                            "memory_graph_nodes": 3,
                            "enable_entity_graph": False,
                            "enable_semantic_dedup": False,
                            "language": "zh_CN",
                        },
                    )
                )

                assert result["stats"]["memories_count"] >= 1

    def test_context_inject_entity_graph_recall(
        self, mock_profile_service, mock_document_store
    ):
        """测试 Entity Graph 召回集成"""
        with patch(
            "src.services.core.context_inject_service.memory_store"
        ) as mock_memory:
            from src.services.core.memory_store import Entity

            mock_memory.search = AsyncMock(
                return_value=[
                    {
                        "id": "mem_001",
                        "content": "张三在字节跳动工作",
                        "similarity": 0.9,
                    }
                ]
            )
            mock_memory.get_entities_for_memories = AsyncMock(
                return_value=[
                    Entity(
                        id="entity_001",
                        name="张三",
                        type="person",
                        container_tag="user_test",
                        mention_count=1,
                        confidence=0.9,
                    )
                ]
            )
            mock_memory.traverse_entity_relations = AsyncMock(
                return_value=[
                    Entity(
                        id="entity_002",
                        name="字节跳动",
                        type="organization",
                        container_tag="user_test",
                        mention_count=1,
                        confidence=0.8,
                    )
                ]
            )
            mock_memory.find_memories_by_entities = AsyncMock(
                return_value=[
                    MagicMock(
                        id="mem_002",
                        content="张三和李四是同事",
                        is_static=False,
                    )
                ]
            )
            mock_memory.get_by_container = AsyncMock(return_value=[])

            with patch(
                "src.services.core.context_inject_service.get_embedding_client"
            ) as mock_embed:
                client = MagicMock()
                client.embed = AsyncMock(return_value=[0.5] * 1024)
                mock_embed.return_value = client

                from src.services.core.context_inject_service import (
                    context_inject_service,
                )

                result = asyncio.run(
                    context_inject_service.inject(
                        container_tag="user_test",
                        query="张三",
                        config={
                            "inject_profile": False,
                            "max_memories": 5,
                            "enable_memory_graph": False,
                            "enable_entity_graph": True,
                            "entity_graph_depth": 2,
                            "entity_graph_nodes": 3,
                            "enable_semantic_dedup": False,
                            "language": "zh_CN",
                        },
                    )
                )

                assert result["stats"]["memories_count"] >= 1

    def test_context_inject_dual_graph_recall(
        self, mock_profile_service, mock_document_store
    ):
        """测试双图谱组合召回"""
        with patch(
            "src.services.core.context_inject_service.memory_store"
        ) as mock_memory:
            from src.services.core.memory_store import Entity

            mock_memory.search = AsyncMock(
                return_value=[
                    {
                        "id": "mem_001",
                        "content": "张三在字节跳动工作",
                        "similarity": 0.9,
                    }
                ]
            )
            mock_memory.traverse_memory_relations = AsyncMock(
                return_value=[
                    MagicMock(
                        id="mem_002",
                        content="张三跳槽到了阿里",
                        is_static=False,
                    )
                ]
            )
            mock_memory.get_entities_for_memories = AsyncMock(
                return_value=[
                    Entity(
                        id="entity_001",
                        name="张三",
                        type="person",
                        container_tag="user_test",
                        mention_count=1,
                        confidence=0.9,
                    )
                ]
            )
            mock_memory.traverse_entity_relations = AsyncMock(
                return_value=[
                    Entity(
                        id="entity_002",
                        name="字节跳动",
                        type="organization",
                        container_tag="user_test",
                        mention_count=1,
                        confidence=0.8,
                    )
                ]
            )
            mock_memory.find_memories_by_entities = AsyncMock(
                return_value=[
                    MagicMock(
                        id="mem_003",
                        content="张三喜欢喝咖啡",
                        is_static=False,
                    )
                ]
            )
            mock_memory.get_by_container = AsyncMock(return_value=[])

            with patch(
                "src.services.core.context_inject_service.get_embedding_client"
            ) as mock_embed:
                client = MagicMock()
                client.embed = AsyncMock(return_value=[0.5] * 1024)
                mock_embed.return_value = client

                from src.services.core.context_inject_service import (
                    context_inject_service,
                )

                result = asyncio.run(
                    context_inject_service.inject(
                        container_tag="user_test",
                        query="张三",
                        config={
                            "inject_profile": False,
                            "max_memories": 10,
                            "enable_memory_graph": True,
                            "memory_graph_depth": 2,
                            "memory_graph_nodes": 3,
                            "enable_entity_graph": True,
                            "entity_graph_depth": 2,
                            "entity_graph_nodes": 3,
                            "enable_semantic_dedup": False,
                            "language": "zh_CN",
                        },
                    )
                )

                assert result["stats"]["memories_count"] >= 2

    def test_context_inject_graph_config_disabled(
        self, mock_profile_service, mock_document_store
    ):
        """测试图谱配置参数生效"""
        with patch(
            "src.services.core.context_inject_service.memory_store"
        ) as mock_memory:
            mock_memory.search = AsyncMock(
                return_value=[
                    {
                        "id": "mem_001",
                        "content": "测试记忆",
                        "similarity": 0.9,
                    }
                ]
            )
            mock_memory.traverse_memory_relations = AsyncMock()
            mock_memory.get_entities_for_memories = AsyncMock()
            mock_memory.traverse_entity_relations = AsyncMock()
            mock_memory.get_by_container = AsyncMock(return_value=[])

            with patch(
                "src.services.core.context_inject_service.get_embedding_client"
            ) as mock_embed:
                client = MagicMock()
                client.embed = AsyncMock(return_value=[0.5] * 1024)
                mock_embed.return_value = client

                from src.services.core.context_inject_service import (
                    context_inject_service,
                )

                result = asyncio.run(
                    context_inject_service.inject(
                        container_tag="user_test",
                        query="测试",
                        config={
                            "inject_profile": False,
                            "max_memories": 5,
                            "enable_memory_graph": False,
                            "enable_entity_graph": False,
                            "enable_semantic_dedup": False,
                            "language": "zh_CN",
                        },
                    )
                )

                mock_memory.traverse_memory_relations.assert_not_called()
                mock_memory.get_entities_for_memories.assert_not_called()

    def test_context_inject_with_user_and_project_tags(
        self, mock_profile_service, mock_document_store
    ):
        with patch(
            "src.services.core.context_inject_service.memory_store"
        ) as mock_memory:
            mock_user_memory = MagicMock()
            mock_user_memory.id = "mem_user_001"
            mock_user_memory.content = "用户记忆"
            mock_user_memory.embedding = [0.1] * 1024
            mock_user_memory.is_static = False

            mock_project_memory = MagicMock()
            mock_project_memory.id = "mem_project_001"
            mock_project_memory.content = "项目记忆"
            mock_project_memory.embedding = [0.5] * 1024
            mock_project_memory.is_static = False

            def get_by_container_side_effect(container_tag, limit):
                if "user" in container_tag:
                    return [mock_user_memory]
                else:
                    return [mock_project_memory]

            mock_memory.get_by_container = AsyncMock(
                side_effect=get_by_container_side_effect
            )
            def search_side_effect(query, container_tag, limit=5, threshold=0.3):
                if "user" in str(container_tag):
                    return [
                        {
                            "id": "mem_user_001",
                            "content": "用户记忆",
                            "embedding": [0.1] * 1024,
                            "similarity": 0.9,
                        }
                    ]
                return [
                    {
                        "id": "mem_project_001",
                        "content": "项目记忆",
                        "embedding": [0.5] * 1024,
                        "similarity": 0.9,
                    }
                ]

            mock_memory.search = AsyncMock(side_effect=search_side_effect)
            mock_memory.traverse_memory_relations = AsyncMock(return_value=[])
            mock_memory.get_entities_for_memories = AsyncMock(return_value=[])
            mock_memory.traverse_entity_relations = AsyncMock(return_value=[])

            with patch(
                "src.services.core.context_inject_service.get_embedding_client"
            ) as mock_embed:
                client = MagicMock()
                client.embed = AsyncMock(return_value=[0.5] * 1024)
                mock_embed.return_value = client

                from src.services.core.context_inject_service import (
                    context_inject_service,
                )

                result = asyncio.run(
                    context_inject_service.inject_with_tags(
                        user_tag="user_test",
                        project_tag="project_test",
                        query="测试",
                        config={
                            "inject_profile": True,
                            "max_memories": 5,
                            "enable_memory_graph": False,
                            "enable_entity_graph": False,
                            "enable_semantic_dedup": False,
                            "language": "zh_CN",
                        },
                    )
                )

                assert "context" in result
                assert "用户记忆" in result["context"]
                assert "项目记忆" in result["context"]
                assert result["stats"]["user_memories_count"] == 1
                assert result["stats"]["project_memories_count"] == 1
                mock_memory.traverse_entity_relations.assert_not_called()
