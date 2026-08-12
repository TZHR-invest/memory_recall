#!/usr/bin/env python3
"""Memory Recall MCP Server for DeepSeek TUI

通过 MCP 协议在 DeepSeek TUI 中使用 memory_recall 记忆系统。
配置优先级：环境变量 > ~/.deepseek/plugins/memory-recall/config.jsonc > 默认值

15 tools: add, search, profile, forget, list, update, restore,
import-docs, list-docs, read-doc, delete-doc, hybrid-search,
extract-memory, context-inject, status
"""

import os, sys, json, logging, asyncio, re
from pathlib import Path
from urllib.parse import quote
import httpx
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

logger = logging.getLogger("memory-recall-deepseek")

def _strip_jsonc_comments(content: str) -> str:
    content = re.sub(r'//.*$', '', content, flags=re.MULTILINE)
    content = re.sub(r'/\*[\s\S]*?\*/', '', content)
    content = re.sub(r',(\s*[}\]])', r'\1', content)
    return content

def _load_config() -> dict:
    cfg = {
        "base_url": "http://localhost:8000", "api_key": "",
        "user_tag": "deepseek-tui-user", "project_tag": "deepseek-tui-default",
        "max_memories": 10, "max_chunks": 5, "similarity_threshold": 0.3,
        "enable_graph_recall": True, "enable_entity_recall": True,
        "graph_max_depth": 2, "graph_max_nodes": 5,
    }
    config_path = Path.home() / ".deepseek" / "plugins" / "memory-recall" / "config.jsonc"
    if config_path.exists():
        try:
            raw = config_path.read_text(encoding="utf-8")
            clean = _strip_jsonc_comments(raw)
            file_cfg = json.loads(clean)
            cfg.update({k: v for k, v in file_cfg.items() if v not in (None, "")})
        except Exception as e:
            logger.warning(f"Failed to parse config.jsonc: {e}")
    for env_key, cfg_key in {
        "MEMORY_RECALL_BASE_URL": "base_url", "MEMORY_RECALL_API_KEY": "api_key",
        "MEMORY_RECALL_USER_TAG": "user_tag", "MEMORY_RECALL_PROJECT_TAG": "project_tag",
    }.items():
        if os.environ.get(env_key):
            cfg[cfg_key] = os.environ[env_key]
    return cfg

CONFIG = _load_config()
API_BASE_URL, API_KEY = CONFIG["base_url"], CONFIG["api_key"]
USER_TAG, PROJECT_TAG = CONFIG["user_tag"], CONFIG["project_tag"]

app = Server("memory-recall")

_http_client: httpx.AsyncClient | None = None

async def _get_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None or _http_client.is_closed:
        headers = {"Content-Type": "application/json"}
        if API_KEY: headers["X-API-Key"] = API_KEY
        _http_client = httpx.AsyncClient(base_url=API_BASE_URL, headers=headers, timeout=180.0)
    return _http_client

async def api(method: str, path: str, body: dict | None = None, params: dict | None = None) -> dict:
    client = await _get_client()
    if method == "GET":
        resp = await client.get(path, params=params)
    elif method == "DELETE":
        resp = await client.request("DELETE", path, json=body, params=params)
    else:
        resp = await client.request(method, path, json=body, params=params)
    resp.raise_for_status()
    return resp.json()

def _tag(scope: str) -> str:
    return USER_TAG if scope == "user" else PROJECT_TAG

# ── 15 工具定义 ─────────────────────────────────────────────────────

@app.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(name="add", description="存储一条记忆。默认跳过 LLM 实体提取快速返回，提取在后台异步执行。",
             inputSchema={"type":"object","properties":{"content":{"type":"string"},"scope":{"type":"string","enum":["user","project"]},"isStatic":{"type":"boolean"},"type":{"type":"string","enum":["project-config","architecture","error-solution","preference","learned-pattern","conversation"]},"asyncProcess":{"type":"boolean","description":"异步处理实体提取（默认 true，立即返回）"}},"required":["content"]}),
        Tool(name="search", description="语义搜索记忆。基于向量相似度检索。",
             inputSchema={"type":"object","properties":{"query":{"type":"string"},"scope":{"type":"string","enum":["user","project"]},"limit":{"type":"number"},"threshold":{"type":"number"}},"required":["query"]}),
        Tool(name="profile", description="获取用户画像。static=永久特征，dynamic=近期活动。",
             inputSchema={"type":"object","properties":{"query":{"type":"string"}}}),
        Tool(name="forget", description="软删除一条记忆。可通过 restore 恢复。",
             inputSchema={"type":"object","properties":{"memoryId":{"type":"string"}},"required":["memoryId"]}),
        Tool(name="list", description="列出记忆，按创建时间倒序。",
             inputSchema={"type":"object","properties":{"scope":{"type":"string","enum":["user","project"]},"limit":{"type":"number"}}}),
        Tool(name="update", description="更新记忆（版本化）。创建新版本并建立 updates 关系。",
             inputSchema={"type":"object","properties":{"memoryId":{"type":"string"},"content":{"type":"string"}},"required":["memoryId","content"]}),
        Tool(name="restore", description="恢复已删除的记忆。",
             inputSchema={"type":"object","properties":{"memoryId":{"type":"string"}},"required":["memoryId"]}),
        Tool(name="import-docs", description="导入文档。自动分块、生成 embedding。",
             inputSchema={"type":"object","properties":{"content":{"type":"string"},"title":{"type":"string"},"source":{"type":"string"},"doc_type":{"type":"string","default":"text"}},"required":["content"]}),
        Tool(name="list-docs", description="列出已导入的文档。",
             inputSchema={"type":"object","properties":{"limit":{"type":"number"}}}),
        Tool(name="read-doc", description="读取文档完整原文。",
             inputSchema={"type":"object","properties":{"documentId":{"type":"string"}},"required":["documentId"]}),
        Tool(name="delete-doc", description="删除文档及其所有 chunks（不可恢复）。",
             inputSchema={"type":"object","properties":{"documentId":{"type":"string"}},"required":["documentId"]}),
        Tool(name="hybrid-search", description="混合搜索记忆和文档。",
             inputSchema={"type":"object","properties":{"query":{"type":"string"},"limit":{"type":"number"},"scope":{"type":"string","enum":["user","project"]}},"required":["query"]}),
        Tool(name="extract-memory", description="从会话摘要中提取值得长期保存的记忆。",
             inputSchema={"type":"object","properties":{"summary":{"type":"string"},"scope":{"type":"string","enum":["user","project"]},"asyncProcess":{"type":"boolean"}},"required":["summary"]}),
        Tool(name="context-inject", description="统一上下文注入。画像+记忆+文档，后端去重和图谱扩展。",
             inputSchema={"type":"object","properties":{"query":{"type":"string"},"scope":{"type":"string","enum":["user","project"]},"maxMemories":{"type":"number"},"maxChunks":{"type":"number"},"injectProfile":{"type":"boolean"}},"required":["query"]}),
        Tool(name="status", description="检查服务连通性和基本统计。",
             inputSchema={"type":"object","properties":{}}),
    ]

@app.call_tool()
async def call_tool(name: str, args: dict) -> list[TextContent]:
    try:
        h = {
            "add": _add, "search": _search, "profile": _profile,
            "forget": _forget, "list": _list, "update": _update,
            "restore": _restore, "import-docs": _import_docs,
            "list-docs": _list_docs, "read-doc": _read_doc,
            "delete-doc": _delete_doc, "hybrid-search": _hybrid_search,
            "extract-memory": _extract_memory, "context-inject": _context_inject,
            "status": _status,
        }
        if name in h:
            return await h[name](args)
        return [TextContent(type="text", text=f"Unknown tool: {name}")]
    except httpx.HTTPStatusError as e:
        return [TextContent(type="text", text=f"API error ({e.response.status_code}): {e.response.text[:500]}")]
    except Exception as e:
        return [TextContent(type="text", text=f"Error: {str(e)}")]

async def _add(args):
    scope = args.get("scope", "project")
    async_process = args.get("asyncProcess", True)  # 默认异步，后台提取
    body = {
        "content": args["content"],
        "container_tag": _tag(scope),
        "is_static": args.get("isStatic", False),
        "async_process": async_process,
    }
    # asyncProcess=true   → 后台异步提取实体（当前请求立即返回）
    # asyncProcess=false  → 同步等待实体提取完成
    if not async_process:
        body["skip_extraction"] = False
    if args.get("type"): body["metadata"] = {"type": args["type"]}
    r = await api("POST", "/memories", body=body)
    return [TextContent(type="text", text=f"✅ Stored\nID: {r.get('id','N/A')}\nScope: {scope}")]

async def _search(args):
    body = {"query": args["query"], "container_tag": _tag(args.get("scope","project")), "limit": args.get("limit",10), "threshold": args.get("threshold", CONFIG["similarity_threshold"])}
    r = (await api("POST", "/search", body=body)).get("results", [])
    if not r: return [TextContent(type="text", text="No relevant memories found.")]
    lines = [f"Found {len(r)} memories:\n"]
    for i, m in enumerate(r, 1): lines.append(f"{i}. [{int(m.get('similarity',0)*100)}%] {m.get('content','')[:200]}")
    return [TextContent(type="text", text="\n".join(lines))]

async def _profile(args):
    p = (await api("GET", "/profile", params={"container_tag": USER_TAG, **({"query": args["query"]} if args.get("query") else {})})).get("profile", {})
    s, d = p.get("static",[]), p.get("dynamic",[])
    if not s and not d: return [TextContent(type="text", text="No profile yet.")]
    parts = []
    if s: parts.append("## Static\n" + "\n".join(f"- {f}" for f in s))
    if d: parts.append("## Dynamic\n" + "\n".join(f"- {f}" for f in d))
    return [TextContent(type="text", text="\n\n".join(parts))]

async def _forget(args):
    await api("POST", f"/memories/{quote(args['memoryId'], safe='')}/forget")
    return [TextContent(type="text", text=f"✅ Forgotten {args['memoryId']}")]

async def _list(args):
    r = (await api("GET", "/memories", params={"container_tag": _tag(args.get("scope","project")), "limit": args.get("limit",20)})).get("memories", [])
    if not r: return [TextContent(type="text", text="No memories.")]
    lines = [f"Total {len(r)}:\n"]
    for i, m in enumerate(r, 1):
        icon = "🔒" if m.get("is_static") else "📝"
        lines.append(f"{i}. {icon} {m['id'][:12]}... {m.get('content','')[:80]}")
    return [TextContent(type="text", text="\n".join(lines))]

async def _update(args):
    r = await api("POST", f"/memories/{quote(args['memoryId'], safe='')}/update", body={"content": args["content"]})
    return [TextContent(type="text", text=f"✅ Updated {r.get('id', args['memoryId'])}")]

async def _restore(args):
    await api("POST", f"/memories/{quote(args['memoryId'], safe='')}/restore")
    return [TextContent(type="text", text=f"✅ Restored {args['memoryId']}")]

async def _import_docs(args):
    body = {"content": args["content"], "doc_type": args.get("doc_type","text")}
    if args.get("title"): body["title"] = args["title"]
    if args.get("source"): body["source"] = args["source"]
    r = await api("POST", "/documents", body=body)
    return [TextContent(type="text", text=f"✅ Imported doc\nID: {r.get('id','N/A')}")]

async def _list_docs(args):
    r = (await api("GET", "/documents", params={"limit": args.get("limit",20)})).get("documents", [])
    if not r: return [TextContent(type="text", text="No documents.")]
    lines = [f"Total {len(r)} docs:\n"]
    for i, d in enumerate(r, 1): lines.append(f"{i}. [{d.get('doc_type','text')}] {d.get('title','N/A')} ({d['id'][:12]}...)")
    return [TextContent(type="text", text="\n".join(lines))]

async def _read_doc(args):
    r = await api("GET", f"/documents/{quote(args['documentId'], safe='')}")
    c = r.get("content", "")
    if len(c) > 5000: c = c[:5000] + "\n\n... (truncated)"
    return [TextContent(type="text", text=f"📄 {r.get('title','N/A')}\n\n{c}")]

async def _delete_doc(args):
    await api("DELETE", f"/documents/{quote(args['documentId'], safe='')}")
    return [TextContent(type="text", text=f"✅ Deleted doc {args['documentId']}")]

async def _hybrid_search(args):
    r = (await api("POST", "/hybrid-search", body={"query": args["query"], "container_tag": _tag(args.get("scope","project")), "limit": args.get("limit",10)})).get("results", [])
    if not r: return [TextContent(type="text", text="No results.")]
    lines = [f"Hybrid search ({len(r)}):\n"]
    for i, m in enumerate(r, 1): lines.append(f"{i}. [{m.get('source','?')}] [{int(m.get('similarity',0)*100)}%] {m.get('content','')[:200]}")
    return [TextContent(type="text", text="\n".join(lines))]

async def _extract_memory(args):
    body = {"content": args["summary"], "container_tag": _tag(args.get("scope","project")), "extract_only": True, "async_process": args.get("asyncProcess", True)}
    extracted = (await api("POST", "/memories/extract", body=body)).get("memories", [])
    if not extracted: return [TextContent(type="text", text="No worth-saving memories found.")]
    lines = [f"Extracted {len(extracted)}:\n"]
    for i, m in enumerate(extracted, 1): lines.append(f"{i}. {m.get('content','')[:150]}")
    return [TextContent(type="text", text="\n".join(lines))]

async def _context_inject(args):
    scope = args.get("scope", "project")
    body = {
        "user_tag": USER_TAG,
        "project_tag": _tag(scope),
        "query": args["query"],
        "config": {
            "inject_profile": args.get("injectProfile", True),
            "max_profile_items": CONFIG["max_memories"],
            "max_memories": args.get("maxMemories", CONFIG["max_memories"]),
            "max_chunks": args.get("maxChunks", CONFIG["max_chunks"]),
            "memory_similarity_threshold": CONFIG["similarity_threshold"],
            "chunks_similarity_threshold": CONFIG["similarity_threshold"],
            "enable_memory_graph": CONFIG["enable_graph_recall"],
            "enable_entity_graph": CONFIG["enable_entity_recall"],
            "memory_graph_depth": CONFIG["graph_max_depth"],
            "memory_graph_nodes": CONFIG["graph_max_nodes"],
            "entity_graph_depth": CONFIG["graph_max_depth"],
            "entity_graph_nodes": CONFIG["graph_max_nodes"],
            "enable_semantic_dedup": True,
            "dedup_threshold": 0.85,
        },
    }
    r = await api("POST", "/context-inject", body=body)
    ctx = r.get("context", ""); stats = r.get("stats", {})
    if not ctx: return [TextContent(type="text", text="No relevant context.")]
    return [TextContent(type="text", text=f"## Context Injection\nTotal: {stats.get('total_items',0)} -> {stats.get('after_dedup',0)}\nProfile: {stats.get('profile_count',0)} | Memories: {stats.get('memories_count',0)} | Chunks: {stats.get('chunks_count',0)}\n---\n{ctx}")]

async def _status(_args):
    try:
        resp = await (await _get_client()).get("/")
        version = resp.json().get("version", "?")
    except Exception:
        version = "Connection failed"
    return [TextContent(type="text", text=f"Memory Recall Status\nURL: {API_BASE_URL}\nVersion: {version}")]

async def main():
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())

if __name__ == "__main__":
    asyncio.run(main())
