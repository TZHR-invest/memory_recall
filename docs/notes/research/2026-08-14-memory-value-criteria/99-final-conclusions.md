# 最终统一理解（Round 1 收敛）

> 类型: 调研（统一理解）
> 调研: 2026-08-14-memory-value-criteria
> 说明: 五平台（ChatGPT/Claude/Grok/Gemini/doubao）round-01 收敛；外部回答是素材不是事实，
> 以下对照表的实施映射已与本项目源码落点核对（schema.sql / relation_service.py）。
> 平台画像（本次观察）：ChatGPT 最系统（框架完整、分层清楚）；Claude 来源标注最严谨
> （区分二手转引、明确说不知道）；Grok 社区+文献并重；Gemini 结构化但部分编号可疑需源码复核；
> doubao 中文社区实践补充（scope:global、reusable_patterns 等落地细节）。

## 候选判据对照表（产出规格）

### Q1 判据本体——一条信息凭什么值得保留 / 晋升

| # | 判据 | 通俗含义 | 出处 | 怎么操作化 | 适用层级 | 证据强度 |
|---|------|---------|------|-----------|---------|---------|
| 1 | Future Relevance（未来相关性） | 以后解决问题时还可能用到它 | Park et al. 2023 Generative Agents（UIST'23） | embedding 相似度 / 被检索次数 / 进入最终 answer 的次数 / 用户再次提及 | 项目内 + 跨项目 | 原文事实 |
| 2 | Importance / Poignancy（重要性） | 与相关性不同的另一个轴：影响决策、忘记代价高 | Park et al. 2023 | LLM 打 1-10 分；可拆 decision_impact + user_explicitness + downstream_dependency_count（工程化） | 项目内 + 跨项目 | 原文事实（分数）；公式为推断 |
| 3 | Reuse Frequency（复用频率） | 被真的查出来用过多少次 | Roediger & Karpicke 2006/2007（retrieval practice）；knowledge reuse 研究 | reuse_count、reuse_count_7d/30d、cross_project_reuse_count、success_rate | 项目内 + 跨项目 | 原文事实（人类学习）；agent 化属推断 |
| 4 | Reacquisition Cost（再获取成本） | 忘记后重新搞清楚的代价 | Pirolli & Card 1999 Information Foraging；KM ROI 实践（Soutron/Coworker AI） | C = user_input + search + read + reason + verify；token / 时间 / 工具轮次代理 | 项目内 + 跨项目 | 理论基础原文事实；公式为推断 |
| 5 | Predictability / Surprise（意外性 / 预测误差） | 超出预期的信息往往是环境/偏好变了 | NEMORI（arXiv 2508.03341） | prediction error 高 → 晋升候选 | 项目内 + 跨项目 | 原文事实 |
| 6 | Transferability（可迁移性） | 剥离本项目实体后是否仍成立 | Hu/Long/Wang 2026（experience reuse in LLM agents）；doubao 中文社区实践 | dependency footprint 检测（project/environment/temporal/entity/abstraction） | 决定跨项目去向 | 原文事实（抽象经验更易 transfer）+ 推断 |
| 7 | Atomicity（原子性） | 一条 = 一个独立可复用 claim | Zettelkasten（Luhmann/Ahrens） | 1 / independent_claims；能否被单个明确 query 独立召回 | 两者 | 原文事实 |
| 8 | Reliability / Evidence（可靠性） | 多次验证过、可重复 | DIKW 后扩展（Yao et al. 2019）；Adaptive Memory Admission Control | evidence_count、source_count、independent_confirmation、contradiction_count、last_verified_at | 晋升 gate | 原文事实 |
| 9 | Reflection / Abstraction（已升华） | 是否已从事实变成更高层解释 | Park 2023 reflection；Nonaka 1994 SECI（显性化） | 检测是否已有更高层 inference / 是否 tacit→explicit | 晋升 gate | 原文事实 |
| 10 | Explicit User Signal（显式用户信号） | 用户说记住这个 / 以后都这样做 | Tiago Forte 2022 BASB（keep what resonates） | 用户显式指令 → 高权重直入 candidate/permanent | 两者 | 原文事实 |

### Q2 项目内 vs 跨项目——识别信号

| 维度 | 项目内知识 | 跨项目可复用知识 |
|------|-----------|-----------------|
| 核心判据 | 真值依赖本项目唯一实体 / 环境约定 | 真值不依赖本项目实体；剥离后仍成立 |
| 包含内容 | 仓库路径、文件名、表名、实例 ID、本次迭代规划、本项目锁定决策、临时状态 | 通用踩坑根因 + 修复范式、工具原生行为、通用架构权衡、用户长期稳定偏好、领域标准 |
| 失效条件 | 本项目代码/文档变更即失效 | 工具/标准版本迭代才失效 |
| 可操作测试 | — | 复制到全新同领域项目不加修改，是否仍为真、可直接采信 |
| 晋升去向 | 项目级记忆（container_tag 项目域） | 全局 / 用户级记忆（scope:global / reusable_patterns） |

**关键结论**：项目内 vs 跨项目**不是价值差异，是 scope / 晋升去向差异**；区分信号 = dependency
footprint（是否引用本项目实体）。本项目 container_tag = {keyId} | {keyId}_project-<dir>
已具备归属×项目隐式编码，落地时只需在晋升管道上按 dependency footprint 分流。

### Q3 价值度量——可操作信号（最贴锚点）

**统一公式（推断，非文献原话）**：

    Memory Value ≈ P(future need) × C(reacquisition)
      P 代理：历史复用频次 / 同主题查询密度 / 知识类型（通用范式 > 临时碎片）
      C 代理：用户重新输入时间，或 agent 重新推导+工具调用+检索的 token / 工具轮次
      （ChatGPT 扩展：× Transferability × Reliability × Stability − 维护/错误/检索成本）

核心产品指标建议：**Expected Avoided Reacquisition Cost**（最贴锚点、可用真实行为数据校准，
不依赖 LLM importance classifier 的自评）。落地信号：reuse_count（含跨项目计数）、
reacquisition_cost 估算、未来被引用概率（LLM 估计 + 历史 retrieval success rate 后验）。
阈值无文献标准，由产品数据学习。

### Q4 晋升 / 抽象时点（episodic → semantic）

- **转化机制**：渐进转化（CLS 互补学习系统：快速编码 → 重放 → 语义化），非一次性判断；
  Tulving 1972 的 episodic / semantic 相互依赖，非互斥二分。
- **触发信号**：意外性 / 冲突（prediction error）优于定时摘要；重复出现（连续 N 次）为推断信号，
  N 无文献值。
- **保留原始**：时间/空间/因果细节本身未来要用时不抽象；原始 episode 永久保留（不删、只降权），
  抽象带 source 指针回链。
- **双写落地**：episodic 原始记录 + 异步 semantic 蒸馏，derived 记忆可一键重蒸馏 / Purge。

→ 本项目 create_derived_memory 已实现 is_inference=TRUE + derives 边回链，与上述结论吻合；
缺的是触发信号（prediction error / 重复出现检测）与降权而非删除的存储策略。

### Q5 负例 / 污染——晋升安全阀

四类失效模式**防护机制不同，不能共用一套置信度分数**：

| 失效模式 | 本质 | 防护 |
|---------|------|------|
| 幻觉 | 一开始就错 | 准入前正确性验证（写入门禁） |
| 过时 | 当时对现在错 | 时效戳 + 冲突/取代判定（SUPERSEDE + 更新链） |
| 漂移 | 反复摘要逐渐失真 | 限制摘要代数、原始回链、定期用原始记录校验重建 |
| 投毒 | 外部恶意注入 | 准入与权限控制优先；检测层不可靠 |

通用安全阀：**反例验证 + 作用域限定**（单次 episode 不得直接生成全局规则；连续 N 个不同上下文
验证或用户确认才晋升；显式标注 Scope/适用条件）——对应 6 维命题模型的适用条件维度。

## 决策映射（回项目内验证后）

| 调研结论 | 本项目落点 | 状态 |
|---------|-----------|------|
| 多判据组合（relevance/importance/reuse/cost…） | confidence 之外新增信号：reuse_count、reacquisition_cost、cross_project_reuse_count | 需 schema 变更（新列或新表）→ 走 ADR + setup_database.py |
| 项目内 vs 跨项目 = scope 差异 | container_tag 已含 {keyId}_project-<dir>；晋升管道按 dependency footprint 分流 | 无需 schema 变更；属 promotion 逻辑设计 |
| 显式用户信号高权重 | 用户显式指令（如记住这个）应直入 candidate/permanent | 新逻辑，可做规则而非模型 |
| episodic 保留 + derived 回链 | create_derived_memory（is_inference + derives）已实现 | 已满足；补触发信号 + 降权策略 |
| 冲突/取代判定 | is_latest 取代语义（N:1）+ create_update_version 修订语义（1:1）已实现 | 已满足，勿混淆两种语义 |
| 反例验证 + 适用条件显式（防错误泛化） | 6 维命题模型适用条件维度；晋升 gating 必填 | 晋升时强制校验，属规则 |
| 时效稳定性 | valid_until 已存在（_mark_not_latest 设置） | 已满足；漂移防护需限制摘要代数 + 原始回链 |

## 停止条件 / 收敛声明

- 关键判据均达 ≥2 平台一致 + 可溯源文献（Park 2023、NEMORI、Pirolli & Card 1999、Tulving 1972、
  McClelland 1995、AgentPoison 2024、STALE 2026、arXiv 2605.12978）。
- 数值阈值（importance 150、连续 N 次）为实现启发式，明确标注【不知道】，不追。
- 冲突项：无实质冲突（平台间仅详略/视角差异）；Gemini 个别 arXiv 编号（如 2508.13171 系 Cognitive
  Workspace）与 doubao 个别编号（2608.04843 等）未逐一核验，进 ADR 前如需引用应以 arXiv 实际检索为准。
- 本调研为 C 类结论，**尚未进 ADR**：进入晋升规则集前需按上述决策映射回项目内验证/实现。
