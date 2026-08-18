# ADR-0013: 当前状态派生，废除 is_latest 手工标志位（推理在边）

> 状态: Accepted
> 日期: 2026-08-14
> 系统: crystal
> 关联: [目标模型 v1](../initiatives/crystal/v1.md) · [ENTITY_DESIGN](../ENTITY_DESIGN.md) · AGENTS.md「两种取代语义」说明

## 背景

现状用 `is_latest` 手工标志位表达"当前版本"，需人肉维护，已积累"孤儿旧版本"
（`is_latest=false, version=1, root_memory_id=NULL`）这类设计产物（AGENTS.md 记为"设计产物不是数据损坏"）。
目标模型要求"当前状态"是查询派生的，不是手工维护的标志位；同时结论的"为什么这么变"需要落点。

## 选项

- A: **保留 is_latest 标志位**（现状）。
- B: **废除标志位，当前状态 = "没有出边的 Claim"**（谱系 DAG 一次查询派生）。
- C: **status 字段落库**（active/superseded/retracted/disputed），由对账更新。

## 决策

选 **B**（status 默认不落库；"派生 vs 落库"的性能取舍留「实体属性文档」，若派生性能达标则不保留 status 字段）。

同时：

- **Claim 只存简单断言 `statement`，推理/理由放在 Lineage Edge 上**（`reason` + `triggered_by_evidence`）。
- **claim→claim 推理保留，先做再观察**：已知链式推理近似"多次蒸馏"、可能漂移/幻觉；落地后按漂移率/错误率
  决定是否加"限跳 / 强制回溯到 Evidence / 降置信"的收紧（此刻不堵死）。

## 理由

- 标志位是状态手工维护的 bug 来源；谱系 DAG 天然表达"最新 = 无出边"，`N:1` vs `1:1` 取代语义的纠结自动消失。
- 推理放边上是为了让 Claim 极简：推理本身就是"怎么演变"的信息，属于边，不属于 Claim 本体。

## 后果

- 正面：消灭孤儿旧版本 bug 类，取代语义统一，Claim 结构极简。
- 负面：每次"当前状态"查询需沿谱系取末端，多一跳（性能取舍留实体属性文档）。
- 跟进：claim→claim 推理的漂移/错误率观测（先做再观察的触发条件）。
- 跟进（2026-08-18）："推理/理由放边上"中的**触发证据因果**不再驻留 Lineage Edge 表
  （`triggered_by_evidence` 字段移除），改由独立审计日志 `claim_activity` 承载——边只保留
  `reason`（叙述），因果追溯走日志。见 [v1 #35](../initiatives/crystal/v1.md) 与
  [entity-attributes §5.1](../initiatives/crystal/entity-attributes.md)。
