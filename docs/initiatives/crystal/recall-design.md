# 召回技术设计 v1（状态查询读路径）（草稿）

> 状态: 草稿 · 系统: crystal · 版本: v1 · 最后更新: 2026-08-18
> 关联: [目标模型](foundation.md)（§两链路召回 / §置信度与价值信号）· [实体属性文档](entity-attributes.md)（索引）·
> [里程碑](milestone.md)（M2 前置产物 §4.2）· [API 契约](api-contract.md)（§4.2 search/explain）·
> [PRD](prd.md)（US-S1/S2 / A4/A5）· MR-017（注入 cap 教训）
> 定位: 本文是 **状态查询（召回）的实现设计**——三级管道（预过滤→粗排→精排）、精排公式、
> 截断/cap 可见性、trace 契约、注入形态。写路径见 [对账技术设计 v1](reconciliation-design.md)。

## 0. 一句话

**query → 结构化预过滤（scope 匹配 + status=active）→ 向量粗排（top-K）→ 精排
（相关 × content × 复用·outcome，一期复用恒 0）→ 注入；截断/排除项全部可见（不静默丢弃，MR-017 教训）。**

## 1. 三级管道

```
query + scope + claim_kind?
  │
  ▼ ① 结构化预过滤（SQL，零向量成本）
  │    WHERE owner_id = :key_id
  │      AND status = 'active'                    -- 当前为真（A4）
  │      AND (scope = :scope OR scope IS NULL)    -- scope 匹配（NULL=全局；精确匹配）
  │      [AND claim_kind = :claim_kind]
  │    → prefilter 候选集
  │
  ▼ ② 向量粗排（pgvector HNSW）
  │    partial HNSW index: WHERE status='active'  （entity-attributes §4 索引）
  │    query embedding → cosine 相似度 top-K（K=50 默认）
  │    → candidates（含分数）
  │
  ▼ ③ 精排（内存计算）
  │    final = relevance × content_factor × reuse_factor（一期 reuse_factor≡1）
  │    → ranked 全量（含未进 final 的，供 explain）
  │
  ▼ ④ 截断
  │    cap = limit（默认 10）→ truncated 列表（不静默丢弃，进 explain）
  │
  ▼ 注入 payload（/context-inject）或 search 结果（/search）
```

- **scope 匹配规则**（A4）：预过滤层做，不等精排（v1 #26）；
  `scope=NULL`（全局知识）对任何请求 scope 都匹配；请求 scope=NULL 时只匹配全局（不含项目级）。
- **owner 隔离**：预过滤强制 `owner_id = current_key_id`（个人 key 只看自己，A6）。

## 2. 精排公式（v1 §置信度与价值信号）

```
final(claim) = relevance(claim, query) × content_factor × reuse_factor

content_factor = f(content_confidence):
  一期（P0）: 直接映射——content_factor = content_confidence（NULL/UNKNOWN 按 0.4 低置信兜底，标注不丢弃）
  后续（P1 遥测激活后）: 复用/outcome 引入 reuse_factor = g(reuse_count, outcome_good, outcome_bad)
    （g 的形态随价值引擎，一期恒 1）
```

- **relevance**：粗排余弦相似度（0..1）映射到 0..1（`relevance = (cos + 1)/2` 或 min-max 归一，实现时定）。
- **content 因子**：`content_confidence`（0..1）；NULL 按 0.4 兜底（低置信标注）。
- **一期退化形态**（milestone §4.2）：`final = relevance × content_confidence`——可运行、可观测，
  复用/outcome 恒 0 不参与；P1 遥测来了再加 reuse 因子。
- **B1 衰减不落库**：content 时间衰减只在精排现算（初始恒等项 `×1.0` 占位，发现问题再激活）。

## 3. 截断 / cap（MR-017 教训落地，A5）

| 项 | 一期默认 | 说明 |
|----|---------|------|
| 精排后返回上限 | `limit`（默认 10，最大 100） | `results` 只含前 limit 条 |
| 截断项 | 全部进 `explain.truncated` | **不静默丢弃**：每条带 rank + reason（`cap_limit` / `low_confidence`） |
| 低置信项 | `content_confidence < 0.4` 或 NULL | 只标注（`explain.low_confidence`），不默认丢弃 |
| 粗排候选全貌 | 进 `explain.candidates`（top-K 全量） | 洞察面/工作台复盘用（US-W5） |

- **无硬编码 6/6/4**（MR-017 教训）：cap 只由 `limit` 控制，全部可配置、全部可见；
  crystal 重设计粗排，不沿用旧 6/6/4（v1 #32）。

## 4. trace 契约（explain 结构，与 workbench 复盘共用）

```jsonc
"explain": {
  "query": "正式规划文档在哪",
  "prefilter": {
    "owner_id": "key-01",
    "scope": "project-memory_recall",
    "scope_matched": 12,        // 预过滤候选数
    "active_only": true
  },
  "candidates": [               // 粗排全貌（top-K）
    {"claim_id": "cl_...", "relevance": 0.85, "rank": 1},
    ...
  ],
  "ranked": [                   // 精排后全量（含未进 final）
    {"claim_id": "cl_...", "relevance": 0.85, "content": 0.80, "reuse": 0.0, "final": 0.68, "rank": 1},
    ...
  ],
  "truncated": [                // 截断项（不静默丢弃）
    {"claim_id": "cl_...", "rank": 11, "final": 0.41, "reason": "cap_limit_10"}
  ],
  "low_confidence": [           // 低置信标注
    {"claim_id": "cl_...", "content_confidence": 0.31}
  ]
}
```

- **落库**：`include_explain=true` 时 trace 落 `workbench_review`（workbench 设计 §5），
  workbench 复盘直接读；debug/traces 是 admin 全量视图（A11 权限隔离）。
- **性能**：explain 默认 false（`/search`、`/context-inject` 不带则不计算/不落库）；洞察面/工作台置 true。

## 5. 注入形态（/context-inject，插件消费）

```
POST /api/v2/context-inject {query?, scope?, config?, include_explain?}
  → 同 search 管道 → 组装注入 payload：
    1. 画像层（claim_kind='preference' 的 active claim，首轮注入）——v1 #16 画像=Claim 读视图
    2. 任务上下文（query 动态检索结果，状态查询）
    3. explain（可选）
```

- **与 v5 注入的差异**：返回"当前为真"的 Claim（非相似文本）；截断可见（explain）。
- **exclude_memory_ids / 跨轮去重**：v5 已有机制（dsh 插件 per-agent LRU），crystal 沿用
  （`exclude_claim_ids` 参数，M2 实现时确认）。

## 6. 索引设计（与 entity-attributes 对齐）

| 索引 | 用途 |
|------|------|
| `claim(owner_type, owner_id)` | 预过滤 owner |
| `claim(owner_type, scope)` | 预过滤 scope |
| **partial HNSW `claim(embedding) WHERE status='active'`** | 粗排只扫 active（A4 性能关键） |
| `claim(status)` | 状态过滤 |
| `claim_usage(claim_id)` / `claim_usage(reuse_count DESC)` | 价值排序 |

## 7. 验收标准（对应 PRD A4/A5 + US-S*）

- [ ] **US-S1 / A4**：search/context-inject 只返回 active + scope 匹配；superseded 不混入；
  scope=NULL 全局 claim 对任何请求可见。
- [ ] **US-S2 / A5**：include_explain=true 返回粗排全貌 + 精排分数 + truncated + low_confidence；
  无静默丢弃；默认 false 时零额外开销。
- [ ] **owner 隔离**：跨 key 请求 403 / 空结果（不泄露他人 claim）。
- [ ] **性能**：粗排 p95 < 100ms（partial HNSW active）；精排 < 10ms（内存计算）。
- [ ] **注入**：context-inject 返回"当前为真"Claim + 画像偏好层（claim_kind=preference）。

## 8. 未决 / 后续

- **relevance 归一化形态**（cos → 0..1 映射）：实现时定，先 `(cos+1)/2`。
- **reuse_factor 的 g 形态**：P1 遥测激活后定（价值引擎），一期恒 1。
- **衰减因子**（B1）：恒等占位，发现问题再激活。
- **多 scope 请求**：一期单 scope；跨 scope 聚合（用户级 + 项目级同时注入）在 context-inject 组装时定。

*状态: 草稿 · 最后更新: 2026-08-18*
