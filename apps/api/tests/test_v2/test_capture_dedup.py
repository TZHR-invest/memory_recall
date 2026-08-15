"""自动捕获去重（2026-08-16 膨胀治理）测试。

覆盖：
1. /extract-memory 结果过滤：近似候选进 dropped、fail-open 不阻断、空结果行为
2. process_embedding_async 兜底：捕获来源（_capture）命中走 0.85 阈值物理删除；
   显式写入维持 0.95 merge 语义不变
"""
import sys
import os

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

import pytest
from unittest.mock import AsyncMock, patch
from contextlib import ExitStack

from src.services.core.memory_store import MemoryStore, Memory
from src.api.memories import (
    extract_memory_from_summary,
    ExtractMemoryRequest,
    ExtractMemoryResponse,
)
import src.services.core.memory_store as memory_store_module


class TestExtractMemoryDedup:
    """/extract-memory 蒸馏结果去重（B1）"""

    @pytest.mark.asyncio
    async def test_keeps_new_and_drops_similar(self):
        """候选与容器已有记忆 ≥0.85 近似 → 进 dropped；新内容保留"""
        llm = AsyncMock()
        llm.aextract_json.return_value = {
            "memories": [
                {"content": "与旧记忆高度近似的内容", "type": "learned-pattern", "reason": "x"},
                {"content": "全新的经验：用 X 方案解决 Y", "type": "learned-pattern", "reason": "x"},
            ]
        }
        req = ExtractMemoryRequest(summary="某会话摘要", language="zh_CN")

        with patch("src.llm.client.get_llm_client", return_value=llm):
            with patch.object(
                memory_store_module.memory_store,
                "_check_similar_memory",
                new_callable=AsyncMock,
                side_effect=[
                    {"id": "mem_old", "content": "旧记忆", "similarity": 0.91},
                    None,  # 第二条无近似
                ],
            ):
                resp: ExtractMemoryResponse = await extract_memory_from_summary(
                    req, current_user={"container_tag": "test_dedup_container", "key_id": "test_dedup_container", "permissions": ["read"]}
                )

        assert isinstance(resp, ExtractMemoryResponse)
        assert resp.has_worthwhile is True
        assert len(resp.memories) == 1
        assert "全新的经验" in resp.memories[0].content
        assert len(resp.dropped) == 1
        assert "与旧记忆高度近似" in resp.dropped[0]["content"]
        assert "相似" in resp.dropped[0]["reason"]

    @pytest.mark.asyncio
    async def test_fail_open_when_similarity_check_errors(self):
        """检索异常 → 保留全部候选，不阻断蒸馏"""
        llm = AsyncMock()
        llm.aextract_json.return_value = {
            "memories": [
                {"content": "候选 A", "type": "learned-pattern", "reason": "x"},
            ]
        }
        req = ExtractMemoryRequest(summary="摘要", language="zh_CN")

        with patch("src.llm.client.get_llm_client", return_value=llm):
            with patch.object(
                memory_store_module.memory_store,
                "_check_similar_memory",
                new_callable=AsyncMock,
                side_effect=RuntimeError("embedding 服务不可用"),
            ):
                resp = await extract_memory_from_summary(req, current_user={"container_tag": "test_dedup_container", "key_id": "test_dedup_container", "permissions": ["read"]})

        assert resp.has_worthwhile is True
        assert len(resp.memories) == 1
        assert resp.dropped == []

    @pytest.mark.asyncio
    async def test_request_container_tag_used_for_dedup(self):
        """请求带 container_tag 时，检索应使用该容器（与落库同域）"""
        llm = AsyncMock()
        llm.aextract_json.return_value = {
            "memories": [
                {"content": "候选内容 A", "type": "learned-pattern", "reason": "x"},
            ]
        }
        req = ExtractMemoryRequest(
            summary="摘要", language="zh_CN", container_tag="085288ba_project-x"
        )
        called_with = {}

        async def fake_check(content, container_tag, threshold=None, **kwargs):
            called_with["content"] = content
            called_with["container_tag"] = container_tag
            called_with["threshold"] = threshold
            return None

        with patch("src.llm.client.get_llm_client", return_value=llm):
            with patch.object(
                memory_store_module.memory_store,
                "_check_similar_memory",
                side_effect=fake_check,
            ):
                resp = await extract_memory_from_summary(
                    req, current_user={
                        "container_tag": "085288ba",
                        "key_id": "085288ba",
                        "permissions": ["read"],
                    }
                )

        assert resp.has_worthwhile is True
        assert called_with["container_tag"] == "085288ba_project-x"
        assert called_with["threshold"] == 0.80

    @pytest.mark.asyncio
    async def test_empty_result(self):
        """蒸馏无值得保存内容 → memories 空 + dropped 空"""
        llm = AsyncMock()
        llm.aextract_json.return_value = {"memories": []}
        req = ExtractMemoryRequest(summary="寒暄", language="zh_CN")

        with patch("src.llm.client.get_llm_client", return_value=llm):
            resp = await extract_memory_from_summary(req, current_user={"container_tag": "test_dedup_container", "key_id": "test_dedup_container", "permissions": ["read"]})

        assert resp.has_worthwhile is False
        assert resp.memories == []
        assert resp.dropped == []


class TestProcessEmbeddingAsyncDedup:
    """异步写入兜底（B2）：_capture 标记走 0.85 阈值"""

    @pytest.mark.asyncio
    async def test_capture_source_dropped_physically(self):
        """_capture 命中 0.85 近似 → DELETE 新行，不做 merge"""
        store = MemoryStore()
        mem = Memory(
            id="mem_new",
            container_tag="test_dedup_container",
            content="捕获的候选内容",
            metadata={"_capture": True},
        )
        with ExitStack() as stack:
            stack.enter_context(
                patch.object(store, "get_by_id", new_callable=AsyncMock, return_value=mem)
            )
            stack.enter_context(
                patch.object(
                    store, "_generate_embedding", new_callable=AsyncMock, return_value=[0.1] * 1024
                )
            )
            stack.enter_context(
                patch.object(
                    store,
                    "_check_similar_memory",
                    new_callable=AsyncMock,
                    return_value={"id": "mem_old", "content": "旧记忆", "similarity": 0.9},
                )
            )
            mock_exec = stack.enter_context(
                patch.object(memory_store_module.db, "execute", new_callable=AsyncMock)
            )
            mock_merge = stack.enter_context(
                patch.object(store, "merge_similar_memory", new_callable=AsyncMock)
            )
            await store.process_embedding_async("mem_new")

        delete_calls = [
            c for c in mock_exec.call_args_list
            if "DELETE FROM memories" in c.args[0]
        ]
        assert len(delete_calls) == 1, "捕获来源命中应物理删除新行"
        assert delete_calls[0].args[1] == "mem_new"
        mock_merge.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_explicit_write_keeps_merge_semantics(self):
        """非捕获来源 → 维持原 0.95 merge 语义，不删除"""
        store = MemoryStore()
        mem = Memory(
            id="mem_new",
            container_tag="test_dedup_container",
            content="捕获的候选内容",
            metadata={},
        )
        with ExitStack() as stack:
            stack.enter_context(
                patch.object(store, "get_by_id", new_callable=AsyncMock, return_value=mem)
            )
            stack.enter_context(
                patch.object(
                    store, "_generate_embedding", new_callable=AsyncMock, return_value=[0.1] * 1024
                )
            )
            stack.enter_context(
                patch.object(
                    store,
                    "_check_similar_memory",
                    new_callable=AsyncMock,
                    return_value={"id": "mem_old", "content": "旧记忆", "similarity": 0.9},
                )
            )
            mock_exec = stack.enter_context(
                patch.object(memory_store_module.db, "execute", new_callable=AsyncMock)
            )
            mock_merge = stack.enter_context(
                patch.object(store, "merge_similar_memory", new_callable=AsyncMock)
            )
            await store.process_embedding_async("mem_new")

        delete_calls = [
            c for c in mock_exec.call_args_list
            if "DELETE FROM memories" in c.args[0]
        ]
        assert len(delete_calls) == 0, "显式写入不应物理删除"
        mock_merge.assert_awaited_once_with("mem_old", "捕获的候选内容")

    @pytest.mark.asyncio
    async def test_no_similar_keeps_row(self):
        """无近似命中 → 正常进入实体提取流程（process_memory_async 被调用）"""
        store = MemoryStore()
        mem = Memory(
            id="mem_new",
            container_tag="test_dedup_container",
            content="捕获的候选内容",
            metadata={"_capture": True},
        )
        with ExitStack() as stack:
            stack.enter_context(
                patch.object(store, "get_by_id", new_callable=AsyncMock, return_value=mem)
            )
            stack.enter_context(
                patch.object(
                    store, "_generate_embedding", new_callable=AsyncMock, return_value=[0.1] * 1024
                )
            )
            stack.enter_context(
                patch.object(
                    store,
                    "_check_similar_memory",
                    new_callable=AsyncMock,
                    return_value=None,
                )
            )
            stack.enter_context(
                patch.object(memory_store_module.db, "execute", new_callable=AsyncMock)
            )
            mock_proc = stack.enter_context(
                patch.object(store, "process_memory_async", new_callable=AsyncMock)
            )
            await store.process_embedding_async("mem_new")

        mock_proc.assert_awaited_once_with("mem_new")
