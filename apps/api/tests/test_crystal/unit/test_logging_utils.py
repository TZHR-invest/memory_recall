"""logging_utils 单元测试：TraceIdFilter 前缀 / contextvars 并发隔离 / helper（无 DB 无 key）"""

import asyncio
import logging

import pytest

from src.logging_utils import (
    TraceIdFilter,
    generate_trace_id,
    get_trace_id,
    reset_trace_id,
    set_trace_id,
)


@pytest.fixture
def capture_logger():
    """返回 (logger, records)：logger 挂 TraceIdFilter + 内存 handler，可断言前缀。"""
    logger = logging.getLogger(f"test_trace_{id(object())}")
    logger.setLevel(logging.INFO)
    logger.propagate = False

    records = []
    handler = logging.Handler()
    handler.emit = lambda record: records.append(record)
    handler.addFilter(TraceIdFilter())
    logger.addHandler(handler)
    yield logger, records
    logger.removeHandler(handler)


class TestTraceIdFilter:
    def test_no_trace_no_prefix(self, capture_logger):
        logger, records = capture_logger
        logger.info("普通日志")
        assert len(records) == 1
        assert records[0].getMessage() == "普通日志"

    def test_with_trace_prefix(self, capture_logger):
        logger, records = capture_logger
        token = set_trace_id("ev_abc123")
        try:
            logger.info("对账日志")
        finally:
            reset_trace_id(token)
        assert len(records) == 1
        assert records[0].getMessage() == "[trace_id=ev_abc123] 对账日志"

    def test_reset_removes_prefix(self, capture_logger):
        logger, records = capture_logger
        token = set_trace_id("ev_abc123")
        reset_trace_id(token)
        logger.info("恢复后日志")
        assert records[0].getMessage() == "恢复后日志"

    def test_nested_set_reset_restores_outer(self, capture_logger):
        logger, records = capture_logger
        outer = set_trace_id("ev_outer")
        try:
            inner = set_trace_id("ev_inner")
            logger.info("内层")
            reset_trace_id(inner)
            logger.info("外层")
        finally:
            reset_trace_id(outer)
        assert records[0].getMessage() == "[trace_id=ev_inner] 内层"
        assert records[1].getMessage() == "[trace_id=ev_outer] 外层"


class TestTraceIdConcurrency:
    """并发隔离（计划验收 §4）：并发任务各带各的 trace_id，不串。"""

    @pytest.mark.anyio
    async def test_concurrent_tasks_isolated(self, capture_logger):
        logger, records = capture_logger

        async def worker(name):
            token = set_trace_id(f"ev_{name}")
            try:
                await asyncio.sleep(0.01)  # 让出事件循环，强制交错
                logger.info(f"任务 {name} 日志")
                return get_trace_id()
            finally:
                reset_trace_id(token)

        results = await asyncio.gather(worker("a"), worker("b"), worker("c"))
        # 每个任务读到自己的 trace_id
        assert results == ["ev_a", "ev_b", "ev_c"]
        # 每条日志前缀与对应任务一致
        messages = [r.getMessage() for r in records]
        assert messages == [
            "[trace_id=ev_a] 任务 a 日志",
            "[trace_id=ev_b] 任务 b 日志",
            "[trace_id=ev_c] 任务 c 日志",
        ]


class TestHelpers:
    def test_generate_trace_id_prefix_and_len(self):
        tid = generate_trace_id("ev")
        assert tid.startswith("ev_")
        assert len(tid) == 3 + 12

    def test_generate_trace_id_unique(self):
        assert generate_trace_id("ev") != generate_trace_id("ev")

    def test_default_context_is_none(self):
        # 新任务/主线程默认无 trace
        assert get_trace_id() is None
