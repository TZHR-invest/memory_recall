"""图谱通道的失败必须留日志（2026-09-22）。

背景：`context_inject_service` 里记忆图/实体图原先各有一处 `except Exception: pass`：
- **记忆图**的 try 在 `for mem in all_memories[:3]` 内、且**没有任何外层 handler** ⇒ 整条通道
  可以无声消失；
- **实体图**外层虽有 `logger.error("entity_graph injection failed")`，但逐种子的异常被内层
  `except: pass` 吞掉后**外层永远不会触发**（`traverse_entity_relations` 整体坏掉时零日志）。

这类"静默降级"正是 2026-09-22 那次"要靠人肉 review 才发现图谱通道没有 ORDER BY"的同源病。
本文件锁住：失败要留 WARNING、且单通道失败不影响正常返回。
"""

import asyncio
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

LOGGER_NAME = "src.services.core.context_inject_service"

CONFIG = {
    "inject_profile": True,
    "max_profile_items": 5,
    "max_memories": 5,
    "max_chunks": 3,
    "enable_semantic_dedup": False,
    "enable_memory_graph": True,
    "enable_entity_graph": True,
    "enable_chunks_search": True,
    "language": "zh_CN",
}


def _memory(mid: str, content: str = "记忆内容"):
    m = MagicMock()
    m.id = mid
    m.content = content
    m.embedding = [0.1] * 1024
    m.is_static = False
    m.created_at = None
    m.metadata = {"relations": {}}
    return m


@pytest.fixture
def graph_failure_env():
    """让召回拿到 1 条记忆，并把图谱两个通道打成故障。

    ⚠️ 必须 patch **两处** embedding client 入口，且必须 patch `src.embedding.client` 那一处：
    `_get_chunks` 内部是**本地 import**（`from src.embedding.client import get_embedding_client`），
    只 patch `context_inject_service.get_embedding_client` 对它无效。用真实 client 会让结果取决于环境
    （全套运行时它已绑定前序测试的 event loop ⇒ `embed()` 失败 ⇒ `query_embedding is None` ⇒
    chunks 段提前 return ⇒ 断言随机失败，2026-09-22 实测踩到）。
    """
    with patch(f"{LOGGER_NAME}.memory_store") as ms, patch(
        f"{LOGGER_NAME}.profile_service"
    ) as ps, patch(f"{LOGGER_NAME}.document_store") as ds, patch(
        f"{LOGGER_NAME}.get_embedding_client"
    ) as embed_factory_attr, patch(
        "src.embedding.client.get_embedding_client"
    ) as embed_factory_real:
        client = MagicMock()
        client.embed = AsyncMock(return_value=[0.5] * 1024)
        client.last_cache_hit = False
        client.last_error = None
        embed_factory_attr.return_value = client
        embed_factory_real.return_value = client

        ps.get_profile = AsyncMock(return_value={"profile": {"static": [], "dynamic": []}})
        ds.search_chunks = AsyncMock(return_value=[])
        ds.find_chunks_by_entities = AsyncMock(return_value=[])

        ms.search = AsyncMock(
            return_value=[
                {
                    "id": "mem_001",
                    "content": "记忆一",
                    "similarity": 0.9,
                    "embedding": [0.1] * 1024,
                }
            ]
        )
        ms.get_by_container = AsyncMock(return_value=[_memory("mem_001")])
        ms.get_by_id = AsyncMock(return_value=_memory("mem_001"))
        ms.get_entities_for_memories = AsyncMock(
            return_value=[
                SimpleNamespace(
                    id="ent_1", name="tailscale", type="thing", container_tag="user_test"
                )
            ]
        )
        ms.traverse_entity_relations = AsyncMock(side_effect=RuntimeError("boom-traverse"))
        ms.find_memories_by_entities = AsyncMock(return_value=[])
        yield ms


def _inject(query: str = "测试查询"):
    from src.services.core.context_inject_service import context_inject_service

    return asyncio.run(
        context_inject_service.inject_with_tags(
            user_tag="user_test",
            project_tag="user_test",
            query=query,
            config=CONFIG,
        )
    )


class TestGraphChannelFailureLogging:
    def test_entity_graph_traverse_failure_logs_warning(self, graph_failure_env, caplog):
        """traverse 整体坏掉时必须留日志（外层 error 不会触发，因为内层吞掉了）。"""
        with caplog.at_level(logging.WARNING, logger=LOGGER_NAME):
            result = _inject()

        assert "entity_graph traverse failed" in caplog.text
        assert "boom-traverse" in caplog.text
        assert "seed=tailscale" in caplog.text
        # 单通道失败不影响正常返回
        assert "context" in result and "stats" in result

    def test_memory_graph_failure_logs_warning(self, graph_failure_env, caplog):
        """记忆图的 except 在 for 循环内且无外层 handler ⇒ 必须自己记日志。"""
        graph_failure_env.get_by_id = AsyncMock(side_effect=RuntimeError("boom-memgraph"))

        with caplog.at_level(logging.WARNING, logger=LOGGER_NAME):
            _inject()

        assert "memory_graph expansion failed" in caplog.text
        assert "boom-memgraph" in caplog.text

    def test_chunk_similarity_failure_returns_zero_and_logs_debug(self, caplog):
        """坏 embedding 兜底返回 0.0 是有意设计，但要走 debug 留痕（按 chunk 调用，故不用 warning）。"""
        from src.services.core.context_inject_service import context_inject_service

        with patch(
            "src.services.core.semantic_dedup_service.semantic_dedup_service.compute_cosine_similarity",
            side_effect=RuntimeError("boom-sim"),
        ):
            with caplog.at_level(logging.DEBUG, logger=LOGGER_NAME):
                score = context_inject_service._chunk_similarity([0.1] * 8, [0.2] * 8)

        assert score == 0.0
        assert "chunk similarity failed" in caplog.text

    def test_chunks_entity_hit_failure_logs_warning(self, graph_failure_env, caplog):
        """实体命中 chunk 子通道失败也要留日志（外层 chunks 处理器的 handler 覆盖不到）。"""
        with patch(
            "src.services.core.entity_extraction.entity_extractor.extract",
            return_value=[SimpleNamespace(text="tailscale")],
        ), patch(f"{LOGGER_NAME}.db") as mock_db:
            mock_db.fetch = AsyncMock(side_effect=RuntimeError("boom-chunk-entity"))
            with caplog.at_level(logging.WARNING, logger=LOGGER_NAME):
                result = _inject()

        assert "chunks entity-hit failed" in caplog.text
        assert "boom-chunk-entity" in caplog.text
        assert "context" in result
