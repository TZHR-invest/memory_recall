# Recall Trace - 详细开发设计

> **文档说明**：本文档是 Recall Trace 功能（`docs/RECALL_TRACE_DESIGN.md`）的落地实现设计。描述表结构、数据模型、埋点方案、API、页面、配置与测试方案。
>
> **状态**：开发中
>
> **涉及代码**：
> - `src/services/core/context_inject_service.py`（召回管线，埋点）
> - `src/services/core/semantic_dedup_service.py`（去重，记录丢弃明细）
> - `src/api/context_inject.py`（`include_trace` 参数）
> - `src/api/debug.py`（新增，debug API）
> - `src/background/scheduler.py`（新增清理任务）
> - `web/debug.html`（新增，debug 页面）
> - `schema.sql` / `src/config.py` / `main.py`

---

## 1. 总体流程

```
┌─ 线上调用 ─────────────────────────────────────────────────┐
│ POST /context-inject  (TRACE_ENABLED=true)                │
│    └─ context_inject_service.inject()/inject_with_tags()  │
│        每个渠道调用点埋点 → 填充 RecallTrace               │
│        ├─ 采样命中？ → 异步写入 recall_traces 表           │
│        └─ include_trace=true？ → 响应体附加 trace 字段     │
└───────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─ Debug 页面 ───────────────────────────────────────────────┐
│ web/debug.html                                             │
│  ├─ POST /debug/traces/run  触发真实召回（即时看 trace）   │
│  ├─ GET  /debug/traces      最近 trace 列表（摘要）        │
│  └─ GET  /debug/traces/{id} 单条完整详情（逐渠道）         │
│  ├─ 对比模式：同一 query 两套 config 并排渲染              │
└───────────────────────────────────────────────────────────┘
```

**核心原则**：只做采集与展示，**不改变任何召回逻辑**。埋点对原逻辑只读、可整体开关。

---

## 2. 数据模型

### 2.1 recall_traces 表

```sql
CREATE TABLE IF NOT EXISTS recall_traces (
    id VARCHAR(40) PRIMARY KEY DEFAULT 'trace_' || replace(gen_random_uuid()::text, '-', ''),
    container_tag VARCHAR(100) NOT NULL,
    mode VARCHAR(20) NOT NULL DEFAULT 'single',   -- single / tags
    user_tag VARCHAR(100),
    project_tag VARCHAR(100),
    query TEXT,
    config JSONB DEFAULT '{}',                     -- 完整配置快照，用于复现
    channels JSONB DEFAULT '{}',                   -- 逐渠道明细（核心）
    dedup JSONB DEFAULT '{}',                      -- 去重明细
    final JSONB DEFAULT '[]',                      -- 最终注入顺序
    elapsed_ms JSONB DEFAULT '{}',                 -- 各渠道耗时
    total_ms FLOAT DEFAULT 0,
    summary JSONB DEFAULT '{}',                    -- 列表页摘要（各渠道条数，避免列表查大 JSON）
    error TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_recall_traces_container ON recall_traces(container_tag, created_at DESC);
```

- `id` 采用与 memories 一致的 `trace_` 前缀 + uuid 去横线
- `config` 全量快照（含 `include_trace` 外的全部参数），支持复现与对比
- 列表接口只返回 `summary` + 标量列，不返回 `channels`/`dedup`/`final` 大字段

### 2.2 channels 结构（JSONB）

```jsonc
{
  "profile": {
    "enabled": true,                // config.inject_profile
    "static_count": 5,
    "dynamic_count": 3,
    "items": ["内容截断..."]        // 注入的画像内容
  },
  "vector": {
    "threshold": 0.3,
    "hits": [                       // 向量检索全部候选（含被阈值过滤的）
      { "id": "mem_...", "content": "截断内容", "similarity": 0.82, "passed": true }
    ]
  },
  "memory_graph": {
    "enabled": true,
    "paths": [                      // 记忆演进扩展路径
      { "from_id": "mem_a", "relation_type": "extends", "to_id": "mem_b",
        "content": "截断内容", "added": true }
    ]
  },
  "entity_graph": {
    "enabled": true,
    "query_entities": ["张三"],
    "entity_paths": [               // 实体关系遍历路径
      { "entity": "张三", "relation_type": "works_at", "to_entity": "字节跳动" }
    ],
    "memories": [                   // 通过实体图找到的记忆
      { "id": "mem_...", "content": "截断内容" }
    ]
  },
  "chunks": {
    "threshold": 0.3,
    "hits": [                       // 向量检索文档分块
      { "id": "chk_...", "document_id": "doc_...", "title": "...",
        "content": "截断内容", "similarity": 0.73, "passed": true }
    ],
    "entity_hits": []               // 实体命中分块（query 实体 → chunk）
  }
}
```

### 2.3 dedup / final 结构

```jsonc
{
  "dedup": {
    "threshold": 0.85,
    "kept":   [{ "id": "...", "source": "userMemory" }],
    "dropped":[{ "id": "...", "source": "userMemory",
                 "duplicate_of": { "id": "...", "source": "userMemory" },
                 "similarity": 0.89 }]
  },
  "final": [   // 实际注入顺序（与线上 context 输出一致）
    { "id": "...", "content": "截断内容", "source": "profile|userMemory|chunk", "relation_type": null }
  ]
}
```

---

## 3. 埋点设计（context_inject_service 改动）

### 3.1 采集器 RecallTrace

新增 `src/services/core/recall_trace_service.py`，提供 `RecallTrace` 数据类与存储服务：

```python
class RecallTrace:
    def __init__(self, mode, container_tag, user_tag, project_tag, query, config): ...
    # 各渠道记录方法（幂等、只增不改原逻辑）：
    def record_profile(self, static, dynamic, enabled) -> None
    def record_vector(self, hits, threshold) -> None        # hits 含 passed 计算
    def record_memory_graph(self, path, added) -> None
    def record_entity_graph(self, ...) -> None
    def record_chunks(self, hits, threshold, entity_hits) -> None
    def record_dedup(self, kept, dropped, threshold) -> None
    def record_final(self, items) -> None
    def mark_elapsed(self, channel, ms) -> None
    def to_dict(self) -> dict    # content 统一截断后输出
```

### 3.2 埋点位置（只新增采集调用，不改返回值）

| 调用点 | 采集内容 |
|--------|---------|
| `_get_profile` 调用处 | 注入开关、static/dynamic 数量与内容 |
| `_get_memories` 内部向量检索后 | 全部候选 + threshold + passed |
| `_get_memories` 内部记忆图遍历处 | 每个扩展路径 `(from, rel, to, added)` |
| `_get_memories` 内部实体图遍历处 | query 实体、实体路径、找到的记忆 |
| `_get_chunks` 内部 | 向量命中 + threshold、实体命中 |
| `semantic_dedup_service.deduplicate` 调用处 | kept / dropped（含 duplicate_of）|
| 格式化后 | `final` 注入顺序（去重后的 items 顺序）|
| 全程 | 各渠道耗时（`time.monotonic()` 分段计时）|

**实现方式**：`inject()` / `inject_with_tags()` 内部创建 `RecallTrace`，作为参数传入 `_get_memories(trace=...)`、`_get_chunks(trace=...)`，在各子方法内部填充。子方法签名保持不变（新增可选关键字参数），不破坏外部调用。

**计时**：对 `inject_profile`/`_get_memories`/`_get_chunks`/`deduplicate`/`format` 五段分别计时。

### 3.3 落库与返回

- 落库判断：`TRACE_ENABLED and (include_trace or random() < TRACE_SAMPLE_RATE)`。`include_trace=true` 强制记录（debug 页面即时场景）。
- 落库：`await recall_trace_service.save(trace)`，`INSERT` 单行，不阻塞召回主流程（数据量小，直接 await 保证不丢）。
- 返回：`include_trace=true` 时，`inject()` 返回 dict 增加 `"trace": trace.to_dict()`。
- 异常时：service 捕获异常后 `trace.mark_error()` 并落库（记录失败路径），再向上抛出。

### 3.4 semantic_dedup_service 改动（兼容）

`deduplicate()` 增加可选参数 `dropped_log: Optional[list] = None`：

```python
async def deduplicate(self, items, threshold=0.85, dropped_log=None):
    ...
    if is_duplicate and dropped_log is not None:
        dropped_log.append({
            "id": item.id, "source": item.source,
            "duplicate_of": {"id": kept_item.id, "source": kept_item.source},
            "similarity": round(similarity, 4),
        })
```

默认 `None` 时行为与现在完全一致，零影响。

---

## 4. API 设计

### 4.1 context-inject 扩展（向后兼容）

`ContextInjectRequest` 增加 `include_trace: bool = False`；`ContextInjectResponse` 增加 `trace: Optional[Dict[str, Any]] = None`。线上调用不传则无感。

### 4.2 新增 debug API（`src/api/debug.py`）

所有端点复用现有认证：`require_permission("read")` + `verify_container_ownership`，保证与容器隔离一致。

| 端点 | 方法 | 说明 |
|------|------|------|
| `/debug/traces` | GET | 最近 trace 列表（分页），返回摘要字段，`?container_tag=&limit=&offset=` |
| `/debug/traces/{trace_id}` | GET | 单条完整详情（含 channels/dedup/final） |
| `/debug/traces/run` | POST | 触发一次真实召回并返回 `{result, trace}`，请求体复用 `ContextInjectRequest`（强制 `include_trace=true`）|

### 4.3 scheduler 清理任务

`src/background/scheduler.py` 注册 `trace_cleanup_task`，每 60 分钟删除 `created_at < now - TRACE_RETENTION_DAYS` 的记录。

---

## 5. 配置项（src/config.py + .env）

| 配置 | 默认 | 说明 |
|------|------|------|
| `TRACE_ENABLED` | `True` | 总开关（生产可关） |
| `TRACE_SAMPLE_RATE` | `1.0` | 采样率 0~1，`include_trace` 不受采样影响 |
| `TRACE_RETENTION_DAYS` | `7` | 保留天数，超期由调度任务清理 |
| `TRACE_CONTENT_MAX_LEN` | `200` | trace 中内容截断长度（隐私与体积控制） |

---

## 6. Debug 页面（web/debug.html）

独立单文件页面（现有 `index.html` 面向旧版 `/api/v1` API，不兼容，不修改它）。结构：

```
┌─ 顶部：API Key 输入（X-API-Key，存 localStorage）+ 基础地址 ─┐
├─ 搜索区：query + user_tag/project_tag + 高级 config（折叠）  │
│   阈值：记忆相似度/文档相似度/去重阈值                        │
│   开关：注入画像/语义去重/记忆图/实体图/文档搜索             │
│   数量：max_memories/max_chunks/图深度                       │
│   [执行召回]  [对比模式]                                     │
├─ 结果区（本次 trace 即时展示，逐渠道展开）                    │
│   向量路 / 记忆图路 / 实体图路 / chunk 路 / 去重路 / 最终注入 │
├─ 最近 trace 列表（摘要卡片，点击加载详情）                    │
└─ 对比模式：并排两栏（A config vs B config），差异高亮        │
```

页面实现要点：
- 纯原生 JS + fetch，无依赖，样式参考 `index.html` 的浅色风格（该页为调试工具，用浅色便于长时间阅读）
- 逐渠道区块渲染：相似度色阶（>=0.8 绿 / >=0.5 橙 / <0.5 灰），被过滤项置灰并标注原因（`低于阈值 0.30` / `与 #xxx 重复 0.89`）
- 对比模式：两次 `POST /debug/traces/run`，并排渲染，逐条高亮"A 有 B 无 / B 有 A 无"
- 详情页路由用 `#id=xxx` 简单哈希，无需框架

---

## 7. 变更文件清单

| 文件 | 变更 |
|------|------|
| `docs/RECALL_TRACE_DEV.md` | 新增（本文档） |
| `apps/api/schema.sql` | 新增 recall_traces 表 + 索引 |
| `apps/api/src/config.py` | 新增 TRACE_* 配置 |
| `apps/api/src/services/core/recall_trace_service.py` | 新增：RecallTrace + 存储服务 |
| `apps/api/src/services/core/context_inject_service.py` | 埋点（只读采集，不改召回逻辑） |
| `apps/api/src/services/core/semantic_dedup_service.py` | deduplicate 增加可选 dropped_log |
| `apps/api/src/api/context_inject.py` | include_trace 参数 + trace 响应字段 |
| `apps/api/src/api/debug.py` | 新增 debug API |
| `apps/api/main.py` | 注册 debug router |
| `apps/api/src/background/scheduler.py` | 注册 trace 清理任务 |
| `apps/api/init_db.py` | 打印列表补充 recall_traces |
| `web/debug.html` | 新增 debug 页面 |
| `apps/api/tests/test_recall_trace.py` | 新增测试 |
| `apps/api/.env.example` | 补充 TRACE_* 配置示例 |
| `apps/api/docker-compose.yml` | 新增 web 服务（python http.server 挂载 `../../web`，端口 3000） |
| `apps/api/src/embedding/client.py` | 暴露 `last_error` / `last_cache_hit`（供埋点读取） |
| `apps/api/src/services/core/recall_embedding_service.py` | 新增：embedding 调用日志服务（`recall_embedding_logs` 表） |
| `apps/api/src/services/core/memory_store.py` | `_generate_embedding` 埋点（创建记忆 embedding 调用日志） |
| `apps/api/schema.sql` | 新增 recall_embedding_logs 表 + 索引 |

**数据库迁移**：docker-entrypoint-initdb.d 只在首次启动执行，运行中的容器需手动执行新表 DDL（`schema.sql` 中 recall_traces 部分）。

---

## 8. 测试方案

1. **单元测试**（mock db）：
   - `RecallTrace.to_dict()` 字段完整性、content 截断
   - `semantic_dedup_service.deduplicate` 传 `dropped_log` 时记录 duplicate_of，不传时行为不变
   - 采样逻辑：`TRACE_SAMPLE_RATE=0` 不落库，`include_trace` 强制落库
2. **集成测试**（真实容器）：
   - 造数据 → `POST /context-inject` → 验证 `recall_traces` 有记录且 channels 各渠道字段正确
   - `include_trace=true` → 响应带 trace
   - `GET /debug/traces` / `GET /debug/traces/{id}` 鉴权与数据正确
   - `POST /debug/traces/run` 触发后生成新 trace
   - 清理任务删除超期数据
3. **页面冒烟**：浏览器/curl 验证 debug.html 各功能区。

---

## 9. Embedding 调用日志（v5.3 扩展）

排查 LLM/embedding 故障（如火山 key 401）时，创建记忆与召回都依赖 embedding API。
新增结构化日志表 `recall_embedding_logs`，记录**每次** embedding 调用的成败与耗时：

| 列 | 含义 |
|----|------|
| `kind` | `memory`（创建记忆）/ `context_query`（召回 query）/ `context_chunks`（文档召回） |
| `ok` / `error` | 成败与错误信息（401 等） |
| `cache_hit` | 是否命中 embedding 缓存（未实际调 API） |
| `elapsed_ms` / `output_dim` | 耗时 / 向量维度 |

**埋点位置**（只读采集，失败不影响主流程）：
- `memory_store._generate_embedding`（同步 create + 异步 process_embedding_async 共用）
- `context_inject_service._get_memories` / `_get_chunks`（query embedding）

**查看方式**：
- `GET /debug/embedding-logs?container_tag=&kind=`（鉴权 + 容器归属过滤）
- debug.html 底部"Embedding 调用日志"区块（按类型过滤）

`src/embedding/client.py` 新增 `last_error` / `last_cache_hit` 实例属性，供埋点读取失败详情。

---

*文档版本：v0.1*
*最后更新：2026-08-09*
*维护者：颓弟*
