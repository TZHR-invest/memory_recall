# 实体属性文档（v1 · 已定稿）

> 状态: 草稿（**3 待定项已定案，全部表定义定稿**；待 M1 按此建 `crystal.*` schema）
> 系统: crystal
> 版本: v1 · 最后更新: 2026-08-18
> 关联: [目标模型 v1](v1.md)（语义层，唯一裁判）· [crystal API 契约](api-contract.md)（M1）· 待落文档 #3
> 范围: 本 doc 只定「新表长什么样」——字段 / 类型 / 约束 / 索引 / 枚举 / 派生字段。
> 写入/召回逻辑、迁移机制、workbench API 不在此列（归 api-contract / 对账技术设计 / 召回技术设计 / workbench 设计）。
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
| Claim（主张） | `claim` | 派生，可版本化（版本 = 谱系边）（**已定稿**） |
| Lineage Edge（谱系边） | `lineage_edge` | 推理在边（**已定稿**） |
| Claim↔Evidence 支持 | `claim_evidence` | 派生物化（**已定：关系表**） |
| 复用/outcome 统计 | `claim_usage` | 离散价值信号（**已定：独立表**） |
| 变更审计日志 | `claim_activity` | **非核心模型**（append-only 审计叙事，2026-08-18 新增） |

> Entity / 主题 = P2 附属，不进核心 schema。
> **2026-08-18 定案（§7 三项）**：`claim_kind` 枚举定 4 值、`claim_evidence` 用关系表（弃数组）、
> `claim_usage` 独立表（弃 claim 计数字段）。→ 全部表定义定稿，M1 可照此建表。

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
| `extraction_type` | TEXT | NULL | 提炼方式 `verbatim / paraphrase / inference`（B5 定案 2026-08-16）：服务初值"提炼过程"维度——inference 类降档，防模型推断虚高（Grok r2） | 存储·不可变 |
| `embedding` | vector | NULL | 检索向量（维度随 embedding 模型） | 派生·可空 |
| `created_at` | TIMESTAMPTZ | NOT NULL | **入库时间**（运维：数据重放/审计/对账顺序） | 存储·不可变 |

**索引**：PK(id) · (owner_type, owner_id) · (owner_type, scope) · (source_kind) · (observed_at DESC) · embedding vector 索引。

> ⚠️ **2026-08-16 修正（用户评审）**：曾考虑加 `root_observation_id`（证据独立性格线根）防"复述 → 置信虚高"，经评审**缓置**——
> 该字段防的是 P2/P3 自动采集路径（文档蒸馏/全量上下文）的复述，而这两条当前挂起/不做；P0 add（显式自报，
> 每次即新原始观察）+ P1 report_effect（只动复用统计、不新增 evidence）均不产生复述，不需要 lineage 根。
> 真正的防线是**对账规则**："reinforce 只认新的原始观察，agent 自陈/复述不构成 reinforce 证据"；
> 另需**幂等键**（source_ref 会话消息 ID + content 哈希）防 v1 #17 重试导致的重复入库（此为幂等问题，非 lineage）。
> 将来 P2/P3 采集扩大解冻时再引入 root_observation_id，无迁移债。

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

## 4. claim 表（已定稿）

| 字段 | 类型 | 约束 | 语义 | 性质 |
|------|------|------|------|------|
| `id` | TEXT | PK | `'cl_' + 22 hex` | 存储 |
| `statement` | TEXT | NOT NULL | 简单断言，**适用条件折入句子** | 存储 |
| `claim_kind` | TEXT | NOT NULL, 枚举 | `fact / preference / constraint / learned-pattern`（见 §4.1；画像偏好层筛选依据） | 存储 |
| `content_confidence` | FLOAT | NULL | **单轴内容置信度**，NULL = UNKNOWN（冷启动） | 派生·物化 |
| `scope` | TEXT | NULL | 继承 Evidence；scope 提权后可 NULL | 存储 |
| `owner_type` | TEXT | NOT NULL, 枚举 | `personal` / `team` | 存储 |
| `owner_id` | TEXT | NOT NULL | key_id / team_id | 存储 |
| `status` | TEXT | NOT NULL | **派生物化缓存**（写边事务内维护）：active/superseded/disputed/retracted | 派生·物化 |
| `embedding` | vector | NULL | 检索向量 | 派生·物化 |
| `created_at` | TIMESTAMPTZ | NOT NULL | 建 Claim 时刻 | 存储 |

- **无 `valid_from`/`valid_until`**（v1 #24 砍）：时间失效由 supersede 承载，实用性衰减由复用频率承载。
- **复用/outcome 不在 claim 表**：`复用频率`/`outcome` 是离散价值信号（v1 #8），落 `claim_usage`，不物化置信度。
- **证据支持走 `claim_evidence` 关系表**（§7 已定，弃数组：1..N 可索引、避免 JSONB 内查询）。
- **B5 初值映射**：`content_confidence` 初值 = `source_kind × claim_kind` 网格弱先验（Beta 参数化），
  具体档位表见 [§7.4](#74-b5-初值档位表source_kind--claim_kind-网格)（M1 落地）。

**索引**：PK(id) · (owner_type, owner_id) · (owner_type, scope) · (claim_kind) · **partial HNSW `WHERE status='active'`** · embedding vector 索引。

### 4.1 claim_kind 枚举（2026-08-18 定案）

> 对齐 v5 蒸馏白名单（`preference / constraint / learned-pattern`，服务端白名单兜底 learned-pattern，
> 见 memories.py /extract-memory），crystal 增加 `fact` 覆盖"无类型主张的观察结论"。

| 值 | 语义 | 与 v5 关系 | B5 网格初值维度 |
|----|------|-----------|----------------|
| `fact` | 事实类断言（"正式规划文档是 PROJECT_PLAN.md"） | v5 无此类型（蒸馏时归 learned-pattern） | claim_type 一维 |
| `preference` | 主观喜好/习惯/语言风格/工作方式 | 对齐 v5 `preference` | 同上 |
| `constraint` | 项目/任务硬性边界、必须遵守的规则 | 对齐 v5 `constraint` | 同上 |
| `learned-pattern` | 实践中验证有效的做法/技术决策/踩坑教训 | 对齐 v5 `learned-pattern` | 同上 |

- **对账产物归类**：对账生成 Claim 时由 LLM 或规则判定 claim_kind；从 v5 迁移的旧记忆
  （`memories.metadata.type` 有 `preference/constraint/learned-pattern`）原样映射，未知类型归 `fact`。
- **兜底**：`fact` 是万能兜底（v5 兜底是 learned-pattern，crystal 语义上"事实陈述"更贴切；
  迁移映射时旧 `learned-pattern` 仍映射 `learned-pattern`，仅"无类型"归 fact）。

### 4.5 claim_evidence 表（已定稿，2026-08-18 定案：关系表）

> 派生物化：记录 Claim 引用了哪些 Evidence（**只存"支持"**，矛盾靠 supersede 边派生，v1 #10）。
> 语义上可重算（从对账结果重生成），物化为关系表支持"点开证据"查询与计数。

| 字段 | 类型 | 约束 | 语义 |
|------|------|------|------|
| `claim_id` | TEXT | PK(复合), FK→claim ON DELETE CASCADE | 引用方 |
| `evidence_id` | TEXT | PK(复合), FK→evidence | 被引用 Evidence |
| `role` | TEXT | NOT NULL, 枚举 | `support`（支持，默认；contradicts 仲裁后不再引用） |
| `created_at` | TIMESTAMPTZ | NOT NULL | 关联建立时刻 |

- 复合 PK `(claim_id, evidence_id)` 天然防重复关联；`role` 保留为将来"支持/反证"分离留位
  （一期恒 `support`，反证走 supersede 边）。
- **不变量①落地**：Claim 创建事务内同时写 `claim_evidence`，保证"结论必须引用证据"（1..N）。
- **索引**：PK(claim_id, evidence_id) · (evidence_id)（反查"这条证据支持了哪些 claim"）。

### 4.6 claim_usage 表（已定稿，2026-08-18 定案：独立表）

> 离散价值信号（v1 #8）：`复用频率` / `outcome` 是消费（P1 遥测）回写的统计，**不物化进 claim 表**
> （避免消费回写频繁 UPDATE claim 大表）；独立表按 claim 聚合，召回精排时 LEFT JOIN 读。

| 字段 | 类型 | 约束 | 语义 |
|------|------|------|------|
| `claim_id` | TEXT | PK, FK→claim ON DELETE CASCADE | 1:1 聚合行 |
| `reuse_count` | INTEGER | NOT NULL DEFAULT 0 | 近期被采用次数（P1 遥测回写，非累计） |
| `outcome_good` | INTEGER | NOT NULL DEFAULT 0 | 采用后结果好计数 |
| `outcome_bad` | INTEGER | NOT NULL DEFAULT 0 | 采用后结果坏计数 |
| `last_used_at` | TIMESTAMPTZ | NULL | 最近一次采用时刻（召回精排衰减现算用） |
| `updated_at` | TIMESTAMPTZ | NOT NULL | 最后回写时刻 |

- 一期（P0）该表**不写入**（复用/outcome 恒 0，精排因子退化为 相关×content），表先建好、P1 遥测激活。
- **索引**：PK(claim_id) · (reuse_count DESC)（价值排序查询用）。

## 5. lineage_edge 表（已定稿）

| 字段 | 类型 | 约束 | 语义 |
|------|------|------|------|
| `id` | TEXT | PK | `'le_' + 22 hex` |
| `from_claim_id` | TEXT | NOT NULL FK→claim | 源 |
| `to_claim_id` | TEXT | **NULL 允许（仅 retract）** FK→claim | 目标 |
| `edge_type` | TEXT | NOT NULL, 枚举 | `supersedes` / `generalizes` / `contradicts` / `retract` |
| `reason` | TEXT | NOT NULL | 为什么这么变 |
| `created_at` | TIMESTAMPTZ | NOT NULL | 建边时刻 |

- 约束：`CHECK (from_claim_id <> to_claim_id)`；永久边 `UNIQUE(from,to,type)`。
- `retract` = 单端边（to=NULL）；`contradicts` = 双向两条边、**仲裁后删除 + 改写 supersedes**（v1 #22/#23）。
- active 派生 = 无失效类出边（supersedes / 未解决 contradicts / retract）；`generalizes` 不失效。
- **无 `triggered_by_evidence` 字段（2026-08-18 定案）**：边的"触发证据"因果信息**不驻留在核心表**，
  迁至独立审计日志表 `claim_activity`（见 §5.1）——边只表达"谁取代谁 + 叙述性 reason"，因果追溯/审计走日志；
  重建（重算）按时间重跑对账，接受 LLM 不确定性，不依赖该字段。

**索引**：PK(id) · (from_claim_id, edge_type) · (to_claim_id)。

### 5.1 claim_activity 表（独立审计日志，2026-08-18 定案）

> 承接原 `triggered_by_evidence` 的职责：记录"谁 / 哪条证据 / 什么动作导致了一次状态变更"。
> **非核心模型**（Evidence/Claim/Edge 之外），append-only 日志，供审计 / 裁决面"为什么变"追溯 / 洞察统计。

| 字段 | 类型 | 约束 | 语义 |
|------|------|------|------|
| `id` | TEXT | PK | `'ca_' + 22 hex` |
| `claim_id` | TEXT | NOT NULL FK→claim | 受影响的 claim（被取代 / 被确认 / 被遗忘…） |
| `action` | TEXT | NOT NULL, 枚举 | `superseded_by` / `generalized_to` / `confirmed` / `retracted` / `promoted_scope` / `poison_warning` |
| `actor_type` | TEXT | NOT NULL, 枚举 | `system`（对账自动）/ `user`（workbench 动作）/ `admin` |
| `actor_id` | TEXT | NULL | 操作者：key_id（user/admin）；system 可 NULL |
| `triggered_by_evidence_id` | TEXT | NULL FK→evidence | **触发该变更的新 Evidence**（原 lineage_edge 字段迁入） |
| `detail` | JSONB | NULL | 补充：目标 claim_id / reason / 旧值快照等 |
| `created_at` | TIMESTAMPTZ | NOT NULL | 日志时刻 |

- **与 lineage_edge 的分工**：边 = 谱系结构（谁→谁，唯一约束防重）；activity = 审计叙事
  （为什么、谁、哪条证据触发）。二者同事务写（见 [对账技术设计](reconciliation-design.md) §2.2）。
- **索引**：PK(id) · (claim_id, created_at DESC) · (triggered_by_evidence_id) · (action)。

## 6. 枚举汇总

| 枚举 | 值 | 备注 |
|------|-----|------|
| `source_kind` | `agent_add` / `outcome_trace` / `document` / `user_correction` | 采集四档 + 纠正特权 |
| `owner_type` | `personal` / `team` | P0 只 personal |
| `processing_state` | `pending` / `processing` / `done` / `failed` | evidence_processing 表 |
| `edge_type` | `supersedes` / `generalizes` / `contradicts` / `retract` | contradicts 临时、retract 单端 |
| `claim.status` | `active` / `superseded` / `disputed` / `retracted` | 派生物化缓存 |
| `claim_kind` | `fact` / `preference` / `constraint` / `learned-pattern` | §4.1 定案（对齐 v5 蒸馏白名单 + fact 兜底） |
| `claim_evidence.role` | `support` | 一期恒 support，反证走 supersede 边 |

## 7. 待定项（2026-08-18 已全部定案）

> 本节原 3 项 open 全部收敛；**保留定案记录**供追溯，不再有待定项。

- ~~`claim_kind` 枚举取值~~ → **2026-08-18 定案**：`fact / preference / constraint / learned-pattern`（§4.1），
  对齐 v5 蒸馏白名单（memories.py /extract-memory）+ crystal 语义兜底 `fact`；画像偏好层筛选依据 = `claim_kind='preference'`。
- ~~`evidence_refs` 数组 vs 关系表 `claim_evidence`~~ → **2026-08-18 定案：关系表**（§4.5）：
  1..N 可索引（"点开证据"反查）、避免 JSONB 数组内查询与并发写冲突；复合 PK 防重复；role 留扩展位。
- ~~复用/outcome 统计的落点~~ → **2026-08-18 定案：独立 `claim_usage` 表**（§4.6）：
  消费回写不频繁 UPDATE claim 大表；召回精排 LEFT JOIN 读；一期不写入、P1 遥测激活。
- ~~衰减曲线形态（content 时间衰减 + 复用频率时间窗口，B1）~~ → **2026-08-16 已定：不落库**；只在召回精排按属性现算，初始恒等项，发现相关问题再激活。参见 [milestone.md](milestone.md)。
- ~~LLM 自报信心初值规则（B5）~~ → **2026-08-16 已定案 + 2026-08-18 落具体档位表（§7.4）**：冷启动初值 = source×claim_type 网格弱先验（Beta 参数化），不含 LLM 自报；evidence 已加 `extraction_type` 字段（见 §2）；**root_observation_id 缓置**（见 §2 修正注）。参见 [调研最终结论](../../notes/research/2026-08-16-llm-confidence-initial-value/99-final-conclusions.md)。

### 7.4 B5 初值档位表（source_kind × claim_kind 网格，2026-08-18 落地）

> 语义依据：[99 结论](../../notes/research/2026-08-16-llm-confidence-initial-value/99-final-conclusions.md) 核对 3 ——
> `(source_type, claim_type)` 组合各给 Beta 先验；V2 用 Beta-Binomial hierarchical 收缩（小样本向总体收缩）。
> 数值均为**工程 heuristic**（调研明示非文献标准值），上线后按真实日志 A/B，V2 收敛。
> `content_confidence` = Beta 期望 α/(α+β)；NULL = UNKNOWN（不入表，冷启动无任何证据）。

| source_kind × claim_kind | `fact` | `preference` | `constraint` | `learned-pattern` |
|--------------------------|--------|--------------|--------------|--------------------|
| `agent_add`（显式自报） | Beta(4,1)=0.80 | Beta(5,1)=0.83 | Beta(4,1)=0.80 | Beta(3,1)=0.75 |
| `user_correction`（特权纠正） | Beta(6,1)=0.86 | Beta(6,1)=0.86 | Beta(6,1)=0.86 | Beta(6,1)=0.86 |
| `outcome_trace`（结果痕迹，P1） | Beta(3,1)=0.75 | Beta(3,1)=0.75 | Beta(3,1)=0.75 | Beta(3,1)=0.75 |
| `document`（文档蒸馏，P2 挂起） | Beta(2,1)=0.67 | Beta(2,1)=0.67 | Beta(2,1)=0.67 | Beta(2,1)=0.67 |

**规则**：

1. **不含 LLM 自报**（冷启动完全弃用，仅留作 V2 校准 feature）；
2. **`extraction_type` 门控**（evidence 侧）：`inference` 类降档——claim 初值在网格基础上 **×0.7 折扣**
   （防模型推断虚高，Grok r2 教训）；`verbatim` / `paraphrase` 不折扣；
3. **UNKNOWN 语义**：网格未覆盖组合或提取失败 → 不入表（`content_confidence=NULL`），召回按"低置信项"标注
   （只标注不静默丢弃，MR-017 教训）；
4. **初值仅建 Claim 时写一次**；之后 content 更新只走 reinforce 计分（§对账技术设计 v1 强度权重表）；
5. **展示形态**：UI/API 展示"来源标签 + 置信档"而非裸分数（调研结论 #4）。
