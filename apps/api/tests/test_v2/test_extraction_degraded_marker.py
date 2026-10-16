"""抽取降级标记（`metadata._extraction_degraded`）回归测试

背景（2026-10-16 事故）：LLM 不可用时实体/关系**静默**退回规则抽取（`relations` 恒为空列表），
只在日志里留一条 WARNING ⇒ 上游账号欠费 12 天、实体/天 220~685 → 11~27、dsh 自动捕获
65~117 条/天 → 0，而看板全绿、无人发现（同类 429 事故 09-23~09-26 也静默过一次）。

本测试锁死两条不变量，防止"降级再次变得不可观测"：
1) 抽取降级 ⇒ `process_memory_async` 必须把原因写进 `metadata._extraction_degraded`；
2) 抽取正常 ⇒ 必须**清除**该键（否则恢复后看板/回填仍把它当降级，且回填无法收敛）。

降级原因的具体取值由 `llm_entity_extraction` 决定（供看板/邮件归因，如
`llm_error: insufficient_credits`、`llm_timeout`、`llm_parse_failed`）。
"""

import pytest
from unittest.mock import AsyncMock, patch

from src.services.core.llm_entity_extraction import LLMEntityExtractor
from src.services.core.memory_store import Memory, MemoryStore


def _make_memory() -> Memory:
    return Memory(
        id="mem_degraded_test",
        container_tag="test_degraded",
        content="memory_recall 用 FastAPI + pgvector 提供记忆检索" * 3,
        is_static=False,
        metadata={
            "type": "architecture",
            "_pending_extract_entities": True,
            "_pending_extract_relations": True,
            "_pending_use_llm_extraction": True,
        },
    )


async def _run_async_path(extraction: dict) -> dict:
    """跑真实 process_memory_async（只 mock 外部依赖），返回最终写入的 metadata。"""
    store = MemoryStore()
    mem = _make_memory()
    extractor = AsyncMock()
    extractor.extract_with_relations.return_value = extraction
    relations_svc = AsyncMock()
    relations_svc.auto_create_relations = AsyncMock(return_value=[])

    with patch.object(store, "get_by_id", new_callable=AsyncMock, return_value=mem), \
         patch.object(store, "_get_llm_extractor", return_value=extractor), \
         patch.object(store, "_store_entity_graph", new_callable=AsyncMock), \
         patch("src.services.core.memory_store.relation_service", relations_svc), \
         patch.object(store, "update_metadata", new_callable=AsyncMock) as upd, \
         patch("src.services.core.profile_service.profile_service", AsyncMock()):
        await store.process_memory_async(mem.id)

    assert upd.await_count >= 1, "收尾必须写回 metadata"
    written = upd.await_args[0][1]
    assert isinstance(written, dict)
    return written


@pytest.mark.asyncio
async def test_degraded_extraction_writes_marker():
    """LLM 降级（此处模拟欠费）⇒ 落 _extraction_degraded，且仍写 completed 终态"""
    written = await _run_async_path({
        "entities": [], "relations": [],
        "degraded": "llm_error: insufficient_credits",
        "confidence": 0.3,
    })
    assert written.get("_extraction_degraded") == "llm_error: insufficient_credits"
    assert written.get("_status") == "completed"
    assert written.get("_processed_at"), "终态契约：completed 必须带 _processed_at"


@pytest.mark.asyncio
async def test_healthy_extraction_clears_marker():
    """LLM 正常 ⇒ 不得留下降级标记（恢复后要看板/回填能收敛）"""
    written = await _run_async_path({
        "entities": [{"name": "FastAPI", "type": "technology"}],
        "relations": [{"from": "memory_recall", "to": "FastAPI", "type": "uses", "confidence": 0.9}],
        "is_static": False,
        "confidence": 0.8,
    })
    assert "_extraction_degraded" not in written
    assert written.get("_status") == "completed"


def test_rule_fallback_is_flagged_with_reason():
    """规则兜底的返回值必须自带 degraded 原因（否则调用方无从落标记）"""
    extractor = LLMEntityExtractor()
    extractor.llm_client = None  # 模拟 LLM 不可用

    result = extractor._fallback_extract_with_relations("某段技术文本", None, "llm_timeout")
    assert result["degraded"] == "llm_timeout"
    assert result["relations"] == [], "规则兜底不产关系（写死空）——正是需要标记的原因"

    fact = extractor._fallback_extraction("某段技术文本", None, "llm_error: insufficient_credits")
    assert fact.degraded == "llm_error: insufficient_credits"


@pytest.mark.asyncio
async def test_extract_with_relations_marks_insufficient_credits():
    """异常含 insufficient credits ⇒ 原因归类到 llm_error: insufficient_credits（供告警归因）"""
    extractor = LLMEntityExtractor()
    extractor.llm_client = AsyncMock()
    extractor.llm_client.aextract_json = AsyncMock(
        side_effect=Exception("Error code: 400 - You have insufficient credits to make this request")
    )

    result = await extractor.extract_with_relations("随便一段文本")
    assert result["degraded"] == "llm_error: insufficient_credits"
    assert result["relations"] == []
