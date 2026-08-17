# 实体属性文档（草稿 v1）

> 状态: 草稿（evidence / evidence_processing / lineage_edge 已定稿；claim 基本定稿，claim_kind 待定）
> 系统: crystal
> 版本: v1 · 最后更新: 2026-08-15
> 关联: [目标模型 v1](v1.md)（语义层，唯一裁判）· 待落文档 #3
> 范围: 本 doc 只定「新表长什么样」——字段 / 类型 / 约束 / 索引 / 枚举 / 派生字段。
> 写入/召回逻辑、迁移机制、workbench API 不在此列。
> **Entity / 主题 = P2 可选附属，不进核心 schema**，另建「P2 实体网络文档」（待建）时再定。

## 0. 总原则（承接 v1）

- **evidence 是唯一不可再生源**；claim / lineage_edge / claim_evidence 都是**派生层的物化落库**（为性能落库，语义上可重算）。
- **Evidence 不关联 Claim**（v1 #11）：evidence 表无 claim 外键；关联只从 claim 侧单向记。
- **纠正只发生在 Claim 层**（v1 #4）：纠正 claim = 新增一条 `user_correction` Evidence → 对账自行与错误 claim 碰撞、supersede 取代；**不设 Evidence 层「修改/否定」机制**。
- **status 是派生物化缓存**（v1 #25）：语义上由谱系边派生，物理上物化 status 列、写边同一事务同步维护（非手工标志位），支撑召回 partial HNSW on active。
- 表名/字段名用占位，不依赖产品命名（C7 命名漂移后 rename 零成本）。

## 1. 对象 → 表映射

| 对象 | 表 | 性质 |
|------|-----|------|
| Evidence（证据） | `evidence` | append-only，语义字段不可变（**已定稿**） |
| Evidence 处理状态 | `evidence_processing` | 1:1 伴随表，异步管道状态机（**已定稿**） |
| Claim（主张） | `claim` | 派生，可版本化（版本 = 谱系边）（基本定稿，claim_kind 待定） |
| Lineage Edge（谱系边） | `lineage_edge` | 推理在边（基本定稿） |
| Claim↔Evidence 支持 | `claim_evidence` | 派生物化（数组 vs 关系表待定） |
| 复用/outcome 统计 | `claim_usage` | 离散价值信号（落点待定） |

> Entity / 主题 = P2 附属，不进核心 schema。

## 2. evidence 表（已定稿）

| 字段 | 类型 | 约束 | 语义 / 用途 | 性质 |
|------|------|------|-------------|------|
| `id` | TEXT | PK | `'ev_' + 22 hex` | 存储 |
| `observed_at` | TIMESTAMPTZ | NOT NULL | **事件时间**（不可再生、语义核心）；默认 = 入库时刻，可显式覆盖（批量上报/补录传真实时间） | 存储·不可变 |
| `source_kind` | TEXT | NOT NULL, 枚举 | `agent_add` / `outcome_trace` / `document` / `user_correction` | 存储·不可变 |
| `content` | TEXT | NOT NULL | 原始观察文本（可同时含情景 + 语义） | 存储·不可变 |
| `scope` | TEXT | NULL | 项目作用域；NULL = 全局 | 存储·不可变 |
| `owner_type` | TEXT | NOT NULL, 枚举 | `personal`(P0) / `team`(P1) | 存储·不可变 |
| `owner_id` | TEXT | NOT NULL | 归属主体：personal = key_id；team = team_id | 存储·不可变 |
| `source_ref` | JSONB | NULL | 出处 `{session_id, plugin, file, …}` | 存储·不可变 |
| `embedding` | vector | NULL | 检索向量（维度随 embedding 模型） | 派生·可空 |
| `created_at` | TIMESTAMPTZ | NOT NULL | **入库时间**（运维：数据重放/审计/对账顺序） | 存储·不可变 |

**索引**：PK(id) · (owner_type, owner_id) · (owner_type, scope) · (source_kind) · (observed_at DESC) · embedding vector 索引。

## 3. evidence_processing 表（已定稿，1:1 伴随）

> 处理状态机从 evidence 表拆出，保持 evidence 表纯净（只答"观察到了什么"，不答"消化了没有"）。

| 字段 | 类型 | 约束 | 语义 |
|------|------|------|------|
| `evidence_id` | TEXT | PK, FK→evidence | 1:1 |
| `processing_state` | TEXT | NOT NULL | `pending / processing / done / failed`（4 稳定值） |
| `current_step` | TEXT | NULL | 下一个待执行步骤名（**开放枚举**，done 时 NULL） |
| `last_error` | JSONB | NULL | `{step, message, attempts, last_attempt_at}` |
| `updated_at` | TIMESTAMPTZ | NOT NULL | 最后推进时刻 |

**通用状态机（A2）**：写接口 ms 级落 evidence（`processing_state=pending, current_step=embedding`）→ 每步完成推进 `current_step` → 全完成 `done`；任一步失败 `failed + last_error.step` 定位，后端自行重试。**步骤名是数据不是列**，加步骤只加字符串。worker 直接扫 `evidence_processing WHERE processing_state IN ('pending','processing','failed')` 找活，不碰 evidence 大表。

**索引**：PK(evidence_id) · (processing_state)。

## 4. claim 表（基本定稿，claim_kind 待定）

| 字段 | 类型 | 约束 | 语义 | 性质 |
|------|------|------|------|------|
| `id` | TEXT | PK | `'cl_' + 22 hex` | 存储 |
| `statement` | TEXT | NOT NULL | 简单断言，**适用条件折入句子** | 存储 |
| `claim_kind` | TEXT | 待定 | `fact/preference/constraint/…`（画像偏好层筛选依据） | 存储 |
| `content_confidence` | FLOAT | NULL | **单轴内容置信度**，NULL = UNKNOWN（冷启动） | 派生·物化 |
| `scope` | TEXT | NULL | 继承 Evidence；scope 提权后可 NULL | 存储 |
| `owner_type` | TEXT | NOT NULL, 枚举 | `personal` / `team` | 存储 |
| `owner_id` | TEXT | NOT NULL | key_id / team_id | 存储 |
| `status` | TEXT | NOT NULL | **派生物化缓存**（写边事务内维护）：active/superseded/disputed/retracted | 派生·物化 |
| `embedding` | vector | NULL | 检索向量 | 派生·物化 |
| `created_at` | TIMESTAMPTZ | NOT NULL | 建 Claim 时刻 | 存储 |

- **无 `valid_from`/`valid_until`**（v1 #24 砍）：时间失效由 supersede 承载，实用性衰减由复用频率承载。
- **复用/outcome 不在 claim 表**：`复用频率`/`outcome` 是离散价值信号（v1 #8），落 `claim_usage`，不物化置信度。
- **证据支持走 `claim_evidence`**（数组 vs 关系表待定）。

**索引**：PK(id) · (owner_type, owner_id) · (owner_type, scope) · (claim_kind) · **partial HNSW `WHERE status='active'`** · embedding vector 索引。

## 5. lineage_edge 表（基本定稿）

| 字段 | 类型 | 约束 | 语义 |
|------|------|------|------|
| `id` | TEXT | PK | `'le_' + 22 hex` |
| `from_claim_id` | TEXT | NOT NULL FK→claim | 源 |
| `to_claim_id` | TEXT | **NULL 允许（仅 retract）** FK→claim | 目标 |
| `edge_type` | TEXT | NOT NULL, 枚举 | `supersedes` / `generalizes` / `contradicts` / `retract` |
| `reason` | TEXT | NOT NULL | 为什么这么变 |
| `triggered_by_evidence` | TEXT | NULL FK→evidence | 触发边的新 Evidence |
| `created_at` | TIMESTAMPTZ | NOT NULL | 建边时刻 |

- 约束：`CHECK (from_claim_id <> to_claim_id)`；永久边 `UNIQUE(from,to,type)`。
- `retract` = 单端边（to=NULL）；`contradicts` = 双向两条边、**仲裁后删除 + 改写 supersedes**（v1 #22/#23）。
- active 派生 = 无失效类出边（supersedes / 未解决 contradicts / retract）；`generalizes` 不失效。

**索引**：PK(id) · (from_claim_id, edge_type) · (to_claim_id) · (triggered_by_evidence)。

## 6. 枚举汇总

| 枚举 | 值 | 备注 |
|------|-----|------|
| `source_kind` | `agent_add` / `outcome_trace` / `document` / `user_correction` | 采集四档 + 纠正特权 |
| `owner_type` | `personal` / `team` | P0 只 personal |
| `processing_state` | `pending` / `processing` / `done` / `failed` | evidence_processing 表 |
| `edge_type` | `supersedes` / `generalizes` / `contradicts` / `retract` | contradicts 临时、retract 单端 |
| `claim.status` | `active` / `superseded` / `disputed` / `retracted` | 派生物化缓存 |

## 7. 待定项

- `claim_kind` 枚举取值（画像偏好层筛选依据，随 v1 讨论）。
- `evidence_refs` 数组 vs 关系表 `claim_evidence`（建议关系表）。
- 复用/outcome 统计的落点（`claim_usage` 表 vs claim 表计数字段——倾向独立表，避免消费回写频繁 update claim 表）。
- 衰减曲线形态（content 时间衰减 + 复用频率时间窗口，B1）。
