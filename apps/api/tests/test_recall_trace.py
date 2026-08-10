"""
Tests for Recall Trace feature:
- RecallTrace data class (channels/dedup/final/summary/truncate)
- semantic_dedup_service dropped_log (compatibility)
- recall_trace_service sampling logic
"""

import sys
import os
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

from src.services.core.recall_trace_service import RecallTrace, _truncate
from src.services.core.semantic_dedup_service import (
    SemanticDedupService,
    DedupItem,
    SOURCE_PRIORITY,
)


class TestTruncate:
    def test_short_text_unchanged(self):
        assert _truncate("短文本", max_len=200) == "短文本"

    def test_long_text_truncated(self):
        result = _truncate("a" * 100, max_len=10)
        assert len(result) <= 11
        assert result.startswith("a" * 10)

    def test_none_returns_none(self):
        assert _truncate(None) is None


class TestRecallTrace:
    def test_record_profile_and_vector(self):
        trace = RecallTrace(
            mode="single",
            container_tag="c",
            user_tag="c",
            project_tag=None,
            query="张三在哪里工作",
            config={"inject_profile": True, "dedup_threshold": 0.85},
        )
        trace.record_profile(["张三是工程师"], ["最近在学Rust"], True)
        trace.record_vector(
            [{"id": "mem_1", "content": "张三在字节", "similarity": 0.82}],
            threshold=0.3,
        )
        data = trace.to_dict()
        assert data["channels"]["profile"]["static_count"] == 1
        assert data["channels"]["profile"]["dynamic_count"] == 1
        assert data["channels"]["vector"]["hits"][0]["passed"] is True
        assert data["channels"]["vector"]["hits"][0]["similarity"] == 0.82
        assert data["mode"] == "single"
        assert data["query"] == "张三在哪里工作"

    def test_vector_passed_flag_with_threshold(self):
        trace = RecallTrace("single", "c", "c", None, "q", {})
        trace.record_vector(
            [
                {"id": "a", "content": "x", "similarity": 0.9},
                {"id": "b", "content": "y", "similarity": 0.2},
            ],
            threshold=0.5,
        )
        hits = trace.channels["vector"]["hits"]
        assert hits[0]["passed"] is True
        assert hits[1]["passed"] is False

    def test_record_memory_graph_and_entity(self):
        trace = RecallTrace("tags", "proj", "user", "proj", "q", {})
        trace.record_memory_graph("mem_a", "extends", {"id": "mem_b", "content": "新信息"}, added=True)
        trace.record_entity_graph_path("张三", "works_at", "字节")
        trace.record_entity_graph_memory({"id": "mem_c", "content": "相关记忆"})
        data = trace.to_dict()
        assert data["channels"]["memory_graph"]["paths"][0]["added"] is True
        assert data["channels"]["entity_graph"]["entity_paths"][0]["to_entity"] == "字节"
        assert data["channels"]["entity_graph"]["memories"][0]["id"] == "mem_c"

    def test_scope_field_recorded(self):
        trace = RecallTrace("tags", "proj", "user", "proj", "q", {})
        trace.record_vector([{"id": "m", "content": "c", "similarity": 0.8}], 0.3, scope="user")
        assert trace.channels["vector"]["hits"][0]["scope"] == "user"

    def test_record_final_and_summary(self):
        trace = RecallTrace("single", "c", "c", None, "q", {})
        items = [
            DedupItem(content="静态特征", source="profile", priority=SOURCE_PRIORITY["profile"]),
            DedupItem(content="相关记忆", source="userMemory", priority=SOURCE_PRIORITY["userMemory"], id="mem_1"),
        ]
        trace.record_final(items)
        s = trace.summary()
        assert s["final"] == 2
        assert trace.final[1]["source"] == "userMemory"

    def test_error_recorded(self):
        trace = RecallTrace("single", "c", "c", None, "q", {})
        trace.mark_error("boom")
        assert trace.error == "boom"
        assert trace.to_dict()["error"] == "boom"


class TestDedupDroppedLog:
    def setup_method(self):
        self.service = SemanticDedupService()

    def test_dropped_log_records_duplicates(self):
        embedding = [0.1] * 16
        items = [
            DedupItem(content="我在字节工作", source="userMemory", priority=2, embedding=embedding, id="mem_a"),
            DedupItem(content="我目前就职于字节", source="userMemory", priority=2, embedding=embedding, id="mem_b"),
        ]
        dropped_log = []
        import asyncio
        kept = asyncio.run(self.service.deduplicate(items, threshold=0.8, dropped_log=dropped_log))
        assert len(kept) == 1
        assert len(dropped_log) == 1
        assert dropped_log[0]["id"] == "mem_b"
        assert dropped_log[0]["duplicate_of"]["id"] == "mem_a"
        assert dropped_log[0]["similarity"] == pytest.approx(1.0, abs=0.01)

    def test_dropped_log_none_preserves_behavior(self):
        embedding = [0.5] * 16
        items = [
            DedupItem(content="a", source="userMemory", priority=2, embedding=embedding, id="m1"),
            DedupItem(content="b", source="userMemory", priority=2, embedding=embedding, id="m2"),
            DedupItem(content="c", source="profile", priority=4, embedding=None),
        ]
        import asyncio
        kept = asyncio.run(self.service.deduplicate(items, threshold=0.9))
        assert len(kept) == 2
        # 不带 embedding 的项无条件保留
        assert any(i.id is None and i.source == "profile" for i in kept)

    def test_different_embeddings_kept(self):
        import asyncio
        items = [
            DedupItem(content="苹果", source="userMemory", priority=2, embedding=[1.0, 0.0], id="m1"),
            DedupItem(content="香蕉", source="userMemory", priority=2, embedding=[0.0, 1.0], id="m2"),
        ]
        dropped_log = []
        kept = asyncio.run(self.service.deduplicate(items, threshold=0.5, dropped_log=dropped_log))
        assert len(kept) == 2
        assert dropped_log == []


class TestSampling:
    @pytest.mark.asyncio
    async def test_disabled_never_records(self):
        from src.services.core.recall_trace_service import recall_trace_service
        with patch("src.services.core.recall_trace_service.settings.TRACE_ENABLED", False):
            assert await recall_trace_service.should_record(force=False) is False
            assert await recall_trace_service.should_record(force=True) is False

    @pytest.mark.asyncio
    async def test_rate_zero_but_force_records(self):
        from src.services.core.recall_trace_service import recall_trace_service
        with patch("src.services.core.recall_trace_service.settings.TRACE_ENABLED", True), \
             patch("src.services.core.recall_trace_service.settings.TRACE_SAMPLE_RATE", 0.0):
            assert await recall_trace_service.should_record(force=False) is False
            assert await recall_trace_service.should_record(force=True) is True

    @pytest.mark.asyncio
    async def test_rate_one_always_records(self):
        from src.services.core.recall_trace_service import recall_trace_service
        with patch("src.services.core.recall_trace_service.settings.TRACE_ENABLED", True), \
             patch("src.services.core.recall_trace_service.settings.TRACE_SAMPLE_RATE", 1.0):
            assert await recall_trace_service.should_record(force=False) is True


class TestRecallEmbeddingLog:
    def setup_method(self):
        from src.services.core.recall_embedding_service import (
            RecallEmbeddingService,
        )
        self.service = RecallEmbeddingService()

    @pytest.mark.asyncio
    async def test_log_success(self):
        row = {"id": "embed_abc"}
        with patch("src.services.core.recall_embedding_service.db.fetchrow", new=AsyncMock(return_value=row)) as m:
            rid = await self.service.log("container_x", "memory", "测试内容", True,
                                         model="m1", elapsed_ms=12.5, output_dim=1024)
            assert rid == "embed_abc"
            args = m.await_args.args
            assert args[1] == "container_x"
            assert args[2] == "memory"
            assert args[4] == "测试内容"
            assert args[5] == 4  # text_len
            assert args[6] is True
            assert args[10] == 1024

    @pytest.mark.asyncio
    async def test_log_failure_records_error(self):
        with patch("src.services.core.recall_embedding_service.db.fetchrow", new=AsyncMock(return_value=None)):
            rid = await self.service.log("c", "memory", "文本", False, error="401 Unauthorized", elapsed_ms=300)
            assert rid is None
            # 不抛异常，失败不中断主流程

    @pytest.mark.asyncio
    async def test_log_never_raises_on_db_error(self):
        with patch("src.services.core.recall_embedding_service.db.fetchrow", new=AsyncMock(side_effect=Exception("db down"))):
            rid = await self.service.log("c", "memory", "文本", False)
            assert rid is None

    @pytest.mark.asyncio
    async def test_long_text_preview_truncated(self):
        with patch("src.services.core.recall_embedding_service.db.fetchrow", new=AsyncMock(return_value={"id": "x"})) as m:
            await self.service.log("c", "memory", "长" * 500, True)
            args = m.await_args.args
            assert len(args[4]) <= 201
            assert args[5] == 500

    @pytest.mark.asyncio
    async def test_list_with_kind(self):
        rows = [{"id": "e1", "kind": "memory", "ok": True}]
        with patch("src.services.core.recall_embedding_service.db.fetch", new=AsyncMock(return_value=rows)) as m:
            result = await self.service.list_logs("c", kind="memory", limit=10, offset=0)
            assert result[0]["id"] == "e1"
            sql = m.await_args.args[0]
            assert "kind = $2" in sql

    @pytest.mark.asyncio
    async def test_list_without_kind(self):
        with patch("src.services.core.recall_embedding_service.db.fetch", new=AsyncMock(return_value=[])) as m:
            await self.service.list_logs("c", limit=10, offset=0)
            sql = m.await_args.args[0]
            assert "kind = $" not in sql

    @pytest.mark.asyncio
    async def test_count(self):
        with patch("src.services.core.recall_embedding_service.db.fetchrow", new=AsyncMock(return_value={"n": 7})):
            assert await self.service.count_for_container("c") == 7
