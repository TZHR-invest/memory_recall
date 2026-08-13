import importlib.util
import json
import socket
import sys
from contextlib import asynccontextmanager
from pathlib import Path

import pytest

PLUGIN_DIR = Path(__file__).resolve().parents[1] / "src" / "plugins" / "memory-recall-codex"


def _backend_reachable() -> bool:
    cfg = Path.home() / ".config" / "codex" / "memory-recall.jsonc"
    if not cfg.exists():
        return False
    try:
        raw = json.loads(cfg.read_text(encoding="utf-8"))
        url = raw.get("base_url", "http://localhost:8000")
        host = url.split("://")[1].split(":")[0]
        port = int(url.split(":")[2].split("/")[0])
        with socket.create_connection((host, port), timeout=1):
            return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _backend_reachable() or importlib.util.find_spec("mcp") is None,
    reason="需要本机 memory_recall 后端 + 配置文件 + mcp 包（真实链路测试）",
)


@asynccontextmanager
async def _client():
    """每个测试内独立拉起 server.py 的 stdio 连接（避免跨任务关闭问题）。"""
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    venv_python = Path.home() / ".config" / "codex" / "memory-recall-venv" / "bin" / "python"
    python = str(venv_python) if venv_python.is_file() else sys.executable
    params = StdioServerParameters(
        command=python,
        args=[str(PLUGIN_DIR / "server.py")],
    )
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            yield s


async def test_tools_registered():
    async with _client() as s:
        tools = await s.list_tools()
        names = sorted(t.name for t in tools.tools)
        assert len(names) == 15
        assert "context-inject" in names and "status" in names and "add" in names


async def test_status_ok():
    async with _client() as s:
        out = await s.call_tool("status", {})
        text = out.content[0].text
        assert "memory_recall 服务正常运行" in text
        assert "项目标签" in text


async def test_search_returns_list():
    async with _client() as s:
        out = await s.call_tool("search", {"query": "部署", "scope": "project", "limit": 2})
        text = out.content[0].text
        assert text.startswith("🔍") or "未找到" in text


async def test_context_inject_ok():
    async with _client() as s:
        out = await s.call_tool(
            "context-inject", {"query": "部署流程", "maxMemories": 3, "maxChunks": 2},
        )
        text = out.content[0].text
        assert "## 用户上下文" in text or "未找到相关上下文" in text
