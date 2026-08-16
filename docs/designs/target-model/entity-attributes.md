# 实体属性文档（草稿 v1）

> 状态: 草稿（Evidence 表已定稿；Claim / Lineage 表随 v1 数据模型讨论，标「待定」）
> 版本: v1 · 最后更新: 2026-08-15
> 关联: [目标模型 v1](v1.md)（语义层，唯一裁判）· 待落文档 #3
> 范围: 本 doc 只定「新表长什么样」——字段 / 类型 / 约束 / 索引 / 枚举 / 派生字段。
> 写入/召回逻辑（对账/状态查询）、迁移机制、workbench API 不在此列。
> **Entity / 主题 = P2 可选附属，不进核心 schema**，另建「P2 实体网络文档」（待建）时再定。

## 0. 总原则（承接 v1）

- **evidence 是唯一不可再生源**；claim / lineage_edge / claim_evidence 都是**派生层的物化落库**（为性能落库，语义上可重算）。
- **Evidence 不关联 Claim**（v1 #11）：evidence 表无 claim 外键；关联只从 claim 侧单向记。
- **纠正只发生在 Claim 层**（v1 #4）：纠正 claim = 新增一条 `user_correction` Evidence → 对账自行与错误 claim 碰撞、supersede 取代；**不设 Evidence 层「修改/否定」机制**——Evidence 是"当时发生了什么"的不可变历史，个人私有、无隐私顾虑，重算 claim 时新 Evidence 自然覆盖旧结论。
- 表名/字段名用占位，不依赖产品命名（C7 命名漂移后 rename 零成本）。

## 1. 对象 → 表映射

| 对象 | 表 | 性质 |
|------|-----|------|
| Evidence（证据） | `evidence` | append-only，语义字段不可变，仅处理元数据可变（**已定稿**） |
| Claim（主张） | `claim` | 派生，可版本化（版本 = 谱系边）——**待定，随 v1 讨论** |
| Lineage Edge（谱系边） | `lineage_edge` | 推理在边——**待定，随 v1 讨论** |
| Claim↔Evidence 支持 | `claim_evidence` | 派生物化——**待定（数组 vs 关系表）** |

> Entity / 主题 = P2 附属，不进核心 schema；「Claim 不主动关联 Entity」原则（v1 #15）留到 P2 实体网络文档展开。

## 2. evidence 表（已定稿）

| 字段 | 类型 | 约束 | 语义 / 用途 | 性质 |
|------|------|------|-------------|------|
| `id` | TEXT | PK | `'ev_' + 22 hex` | 存储 |
| `observed_at` | TIMESTAMPTZ | NOT NULL | **事件时间**（不可再生、语义核心）：回答"事实发生在何时"。**默认 = 入库时刻，可显式覆盖**（批量上报/补录时传真实事件时间） | 存储·不可变 |
| `source_kind` | TEXT | NOT NULL, 枚举 | `agent_add` / `outcome_trace` / `document` / `user_correction`（采集四档 + 纠正特权） | 存储·不可变 |
| `content` | TEXT | NOT NULL | 原始观察文本（可同时含情景 + 语义，见 v1 #18） | 存储·不可变 |
| `scope` | TEXT | NULL | 项目作用域；NULL = 无 scope/全局 | 存储·不可变 |
| `owner_type` | TEXT | NOT NULL, 枚举 | `personal`(P0) / `team`(P1) | 存储·不可变 |
| `owner_id` | TEXT | NOT NULL | 归属主体 id：personal = key_id；team = team_id | 存储·不可变 |
| `source_ref` | JSONB | NULL | 出处 `{session_id, plugin, file, …}`（结果痕迹 Evidence 化的回溯） | 存储·不可变 |
| `embedding` | vector | NULL | 检索向量（维度随 embedding 模型） | 处理元数据·可变 |
| `embedding_state` | TEXT | NOT NULL | `pending / done / failed`（向量化步骤） | 处理元数据·可变 |
| `reconciliation_state` | TEXT | NOT NULL | `pending / done / failed`（对账步骤，done 时置 `reconciled_at`） | 处理元数据·可变 |
| `reconciled_at` | TIMESTAMPTZ | NULL | 对账完成时刻 | 处理元数据·可变 |
| `last_error` | JSONB | NULL | `{stage, message, attempts, last_attempt_at}`——**回答"失败在哪一步"** | 处理元数据·可变 |
| `created_at` | TIMESTAMPTZ | NOT NULL | **入库时间**（管道元数据、运维用：数据重放 / 审计 / 对账顺序） | 存储·不可变 |

**关键区分（A2）**：语义字段（`observed_at/source_kind/content/scope/owner_type/owner_id/source_ref/created_at`）永不改；
处理元数据（`embedding/embedding_state/reconciliation_state/reconciled_at/last_error`）随异步管道推进。

**异步管道（A2）**：写接口 ms 级落库（两步 state = pending）→ 向量化（`embedding_state` done）→ 对账（`reconciliation_state` done）；
两步各自独立标记失败，用 `embedding_state`/`reconciliation_state` + `last_error.stage` 定位"失败在哪一步"，后端自行重试。

**索引**：PK(id) · (owner_type, owner_id) · (owner_type, scope) · (source_kind) · (observed_at DESC) · (embedding_state, reconciliation_state) · embedding vector 索引。

## 3. claim 表（待定，随 v1 数据模型讨论）

> ⚠️ 未定稿。字段为草稿占位，待 v1 讨论「Claim 数据模型」后重写——
> statement 粒度、claim_kind 分类（画像偏好层筛选依据）、适用条件折入句子的边界、纠正语义。

占位字段（非最终）：`id` / `statement` / `claim_kind` / `content_confidence` / `reuse_confidence` / `valid_from` / `valid_until` / `scope` / `owner_type` / `owner_id` / `embedding` / `created_at`；
`status` 派生不落库（待定）；证据支持走 `claim_evidence`（数组 vs 关系表，待定）。

## 4. lineage_edge 表（待定，随 v1 讨论）

> ⚠️ 未定稿。结构源自 v1 已拍板 #5/#7，随 Claim 讨论一并复核。

占位字段（非最终）：`id` / `from_claim_id` / `to_claim_id` / `edge_type`（`supersedes` / `contradicts` / `refines` / `generalizes`，+`retract` 预留 B1）/ `reason` / `triggered_by_evidence` / `created_at`。

## 5. 枚举汇总

| 枚举 | 值 | 备注 |
|------|-----|------|
| `source_kind` | `agent_add` / `outcome_trace` / `document` / `user_correction` | 采集四档 + 用户纠正特权 |
| `owner_type` | `personal` / `team` | P0 只 personal |
| `embedding_state` / `reconciliation_state` | `pending` / `done` / `failed` | A2 异步管道，两步独立 |
| `edge_type` | `supersedes` / `contradicts` / `refines` / `generalizes`（+`retract` 预留 B1） | 随 v1 讨论 |
| `claim_kind` | 待定 | 随 v1 讨论（画像偏好层筛选依据） |

## 6. 待拍板 / 待定项

**本轮已定（2026-08-15 review）**：
- owner 拆为 `owner_type + owner_id`（多态，不建统一 identity/ownership 表）。
- 处理状态拆为 `embedding_state + reconciliation_state + last_error`（回答"失败在哪一步"）。
- Entity / 主题移出核心（P2 附属，另建文档）。

**随 v1 Claim 数据模型讨论再定**：
1. `status` 派生 vs 落库（建议不落库 + partial index 加速"无出边"判定）。
2. `evidence_refs` 数组 vs 关系表 `claim_evidence`（建议关系表）。
3. `applicability` 拆不拆（v1 #10 已定折入 statement，此处定死）。
4. 画像偏好层字段标记（`claim_kind` 枚举取值）。

## 7. 预留项（B/C 触达）

- **B1 遗忘**：`edge_type` 预留 `retract`（forget 如何映射谱系边），S2 再定。
