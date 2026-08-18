# ADR-0012: 证据/结论分离，Evidence 是不可再生地基

> 状态: Accepted
> 日期: 2026-08-14
> 系统: crystal
> 关联: [目标模型](../initiatives/crystal/foundation.md) · [状态有效性 thread](../notes/2026-08-14-agent-memory-state-validity-thread.md) · MR-011

## 背景

现状 `memories` 表是"文本 + 一堆手工标志位"的大杂烩：证据与结论混在一起、结论不记来源。
状态有效性 thread 指出：长期记忆的第一等公民是"找回来的信息现在还成立吗"，其前提是能把
"原始观察"和"结论"分开。agent 自行蒸馏的"记忆"本质只是"agent 说了这句话"的观察，不是"X 为真"的结论。

## 选项

- A: **维持单一 memories 表**（证据结论混存）——现状，无法追溯"结论哪来的"。
- B: **拆 Evidence / Claim 两张表，多对多**——Evidence 不可变，Claim 可版本化。
- C: **只存 Evidence，Claim 使用时现场提取不落库**——最简单，但结论没有可寻址对象。

## 决策

选 **B**。

- **Evidence = agent 生命周期的输入**（会话里的一句话、一段代码事实、一次工具结果、一个文档片段，
  **含 agent 自行蒸馏/注入的输出**——agent 的自陈只是观察不是结论）；是系统**唯一不可再生数据**，append-only、不可变。
- **Claim = 系统对 Evidence 理解、并与其他相关 Claim 碰撞后的结论/推论**；全部**派生、可重算**。
- 二者**多对多**：Evidence 0..N Claim；Claim 1..N Evidence（或经谱系边传递）。
- **用户显式纠正 = 特权 Evidence**（`source_kind=user_correction`），不单独成类；对账时直接 supersede，不走 LLM 推理。
- **Evidence 不关联 Claim**（回指由 Claim 的 `evidence_refs[]` 承担），利于从 Evidence 重建整张 Claim 图。

## 理由

- 选 B 而非 C：价值公式 / 置信度两轴 / 晋升都作用在"事实"上，需要**可寻址的结论对象**；
  现场提取的 Claim 无地址，无法复用计数、无法置信度累积、无法晋升。但 Claim 是派生缓存，可随时从 Evidence 重算，
  所以"可重算"是原则、不是负担。
- 证据/结论分离是这次最大的概念翻转，其余（时间有效性、谱系边、当前状态派生）都是它的推论。

## 后果

- 正面：纠错闭环（MR-011）有据可依（结论能指回证据）；不静默覆盖；系统可重建。
- 负面：引入**对账（reconciliation）**这个最难、最易错的 LLM 任务（冲突判定）；
  Evidence 采集（S-pre）升为最高优先级——漏采一次观察 = 永久丢失。
- 跟进：对账的冲突判定粒度与评测（对应 MR-009 实体合并、状态有效性 thread 的 5 类评测场景）。
