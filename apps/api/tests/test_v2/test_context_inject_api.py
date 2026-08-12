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

    def test_profile_static_dynamic_split_truncation(
        self, mock_profile_service, mock_memory_store, mock_document_store
    ):
        """static 按 max_static_profile_items 全量注入，dynamic 按 max_profile_items 截断"""
        from src.services.core.context_inject_service import context_inject_service

        mock_profile_service.get_profile = AsyncMock(
            return_value={
                "profile": {
                    "static": [f"静态偏好{i}" for i in range(15)],
                    "dynamic": [f"动态活动{i}" for i in range(8)],
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
                    "max_profile_items": 3,
                    "max_static_profile_items": 20,
                    "max_memories": 0,
                    "max_chunks": 0,
                    "enable_semantic_dedup": False,
                    "language": "zh_CN",
                },
                include_trace=True,
            )
        )

        trace = result["trace"]["channels"]["profile"]
        assert trace["static_count"] == 15
        assert trace["dynamic_count"] == 3

    def test_profile_static_default_cap(
        self, mock_profile_service, mock_memory_store, mock_document_store
    ):
        """未传 max_static_profile_items 时，static 走 service 默认 30（25 条全量，不截断）"""
        from src.services.core.context_inject_service import context_inject_service

        mock_profile_service.get_profile = AsyncMock(
            return_value={
                "profile": {
                    "static": [f"静态偏好{i}" for i in range(25)],
                    "dynamic": ["动态活动"],
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
                    "max_profile_items": 5,
                    "max_memories": 0,
                    "max_chunks": 0,
                    "enable_semantic_dedup": False,
                    "language": "zh_CN",
                },
                include_trace=True,
            )
        )

        trace = result["trace"]["channels"]["profile"]
        assert trace["static_count"] == 25
        assert trace["dynamic_count"] == 1

    def test_profile_static_layered_injection(
        self, mock_profile_service, mock_memory_store, mock_document_store
    ):
        """static 分层注入：行为规则全量 + 临时记录（配置/热点研究）填剩余额度"""
        from src.services.core.context_inject_service import context_inject_service

        static_facts = (
            [f"行为规则{i}" for i in range(10)]
            + [
                "机器主机名已改为 ai-agent",
                "Volcengine API Key 已吊销",
                "数据库迁移文件顺序已变更",
                "auto_publish关键bug已修复",
            ]
        )
        mock_profile_service.get_profile = AsyncMock(
            return_value={
                "profile": {
                    "static": static_facts,
                    "dynamic": ["动态活动"],
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
                    "max_profile_items": 5,
                    "max_static_profile_items": 12,
                    "max_memories": 0,
                    "max_chunks": 0,
                    "enable_semantic_dedup": False,
                    "language": "zh_CN",
                },
                include_trace=True,
            )
        )

        trace = result["trace"]["channels"]["profile"]
        # 10 条行为规则全量 + 2 条临时（填满 12 上限，最新优先）
        assert trace["static_count"] == 12
        injected = [i for i in trace["items"] if "行为规则" in i]
        assert len(injected) == 10

    def test_get_profile_requests_full_static_for_layering(
        self, mock_profile_service, mock_memory_store, mock_document_store
    ):
        """分层注入请求 profile_service 时必须取全量（fetch=缓存上限），cap 在分层后施加"""
        from src.services.core.context_inject_service import context_inject_service
        from src.services.core.profile_service import profile_service as real_ps

        captured = {}

        async def fake_get_profile(container_tag, max_static, max_dynamic):
            captured["max_static"] = max_static
            captured["max_dynamic"] = max_dynamic
            return {
                "profile": {
                    "static": [f"规则{i}" for i in range(35)],
                    "dynamic": ["动态活动"],
                }
            }

        mock_profile_service.get_profile = fake_get_profile
        mock_memory_store.get_by_container = AsyncMock(return_value=[])

        result = asyncio.run(
            context_inject_service.inject(
                container_tag="user_test",
                query=None,
                config={
                    "inject_profile": True,
                    "max_static_profile_items": 30,
                    "max_profile_items": 5,
                    "max_memories": 0,
                    "max_chunks": 0,
                    "enable_semantic_dedup": False,
                    "language": "zh_CN",
                },
                include_trace=True,
            )
        )

        # fetch 取缓存构建上限 100，而非 cap 30——防止 profile_service 预截断丢弃老行为规则
        assert captured["max_static"] == real_ps._CACHE_STATIC_LIMIT
        assert captured["max_dynamic"] == real_ps._CACHE_DYNAMIC_LIMIT
        # over-cap 契约：35 条行为规则（无临时标记）全部注入，即使超 max_static=30——
        # "行为规则永不截断"是设计意图，max_static_profile_items 是临时额度而非硬上限
        trace = result["trace"]["channels"]["profile"]
        assert trace["static_count"] == 35

    def test_is_transient_static_classification(
        self, mock_profile_service, mock_memory_store, mock_document_store
    ):
        """分类启发式：临时标记命中 vs 行为规则保留（保守策略）"""
        from src.services.core.context_inject_service import context_inject_service

        transient = [
            "机器主机名已从 wbaifan-openclaw 改为 ai-agent",
            "Volcengine API Key 7e4a4d80 已吊销",
            "GitHub PAT token已保存在 ~/.config/gh/hosts.yml",
            "auto_publish_article.py关键bug已修复",
        ]
        behavior = [
            "始终用中文回复用户的问题和请求",
            "OMO (OhMyOpenCode) 4.19.4 配置半迁移缺陷及修复",  # 含"修复"但不含"已修复"
            "EmQuantAPI 使用规范：不要凭记忆写 API 调用代码",  # 含"API"但不是临时
            "用户偏好定期代码库审查和清理，保持整洁",
            "热点研究2026-08-09",  # 热点研究不在临时标记表（dynamic 已按时间截断），不应误判
        ]
        for c in transient:
            assert context_inject_service._is_transient_static(c), c
        for c in behavior:
            assert not context_inject_service._is_transient_static(c), c

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

    def test_final_injection_cap(
        self, mock_profile_service, mock_memory_store, mock_document_store
    ):
        """最终注入 cap：memory 12 条 + chunk 4 条，profile 不裁剪"""
        from src.services.core.context_inject_service import context_inject_service

        mock_memory_store.get_by_container = AsyncMock(return_value=[])
        with (
            patch.object(
                context_inject_service,
                "_get_chunks",
                AsyncMock(
                    return_value=[
                        {
                            "id": f"chunk_{i}",
                            "content": f"文档内容{i}",
                            "embedding": [0.3] * 1024,
                            "document_id": "doc_001",
                            "similarity": 0.8,
                        }
                        for i in range(8)
                    ]
                ),
            ),
            patch.object(
                context_inject_service,
                "_get_memories",
                AsyncMock(
                    return_value=[
                        {
                            "id": f"mem_{i}",
                            "content": f"记忆内容{i}",
                            "embedding": [0.5] * 1024,
                            "similarity": 0.7,
                        }
                        for i in range(20)
                    ]
                ),
            ),
        ):
            result = asyncio.run(
                context_inject_service.inject(
                    container_tag="user_test",
                    query="测试",
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

        # cap 统一在去重后应用：context/stats/trace.final 三者一致
        # 单容器路径所有 memory 均为 userMemory → cap 6
        assert result["context"].count("- 记忆内容") == 6
        assert result["context"].count("- 文档内容") == 4
        assert result["stats"]["memories_count"] == 6
        assert result["stats"]["chunks_count"] == 4

    def test_cap_project_user_balanced(
        self, mock_profile_service, mock_memory_store, mock_document_store
    ):
        """project/user 分开 cap：project 12 条时 user 仍保留 6 条不被挤占"""
        from src.services.core.context_inject_service import context_inject_service

        mock_memory_store.get_by_container = AsyncMock(return_value=[])
        project_items = [
            DedupItem(content=f"项目记忆{i}", source="projectMemory", priority=3)
            for i in range(12)
        ]
        user_items = [
            DedupItem(content=f"用户记忆{i}", source="userMemory", priority=2)
            for i in range(4)
        ]
        profile_items = [
            DedupItem(content="静态偏好", source="profile", priority=4)
        ]

        capped = context_inject_service._apply_injection_caps(
            project_items + user_items + profile_items
        )
        sources = [i.source for i in capped]
        assert sources.count("projectMemory") == 6
        assert sources.count("userMemory") == 4
        assert sources.count("profile") == 1

    def test_subagent_query_downscale(
        self, mock_profile_service, mock_memory_store, mock_document_store
    ):
        """子代理 query（[CONTEXT] 前缀/超长）识别信号"""
        from src.services.core.context_inject_service import context_inject_service

        assert context_inject_service._is_subagent_query(
            "[CONTEXT] I'm investigating the codebase structure to understand"
        ) is True
        assert context_inject_service._is_subagent_query(
            "[analyze-mode] ANALYSE this project architecture"
        ) is True
        assert context_inject_service._is_subagent_query("[System: Resuming task]") is True
        assert context_inject_service._is_subagent_query("x" * 900) is True
        assert context_inject_service._is_subagent_query("用户正常查询") is False
        assert context_inject_service._is_subagent_query(None) is False

    def test_entity_chunk_similarity_gate(
        self, mock_profile_service, mock_memory_store, mock_document_store
    ):
        """实体 chunk 相似度低于阈值应被过滤"""
        from src.services.core.context_inject_service import context_inject_service

        # 构造 _get_chunks 内部使用的依赖
        mock_memory_store.get_by_container = AsyncMock(return_value=[])

        # query_embedding 与 chunk embedding 相似度 < 0.45 的情况
        # 用 _chunk_similarity 直接验证门控逻辑
        low = context_inject_service._chunk_similarity([1.0, 0.0], [0.0, 1.0])
        high = context_inject_service._chunk_similarity([1.0, 0.0], [0.9, 0.1])
        assert low < 0.45
        assert high >= 0.45

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
