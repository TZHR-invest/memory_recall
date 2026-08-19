"""LLM client trace 日志单元测试：请求/响应日志行包含 trace_id 与关键字段（无真实 API 调用）"""

import logging

import pytest

from src.llm.client import LLMClient, _prompt_len, _response_summary


class _FakeUsage:
    total_tokens = 1003

    class _Details:
        reasoning_tokens = 737

    completion_tokens_details = _Details()


class _FakeMessage:
    content = "返回内容"
    reasoning_content = "思考链内容"


class _FakeChoice:
    message = _FakeMessage()


class _FakeResponse:
    choices = [_FakeChoice()]
    usage = _FakeUsage()


class _FakeEmptyMessage:
    content = None
    reasoning_content = "x" * 3998


class _FakeEmptyChoice:
    message = _FakeEmptyMessage()


class _FakeEmptyResponse:
    choices = [_FakeEmptyChoice()]
    usage = None


class TestPromptLen:
    def test_sums_all_content(self):
        messages = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "hello world"},
        ]
        assert _prompt_len(messages) == 3 + 11


class TestResponseSummary:
    def test_ok_summary(self):
        summary = _response_summary(_FakeResponse(), "返回内容", 12.3)
        assert "ok=true" in summary
        assert "content_len=4" in summary
        assert "reasoning_len=5" in summary
        assert "usage=1003" in summary
        assert "(reasoning=737)" in summary
        assert "elapsed=12.3s" in summary

    def test_empty_content_marks_return_empty(self):
        """deepseek 思考链吃光预算 → 返回空：日志显式标"→ 返回空"（trace-id 计划 §3.3 排查抓手）"""
        summary = _response_summary(_FakeEmptyResponse(), None, 8.1)
        assert "ok=false" in summary
        assert "content=''" in summary
        assert "reasoning_len=3998" in summary
        assert "→ 返回空" in summary


class TestLLMClientLogging:
    """LLM client 请求/响应日志：mock OpenAI client 的 create，验证日志行字段。

    不触发真实 API：用 object.__new__ 绕过 LLMClient.__init__ 的 key 校验。
    """

    @pytest.fixture
    def fake_client(self, monkeypatch):
        client = object.__new__(LLMClient)
        client.model = "test-model"
        client.provider = "volcengine"
        client._min_max_tokens = 0

        class _FakeCompletions:
            def __init__(self, resp):
                self._resp = resp

            def create(self, **kwargs):
                return self._resp

        # 替换底层 chat.completions（object.__new__ 绕过 __init__，需手动挂 client/async_client）
        from openai import OpenAI

        fake_openai = object.__new__(OpenAI)
        fake_openai.chat = type("Chat", (), {"completions": _FakeCompletions(_FakeResponse())})()
        client.client = fake_openai
        client.async_client = fake_openai
        return client

    def test_chat_logs_request_and_response(self, fake_client, monkeypatch, caplog):
        from src.llm import client as llm_client_module
        from src.logging_utils import TraceIdFilter, set_trace_id, reset_trace_id

        # 挂内存 handler 收集 llm.client logger 日志（与生产一致：handler 带 TraceIdFilter）
        logger = logging.getLogger("src.llm.client")
        records = []
        handler = logging.Handler()
        handler.emit = lambda r: records.append(r)
        handler.addFilter(TraceIdFilter())
        old_level = logger.level
        logger.setLevel(logging.INFO)
        logger.addHandler(handler)
        logger.propagate = False
        try:
            token = set_trace_id("ev_trace_test")
            try:
                result = fake_client.chat(
                    [{"role": "user", "content": "你好"}], max_tokens=100
                )
            finally:
                reset_trace_id(token)
        finally:
            logger.removeHandler(handler)
            logger.setLevel(old_level)

        assert result == "返回内容"
        messages = [r.getMessage() for r in records]
        # 请求日志带 trace_id + model + max_tokens + prompt_len
        req = next(m for m in messages if "LLM 请求" in m)
        assert req.startswith("[trace_id=ev_trace_test]")
        assert "model=test-model" in req
        assert "max_tokens=100" in req
        assert "prompt_len=" in req
        # 响应日志带 trace_id + ok + usage
        resp = next(m for m in messages if "LLM 响应" in m)
        assert resp.startswith("[trace_id=ev_trace_test]")
        assert "ok=true" in resp
        assert "usage=1003" in resp

    def test_achat_logs_with_trace(self, fake_client, monkeypatch):
        """异步链路：achat 日志同样带 trace_id（asyncio contextvars 传播）"""
        import asyncio
        from src.llm import client as llm_client_module
        from src.logging_utils import TraceIdFilter, set_trace_id, reset_trace_id

        class _FakeAsyncCompletions:
            async def create(self, **kwargs):
                return _FakeResponse()

        fake_async_openai = object.__new__(type("A", (), {}))
        fake_async_openai.chat = type("Chat", (), {"completions": _FakeAsyncCompletions()})()
        fake_client.async_client = fake_async_openai

        logger = logging.getLogger("src.llm.client")
        records = []
        handler = logging.Handler()
        handler.emit = lambda r: records.append(r)
        handler.addFilter(TraceIdFilter())
        logger.setLevel(logging.INFO)
        logger.addHandler(handler)
        logger.propagate = False
        try:
            async def run():
                token = set_trace_id("ev_async_test")
                try:
                    return await fake_client.achat(
                        [{"role": "user", "content": "异步"}], max_tokens=200
                    )
                finally:
                    reset_trace_id(token)

            result = asyncio.run(run())
        finally:
            logger.removeHandler(handler)

        assert result == "返回内容"
        messages = [r.getMessage() for r in records]
        assert any(
            m.startswith("[trace_id=ev_async_test]") and "LLM 请求" in m
            for m in messages
        )
        assert any(
            m.startswith("[trace_id=ev_async_test]") and "LLM 响应" in m
            for m in messages
        )
