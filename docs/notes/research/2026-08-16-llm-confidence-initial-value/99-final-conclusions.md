# 99 · 最终统一理解与实施映射（B5 定案）

> 归属: [README](README.md) · 日期: 2026-08-16
> 输入: round-01 五平台 + round-02 四平台 + 回项目内核对（[foundation](../../../initiatives/crystal/foundation.md) / [milestone](../../../initiatives/crystal/milestone.md) / [entity-attributes](../../../initiatives/crystal/entity-attributes.md) / [memory-confidence](../../2026-08-14-memory-confidence.md)）
> 状态: **收敛完成**——B5（LLM 自报信心的初值规则）定案

## 最终结论（一句话）

**冷启动初始置信度 = 来源分层先验（source_type × claim_type 弱先验，Beta 参数化，不含 LLM 自报）；
LLM 自报信心完全弃用（冷启动），仅保留为 V2 校准的潜在 feature；
真正的置信度靠后续证据更新，且证据必须带 lineage 独立性判断（root_observation_id）防止自我强化。**

这五平台共识、无冲突，且与项目已拍板（v1 #8 单轴 content_confidence、#24 砍 valid 区间、source_kind 弱先验）兼容。
详见 [round-01 统一理解](08-round-01-conclusions.md) + [round-02 统一理解](09-round-02-conclusions.md)。

## 共识结论清单（收敛后）

| # | 结论 | 证据强度 | 回项目内核对 |
|---|------|---------|-------------|
| 1 | **LLM 自报信心不能当概率**（过度自信、校准差、模型信息量少处更自信） | 5/5 平台 + 多处文献 | 验证 memory-confidence 已定；**升级为"冷启动完全忽略"** |
| 2 | **冷启动初值 = 来源分层先验**（用户纠正/显式 > 直白陈述 > 自动推断 > 纯猜测） | 5/5 平台排序一致 | 与 v1 "source_kind 弱先验"同向；**细化为 source×claim_type 网格** |
| 3 | **自报分数降级为弱特征/过滤门槛，严禁跨档跳变** | 5/5 平台 | 采纳：冷启动不用，V2 校准后作为 feature |
| 4 | **置信度 = 可更新的起点，不是终值**；冷启动应标记"未验证"而非给精确数字 | 5/5 平台 | 与 v1 "content 派生、后续更新"一致；UI 展示来源而非裸分数 |
| 5 | **内容真实 ∥ 当前有效两个维度概念分离** | ChatGPT/Grok/Claude | **采纳概念，不新增字段**（见下） |
| 6 | **truth discovery 经典算法不做**（单用户单来源无信息可迭代） | ChatGPT+Claude 一致收敛 | 采纳：V1 规则先验 → V2 校准 → V3 才考虑 claim-level TD |
| 7 | **source reliability = source×claim_type 分层历史统计 + Beta-Binomial 收缩** | ChatGPT+Claude 一致 | **落地形态**：v1 弱先验的工程细化 |
| 8 | **证据独立性 = lineage 判断**：只有"不可由已有证据机械复制的原始观察"算独立；模型复述/总结/召回引用不算 | ChatGPT（强）+ doubao 同向 | **新增需求**：evidence 加 root_observation_id |
| 9 | **自强化失败模式（epistemic feedback loop）**：系统越来越相信自己说过的话 | ChatGPT（强提示） | 新增监控指标 EIR（独立证据比） |
| 10 | **低置信记忆双池/假说池**：默认不参与注入，但永久存储、可检索、可审计、可确认升级；"不静默丢弃"与"不默认注入"解耦 | doubao + 多产品实践 | **采纳为 MR-011 洞察面/裁决面的工程形态** |
| 11 | **草稿确认时机**：命中 + 轻负载间隙 + 冷却节流；隐性确认优先、显性兜底；严禁打断核心流 | doubao + 多产品实践 | 进 MR-011 交互设计 |

## 回项目内核对结论（收敛轮）

### 核对 1：freshness 维度 vs v1 已拍板"砍 valid_from/valid_until" → **兼容，采纳概念不新增字段**

- 外部建议的"R（来源可信度）∥ V（当前有效性）"分离，**概念上有价值**：content_confidence 内部不再混入时效因子。
- 但 V 的三大驱动信号我们**已有等价机制**：supersession（→谱系边）、访问/复用强化（→复用频率）、时间衰减（→content 缓降 或 召回现算，B1 已定不落库）。
- 结论：不新增 `valid_from`/`valid_to` 字段（维持 v1 #24）；V 的时效分量在**召回精排现算**（B1 的"恒等占位项"将来激活成 freshness 因子）。语义上认同"content_confidence 尽量收敛为 P(内容为真)"。

### 核对 2：跨会话复现独立性 → **采纳 lineage 判断，升级后续信号设计**

- memory-confidence 曾把"跨 session 稳定复现"列为后续正向信号，但**未做独立性限定**——ChatGPT 指出这会踩"echo amplification"。
- 收敛：**同一用户的跨会话陈述，若都追溯到同一原始观察（含模型复述/召回引用回环），不新增独立证据**；只有新的原始用户陈述（不是"我昨天说过"）才算。
- **落地：evidence 新增 `root_observation_id`（或 lineage 链）字段**——这是本轮调研最强的新增需求，进 entity-attributes。V2 校准与 S-pre 遥测的证据计数都基于它。

### 核对 3：source×claim_type 分层 → **落地形态确认**

- v1 "按 source_kind 弱先验"细化为**网格先验**：`(source_type, claim_type)` 组合各给 Beta 先验（如 user_explicit+preference 0.98 / llm_inference+project_architecture 0.65 等语义档位）。
- V2 用 Beta-Binomial hierarchical 收缩，小样本类别向总体收缩（避免"3 条全对→100%"）。
- 这是 v1 初值规则的工程细化，不改变 v1 决策。

## 实施映射（进 crystal 设计/开发）

| 落点 | 改动 | 阶段 |
|------|------|------|
| [foundation](../../../initiatives/crystal/foundation.md) | **reinforce 计分规则**（独立证据 × 强度 × 派生折扣 − 负向，被使用不喂分）已落 §置信度与价值信号 + #34 | 已回写 |
| [entity-attributes](../../../initiatives/crystal/entity-attributes.md) | evidence 保留 `extraction_type`；root_observation_id 缓置（见实施校正）；初值语义 = source×claim_type 网格 Beta 先验（待落具体取值表 + 强度权重表，M1/M2） | M1/M2 |
| [milestone](../../../initiatives/crystal/milestone.md) | B5 决策门 → 已收敛；M2 §4.1 已加 reinforce 计分实现指引（细化为对账技术设计 v1） | 已回写 |
| [prd](../../../initiatives/crystal/prd.md) | US-R4 已加计分规则引用；§5 B5 项已更新 | 已回写 |
| MR-011（待落文档） | 洞察面：低置信"假说池"视图（可查、可审计、可确认升级）；裁决面：草稿确认交互（命中+轻负载+冷却；隐性优先）；展示来源标签而非裸分数 | M2 |
| S-pre / P1 遥测 | 复用/outcome 证据计数独立于 content（不喂分）；EIR 缓置（P2/P3 解冻时引入） | M2+ |

## 边界与后续（诚实声明）

- **数值类建议（先验档位、α/β、half-life、independence weight）均为工程 heuristic，不是文献标准值**；
  上线后应用真实日志 A/B，V2 用 Beta-Binomial 收敛到实测。
- 一致性采样（多次独立提炼看收敛）作为 content 信号**未被证伪也未证实**：Claude 建议若启用需按记忆类型分层的小实验（100–200 正负样本、盲标、对照自报分数与零成本特征）。**一期不启用**，列入 P2 候选。
- 文献引用见各平台回答原文（ChatGPT: truth discovery / calibration 系列；Claude: 知识融合 / 时序 truth discovery；Grok: agent memory 实践；Gemini: logprobs / verbalized confidence；doubao: Mem0 / Cursor / LangGraph 等产品实践）。

## 实施校正（2026-08-16 用户评审，取代上文相应结论）

> 用户评审指出：root_observation_id（lineage 根）**在当前采集面下是过早设计，应缓置**。本校正已回写
> v1 #34 / §B5·5、entity-attributes §2/§7、milestone 决策门、prd §5。

- **理由**：会"复述"的采集路径只有 P2（文档蒸馏，挂起 MR-019）与 P3（全量上下文，明确不做）；
  P0 add = agent 显式自报新观察（每次天然独立，无复述）；P1 report_effect = 只动 `claim.reuse +1`
  （不新增 evidence、不碰 content，你确认的契约）。故"复述 → 置信虚高"无入口 → 不需要 lineage 根。
- **替代防线（保留）**：① **对账规则**："reinforce 只认新的原始观察；agent 自陈/复述不构成 reinforce 证据"；
  ② **幂等键**（source_ref 会话消息 ID + content 哈希）：防 v1 #17"client 异步上报 + 重试 3 次"在
  服务端已落库但响应丢失时的重复入库（幂等问题，非 lineage 问题）。
- **保留项**：`extraction_type {verbatim/paraphrase/inference}`——服务 source×claim_type 网格初值的
  "提炼过程"维度（inference 类降档防初值虚高），独立于独立性判断，**不缓置**。
- **将来触发条件**：P2/P3 采集扩大解冻（文档蒸馏重启、或引入全量上下文捕获）时，再引入
  root_observation_id（新列/新表，无迁移债），届时对账规则才需要字段支撑。

*状态: 收敛完成 · 日期: 2026-08-16 · 校正: 2026-08-16 用户评审（root_observation_id 缓置）· B5 从 open 转已拍板*