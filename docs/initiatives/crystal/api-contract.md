# Crystal API 契约 v1（草稿）

> 状态: 草稿 · 系统: crystal · 版本: v1 · 最后更新: 2026-08-18
> 关联: [实体属性文档](entity-attributes.md)（schema）· [渐进迁移路径](migration-path.md)（Stage A）·
> [里程碑](milestone.md)（M1 前置产物）· [PRD](prd.md)（能力验收 A1–A11）· ADR-0018（命名）
> 定位: 本文是 crystal `/api/v2` 的 **API 层契约**——路由表、鉴权映射、错误规范、请求/响应骨架。
> 各端点的业务语义（对账触发、召回精排、裁决动作）不在此展开，归对账/召回/workbench 设计 v1。
> 本文是 M1（`/api/v2` 骨架）的实施依据；M1 只落"路由 + 鉴权 + 空实现/桩"，业务逻辑随 M2。

## 0. 目标与原则

- **命名空间隔离**：所有 crystal 端点挂 `/api/v2/*`，与 v5 无前缀路由物理并存；ADR-0018。
- **v5 零影响**：M1 合入后旧插件继续走 v5 路由，不受任何影响；回退 = 摘 `/api/v2` 路由。
- **鉴权沿用 X-API-Key**（迁移路径 §7 已拍板 3）：P0 阶段 `owner_type=personal`、`owner_id=keyId`
  由鉴权层直接填，客户端**不传** owner（防越权）；scope 由客户端显式传（与 v5 `container_tag` 同源）。
- **个人 key + API**（PRD 原则）：裁决/洞察核心能力走 API（插件也能调），web 工作台只是可选管理层。
- **不静默丢弃**（MR-017 教训）：召回响应必须携带截断/排除说明（`explain` 字段），A5 验收。
- **幂等与重试友好**（v1 #17）：写接口带 `idempotency_key`，服务端 202 返回既有结果。

## 1. 鉴权映射

### 1.1 鉴权层（复用 v5 auth）

| v5 概念 | crystal 映射 | 说明 |
|---------|-------------|------|
| `X-API-Key` header | 不变 | `get_current_user` 依赖直接复用 |
| `key_id`（api_keys.id） | `owner_id`（personal） | 鉴权层从 key 解出，客户端不可覆盖 |
| `owner_type` | `personal`（P0 恒值） | P1 团队扩展时再加 `team` 与对应鉴权 |
| `container_tag` | **拆成 `scope` + `owner`** | 迁移路径 §7 已拍板 2：`{keyId}_project-<dir>` → `scope=<dir>`；`{keyId}` → `scope=NULL` |
| `verify_container_ownership` | `verify_scope_ownership`（新 helper） | 精确/前缀匹配语义保留：`scope` 允许值 = 由 key_id 推导的合法 scope（见 §1.2） |
| `require_permission("read"/"write")` | 保留 | 读端点 `read`，写端点 `write` |

### 1.2 scope 归属校验（新 helper：`verify_scope_ownership`）

```text
合法 scope 集合（从 key_id 推导，与 v5 container 前缀规则同构）：
  1. scope == NULL（全局：user 级容器 {keyId}）→ 允许
  2. scope 以 key_id + "_" 开头（项目级：{keyId}_project-<dir> 的 <dir> 部分）→ 允许
  3. 其他 → 403
```

- 客户端传 `scope="project-memory_recall"`（不含 key_id 前缀），服务端拼 `{key_id}_project-memory_recall`
  做所有权校验，落库时**只存 scope 部分**（`scope='project-memory_recall'` 或 NULL）。
- 好处：与 v5 container_tag 规则同构（`{keyId}_project-<dir>`），旧插件迁移时只改路径、不改语义；
  scope 字段本身不带 key_id，跨 key 的 scope 碰撞天然隔离（校验时已加前缀）。

### 1.3 admin vs 个人 key

| 角色 | 可访问 | 说明 |
|------|--------|------|
| 个人 key（`permissions` 含 read/write） | `/api/v2/evidence`、`/api/v2/claims`（自己 owner）、`/api/v2/workbench/*`（自己 owner） | 主场景 |
| admin key（`is_test` 或权限含 debug） | `/api/v2/debug/*`（trace/embedding 日志）、迁移端点 | A11 权限隔离：debug 链路与个人数据互不混淆 |

## 2. 路由表（M1 骨架 = 全部列出，M2 填充业务）

> 约定：`{owner}` 路径段不出现——owner 由鉴权层填；`scope` 作为 query/body 参数显式传。

### 2.1 证据层（写侧输入）

| 方法 | 路径 | 权限 | 请求体/参数 | 响应 | 对应 US/验收 |
|------|------|------|------------|------|-------------|
| `POST` | `/api/v2/evidence` | write | `{content, source_kind, scope?, observed_at?, source_ref?, extraction_type?, idempotency_key?}` | `202 {evidence_id, processing_state:"pending"}` | US-E1 / A1 |
| `GET` | `/api/v2/evidence/{id}` | read | — | evidence 详情 + 处理状态 | US-E2 / A1 |
| `GET` | `/api/v2/evidence` | read | `?scope=&source_kind=&state=&limit=&cursor=` | 分页列表（按 observed_at DESC） | US-E2 |
| `GET` | `/api/v2/evidence/{id}/claims` | read | — | 该证据支持的所有 claim（经 claim_evidence） | A2 溯源 |

### 2.2 对账（写路径，M2）

> 对账由 evidence 落库异步触发（写接口不等待对账完成）；显式触发对账为调试/运维端点。

| 方法 | 路径 | 权限 | 请求体/参数 | 响应 | 对应 |
|------|------|------|------------|------|------|
| `POST` | `/api/v2/reconcile/run` | write（admin 亦可） | `{evidence_id?}`（缺省 = 重跑 pending/failed） | `202 {job_id}` | A1 对账触发 |
| `GET` | `/api/v2/reconcile/jobs/{job_id}` | read | — | 对账 job 状态/进度 | US-E2 |

### 2.3 状态查询（召回，M2）

| 方法 | 路径 | 权限 | 参数 | 响应 | 对应 |
|------|------|------|------|------|------|
| `POST` | `/api/v2/search` | read | `{query, scope?, claim_kind?, limit?, include_explain?}` | 精排后 Claim 列表 + `explain`（粗排全貌/精排分数/截断项） | US-S1 / US-S2 / A4 / A5 |
| `POST` | `/api/v2/context-inject` | read | 同 v5 语义 + `include_explain` | 注入 payload + 截断说明 | US-S1 / A5 |
| `GET` | `/api/v2/claims/{id}` | read | — | claim 详情 + 证据（claim_evidence）+ 谱系（出/入边） | A2 / A3 |
| `GET` | `/api/v2/claims/{id}/lineage` | read | — | 该 claim 的谱系树（supersedes/generalizes/retract） | A3 |

### 2.4 个人工作台（MR-011，M2）

| 方法 | 路径 | 权限 | 说明 | 对应 |
|------|------|------|------|------|
| `POST` | `/api/v2/workbench/claims/{id}/confirm` | write | 确认（+Δ content） | US-W1 / A6 |
| `POST` | `/api/v2/workbench/claims/{id}/correct` | write | 纠错 = 创建 `user_correction` Evidence → 对账 supersede | US-W1 / A3 / A6 |
| `POST` | `/api/v2/workbench/claims/{id}/forget` | write | 遗忘 = `retract` 边 | US-W1 / A6 |
| `POST` | `/api/v2/workbench/claims/{id}/promote-scope` | write | scope 提权审计：采纳/拒绝（系统建议 + 用户事后审计） | US-W2 / A7 |
| `GET` | `/api/v2/workbench/overview` | read | 统计（claim 拓扑/价值分布/source_kind 构成） | US-W4 / A8 |
| `GET` | `/api/v2/workbench/reviews` | read | 召回复盘列表（trace 展开） | US-W5 / A8 |
| `GET` | `/api/v2/workbench/reviews/{trace_id}` | read | 单次召回 trace：粗排全部候选/精排因子分数/截断项 | US-W5 / A5 / A8 |

> 审批面（owner 提权，US-W3）依赖团队 owner P1，一期不开放（PRD §4）。

### 2.5 调试 / 迁移（admin）

| 方法 | 路径 | 权限 | 说明 | 对应 |
|------|------|------|------|------|
| `GET` | `/api/v2/debug/traces` | admin | 召回 trace 日志（与个人 workbench 隔离） | A11 |
| `GET` | `/api/v2/debug/embedding-logs` | admin | embedding 日志 | A11 |
| `POST` | `/api/v2/migrate/run` | admin | 一次性全量迁移（memories → evidence），幂等可重放 | US-M1 / A9 |
| `GET` | `/api/v2/migrate/status` | admin | 迁移进度/断点 | US-M1 / A9 |

## 3. 错误规范

### 3.1 错误码（与 v5 风格一致：`{code, message, detail?}`）

| HTTP | code | 场景 |
|------|------|------|
| 400 | 400 | 参数校验失败（缺 content / 非法 source_kind / observed_at 未来等） |
| 401 | 401 | 缺 / 无效 API key |
| 403 | 403 | scope 越权（`verify_scope_ownership` 失败）/ 权限不足 |
| 404 | 404 | evidence / claim / job 不存在 |
| 409 | 409 | 幂等键冲突（同键不同 payload）/ 重复提交被拒 |
| 422 | 422 | body 结构校验失败（FastAPI 默认） |
| 429 | 429 | 速率限制（复用 v5 `check_rate_limit`） |
| 500 | 500 | 服务器内部错误（`settings.APP_DEBUG` 控制 detail 透出） |

### 3.2 响应信封（统一）

```json
{
  "code": 0,
  "message": "ok",
  "data": { "...": "端点数据" }
}
```

- 成功 `code=0`；错误 `code` 见上表（与 v5 的 `{code, message, errors}` 兼容风格，v5 未统一信封，crystal 统一）。
- `data` 内各端点结构在 §2 响应列标注。

### 3.3 幂等

- `POST /api/v2/evidence` 支持 `idempotency_key`（推荐 `source_ref.session_id + message_id + content 哈希`）：
  服务端在 `evidence_processing` 查重（幂等键 = source_ref 消息 ID + content 哈希，entity-attributes §2 修正注）；
  命中返回既有 `evidence_id`（202），不重复落库。
- 幂等键冲突（同键不同 payload）→ 409。

## 4. 请求/响应骨架（关键端点）

### 4.1 POST /api/v2/evidence

```jsonc
// Request
{
  "content": "正式规划文档是 docs/PROJECT_PLAN.md",   // NOT NULL
  "source_kind": "agent_add",                          // agent_add|outcome_trace|document|user_correction
  "scope": "project-memory_recall",                    // 可选；NULL=全局
  "observed_at": "2026-08-18T10:00:00Z",               // 可选，默认=入库时刻
  "source_ref": {"session_id": "s-01", "message_id": "m-03", "plugin": "dsh"},  // 可选
  "extraction_type": "verbatim",                       // 可选 verbatim|paraphrase|inference
  "idempotency_key": "s-01:m-03:sha256..."             // 可选
}

// Response 202
{
  "code": 0, "message": "ok",
  "data": {
    "evidence_id": "ev_abcd...",
    "processing_state": "pending",
    "current_step": "embedding",
    "accepted": true            // false = 幂等命中已存在
  }
}
```

- `observed_at` 允许显式覆盖（批量上报/补录传真实时间，entity-attributes §2）。
- 写接口**同步返回 202**，embedding/对账异步推进（v1 #17 写路径可靠性）。

### 4.2 POST /api/v2/search

```jsonc
// Request
{
  "query": "正式规划文档在哪",
  "scope": "project-memory_recall",   // 可选；预过滤
  "claim_kind": null,                 // 可选过滤
  "limit": 10,                        // 1..100，默认 10
  "include_explain": true             // 默认 false（性能）；洞察面/工作台置 true
}

// Response 200
{
  "code": 0, "message": "ok",
  "data": {
    "results": [
      {
        "claim_id": "cl_...",
        "statement": "memory_recall 的正式规划文档是 PROJECT_PLAN.md",
        "claim_kind": "fact",
        "content_confidence": 0.80,
        "confidence_label": "较高",     // 展示来源标签而非裸分数（调研 #4）
        "status": "active",
        "scope": "project-memory_recall",
        "evidence_refs": [{"evidence_id": "ev_...", "role": "support"}],
        "scores": {"relevance": 0.91, "content": 0.80, "reuse": 0.0, "final": 0.728}
      }
    ],
    "explain": {                        // include_explain=true 时
      "prefilter": {"scope_matched": 12, "active": 12, "passed": 12},
      "candidates": [{"claim_id": "cl_...", "raw_score": 0.85, "rank": 1}],
      "ranked": [...],                  // 精排后全量（含未进 final 的）
      "truncated": [                    // 截断项（不静默丢弃）
        {"claim_id": "cl_...", "reason": "cap_limit_10", "rank": 11, "final": 0.40}
      ],
      "low_confidence": [{"claim_id": "cl_...", "content_confidence": 0.31}]
    }
  }
}
```

- `results` 只含 **status=active 且 scope 匹配**的 Claim（A4）；`explain.truncated` 展示被 cap 砍掉的项（A5）。

### 4.3 POST /api/v2/workbench/claims/{id}/correct

```jsonc
// Request
{
  "new_statement": "开发文档实际是 docs/PROJECT_PLAN.md",  // 用户给出的正确版本
  "reason": "用户会话中纠正",                               // 可选
  "source_ref": {"session_id": "s-02", "message_id": "m-09"} // 可选
}
// Response 201
{
  "code": 0, "message": "ok",
  "data": {
    "correction_evidence_id": "ev_...",   // 新建 user_correction Evidence
    "superseded_claim_id": "cl_old...",
    "new_claim_id": "cl_new...",
    "edge": {"id": "le_...", "edge_type": "supersedes", "reason": "用户纠正"}
  }
}
```

- 语义（v1 #4）：correct = 特权 Evidence（`source_kind=user_correction`）→ 对账**直接 supersede**，不走 LLM 推理。

## 5. 分页与游标约定

- 列表端点（evidence / reviews）用 `cursor` 游标分页：`cursor = base64(observed_at + id)`，
  响应带 `next_cursor`（无更多则 null）；`limit` 默认 20，最大 100。
- 不用 offset 分页（大表深翻页性能差）。

## 6. 与 v5 的映射速查（插件迁移参考，Stage D）

| v5 端点 | crystal 端点 | 变化 |
|---------|-------------|------|
| `POST /memories` | `POST /api/v2/evidence` | container_tag → scope + owner（鉴权层填）；异步对账 |
| `GET /memories?container_tag=` | `GET /api/v2/claims?...` | 返回"当前为真"的 Claim，非文本记忆 |
| `POST /search` | `POST /api/v2/search` | + explain / + active 预过滤 |
| `POST /context-inject` | `POST /api/v2/context-inject` | 同语义 + explain |
| `PUT /memories/{id}/update` | `POST /api/v2/workbench/claims/{id}/correct`（纠正）/ `forget`（遗忘） | 版本链 → 谱系边 |
| `DELETE /memories/{id}` | `POST /api/v2/workbench/claims/{id}/forget` | 物理删 → retract 逻辑删 |
| `GET /debug/*` | `GET /api/v2/debug/*` | 权限收归 admin |

## 7. 验收标准（M1 骨架 + M2 业务，对应 PRD A1–A11）

- [ ] **A1**：`POST /api/v2/evidence` 落库返回 202 + pending；失败可见（US-E2 状态可追踪）。
- [ ] **A2**：`GET /api/v2/evidence/{id}/claims` 与 `GET /api/v2/claims/{id}` 都能点开证据；evidence 不可变。
- [ ] **A3**：correct 端点生成 supersede 边 + reason，旧 claim 不丢（status=superseded）。
- [ ] **A4**：search 只返回 active + scope 匹配；superseded 不混入。
- [ ] **A5**：include_explain=true 时返回粗排全貌 + 精排分数 + truncated 项；无静默丢弃。
- [ ] **A6**：confirm/correct/forget 只作用于自己 owner 的 claim；越权 403。
- [ ] **A7**：promote-scope 采纳/拒绝可审计（建议可见 + 操作留痕）。
- [ ] **A8**：overview 统计 + reviews trace 展开可用，只用个人数据。
- [ ] **A9**：`POST /api/v2/migrate/run` 幂等可重放；status 报告断点。
- [ ] **A10**：四端切 /api/v2 后无旧路由调用（访问日志核对）；回退演练过。
- [ ] **A11**：debug/traces 与 workbench/reviews 数据隔离；admin 才可访问 debug。

## 8. 未决 / 后续

- **P1 团队 owner**：`owner_type=team` 的鉴权映射（team 成员 key → 团队 owner_id）随 P1 定，本期不展开。
- **promote-scope 建议如何产生**（系统主动触发判据）：归对账/召回技术设计 v1（S1 质变判据），
  本契约只定 API 形态（采纳/拒绝两动作）。
- **web 工作台页面**（可选管理层）不在此契约；其调用本契约 API。

*状态: 草稿 · 最后更新: 2026-08-18*
