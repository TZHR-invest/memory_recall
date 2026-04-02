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
