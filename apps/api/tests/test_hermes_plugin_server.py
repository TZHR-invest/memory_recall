"""Memory Recall hermes 插件 server.py handler 单元测试（mock API，不需后端）。

依赖 mcp 包；不可用时自动跳过（仓库默认 venv 未装 mcp，用带 mcp 的 venv 跑：
`python -m pytest tests/test_hermes_plugin_server.py`）。

覆盖 2026-10-01 新增的 `add(profileWorthy=…)`（MR-027 配套）：
画像通道开关此前只有后端 `metadata.profile_worthy` 一个入口，四端插件工具都传不出去 ⇒
长留档（prompt 全文备份等）无法显式退出画像。hermes 端先补齐，且**缺省零行为变化**。
"""

import asyncio
import importlib.util
import sys
from pathlib import Path

import pytest

PLUGIN_DIR = Path(__file__).resolve().parents[1] / "src" / "plugins" / "hermes"

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("mcp") is None,
    reason="需要 mcp 包（pip install mcp）",
)


@pytest.fixture(scope="module")
def mod():
    sys.path.insert(0, str(PLUGIN_DIR))
    import server

    return server


@pytest.fixture
def captured(monkeypatch, mod):
    """捕获 POST /memories 的 body。"""
    box = {}

    async def fake_api(method, path, body=None, params=None, timeout=None):
        box["method"] = method
        box["path"] = path
        box["body"] = body
        return {"id": "mem_test", "status": "done", "container_tag": body.get("container_tag")}

    monkeypatch.setattr(mod, "api_request", fake_api)
    return box


def _call_add(mod, args):
    return asyncio.run(mod._handle_add(args))


class TestAddProfileWorthy:
    def test_default_omits_profile_worthy(self, mod, captured):
        """不传 profileWorthy ⇒ body 里不得出现该键（保持后端缺省 true 的零行为变化）。"""
        _call_add(mod, {"content": "普通记忆"})

        body = captured["body"]
        assert captured["path"] == "/memories"
        assert "metadata" not in body, "缺省不应下发 metadata"
        assert "profile_worthy" not in str(body)

    def test_false_sets_profile_worthy_in_metadata(self, mod, captured):
        out = _call_add(
            mod,
            {"content": "round=999 | 旧prompt全文备份", "profileWorthy": False},
        )

        body = captured["body"]
        assert body["metadata"] == {"profile_worthy": False}
        assert "已排除出画像通道" in out[0].text

    def test_false_coexists_with_type(self, mod, captured):
        """type 与 profile_worthy 必须共存（此前 metadata 只在有 type 时下发）。"""
        _call_add(
            mod,
            {"content": "留档", "type": "project-config", "profileWorthy": False},
        )
        assert captured["body"]["metadata"] == {
            "type": "project-config",
            "profile_worthy": False,
        }

    def test_explicit_true_is_sent(self, mod, captured):
        """显式 true 与"缺省"语义不同：显式传就下发 true（可覆盖未来默认值变化）。"""
        out = _call_add(mod, {"content": "普通记忆", "profileWorthy": True})

        assert captured["body"]["metadata"] == {"profile_worthy": True}
        assert "已排除出画像通道" not in out[0].text

    def test_type_only_unchanged(self, mod, captured):
        """老调用方（只传 type）payload 与修复前逐字一致。"""
        _call_add(mod, {"content": "偏好", "type": "preference"})

        assert captured["body"]["metadata"] == {"type": "preference"}

    def test_other_fields_untouched(self, mod, captured):
        _call_add(
            mod,
            {
                "content": "x",
                "scope": "user",
                "isStatic": True,
                "entityContext": "ctx",
                "skipExtraction": True,
                "asyncProcess": False,
            },
        )

        body = captured["body"]
        assert body["container_tag"] == mod.USER_TAG
        assert body["is_static"] is True
        assert body["entity_context"] == "ctx"
        assert body["skip_extraction"] is True
        assert body["async_process"] is False


class TestToolSchema:
    def test_schema_exposes_profile_worthy(self, mod):
        """工具 schema 必须暴露该参数，否则 agent 无从得知（开关不可达 = 本次要修的缺口）。"""
        tools = asyncio.run(mod._list_tools_impl())
        add_tool = next(t for t in tools if t.name == "add")
        # mcp 的 Tool 是 pydantic 模型：字段别名为 inputSchema，属性名为 input_schema
        schema = add_tool.input_schema
        props = schema["properties"]

        assert "profileWorthy" in props
        assert props["profileWorthy"]["type"] == "boolean"
        assert "画像" in props["profileWorthy"]["description"]
        assert schema["required"] == ["content"], "required 不应变化"
