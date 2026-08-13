"""Memory Recall Codex 插件 server.py handler 单元测试（mock API，不需后端）。

依赖 mcp 包；不可用时自动跳过（仓库默认 venv 未装 mcp，用插件自举 venv 跑：
`~/.config/codex/memory-recall-venv/bin/python -m pytest`）。
"""

import importlib.util
import sys
from pathlib import Path

import pytest

PLUGIN_DIR = Path(__file__).resolve().parents[1] / "src" / "plugins" / "memory-recall-codex"

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("mcp") is None,
    reason="需要 mcp 包（pip install mcp）",
)


@pytest.fixture(scope="module")
def mod():
    sys.path.insert(0, str(PLUGIN_DIR))
    import server
    return server


class TestStatus:
    async def test_dual_scope_counts(self, mod, monkeypatch):

        async def fake_api(method, path, body=None, params=None, timeout=None):
            return {"total": 7}

        monkeypatch.setattr(mod, "api_request", fake_api)
        out = await mod._handle_status({})
        assert "用户范围: 记忆 7 / 文档 7" in out[0].text
        assert "项目范围: 记忆 7 / 文档 7" in out[0].text

    async def test_backend_down(self, mod, monkeypatch):

        async def boom(method, path, body=None, params=None, timeout=None):
            raise httpx_exc()

        def httpx_exc():
            import httpx

            return httpx.ConnectError("boom")

        monkeypatch.setattr(mod, "api_request", boom)
        out = await mod._handle_status({})
        assert "服务不可用" in out[0].text


class TestUpdate:
    async def test_async_process_passthrough(self, mod, monkeypatch):
        captured = {}

        async def fake_api(method, path, body=None, params=None, timeout=None):
            captured["body"] = body
            return {"id": "mem_new1234567890", "status": "processing"}

        monkeypatch.setattr(mod, "api_request", fake_api)
        out = await mod._handle_update({"memoryId": "mem_old1234567890", "content": "新内容"})
        assert captured["body"]["async_process"] is True
        assert "后台处理" in out[0].text

    async def test_sync_when_explicitly_disabled(self, mod, monkeypatch):
        captured = {}

        async def fake_api(method, path, body=None, params=None, timeout=None):
            captured["body"] = body
            return {"id": "mem_new1234567890", "status": "done"}

        monkeypatch.setattr(mod, "api_request", fake_api)
        out = await mod._handle_update(
            {"memoryId": "mem_old1234567890", "content": "新内容", "asyncProcess": False}
        )
        assert captured["body"]["async_process"] is False
        assert "后台处理" not in out[0].text


class TestSearch:
    async def test_formats_results(self, mod, monkeypatch):

        async def fake_api(method, path, body=None, params=None, timeout=None):
            return {
                "results": [
                    {"id": "mem_1234567890", "content": "部署流程：先构建再发布", "similarity": 0.87},
                ]
            }

        monkeypatch.setattr(mod, "api_request", fake_api)
        out = await mod._handle_search({"query": "部署"})
        assert "找到 1 条记忆" in out[0].text
        assert "[mem_1234]" in out[0].text
        assert "相似度: 0.87" in out[0].text

    async def test_no_results(self, mod, monkeypatch):

        async def fake_api(method, path, body=None, params=None, timeout=None):
            return {"results": []}

        monkeypatch.setattr(mod, "api_request", fake_api)
        out = await mod._handle_search({"query": "不存在的东西"})
        assert "未找到" in out[0].text


class TestAdd:
    async def test_add_success(self, mod, monkeypatch):

        async def fake_api(method, path, body=None, params=None, timeout=None):
            assert body["container_tag"] == mod.PROJECT_TAG
            assert body["async_process"] is True
            return {"id": "mem_new1", "status": "processing"}

        monkeypatch.setattr(mod, "api_request", fake_api)
        out = await mod._handle_add({"content": "重要决策"})
        assert "已存储到 project 范围" in out[0].text
        assert "mem_new1" in out[0].text
        assert "后台处理" in out[0].text

    async def test_user_scope_static(self, mod, monkeypatch):

        async def fake_api(method, path, body=None, params=None, timeout=None):
            assert body["container_tag"] == mod.USER_TAG
            assert body["is_static"] is True
            assert body["metadata"] == {"type": "preference"}
            return {"id": "mem_static", "status": "done"}

        monkeypatch.setattr(mod, "api_request", fake_api)
        await mod._handle_add({"content": "偏好", "scope": "user", "isStatic": True, "type": "preference"})


class TestContextInject:
    async def test_passes_tags_and_config(self, mod, monkeypatch):

        captured = {}

        async def fake_api(method, path, body=None, params=None, timeout=None):
            captured["body"] = body
            return {
                "context": "## 用户上下文\n- 喜欢喝咖啡",
                "sources": {"profile": ["a"], "memories": ["b"]},
                "stats": {"total_items": 5, "after_dedup": 4, "deduped_count": 1},
            }

        monkeypatch.setattr(mod, "api_request", fake_api)
        out = await mod._handle_context_inject({"query": "测试", "injectProfile": True})
        body = captured["body"]
        assert body["user_tag"] == mod.USER_TAG
        assert body["project_tag"] == mod.PROJECT_TAG
        assert body["config"]["inject_profile"] is True
        assert body["config"]["max_memories"] == mod.CONFIG["max_memories"]
        assert "统计: 4 条" in out[0].text

    async def test_no_context(self, mod, monkeypatch):

        async def fake_api(method, path, body=None, params=None, timeout=None):
            return {"context": "", "sources": {}, "stats": {}}

        monkeypatch.setattr(mod, "api_request", fake_api)
        out = await mod._handle_context_inject({"query": "x"})
        assert "未找到相关上下文" in out[0].text

