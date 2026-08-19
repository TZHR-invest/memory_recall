# 目标模型（北极星）· 语义基石文档

> 状态: 草稿（讨论收敛中，未成为实施依据）
> 系统: crystal
> 版本: v1
> 定位: 本文件是 crystal 的**语义基石**——北极星价值公式 + 对象模型 + 两链路 + 拍板清单。
> 其他所有文档（落库/工程/需求/规划）以此为准、从此派生；本文是**唯一裁判**。
> 最后更新: 2026-08-16
> 关联: [命题晋升总纲](../../notes/2026-08-14-proposition-promotion.md) ·
> [状态有效性 thread](../../notes/2026-08-14-agent-memory-state-validity-thread.md) ·
> [复用反馈回收调研](../../notes/research/2026-08-14-reuse-feedback-signals/99-final-conclusions.md) ·
> MR-006 / MR-011

## 背景与目标

现状 `memories` 表是"文本 + 一堆手工标志位"的大杂烩：`is_latest` 需人肉维护、证据与结论混在一起、
没有"这条结论为什么成立"的来源。近期三路输入收敛到同一结论：

1. **命题晋升 S0–S5**（[总纲](../../notes/2026-08-14-proposition-promotion.md)）：记忆是带生命周期的命题，按价值晋升/降级，置信度拆两轴（内容∥复用；后收敛为 content 单轴 + 复用统计，见 §置信度与价值信号）。
2. **复用反馈回收 Q2**（[99 结论](../../notes/research/2026-08-14-reuse-feedback-signals/99-final-conclusions.md)）：缺的不是评分是 outcome 遥测；置信度由证据推导，软失效+版本链，归因两层。
3. **状态有效性 thread**（[note](../../notes/2026-08-14-agent-memory-state-validity-thread.md)）：难点已从"找回来"转向"找回来的现在还成立吗"，核心是证据/结论分离与演变轨迹。

本文是三者对齐后的**目标模型（北极星）**：定义"什么是正确的"，作为后续增量重构的唯一裁判。
**现状代码与既有设计（schema、`is_latest`、N:1 vs 1:1 取代语义等）只作参考，不构成约束，可推翻重来。**
渐进式重构，不搞大爆炸。

## 北极星

> **系统记住/召回的东西，长期净价值最大。**
> 价值 = 复用机会 × 有效性 × 影响 − 维护/遗忘成本；
> **错误信息按负价值计，且权重高于"缺信息"**（无信息 > 错误信息）。

- 这是**排序启发式**，不是精确计算；永远"分解后再估"（P/C 分开估，好过直接估乘积）。
- **"状态有效性"不是北极星**，它是价值公式里"有效性"因子的度量手段（+ 错误信息的惩罚项）。
- 召回精度（搜 X 回来是不是关于 X）与内容有效性（回来的这条现在还成立吗）是**两个正交轴**，
  本北极星管的是后者（以及价值/复用），前者是检索器质量、另有其道。

## 对象模型（两层）

**核心判断：Evidence 是系统唯一不可再生数据；用户显式纠正不单独成类，它是带特权 source_kind 的 Evidence；**
**其余（Claim / Edge）全部是派生、可重新计算。**

**Evidence 与 Claim 的边界**（关键，本会话定义）：
- **Evidence = agent 生命周期的输入**：会话里的一句话、一段代码事实、一次工具结果、一个文档片段；
  **含 agent 自己的"自行蒸馏/注入"输出**——agent 说"我记住了 X"只是一笔观察，不是"X 为真"的结论
  （对应 Q2"模型自陈信号永不单独提权"）。
- **Claim = 系统对 Evidence 理解、并与其他相关 Claim 碰撞后的结论/推论**（即对账的产物），不是输入本身。

| 层 | 对象 | 定义 | 性质 |
|----|------|------|------|
| **不可再生核心** | **Evidence（证据）** | agent 生命周期输入；含 agent 自行蒸馏输出、用户显式纠正（`source_kind = user_correction`，对账时直接 supersede，不走 LLM 推理） | append-only、不可变、永不改写/静默删除；丢失即永久丢失 |
| **派生层** | **Claim（主张/结论）** | 系统理解 + 碰撞后的一条结论/推论；memory 与 knowledge 都是 Claim，只是成熟度/抽象度不同 | 可版本化、可被 supersede/generalize；从 Evidence 派生，可重算 |
| | **Lineage Edge（谱系边）** | Claim 之间"怎么演变"：`supersedes / generalizes / contradicts（临时）/ retract（单端）` + `reason`；**触发证据因果不驻留核心表，走独立审计日志 `claim_activity`**（2026-08-18 定案） | **推理（"为什么这么变"）存在这条边上**，不塞进 Claim |
### 可选附属（P2，非核心）

> Entity / entity_network、主题（category/tags）= **P2 可选附属，不进核心模型**；核心模型只有 Evidence / Claim / Lineage Edge。
> 二者与 `scope`/`owner` 不同：scope/owner 是核心维度，Entity/主题是可选附属。
> 细节（含「Claim 不主动关联 Entity」的展开、关系表反挂）另建「P2 实体网络文档」（待建）时再定。

### Evidence ↔ Claim 是多对多

- 一次 Evidence 可衍生 **0..N 个 Claim**（一次输入可拆出多条结论）；
- 一个 Claim 引用 **1..N 条 Evidence**（下界"至少 1"即不变量①"结论必须引用证据"）；
- **claim→claim 推理保留**：Claim 也可经谱系边从其它 Claim 派生（无直接新 Evidence），此时其证据 = 前置 Claim 的证据（传递可得）。
  ⚠️ 已知风险：链式推理近似"多次蒸馏"，可能不可控地跑偏/幻觉。**决策：先做，落地后观察其漂移与错误率，再决定是否限跳/收紧**（不在此刻堵死）。

### Lineage Edge 的边类型与 Claim 生命周期（2026-08-15 收敛）

| 边 | 方向 | to | 语义 | 生命周期 |
|----|------|-----|------|---------|
| `supersedes` | A→B | B（新 claim） | A 被 B 取代（A 错误/过时/被纠正/宽让位窄） | 永久，单调增 |
| `generalizes` | 情景→语义 | B | B 从 A 提炼（scope 提权），**A 仍 active** | 永久，单调增 |
| `contradicts` | **双向 A↔B** | 对方 | 冲突无法自动裁决，双方 disputed | **临时**：仲裁后删除双向边 + 改写为 supersedes |
| `retract` | A→**NULL** | 空 | 撤销（forget/清理），无替代者 | 永久，单调增 |

- **active = 无"失效类出边"**（`supersedes` / 未解决的 `contradicts` / `retract`）；`generalizes` 是派生边、不失效。
- **`refines` 删除**：宽→窄的下钻要么"无边"（两 claim 并存）、要么"supersedes"（宽让位窄），无独立价值。
- **contradicts 是临时状态、不保持单调增**：仲裁选 B 后删除双向 contradicts 边 + 写 A→B 的 `supersedes` 边（不需要给 B 造 B1 副本）；"系统曾纠结过"归 workbench/审计，不进 claim 谱系。
- **删除 = `retract`（逻辑删除，加边），不物理删**；物理删只留给"清理对账 bug 产生的垃圾 claim"（admin 维护）。
- **被 superseded 的 B 在 A 被 retract 后不自动恢复**：谱系是历史，A 撤销不级联翻转 B；若 B 应恢复，走显式新 `supersedes` 边（A→B，"撤销 A 恢复 B"）或对账重算（Claim 可重算）。

### Evidence 采集范围（四档，本会话收敛）

| 档 | 来源 | 性质 | 判定 |
|----|------|------|------|
| **P0 必做（已在）** | **add 接口自报** | 事实类 Evidence（agent 显式想记的） | 最便宜、意图最高，是地基 |
| **P1 下一步做** | **召回后结果上报** | **主要不是 Evidence，是复用标注**（喂复用频率/outcome 统计）；其中"结果痕迹"（diff/测试/退出码）将来可升格为"结果类 Evidence" | 先做轻量标注（被采纳/未被采纳/结果好坏）；结果痕迹 Evidence 化留后 |
| **P2 有条件** | **项目文档读取蒸馏** | 事实类 Evidence（文档片段） | 仅 opencode/dsh 这类能被动收事件的端做得了，MCP 端采不到；且与 MR-019 纠缠、ADR-0010 刚移出文档——**挂起，等解冻** |
| **P3 先不做** | **整个上下文理解** | 全量观察类 | 99% 是过程噪音；违背"agent 自报优先"分工；贵且低质。高价值观察通常已被 add/结果痕迹覆盖 |

- **P0 是"内容轴"的地基，P1 才是让北极星（价值公式）算得动的输入**（它喂最难观测的"有效性×影响"）。
- **"理解整个上下文" ≠ "存原文 dump"**：理解（LLM 蒸馏）现在不做；存原文（append-only dump 供将来重算）符合 Evidence 不可再生原则，但**存储成本需单独评估，也不现在拍板**。

### 字段语义（语义级；落库细节与类型留「实体属性文档」）

**Evidence**（不可再生核心）：

| 字段 | 语义 | 性质 |
|------|------|------|
| `id` | 唯一标识 | 存储 |
| `observed_at` | 观察发生时刻 | 存储，不可变 |
| `source_kind` | `agent_add` / `outcome_trace` / `document` / `user_correction` | 存储（编码采集四档 + 特权） |
| `content` | 原始观察文本 | 存储，不可变 |
| `scope` | 项目作用域（哪次会话/哪个容器采集） | 存储，继承采集上下文 |
| `owner` | access control：个人(P0) / 团队(P1) | 存储，继承采集上下文 |
| `embedding` | 检索用 | 存储 |
| `source_ref` | 出处（会话/插件/文件） | 存储 |

**Claim**（派生层）：

| 字段 | 语义 | 性质 |
|------|------|------|
| `statement` | 简单断言一句，**适用条件折入句子内**（如"无翻墙设备上 export HTTP_PROXY 加速 npm"） | 存储 |
| `content_confidence` | **单轴内容置信度**：P(内容为真且当前成立)，冷启动 UNKNOWN | 派生（正确性信号推导，材料化缓存） |
| `scope` + `owner` | 从 Evidence 继承；scope 可经提权变无 scope，owner 可经提权个人→团队 | 存储（提权走谱系边/审批） |
| `evidence_refs[]` | **只存"支持"本 Claim 的 Evidence（1..N）**；矛盾靠 supersede 边派生 | 存储（关联） |
| `embedding` | 检索用 | 存储 |

- **`status` 是派生物化缓存，不手工维护**：语义上 active/superseded/disputed/retracted 由谱系边派生，物理上物化一个 status 列、由**写边的同一事务**同步更新（非 `is_latest` 手工标志位），支撑召回索引（partial HNSW on active）。落库细节留「实体属性文档」。
- **`applicability` 不设独立字段**：折入 `statement`；将来 S5 需要结构化条件过滤时重跑提取拆分，无迁移债。
- **时间有效区间砍掉**（无 `valid_from`/`valid_until`）：时间失效由 supersede 承载（到期 = 主动取代），实用性衰减由复用频率承载。

### 置信度与价值信号（单轴 + 离散统计）

> 2026-08-15 二轮收敛，**取代早先的"两轴置信度"**。

**为什么不是两轴**：价值公式的三个因子（复用机会 × 有效性 × 影响）里，只有"有效性"配得上一个置信度；"复用机会"（会不会再用）是频率统计、"影响"（用了多大用）是 outcome 统计，二者够不上"置信度"，且与内容正确性强相关（对的才可能有用）。硬造一个 `reuse_confidence` 只会定义混乱（P(useful|M,C) 上下文相关 vs 全局标量实现矛盾）+ 冷启动无数据。

| 信号 | 定义 | 初值 | 更新 | 用途 |
|------|------|------|------|------|
| `content_confidence`（连续后验） | P(内容为真且当前成立) | 按 `source_kind` 弱先验，无则 UNKNOWN | 用户确认/纠正（↑）、与新证据冲突（↓）、时间衰减（缓↓到下限） | 召回精排"可信项" + 低分标"存疑" |
| `复用频率`（近期加权） | 近期被采用次数，非累计 | 0 | 消费时：被采用 → +1 | 召回精排"价值项" + 遗忘/晋升决策 |
| `outcome`（好/坏计数） | 采用后结果好坏 | 0 | 消费时：结果好坏计数 | 召回精排"价值项" + 晋升/降级决策 |

**三信号独立更新、不互相喂**：outcome 好不提 content（"有用"≠"正确"），复用高不提 content；相关性是"好 claim 三个都高"涌现的，不是交叉喂出来的。

**content 计分规则（evidence→claim reinforce，2026-08-16 定）**：

> content_confidence 的**证据侧更新**按"独立证据 × 强度 × 派生折扣 − 负向"计分，再映射为 Beta 更新
> （α 累加正向，β 累加负向）。**被使用（report_effect）永不喂这个分数**——使用/复用/outcome 走独立通道。

| 因子 | 规则 |
|------|------|
| **独立证据强度** | 每条独立原始观察按强度加权（非全 1 分）：artifact 验证 1.0 / 用户另一场合 verbatim 明确陈述 0.8 / 用户 paraphrase 0.6 / agent 提炼(paraphrase) 0.3 / agent 推断(inference) **0** / 仅被召回或被使用 **0**。`extraction_type` 提供 verbatim/paraphrase/inference 门控 |
| **独立证据闸门** | 只有"新的原始观察"计数；同源复述（用户说→agent 总结→摘要再提）**只算 1 个**——对账规则 "reinforce 只认新原始观察，agent 自陈/复述不构成 reinforce 证据" |
| **派生折扣** | claim→claim 派生继承证据权重时**每跳 ×0.7**（防链式推理自我强化/漂移，v1 #6 落地）；决策/推断类可更严（0.5），偏好类可放宽——M2 对账技术设计细化 |
| **负向通道** | 矛盾证据（执行失败/用户纠正/代码对不上）**扣分**：新 evidence 与 claim 冲突 → 触发 supersede（不是加分）；contradicts 仲裁后改写 supersede。计分不成立（冲突 claim 不因"说得多"保持高分） |
| **分数形态** | `score = Σ(独立证据强度 × 派生折扣) − Σ(矛盾证据强度)`；score → Beta(α,β) 的 α+β 量（evidence mass），`content_confidence = Beta 期望`（概率语义供展示）——两者并存不冲突 |

**生命周期四阶段**：
1. **写入（对账）**：content 按 `source_kind` 给初值（Beta 先验）；后续新 evidence 与 claim 一致 → **reinforce 计分**（独立证据 × 强度 × 派生折扣，见上）；冲突 → supersede。复用/outcome = 0。
2. **召回（状态查询）**：结构化预过滤（scope + active）→ 向量粗排（top-K）→ 精排（相关性 × content × 复用·outcome）。
3. **消费（P1 回写）**：采用/忽略 + 结果好坏 → 复用频率 +1、outcome 计数（**不碰 content**——使用不是正确性证据）。
4. **维护（遗忘/晋升/纠正）**：近期复用 ≈ 0 且净价值为负 → `retract`；复用高 + outcome 好 → scope 提权（`generalizes`）；冲突/纠正 → `supersede`；content 长期未验证缓降。

**P0/P1 节奏**：P0 只跑阶段 1+2（复用/outcome 恒 0，排序退化为"相关性 × content"）；P1 接入遥测后阶段 3/4 才激活。

### scope 与 owner（核心维度）+ 提权

- **scope = 项目作用域**：适用条件里最重要、最结构化的一维（"只在 memory_recall 项目生效"）。
  **Evidence 通常有 scope**（继承采集上下文）；**Claim 继承 Evidence 的 scope，但可经提权变无 scope**。
- **owner = access control（数据归属）**：个人(P0) / 团队(P1)；砍掉"项目"作为 owner（项目是 scope，不是归属）。
  两个正交维度取代 S4 的 `owner×project + visibility`（visibility 被 owner 的"个人/团队" + scope 的"项目"分解）。
- **提权（promotion）两条，审批机制不同**（因风险不同）：

| 提权 | 含义 | 对应 | 机制 |
|------|------|------|------|
| **scope 提权** | 有 scope → 无 scope（项目内知识 → 全局知识） | S1 质变（`generalizes` 边） | **系统主动 + 用户审计**（事后） |
| **owner 提权** | 个人 → 团队（个人知识 → 团队知识） | S4 迁移 | **系统建议 + 用户审批**（事前） |

- 理由：scope 提权最坏是"一条略错的全局 Claim"（可经 supersede 纠正，风险低）→ 可事后审计；
  owner 提权是把私人数据共享给团队（风险高）→ 必须事前审批。
- 两条提权都依赖 workbench（MR-011）作界面：scope 提权要"审计面"，owner 提权要"审批面"。

### 举例（仓库真实事实）

- **Evidence**：「2026-08-13 会话里确认：正式规划文档是 docs/PROJECT_PLAN.md」。
- **Claim**：「memory_recall 的正式规划文档是 PROJECT_PLAN.md」（`evidence_refs` 指向上条）。
- **Edge**：旧 Claim「规划文档是 development-plan.md」 —`supersedes(reason="新会话确认规划已迁移")`→ 新 Claim；触发证据因果记入 `claim_activity`（`triggered_by_evidence_id=上条`，2026-08-18 起审计日志承载）。
- **提炼（S1）**：情景 Claim「这台机器上 export HTTP_PROXY 加速 npm」 —`generalizes(reason="去掉具体时空仍成立")`→ 语义 Claim「无翻墙设备上 export HTTP_PROXY 可加速 npm」。

## 关键原则（在 note 的 5 不变量上甄别后，只取这一组）

| 原则 | 内容 | 判定 |
|------|------|------|
| ① 证据/结论分离 | 结论必须引用证据（直接 1..N，或经谱系边传递）；证据不可变 | **保留**（地基） |
| ② 变更 = 谱系边 | 任何状态变更是一条边（type + reason），绝不静默覆盖；推理在边上，**触发证据因果走 `claim_activity` 审计日志**（2026-08-18 定案） | **保留**（已有 update 版本链雏形） |
| ③ 有效期一等公民 | （原：`valid_from`/`valid_until` 回答"现在还成立吗"） | **字段砍掉**："现在还成立吗"由谱系派生（无失效出边）+ content 置信度回答，不设时间区间字段 |
| ④ 当前状态派生 | 没有 `is_latest` 手工标志位；active = "无失效类出边的 Claim" | **保留**（消灭孤儿旧版本 bug 类）；工程上物化 status 派生缓存（写边事务内维护）加速召回 |
| ⑤ 召回四问默认契约 | 每次召回都回答"还成立吗/被什么取代/证据是什么/T 时刻信什么" | **只留一问**："证据是什么"（纠错时能点开）；其余三问**砍** |

一句话：**我们要的是"价值导向的记忆生命周期"，不是"记忆演变审计系统"。**

## 两链路（定义，非实现）

- **写路径 = 对账（reconciliation）**：新 Evidence 进来 → 定位相关 Claim（向量/scope）→ 与当前 active Claim 比对 →
  冲突则 supersede（新 Claim + 边 + reason + 证据）/ 新事实则建 Claim / 冗余则 reinforce（追加证据引用、提 content 置信度）。
  用户显式纠正 = 特权 Evidence（`source_kind=user_correction`），对账时直接 supersede 现有 Claim，不走 LLM 推理。
- **召回路径 = 状态查询**：query → **结构化预过滤（scope 匹配 + status=active）→ 向量粗排（top-K）→ 精排（相关性 × content × 复用·outcome）** → 注入。
  返回"当前为真"的 Claim，不是"相似度最高的文本"。

## 权衡（为什么这么取舍）

- **砍"任意 T 切片 / 四问全默认"**：审计回溯是技术秀技，不是用户价值；既然 Claim 可从 Evidence 重算，
  "回溯当时"靠重算而非靠存，谱系边只需记录"这一步为什么这么推"（推理）。
- **Evidence 不可再生 → 采集入口（P0 add）是地基、必须在核心**：漏采一次观察 = 永久丢失；**遥测/复用标注（P1/S-pre）是第二期增强**，喂复用/outcome 统计、激活遗忘/晋升，不阻塞核心闭环。
- **"可重新计算" = 可重新派生，非 bit 级复现**：派生靠 LLM 抽取有非确定性；原则是"原始输入永不丢、派生随时可重跑"，
  不承诺"重跑结果完全一致"。
- **memory vs knowledge 同源**：二者都是 Claim，差异只在抽象度（情景→语义，靠 `generalizes` 边）
  与复用价值分；晋升 = 一条边 + 价值变化，不是"换一种存储"。
- **claim→claim 推理的风险**：链式推理近似"多次蒸馏"，可能不可控漂移/幻觉。暂**保留并观察**，
  不在此刻限跳；落地后以其漂移率/错误率决定是否加"限跳 / 强制回溯到 Evidence / 降置信"的收紧。

## 影响面（开发阶段才动，此处只定方向）

- **数据模型**：`memories` 大杂烩 → Evidence / Claim / Lineage Edge（用户纠正 = 特权 Evidence `source_kind`，不单独成表）；Entity/主题 = P2 可选附属（关系表反挂 Claim）。
- **API/插件**：召回 = 状态查询；写 = 对账；S-pre 遥测 = Evidence 采集管线（[插件信号面盘点](../../notes/research/2026-08-14-reuse-feedback-signals/10-plugin-signal-surface.md)：仅 opencode/dsh 两端能被动采 outcome）。
- **现有 S0–S5 挂点**：S0 6 维度 = Claim 属性（含 scope/owner）；S1 提炼 = Edge 的 `generalizes` + 判据（scope 提权）；
  S2 = content 单轴置信度 + 复用/outcome 离散统计；S3 判定 = 对账触发 + workbench 裁决；S4 归属 = owner 提权（个人→团队）+ scope 提权（项目内→全局）；
  S5 召回 = 状态查询；S-pre = Evidence 采集。

## 已拍板 vs 待拍板

**已拍板（持续收敛）**：
1. 北极星 = 价值公式（含错误惩罚），状态有效性只是"有效性"因子的度量。
2. 证据/结论分离作为地基；**Evidence 是唯一不可再生数据，Claim 全部派生可重算**。
3. **Evidence 与 Claim 的边界**：Evidence = agent 生命周期输入（含 agent 自行蒸馏输出，agent 的自陈只是观察不是结论）；Claim = 系统理解 + 与其它 Claim 碰撞后的结论/推论。二者**多对多**（Evidence 0..N Claim；Claim 1..N Evidence，或经谱系传递）。
4. **用户显式纠正 = 特权 Evidence**（`source_kind=user_correction`），不单独成类；对账时直接 supersede，不走 LLM 推理。
5. **Claim 只存简单断言（statement），推理放在 Lineage Edge 上**。
6. **claim→claim 推理保留，先做再观察**（已知"多次蒸馏"漂移风险，落地后按漂移/错误率决定是否收紧）。
7. 演变只做"推导记录"，不做"任意 T 切片 / 四问全默认"的审计回溯。
8. 置信度 = **content 单轴 + 复用/outcome 离散统计**（2026-08-15 二轮收敛，取代两轴）：content 是唯一置信度（正确性，连续后验）；复用频率/outcome 是离散价值信号、不物化置信度；三信号独立更新、不互相喂。
9. **Evidence 采集范围分四档**：P0 add 自报（必做，已在）→ P1 召回结果上报（先做复用标注，结果痕迹 Evidence 化留后）→ P2 项目文档蒸馏（挂起，仅 opencode/dsh 可采，等 MR-019 解冻）→ P3 整个上下文理解（**不做**）。
10. **字段语义（v1，语义级）**：Claim = `statement`（适用条件折入句子）+ `content_confidence`（单轴派生）+ `scope`/`owner`（从 Evidence 继承）+ `evidence_refs[]`（只存支持）；**`applicability` 不单设字段、`valid_from`/`valid_until` 砍掉、`status` 派生物化缓存**（写边事务内维护，落库细节留「实体属性文档」）。
11. **Evidence 需要归属**：`scope`（项目作用域）+ `owner`（个人/团队，继承自采集上下文）；Evidence **不关联 Claim**（有利于从 Evidence 重建整张 Claim 图）。
12. **scope = 项目作用域（核心维度）**：适用条件里最重要、最结构化的一维；Evidence 通常有 scope，Claim 继承 scope、可经提权变无 scope。
13. **owner = 个人/团队（access control）**；砍掉"项目"作为 owner（项目是 scope，不是归属）；`owner×scope` 取代 S4 的 `owner×project + visibility`。（2026-08-15：团队 owner 定为 P1，见 #20。）
14. **提权两条**：scope 提权（项目内→全局 = S1 质变，**系统主动+用户审计**）；owner 提权（个人→团队 = S4 迁移，**系统建议+用户审批**）；均依赖 workbench（MR-011）。
15. **Entity/entity_network 与 主题（category/tags）= P2 可选附属**，不进核心；Entity 经关系表反挂 Claim，Claim 不主动关联 Entity。
16. **画像 = Claim + Evidence 的读视图，是第一轮注入的一半**：偏好层 = 筛「明确个人偏好 + 影响 agent 思考方式」的 Claim（判据是"是偏好且改变 agent 怎么想/做"，不是"时间够长"）；近期工作层 = 近期 Evidence 的「最近在做什么」总结；画像无独立生命周期/独立存储，`memory_profiles` 缓存表废除（收 MR-008/018）。第一轮注入的另一半 = 首句 query 动态检索（S5 状态查询），补"现在要做什么"的任务上下文。
17. **写路径可靠性**（收 MR-004）：client 异步上报 + 失败重试 3 次（不做队列）；后端接口异步化——写接口 ms 级落原始 Evidence，embedding / 对账 / 理解等复杂计算后端异步执行 + 自行重试；记忆正确性不损害用户主流程。
18. **提炼判据 = 去上下文后仍为真且可复用**（S1 心脏）：Evidence 里可复用的语义断言提成 Claim；带具体时空的情景部分不丢弃、进画像「近期工作」；证据未写明原因的跨证据泛化 = claim→claim `generalizes` 边（承接 #6，先做再观察）。
19. **文档系统（git/docs）= P3+ 附属/独立模块**：非核心、非记忆系统；Evidence/Claim 只在 PG、只在 memory_recall，不管落文档到 git；可选内置"帮用户落文档"的 prompt，长期再做。
20. **owner = 个人(P0) + 团队(P1)**（更新 #13 的"v1 只个人"）：团队 owner 是 P1 一等实体；记忆与知识都是 Claim，都存 memory_recall（含个人+团队）。
21. **任务级上下文 = 召回侧优先**：首次召回丰富/准确优先；采集侧用 `save_thread` / 主动 summary / 主动上报，不 hack 全上下文（承接 #9 的 P3 不做）。
22. **边类型收敛**：`supersedes` / `generalizes` / `contradicts`（临时）/ `retract`（单端，to=NULL）；删 `refines`；active = 无"失效类出边"（supersedes / 未解决 contradicts / retract），`generalizes` 不失效。
23. **contradicts 是临时状态、不单调增**：仲裁选 B 后删除双向 contradicts 边 + 写 A→B 的 `supersedes` 边（不造 B1 副本）；单调增只对永久边（supersedes/generalizes/retract）成立。
24. **砍 `valid_from`/`valid_until`**：时间失效由 supersede 承载（到期 = 主动取代），实用性衰减由复用频率承载。
25. **`status` 物化派生缓存**：语义上由谱系边派生，物理上物化 status 列、写边同一事务同步维护（非手工标志位），支撑召回 partial HNSW on active。
26. **召回顺序**：结构化预过滤（scope 匹配 + status=active）→ 向量粗排 → 精排（相关性 × content × 复用·outcome）；scope 在预过滤层做，不等精排。
27. **Claim 删除/恢复**：删除 = `retract`（逻辑删，加边），不物理删；被 superseded 的 B 在 A 被 retract 后不自动恢复，走显式 `supersedes` 边或对账重算。
28. **Evidence 处理状态 = 通用状态机**：`processing_state`(pending/processing/done/failed) + `current_step`(开放枚举) + `last_error{step}`，拆独立 `evidence_processing` 表（步骤名是数据非列，可扩 5+ 步）。
29. **衰减曲线不物化、延后启动**（2026-08-16）：content 无 `decay_at`/半衰期列；只在召回精排时按 Claim 属性（observed_at/复用频率）现算，初始恒等项占位，发现问题再激活（B1）。
30. **提炼触发 = 显式优先，自省后置**（2026-08-16）：一期提炼/晋升靠用户显式「记住」+ 手动裁决；稳定后 Low 峰期定时跑「每日自省」（对当日产生数据的用户，峰谷定价降成本）（B3）。
31. **投毒 guard 走证据处理流**（2026-08-16）：新 evidence 对账时若同时破坏大量 claim → 预警 + 暂停破坏 + 裁决页用户再确认；属 crystal 完整项目，非一期（B4）。
32. **MR-017 注入 cap 仅对 v5 有效**（2026-08-16）：非 crystal 契约；crystal 重设计 `/api/v2` 与粗排，参考"不静默丢弃"教训但不被旧 6/6/4 约束（C9）。
33. **crystal 专项完整里程碑**（2026-08-16）：见 [milestone.md](milestone.md)——裁决面 + 洞察面双轨个人工作台、价值引擎不做/推后、以迁移路径 Stage A–E 为工程节奏，每 M 带文档门槛（研发流程，§3.5）；需求层见 [prd.md](prd.md)（用户故事 US-* + 能力验收 A1–A11）。
34. **content 初始置信度定案（B5，2026-08-16 外部调研五平台收敛）**：冷启动初值 = source_type × claim_type 网格弱先验（Beta 参数化），**不含 LLM 自报**（冷启动完全弃用，仅留作 V2 校准 feature）；**2026-08-16 用户评审修正：`root_observation_id`（lineage 根）缓置**——它防的 P2/P3 自动采集复述路径当前挂起/不做，P0 add（显式自报=新原始观察）+ P1 report_effect（只动复用统计、不新增 evidence）不产生复述；防线=**对账规则**（reinforce 只认新原始观察，agent 自陈/复述不 reinforce）+ **幂等键**（防 v1 #17 重试重复入库）；**reinforce 计分规则**（独立证据 × 强度 × 派生折扣 − 负向，使用信号不喂分）见 §置信度与价值信号；stock 先验档位为工程 heuristic，V2 用 Beta-Binomial 分层收缩校准。
35. **Lineage Edge 去 `triggered_by_evidence`，审计迁独立表（2026-08-18 用户拍板）**：边不再驻留"触发证据"字段（lineage_edge 只表达"谁取代谁 + 叙述性 reason"）；因果追溯（谁/哪条证据/什么动作导致变更）由独立 append-only 审计日志 `claim_activity` 承载（非核心模型，与原 `workbench_audit` 合并为同一张表）；**重建 = 重算**：按时间重跑对账，接受 LLM 不确定性，不依赖该字段；**幂等主防线** = `UNIQUE(from,to,type)` 永久边约束（不受影响）。
36. **Claim 原子化判据（M2.1，2026-08-19 外部调研五平台收敛 + 项目内核对）**：粒度不由字数/句子数决定，由**独立生命周期**决定——两个部分未来可能被分别裁决（一个被纠正/失效/取代，另一个仍成立）→ 是则拆。落地四测试：独立检索 / 独立纠正（最强信号）/ 独立失效 / 独立证据。整篇文档原文照抄不是"粗 Claim"而是"分层错误"（原文属 Evidence，Claim 只放提炼出的可独立维护结论）。
37. **拆条形态（M2.1，2026-08-19 定案）**：一条 Evidence → 0..N 条**平行原子 Claim** + 轻量 `event_key` 弱组织字段（非实体、无 truth lifecycle、不可被用户裁决、只是"同一次 Evidence/决策表达中一起拆出来"的 grouping hint；**event_key 不参与真值**——成员被 supersede 不连带失效同 key 其他成员）；不做 Group/Decision 实体（Entity/主题 P2 不进核心的约束下，持久化分组=半实体网络雏形）；碎片化靠召回时动态聚合解决。二期观察到真实 usage pattern 再演进成 Decision/Group，event_key 可平滑迁移。
38. **拆条质量与流程（M2.1，2026-08-19 定案）**：**宁可多拆不要漏拆**（错误可恢复性不对称——拆粗破坏用户裁决历史、拆细可合并且不破坏 confirm 记录）；**拆条与碰撞判定分步**（LLM ① 拆条 → 检索候选(embedding，非 LLM) → LLM ② 碰撞判定批处理 N 条；拆条阶段输出不含冲突/支持字段）；质量监控 = 拆出条数分布/单条长度分布，落尾部定向抽检。claim_kind 无类型级硬上限，软规则：fact/constraint 积极拆、preference 折入 context、**learned-pattern 保留"条件–做法–结果"最小完整结构**（防因果断链）。
39. **证据引用与文档类例外（M2.1，2026-08-19 定案）**：拆条输出带 `evidence_quote`（原文精确子句）——拆条本身切断置信度污染（不同主题证据不再 reinforce 进同一 claim），quote 主要为溯源 UX（点开证据高亮），不用字符级 offset 坐标（清洗/tokenizer 差异必错位）。**文档类例外**：原子判据适用于对话类/长消息；有路径文档（P2 采集）走"概括 + 指针"（claim=文档存在+路径+主题，细节按路径读原文）。**双上限 + 默认隔离**：evidence 字数上限（1500 字）+ 拆出条目上限（15 条），超上限默认不进系统计算（不自动拆条/对账）、evidence 原文保留、留存 workbench 人工裁决（不静默丢弃，MR-017 教训）。

**待拍板（后续逐项）**：

> 2026-08-15 补入：按「讨论清楚再开发、避免返工」扫描了 notes 的未决问题 + OPEN issues，
> 把 v1 原先漏掉的缺口补进本节。拍板问题分三档——**A 档**进数据模型/写路径前必须定（否则返工）；
> **B 档** S2/S3 阶段再定（不阻塞核心）；**C 档**随迁移路径/实体属性文档收尾。
> **2026-08-15 更新：A 档 5 项已拍板（#16–#21）；二轮收敛新增 #22–#28（边类型/置信度单轴/砍有效区间/status 物化/召回顺序/删除恢复/处理状态机）。**
> **2026-08-16 更新：B/C 档逐项拍板（B1/B3/B4/B6、C1 命名/C2 MR-017/C3 Entity，见下）；B5 初值经外部调研收敛定案（见 #34）；剩 B2 策略 open；crystal 专项完整里程碑见 [milestone.md](milestone.md)。**

**待落设计文档（下一步要写的；写它们时把下面的拍板问题一并定掉）**：

1. 渐进迁移路径：**已出草稿**（[migration-path.md](migration-path.md)）；收 C 档 8（迁移框架，已定**不引入**）；4 未决点已拍板（2026-08-16）。剩迁移粒度 / `container_tag` 拆分 / 鉴权映射 / 退役标准。
2. workbench 裁决界面（MR-011）：用户纠正本身已定为特权 Evidence（已拍板 #4）；**2026-08-16 扩充为"裁决面 + 洞察面"双轨**，见 [milestone](./milestone.md) M2。确权/纠错/遗忘/审计/审批 API 与权限边界（个人 key + API）。
3. 「实体属性文档」：**已出草稿**（[entity-attributes.md](entity-attributes.md)）；剩 `claim_kind` 取值、`evidence_refs` 数组vs关系表、`claim_usage` 落点待定。Entity/主题 P2 → 另见「P2 实体网络文档」。

**拍板问题 B 档（S2/S3 阶段再定，不阻塞核心）——2026-08-16 更新**：

1. 衰减曲线形态 → **决策：不做 DB 留存、预留位置延后启动**；只在召回精排按属性现算（初始恒等项），发现问题再激活。收 entity-attributes §7 待定。
2. 低置信召回策略 → **不拍板**：改"召回行为洞察"先行（粗排全展示 + 精排分数/截断可见，只标注不静默丢弃），策略等真实数据后定；归 MR-011 洞察面。
3. 提炼/晋升触发主信号 → **决策：一期显式触发为主**（用户「记住」+ 手动裁决）；稳定后低峰期定时跑「每日自省」（峰谷定价降成本，每天对当日产生数据的用户跑一次），后置。
4. 安全门之投毒 → **决策：证据处理流做 guard**——新 evidence 同时破坏大量 claim → 预警 + 暂停破坏 + 裁决页再确认；**crystal 完整项目做，非一期**。
5. LLM 自报信心初值修正规则 → **决策（2026-08-16 外部调研收敛，B5 定案）**：**冷启动初始置信度 = 来源分层先验（source_type × claim_type 弱先验，Beta 参数化），不含 LLM 自报**；自报信心冷启动完全弃用（仅保留为 V2 校准的潜在 feature）；真正的置信度靠后续证据更新。**2026-08-16 用户评审修正：`root_observation_id` 缓置**——P0 add + P1 report_effect 不产生复述（add=新原始观察，report_effect 只动复用），防线 = 对账规则（reinforce 只认新原始观察）+ 幂等键（防重试重复入库）；将来 P2/P3 采集扩大解冻时再引入。详见 [调研最终结论](../../notes/research/2026-08-16-llm-confidence-initial-value/99-final-conclusions.md)。
6. 团队多来源置信加权 → **决策：不现在设计**（只影响召回精排；推迟到团队 owner P1 之后）。

**拍板问题 C 档（产品层 / 工程层，随迁移收尾）——2026-08-16 更新**：

7. **命名漂移（MR-010）** → **决策：主线产品名 "Memory Recall" 不变**；crystal 是本次迭代专项代号（非新品牌）；收敛 docs 之外文档到统一叙事（当前 v5 能力/定位 + crystal 专项说明及链接）。
8. 迁移框架（MR-013）→ 并入「渐进迁移路径」设计（**已定不引入**）。
9. 注入 cap 契约（MR-017）→ **决策：仅对 v5 有效，非 crystal 契约**（crystal 重设计 `/api/v2` 与粗排召回，参考其"不静默丢弃"教训但不作为必须契约）。
10. Entity 合并策略（MR-009）→ **决策：随 Entity 构建**，暂不考虑（非核心，P2）。

> **crystal 专项完整里程碑**（能力范围 / 节奏 / 不做清单）见 [milestone.md](milestone.md)。

**已拍板、不再重议（供对照，勿重复讨论）**：

- MR-006（统一知识对象 = Claim）→ 已拍板 #2/#3（证据/结论分离 + 二者边界）。
- MR-020（版本历史双路径不一致）→ 谱系边统一解决 → 已拍板 #5/#7（推理在边 + 演变只做推导记录）。
- MR-019（文档→记忆蒸馏）→ 挂起为采集 P2 档 → 已拍板 #9。
- 去向语义（读写权限 vs 适用条件）→ scope=适用条件 / owner=归属 → 已拍板 #12/#13。
- 命中率回收缺口 → S-pre 遥测基座 → 已拍板 #9（P1 复用标注）。

## 验收标准（方向性，开发阶段细化）

- 召回结果能回答"这条现在还成立吗"（谱系派生：无失效出边）+"它的证据是什么"（证据引用可点开）。
- 纠正一条过时结论时，旧结论不丢、生成一条带 reason 的 supersede 边，且无需人肉改 `is_latest`。
- 任意时刻可从 Evidence 重新派生 Claim（重建能力），不依赖任何手工标志位。

## 实施要点（渐进，暂不排期）

- 先定本文 + 抽取 ADR（证据/结论分离、当前状态派生废除 is_latest、价值公式北极星），再谈 schema 与迁移。
- 每一阶段都朝本文收敛，不做大爆炸重写。
