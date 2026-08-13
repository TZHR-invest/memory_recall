# Memory Recall 架构与模块地图

> 状态: ACTIVE · 版本: v1.0 · 最后更新: 2026-08-13
>
> 后端代码结构与各模块职责（v5 端点层）。领域模型见 [ENTITY_DESIGN.md](ENTITY_DESIGN.md)，
> 核心数据流见 [MEMORY_FLOW.md](MEMORY_FLOW.md)。

## 分层概览

- `apps/api/main.py` — FastAPI 装配。注册 `src.api`（`memories`、`graph`、`auth_endpoints`、`embed`、
  `context_inject`）与 `src.routes`（`health`）的路由。**新路由必须加进这个 `include_router` 块**。
- `src/api/` — 当前 v5 端点层：每个域一个薄 APIRouter（`memories.py` 还承载 `/profile`、`/search`、
  `/documents*`、`/extract-memory`）。`auth.py` 是鉴权依赖层（key 管理、权限校验、限流、
  `verify_container_ownership`），**本身不是 router**。`src/routes/` 是遗留层，只剩 `health.py`
  （含过时的 `/api/stats*`）。

## 核心服务（`src/services/core/`，全部业务逻辑）

- `context_inject_service.py` — **所有召回/注入逻辑**（语义搜索 → 记忆图谱 → 实体图谱 → chunks → 去重 → markdown 格式化）；
- `memory_store.py` — 记忆 CRUD / 版本化 / 向量检索 / 实体图谱写入；
- `document_store.py` — 文档与 chunks 存储、去重、chunk 检索；
- `relation_service.py` — 关系检测、版本历史（`get_version_history`，走 updates 边遍历）；
- `profile_service.py`、`entity_extraction.py`、`llm_entity_extraction.py`、`semantic_dedup_service.py`。

## LLM / Embedding 客户端

- `src/llm/client.py`、`src/embedding/client.py` — 火山引擎客户端，惰性单例 `get_llm_client()` / `get_embedding_client()`。
- 服务是模块级单例（`memory_store`、`db`、`settings`、`context_inject_service` …），导入时构造。

## 关键代码约束

### 循环导入是故意的（勿"修复"）

`profile_service` 在模块顶层 import `memory_store`，所以 `memory_store` 只能在函数内
（`process_memory_async`）惰性 import `profile_service`；`relation_service` 同理
（`create_derived_memory` 内惰性 import `memory_store`）。改成顶层导入会导致启动失败。

### 死代码（勿当功能来源）

`src/models/`、`src/services/{prompts,embedding_cache}.py` 是死代码，不要从里面挖功能。
（`query_parser` / `keyword_extractor` / `image` / `openclaw` 已删除。）

### 一次性脚本

`apps/api/scripts/` 是一类维护脚本（db 优化、实体清理、备份），不属于应用。

### 版本"取代"语义与版本历史

两种"取代"语义（自动关系检测降级 vs 显式版本链）的完整说明见
[ENTITY_DESIGN.md](ENTITY_DESIGN.md#2-记忆模型)。`memory_store.get_version_chain` 是零调用死代码；
真实历史走 `relation_service.get_version_history`（updates 边遍历）。

*状态: ACTIVE · 版本: v1.0 · 最后更新: 2026-08-13*
