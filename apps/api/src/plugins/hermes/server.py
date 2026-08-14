"""
Memory Recall MCP Server for Hermes Agent
通过 MCP 协议暴露 memory_recall HTTP API 给 Hermes 使用

与 Hermes 原生 memory 共存：
- 原生 memory: 精简关键事实（自动注入每轮对话）
- memory_recall: 大量细节、语义搜索、知识图谱（按需调用）

11 个工具:
1. add              - 存储记忆
2. search           - 语义搜索记忆
3. profile          - 用户画像
4. forget           - 删除记忆
5. list             - 列出记忆
6. extract-memory   - 从会话摘要提取记忆
7. hybrid-search    - 混合搜索（记忆+文档）
8. status           - 系统状态检查
9. update           - 更新记忆（版本化）
10. restore         - 恢复已删除记忆
11. context-inject  - 统一上下文注入（支持双重图谱扩展）

用法: python server.py
"""

import os
import json
import logging
import httpx
from urllib.parse import quote
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

logger = logging.getLogger("memory-recall")

# ── 配置 ──────────────────────────────────────────────────────────
API_BASE_URL = os.environ.get("MEMORY_RECALL_BASE_URL", "http://localhost:8000")
API_KEY = os.environ.get("MEMORY_RECALL_API_KEY", "")
USER_TAG = os.environ.get("MEMORY_RECALL_USER_TAG", "your-key-id")
PROJECT_TAG = os.environ.get("MEMORY_RECALL_PROJECT_TAG", "your-key-id_hermes")

app = Server("memory-recall")

# ── 复用 HTTP 客户端 ──────────────────────────────────────────────
_http_client: httpx.AsyncClient | None = None

async def _get_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None or _http_client.is_closed:
        _http_client = httpx.AsyncClient(
            base_url=API_BASE_URL,
            headers={
                "Content-Type": "application/json",
                "X-API-Key": API_KEY,
            },
timeout=120.0,
        )
    return _http_client


# ── API 请求封装 ──────────────────────────────────────────────────
async def api_request(
    method: str,
    path: str,
    body: dict | None = None,
    params: dict | None = None,
    timeout: float | None = None,
) -> dict:
    """调用 memory_recall HTTP API（复用连接池）"""
    client = await _get_client()
    logger.debug(f"{method} {path} body={bool(body)} params={params}")
    if method == "GET":
        resp = await client.get(path, params=params, timeout=timeout or 120.0)
    else:
        resp = await client.request(method, path, json=body, params=params, timeout=timeout or 120.0)
    resp.raise_for_status()
    return resp.json()


def _tag(scope: str) -> str:
    """根据 scope 返回 container_tag"""
    return USER_TAG if scope == "user" else PROJECT_TAG


# ── 工具定义 ──────────────────────────────────────────────────────
@app.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="add",
            description="存储一条记忆到 memory_recall。适合存储项目知识、经验教训、用户偏好、技术决策等。支持 user（跨项目共享）和 project（当前项目独立）两种范围。",
            inputSchema={
                "type": "object",
                "properties": {
                    "content": {
                        "type": "string",
                        "description": "要存储的记忆内容",
                    },
                    "scope": {
                        "type": "string",
                        "enum": ["user", "project"],
                        "description": "记忆范围：user=跨项目共享，project=当前项目（默认）",
                    },
                    "isStatic": {
                        "type": "boolean",
                        "description": "是否为永久特征（如姓名、偏好）。默认 false（动态信息）",
                    },
                    "type": {
                        "type": "string",
                        "enum": [
                            "project-config", "architecture", "error-solution",
                            "preference", "learned-pattern", "conversation",
                        ],
                        "description": "记忆类型（可选）",
                    },
                    "entityContext": {
                        "type": "string",
                        "description": "实体提取上下文（可选，引导实体提取方向，如'关注用户UI偏好'）",
                    },
                    "skipExtraction": {
                        "type": "boolean",
                        "description": "跳过 LLM 实体提取（大批量导入时可加速，默认 false）",
                    },
                    "asyncProcess": {
                        "type": "boolean",
                        "description": "异步处理实体提取和关系创建（默认 true，响应更快）",
                    },
                },
                "required": ["content"],
            },
        ),
        Tool(
            name="search",
            description="语义搜索 memory_recall 中的记忆。基于向量相似度检索。如需图谱扩展召回，请使用 context-inject。",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "搜索查询",
                    },
                    "scope": {
                        "type": "string",
                        "enum": ["user", "project"],
                        "description": "搜索范围（默认 project）",
                    },
                    "limit": {
                        "type": "number",
                        "description": "最大返回数量（默认 10）",
                    },
                    "threshold": {
                        "type": "number",
                        "description": "相似度阈值 0-1（默认 0.3）",
                    },
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="profile",
            description="获取用户画像。static=永久特征（姓名、偏好等），dynamic=近期活动。可按查询聚焦特定方面。",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "可选查询，聚焦画像特定方面",
                    },
                },
            },
        ),
        Tool(
            name="forget",
            description="软删除一条记忆。删除后不再出现在搜索结果中，但可通过 restore 恢复。",
            inputSchema={
                "type": "object",
                "properties": {
                    "memoryId": {
                        "type": "string",
                        "description": "要删除的记忆 ID",
                    },
                },
                "required": ["memoryId"],
            },
        ),
        Tool(
            name="list",
            description="列出指定范围内的所有记忆，按创建时间倒序。用于浏览和回顾已存储的内容。",
            inputSchema={
                "type": "object",
                "properties": {
                    "scope": {
                        "type": "string",
                        "enum": ["user", "project"],
                        "description": "记忆范围（默认 project）",
                    },
                    "limit": {
                        "type": "number",
                        "description": "最大返回数量（默认 20）",
                    },
                },
            },
        ),
        Tool(
            name="extract-memory",
            description="从会话摘要中提取值得长期保存的记忆。使用 LLM 自动判断哪些信息值得保存（用户偏好、项目约束、技术决策等），过滤掉临时状态和代码细节。",
            inputSchema={
                "type": "object",
                "properties": {
                    "summary": {
                        "type": "string",
                        "description": "会话摘要内容",
                    },
                    "language": {
                        "type": "string",
                        "enum": ["zh_CN", "en_US"],
                        "description": "语言（默认 zh_CN）",
                    },
                },
                "required": ["summary"],
            },
        ),
        Tool(
            name="hybrid-search",
            description="混合搜索记忆和文档。同时检索记忆和文档块，返回统一排序的结果。适合需要综合知识检索的场景。",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "搜索查询",
                    },
                    "scope": {
                        "type": "string",
                        "enum": ["user", "project"],
                        "description": "搜索范围（默认 project）",
                    },
                    "limit": {
                        "type": "number",
                        "description": "最大返回数量（默认 10）",
                    },
                    "threshold": {
                        "type": "number",
                        "description": "相似度阈值 0-1（默认 0.5）",
                    },
                    "sources": {
                        "type": "array",
                        "items": {"type": "string", "enum": ["memory", "chunk"]},
                        "description": "搜索来源过滤（默认同时搜记忆和文档）",
                    },
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="status",
            description="检查 memory_recall 服务连通性和基本统计。返回服务状态、记忆数量等。用于诊断连接问题。",
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
        Tool(
            name="update",
            description="更新一条记忆（版本化）。创建新版本并标记旧版本为 is_latest=false，自动建立 'updates' 关系。适合修正或补充已有记忆。",
            inputSchema={
                "type": "object",
                "properties": {
                    "memoryId": {
                        "type": "string",
                        "description": "要更新的记忆 ID",
                    },
                    "content": {
                        "type": "string",
                        "description": "新的记忆内容",
                    },
                },
                "required": ["memoryId", "content"],
            },
        ),
        Tool(
            name="restore",
            description="恢复一条已删除（forget）的记忆。记忆软删除后可通过此工具恢复。",
            inputSchema={
                "type": "object",
                "properties": {
                    "memoryId": {
                        "type": "string",
                        "description": "要恢复的记忆 ID",
                    },
                },
                "required": ["memoryId"],
            },
        ),
        Tool(
            name="context-inject",
            description="统一上下文注入。一次性获取用户画像 + 语义搜索记忆 + 文档片段，后端完成去重和双重图谱扩展（Memory Graph 追踪记忆演进，Entity Graph 追踪实体关系）。比分别调用 profile/search 更高效。",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "用户输入，用于语义搜索相关记忆和文档",
                    },
                    "injectProfile": {
                        "type": "boolean",
                        "description": "是否注入用户画像（默认 false，仅新Session首次注入时设为 true）",
                    },
                    "maxMemories": {
                        "type": "number",
                        "description": "最大记忆数（默认 5，设为 0 可跳过记忆搜索）",
                    },
                    "maxChunks": {
                        "type": "number",
                        "description": "最大文档片段数（默认 3）",
                    },
                    "enableMemoryGraph": {
                        "type": "boolean",
                        "description": "启用记忆图谱扩展（默认 true）",
                    },
                    "enableEntityGraph": {
                        "type": "boolean",
                        "description": "启用实体图谱扩展（默认 true）",
                    },
                    "enableChunksSearch": {
                        "type": "boolean",
                        "description": "启用文档片段搜索（默认 true）",
                    },
                    "memorySimilarityThreshold": {
                        "type": "number",
                        "description": "记忆相似度阈值（默认 0.3，越高越严格，0.3-0.8推荐）",
                    },
                    "chunksSimilarityThreshold": {
                        "type": "number",
                        "description": "文档片段相似度阈值（默认 0.3，越高越严格，0.3-0.8推荐）",
                    },
                    "memoryGraphDepth": {
                        "type": "number",
                        "description": "记忆图谱遍历深度（默认 2，1-5）",
                    },
                    "memoryGraphNodes": {
                        "type": "number",
                        "description": "记忆图谱最大节点数（默认 5，1-20）",
                    },
                    "entityGraphDepth": {
                        "type": "number",
                        "description": "实体图谱遍历深度（默认 2，1-5）",
                    },
                    "entityGraphNodes": {
                        "type": "number",
                        "description": "实体图谱最大节点数（默认 3，1-20）",
                    },
                },
                "required": ["query"],
            },
        ),
    ]


# ── 工具调用分发 ──────────────────────────────────────────────────
@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    try:
        handler = {
            "add": _handle_add,
            "search": _handle_search,
            "profile": _handle_profile,
            "forget": _handle_forget,
            "list": _handle_list,
            "extract-memory": _handle_extract_memory,
            "hybrid-search": _handle_hybrid_search,
            "status": _handle_status,
            "update": _handle_update,
            "restore": _handle_restore,
            "context-inject": _handle_context_inject,
        }.get(name)
        if handler:
            return await handler(arguments)
        return [TextContent(type="text", text=f"未知工具: {name}")]
    except httpx.HTTPStatusError as e:
        detail = e.response.text[:100] if e.response.status_code < 500 else ""
        return [TextContent(type="text", text=f"API 错误 {e.response.status_code}{': ' + detail if detail else ''}")]
    except httpx.ConnectError:
        return [TextContent(type="text", text=f"无法连接 memory_recall 服务 ({API_BASE_URL})，请检查服务是否运行")]
    except Exception as e:
        logger.error(f"工具 {name} 调用失败: {e}", exc_info=True)
        return [TextContent(type="text", text=f"内部错误: {type(e).__name__}，详情已记录日志")]


# ── 各工具实现 ────────────────────────────────────────────────────
async def _handle_add(args: dict) -> list[TextContent]:
    content = args["content"]
    scope = args.get("scope", "project")
    is_static = args.get("isStatic", False)
    memory_type = args.get("type")
    entity_context = args.get("entityContext")
    skip_extraction = args.get("skipExtraction", False)
    async_process = args.get("asyncProcess", True)  # 默认异步，避免超时

    body = {
        "content": content,
        "container_tag": _tag(scope),
        "is_static": is_static,
        "async_process": async_process,
    }
    if memory_type:
        body["metadata"] = {"type": memory_type}
    if entity_context:
        body["entity_context"] = entity_context
    if skip_extraction:
        body["skip_extraction"] = True

    result = await api_request("POST", "/memories", body, timeout=30.0)
    preview = content[:80] + "..." if len(content) > 80 else content
    status = result.get("status", "done")
    status_hint = "（后台处理实体提取中）" if status == "processing" else ""
    return [TextContent(
        type="text",
        text=f'✅ 已存储到 {scope} 范围{status_hint}\nID: {result.get("id", "N/A")}\n内容: "{preview}"',
    )]


async def _handle_search(args: dict) -> list[TextContent]:
    query = args["query"]
    scope = args.get("scope", "project")
    limit = args.get("limit", 10)
    threshold = args.get("threshold", 0.3)

    body = {
        "query": query,
        "container_tag": _tag(scope),
        "limit": limit,
        "threshold": threshold,
    }

    result = await api_request("POST", "/search", body, timeout=60.0)
    memories = result.get("results", result.get("memories", result if isinstance(result, list) else []))
    if not isinstance(memories, list):
        memories = [memories] if memories else []

    if not memories:
        return [TextContent(type="text", text=f"未找到与 '{query}' 相关的记忆")]

    lines = [f"🔍 搜索 '{query}' 找到 {len(memories)} 条记忆:\n"]
    for i, m in enumerate(memories[:limit], 1):
        if isinstance(m, dict):
            mid = m.get("id", "")
            c = m.get("content", "")
            s = m.get("similarity", "")
            sim = f" (相似度: {s:.2f})" if isinstance(s, (int, float)) else ""
            id_str = f"[{mid[:8]}] " if mid else ""
            preview = c[:200] + "..." if len(c) > 200 else c
            lines.append(f"{i}. {id_str}{preview}{sim}")
            if mid:
                lines.append(f"   ID: {mid}")
        else:
            lines.append(f"{i}. {m}")

    return [TextContent(type="text", text="\n".join(lines))]


async def _handle_profile(args: dict) -> list[TextContent]:
    params = {"container_tag": USER_TAG}
    query = args.get("query")
    if query:
        params["query"] = query

    result = await api_request("GET", "/profile", params=params)

    profile = result.get("profile", result)
    static = profile.get("static", []) if isinstance(profile, dict) else []
    dynamic = profile.get("dynamic", []) if isinstance(profile, dict) else []

    if not static and not dynamic:
        return [TextContent(type="text", text="暂无用户画像数据")]

    lines = []
    if static:
        lines.append("## 永久特征")
        for f in static:
            lines.append(f"- {f}")
    if dynamic:
        lines.append("\n## 近期活动")
        for f in dynamic:
            lines.append(f"- {f}")

    return [TextContent(type="text", text="\n".join(lines))]


async def _handle_forget(args: dict) -> list[TextContent]:
    memory_id = args["memoryId"]
    await api_request("POST", f"/memories/{quote(memory_id, safe='')}/forget")
    return [TextContent(type="text", text=f"✅ 已删除记忆 {memory_id}")]


async def _handle_list(args: dict) -> list[TextContent]:
    scope = args.get("scope", "project")
    limit = args.get("limit", 20)

    params = {
        "container_tag": _tag(scope),
        "limit": limit,
    }

    result = await api_request("GET", "/memories", params=params)
    memories = result.get("memories", result if isinstance(result, list) else [])
    if not isinstance(memories, list):
        memories = [memories] if memories else []
    count = result.get("count", len(memories))

    if not memories:
        return [TextContent(type="text", text=f"{scope} 范围内暂无记忆")]

    lines = [f"📋 {scope} 范围记忆列表 (共 {count} 条，显示前 {len(memories)} 条):\n"]
    for i, m in enumerate(memories, 1):
        if isinstance(m, dict):
            c = m.get("content", "")
            mid = m.get("id", "")
            is_s = "📌" if m.get("is_static") else "📝"
            preview = c[:100] + "..." if len(c) > 100 else c
            lines.append(f"{i}. {is_s} [{mid[:8]}] {preview}")
            if mid:
                lines.append(f"   ID: {mid}")
        else:
            lines.append(f"{i}. {m}")

    return [TextContent(type="text", text="\n".join(lines))]


async def _handle_extract_memory(args: dict) -> list[TextContent]:
    summary = args["summary"]
    language = args.get("language", "zh_CN")

    body = {
        "summary": summary,
        "language": language,
    }

    result = await api_request("POST", "/extract-memory", body, timeout=60.0)
    memories = result.get("memories", [])
    has_worthwhile = result.get("has_worthwhile", False)

    if not has_worthwhile or not memories:
        return [TextContent(type="text", text="本次会话无需提取新记忆（内容为临时状态或已在记忆中）")]

    lines = [f"💡 提取到 {len(memories)} 条值得保存的记忆:\n"]
    for i, m in enumerate(memories, 1):
        if isinstance(m, dict):
            c = m.get("content", "")
            t = m.get("type", "")
            r = m.get("reason", "")
            lines.append(f"{i}. [{t}] {c}")
            if r:
                lines.append(f"   原因: {r}")
        else:
            lines.append(f"{i}. {m}")

    lines.append("\n使用 add 工具保存这些记忆")
    return [TextContent(type="text", text="\n".join(lines))]


async def _handle_hybrid_search(args: dict) -> list[TextContent]:
    query = args["query"]
    scope = args.get("scope", "project")
    limit = args.get("limit", 10)
    threshold = args.get("threshold", 0.5)
    sources = args.get("sources")

    body = {
        "query": query,
        "container_tag": _tag(scope),
        "limit": limit,
        "threshold": threshold,
    }
    if sources:
        body["sources"] = sources

    result = await api_request("POST", "/search/hybrid", body, timeout=60.0)
    results = result if isinstance(result, list) else result.get("results", [])
    if not isinstance(results, list):
        results = [results] if results else []

    if not results:
        return [TextContent(type="text", text=f"混合搜索 '{query}' 未找到结果")]

    lines = [f"🔍 混合搜索 '{query}' 找到 {len(results)} 条结果:\n"]
    for i, r in enumerate(results, 1):
        if isinstance(r, dict):
            rid = r.get("id", "")
            c = r.get("content", "")
            src = r.get("source", "")
            sim = r.get("similarity", "")
            doc_title = r.get("document_title", "")
            sim_str = f" (相似度: {sim:.2f})" if isinstance(sim, (int, float)) else ""
            src_icon = "🧠" if src == "memory" else "📄"
            id_str = f"[{rid[:8]}] " if rid else ""
            prefix = f"[{doc_title}] " if doc_title else ""
            preview = c[:200] + "..." if len(c) > 200 else c
            lines.append(f"{i}. {src_icon} {id_str}{prefix}{preview}{sim_str}")
        else:
            lines.append(f"{i}. {r}")

    return [TextContent(type="text", text="\n".join(lines))]


async def _handle_status(args: dict) -> list[TextContent]:
    try:
        # 记忆数（用 total 字段，不受 limit 影响）
        mem_result = await api_request("GET", "/memories", params={"container_tag": PROJECT_TAG, "limit": 1}, timeout=5.0)
        mem_count = mem_result.get("total", mem_result.get("count", 0)) if isinstance(mem_result, dict) else "?"
        return [TextContent(
            type="text",
            text=f"✅ memory_recall 服务正常运行\n"
                 f"API: {API_BASE_URL}\n"
                 f"用户标签: {USER_TAG}\n"
                 f"项目标签: {PROJECT_TAG}\n"
                 f"记忆总数: {mem_count}",
        )]
    except Exception as e:
        return [TextContent(
            type="text",
            text=f"❌ memory_recall 服务不可用\n"
                 f"API: {API_BASE_URL}\n"
                 f"错误: {type(e).__name__}",
        )]


async def _handle_update(args: dict) -> list[TextContent]:
    memory_id = args["memoryId"]
    content = args["content"]

    body = {"content": content}
    result = await api_request("POST", f"/memories/{quote(memory_id, safe='')}/update", body, timeout=60.0)
    new_id = result.get("id", "N/A")
    return [TextContent(
        type="text",
        text=f"✅ 记忆已更新（版本化）\n"
             f"旧 ID: {memory_id}\n"
             f"新 ID: {new_id}\n"
             f"新内容: \"{content[:80]}{'...' if len(content) > 80 else ''}\"",
    )]


async def _handle_restore(args: dict) -> list[TextContent]:
    memory_id = args["memoryId"]
    result = await api_request("POST", f"/memories/{quote(memory_id, safe='')}/restore")
    restored = result.get("restored", False)
    if restored:
        return [TextContent(type="text", text=f"✅ 已恢复记忆 {memory_id}")]
    return [TextContent(type="text", text=f"⚠️ 恢复记忆 {memory_id} 失败（可能不存在或未被删除）")]


async def _handle_context_inject(args: dict) -> list[TextContent]:
    query = args["query"]
    max_memories = args.get("maxMemories", 5)
    max_chunks = args.get("maxChunks", 3)
    enable_memory_graph = args.get("enableMemoryGraph", True)
    enable_entity_graph = args.get("enableEntityGraph", True)
    enable_chunks_search = args.get("enableChunksSearch", True)
    memory_similarity_threshold = args.get("memorySimilarityThreshold")
    chunks_similarity_threshold = args.get("chunksSimilarityThreshold")
    memory_graph_depth = args.get("memoryGraphDepth")
    memory_graph_nodes = args.get("memoryGraphNodes")
    entity_graph_depth = args.get("entityGraphDepth")
    entity_graph_nodes = args.get("entityGraphNodes")
    inject_profile = args.get("injectProfile", False)

    body = {
        "user_tag": USER_TAG,
        "project_tag": PROJECT_TAG,
        "query": query,
        "config": {
            "max_memories": max_memories,
            "max_chunks": max_chunks,
            "inject_profile": inject_profile,
            "enable_semantic_dedup": True,
            "enable_memory_graph": enable_memory_graph,
            "enable_entity_graph": enable_entity_graph,
            "enable_chunks_search": enable_chunks_search,
        },
    }

    # 可选参数：只有明确传入时才覆盖后端默认值
    if memory_similarity_threshold is not None:
        body["config"]["memory_similarity_threshold"] = memory_similarity_threshold
    if chunks_similarity_threshold is not None:
        body["config"]["chunks_similarity_threshold"] = chunks_similarity_threshold
    if memory_graph_depth is not None:
        body["config"]["memory_graph_depth"] = memory_graph_depth
    if memory_graph_nodes is not None:
        body["config"]["memory_graph_nodes"] = memory_graph_nodes
    if entity_graph_depth is not None:
        body["config"]["entity_graph_depth"] = entity_graph_depth
    if entity_graph_nodes is not None:
        body["config"]["entity_graph_nodes"] = entity_graph_nodes

    result = await api_request("POST", "/context-inject", body, timeout=60.0)

    context_text = result.get("context", "")
    sources = result.get("sources", {})
    stats = result.get("stats", {})

    lines = []
    if context_text:
        lines.append(context_text)
    else:
        lines.append("未找到相关上下文")

    if stats:
        total = stats.get("total_items", 0)
        after_dedup = stats.get("after_dedup", 0)
        deduped = stats.get("deduped_count", 0)
        lines.append(f"\n--- 统计: {after_dedup} 条（去重前 {total}，去重 {deduped} 条）---")

    if sources:
        src_parts = []
        for src_type, src_items in sources.items():
            if isinstance(src_items, list) and src_items:
                src_parts.append(f"{src_type}: {len(src_items)}")
        if src_parts:
            lines.append(f"来源: {', '.join(src_parts)}")

    return [TextContent(type="text", text="\n".join(lines))]


# ── 启动 ──────────────────────────────────────────────────────────
async def main():
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
