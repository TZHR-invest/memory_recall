"""
Memory Recall MCP Server for Hermes Agent
通过 MCP 协议暴露 memory_recall HTTP API 给 Hermes 使用

与 Hermes 原生 memory 共存：
- 原生 memory: 精简关键事实（自动注入每轮对话）
- memory_recall: 大量细节、语义搜索、知识图谱（按需调用）

15 个工具:
1. add              - 存储记忆
2. search           - 语义搜索记忆
3. profile          - 用户画像
4. forget           - 删除记忆
5. list             - 列出记忆
6. import-docs      - 导入文档
7. extract-memory   - 从会话摘要提取记忆
8. hybrid-search    - 混合搜索（记忆+文档）
9. status           - 系统状态检查
10. update          - 更新记忆（版本化）
11. restore         - 恢复已删除记忆
12. context-inject  - 统一上下文注入（支持双重图谱扩展）
13. list-docs       - 列出文档
14. read-doc        - 读取文档原文
15. delete-doc      - 删除文档

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
USER_TAG = os.environ.get("MEMORY_RECALL_USER_TAG", "b262d2f1-6232-49f4-820e-3f5e4cf6b956")
PROJECT_TAG = os.environ.get("MEMORY_RECALL_PROJECT_TAG", "b262d2f1-6232-49f4-820e-3f5e4cf6b956_hermes")

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
            timeout=30.0,
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
        resp = await client.get(path, params=params, timeout=timeout or 30.0)
    else:
        resp = await client.request(method, path, json=body, params=params, timeout=timeout or 30.0)
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
                        "description": "相似度阈值 0-1（默认 0.6）",
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
            name="import-docs",
            description="导入文档到 memory_recall。文档会自动分块、生成 embedding，可通过 hybrid-search 或 context-inject 检索。适合导入项目文档、技术规范、API 文档等。",
            inputSchema={
                "type": "object",
                "properties": {
                    "content": {
                        "type": "string",
                        "description": "文档内容",
                    },
                    "title": {
                        "type": "string",
                        "description": "文档标题",
                    },
                    "source": {
                        "type": "string",
                        "description": "文档来源（如文件路径、URL）",
                    },
                    "docType": {
                        "type": "string",
                        "enum": ["text", "markdown", "code"],
                        "description": "文档类型（默认 text）",
                    },
                    "scope": {
                        "type": "string",
                        "enum": ["user", "project"],
                        "description": "存储范围（默认 project）",
                    },
                },
                "required": ["content", "title"],
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
        Tool(
            name="list-docs",
            description="列出已导入的文档。返回文档 ID、标题、类型、chunk 数量等元数据，支持分页。",
            inputSchema={
                "type": "object",
                "properties": {
                    "scope": {
                        "type": "string",
                        "enum": ["user", "project"],
                        "description": "存储范围（默认 project）",
                    },
                    "limit": {
                        "type": "number",
                        "description": "最大返回数量（默认 20）",
                    },
                    "offset": {
                        "type": "number",
                        "description": "分页偏移（默认 0）",
                    },
                },
            },
        ),
        Tool(
            name="read-doc",
            description="按 ID 读取文档完整原文。返回文档内容、元数据和 chunk 列表。",
            inputSchema={
                "type": "object",
                "properties": {
                    "documentId": {
                        "type": "string",
                        "description": "文档 ID（从 list-docs 或 import-docs 获取）",
                    },
                },
                "required": ["documentId"],
            },
        ),
        Tool(
            name="delete-doc",
            description="删除一个文档及其所有 chunks。不可恢复。",
            inputSchema={
                "type": "object",
                "properties": {
                    "documentId": {
                        "type": "string",
                        "description": "要删除的文档 ID",
                    },
                },
                "required": ["documentId"],
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
            "import-docs": _handle_import_docs,
            "extract-memory": _handle_extract_memory,
            "hybrid-search": _handle_hybrid_search,
            "status": _handle_status,
            "update": _handle_update,
            "restore": _handle_restore,
            "context-inject": _handle_context_inject,
            "list-docs": _handle_list_docs,
            "read-doc": _handle_read_doc,
            "delete-doc": _handle_delete_doc,
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

    body = {
        "content": content,
        "container_tag": _tag(scope),
        "is_static": is_static,
    }
    if memory_type:
        body["metadata"] = {"type": memory_type}
    if entity_context:
        body["entity_context"] = entity_context
    if skip_extraction:
        body["skip_extraction"] = True

    result = await api_request("POST", "/memories", body, timeout=60.0)
    preview = content[:80] + "..." if len(content) > 80 else content
    return [TextContent(
        type="text",
        text=f'✅ 已存储到 {scope} 范围\nID: {result.get("id", "N/A")}\n内容: "{preview}"',
    )]


async def _handle_search(args: dict) -> list[TextContent]:
    query = args["query"]
    scope = args.get("scope", "project")
    limit = args.get("limit", 10)
    threshold = args.get("threshold", 0.6)

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
        else:
            lines.append(f"{i}. {m}")

    return [TextContent(type="text", text="\n".join(lines))]


async def _handle_import_docs(args: dict) -> list[TextContent]:
    content = args["content"]
    title = args["title"]
    source = args.get("source", "")
    doc_type = args.get("docType", "text")
    scope = args.get("scope", "project")

    body = {
        "content": content,
        "container_tag": _tag(scope),
        "title": title,
        "source": source,
        "doc_type": doc_type,
    }

    result = await api_request("POST", "/documents", body, timeout=60.0)
    doc_id = result.get("id", "N/A")
    doc_status = result.get("status", "queued")
    status_hint = "（文档正在后台处理，处理完成后可通过搜索检索）" if doc_status == "queued" else ""
    return [TextContent(
        type="text",
        text=f'✅ 文档已提交到 {scope} 范围{status_hint}\nID: {doc_id}\n标题: "{title}"',
    )]


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
        # 记忆数
        mem_result = await api_request("GET", "/memories", params={"container_tag": PROJECT_TAG, "limit": 1}, timeout=5.0)
        mem_count = mem_result.get("count", 0) if isinstance(mem_result, dict) else "?"
        # 文档数
        doc_count = "?"
        try:
            doc_result = await api_request("GET", "/documents", params={"container_tag": PROJECT_TAG, "limit": 1}, timeout=5.0)
            doc_count = doc_result.get("total", 0) if isinstance(doc_result, dict) else "?"
        except Exception:
            pass
        return [TextContent(
            type="text",
            text=f"✅ memory_recall 服务正常运行\n"
                 f"API: {API_BASE_URL}\n"
                 f"用户标签: {USER_TAG}\n"
                 f"项目标签: {PROJECT_TAG}\n"
                 f"记忆总数: {mem_count}\n"
                 f"文档总数: {doc_count}",
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


async def _handle_list_docs(args: dict) -> list[TextContent]:
    scope = args.get("scope", "project")
    limit = args.get("limit", 20)
    offset = args.get("offset", 0)

    params = {
        "container_tag": _tag(scope),
        "limit": limit,
        "offset": offset,
    }
    result = await api_request("GET", "/documents", params=params)

    documents = result.get("documents", [])
    total = result.get("total", 0)

    if not documents:
        return [TextContent(type="text", text=f"📂 {scope} 范围内无文档")]

    lines = [f"📂 {scope} 范围文档列表（共 {total} 个，显示 {len(documents)} 个）：\n"]
    for doc in documents:
        doc_id = doc.get("id", "N/A")
        title = doc.get("title", "无标题")
        doc_type = doc.get("doc_type", "?")
        chunk_count = doc.get("chunk_count", 0)
        created = doc.get("created_at", "?")
        lines.append(f"  📄 [{doc_id[:8]}] \"{title}\" | 类型:{doc_type} | chunks:{chunk_count} | {created}")

    if total > offset + limit:
        lines.append(f"\n💡 还有更多（offset={offset + limit}）")

    return [TextContent(type="text", text="\n".join(lines))]


async def _handle_read_doc(args: dict) -> list[TextContent]:
    document_id = args["documentId"]

    result = await api_request("GET", f"/documents/{quote(document_id, safe='')}")

    doc_id = result.get("id", "N/A")
    content = result.get("content", "")
    container_tag = result.get("container_tag", "")
    metadata = result.get("metadata", {})
    doc_status = result.get("status", "?")
    created = result.get("created_at", "?")

    # 如果 API 没返回 content（documents 表不存原文），通过 chunks 拼接
    if not content:
        try:
            chunks_result = await api_request(
                "GET",
                f"/documents/{quote(document_id, safe='')}/chunks",
                params={"limit": 200},
            )
            chunks = chunks_result if isinstance(chunks_result, list) else chunks_result.get("chunks", [])
            if chunks:
                chunks.sort(key=lambda c: c.get("position", 0))
                # 拼接 chunks，去除 overlap 重复
                parts = []
                for c in chunks:
                    text = c.get("content", "")
                    if not text:
                        continue
                    # 如果上一段结尾和这一段开头重叠，去重
                    if parts and text:
                        # 检查 20-100 字符的 overlap
                        found_overlap = False
                        for overlap_len in range(min(100, len(text), len(parts[-1])), 15, -1):
                            if parts[-1].rstrip().endswith(text[:overlap_len].strip()):
                                text = text[overlap_len:]
                                found_overlap = True
                                break
                    if text.strip():
                        parts.append(text)
                content = "\n\n".join(parts)
        except Exception:
            content = "（无法获取原文，文档可能未存储完整内容）"

    lines = [
        f"📄 文档详情",
        f"ID: {doc_id}",
        f"容器: {container_tag}",
        f"状态: {doc_status}",
        f"创建: {created}",
    ]

    if metadata:
        lines.append(f"元数据: {json.dumps(metadata, ensure_ascii=False)}")

    lines.append(f"\n--- 原文 ---\n{content}")

    return [TextContent(type="text", text="\n".join(lines))]


async def _handle_delete_doc(args: dict) -> list[TextContent]:
    document_id = args["documentId"]

    await api_request("DELETE", f"/documents/{quote(document_id, safe='')}")
    return [TextContent(
        type="text",
        text=f"✅ 已删除文档 {document_id} 及其所有 chunks",
    )]


# ── 启动 ──────────────────────────────────────────────────────────
async def main():
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
