# 最终统一理解（v2 · 无预设调研收敛）

> 类型: 调研（最终结论） · 调研: 2026-08-14-memory-value-criteria-v2
> 执行: round-01（五平台无预设同题）→ round-02（交叉追问，三分歧收敛）→ 收敛轮（回项目内验证）。
> 纪律: 外部回答是素材不是事实；本文件的实施映射已对照 schema.sql v5.1.5 / relation_service.py 核对。
> 平台画像（本次两轮观察）: ChatGPT 最系统且会主动修正自身方案；Claude 来源标注最严谨、主动承认自身方案缺口；
> Grok 裁决式回答、善于吸收其他框架；Gemini 结构最工程化（L1/L2、三种形态表）；doubao 交互设计最落地（确认疲劳/置信度分级）。

## 一、调研核心结论（一句话）

**系统不应在「写入时」一次性判定某条信息值不值得长期存，而应跑一个「低门槛捕获 → 用户闸门 → 按需提炼 → 复用反馈校准」的生命周期；**
**判据方向 = 未来复用机会 × 届时有效性 × 影响 − 维护/遗忘成本，工程上不追求精确分数，用离散等级 + 真实复用反馈逐步校准。**

该结论由五平台在**无预设**条件下独立收敛得出（v2 关键验证），并经受住了 round-02 交叉追问——
ChatGPT / Claude 各自**主动修正**了上一轮方案，说明收敛不是附和而是真实思考。

## 二、S0+S1 第一刀的判据落点（与项目内机制映射）

### 2.1 已有机制（schema.sql / relation_service.py 已验证）

| 调研结论 | 项目内已有落点 | 差距 |
|---------|---------------|------|
| 生命周期而非写入时判定 | 已有 create_derived_memory（is_inference=True + derives 边）；update 显式版本链（version+1, root_memory_id）；自动关系检测 _mark_not_latest 降级 | 已有「晋升」（derive）与「修订」（update）两条链，语义与调研结论一致 |
| 主动冲突检测 | detect_contradiction（关键词 + 时间词 + 更新词）+ auto_create_relations（矛盾→updates + 降级） | 已有 |
| 过时 / 修正机制 | is_latest / valid_from / valid_until / is_forgotten / forget_after / forget_reason | 已有（软删除 + 定时遗忘） |
| 分层存储（会话/项目/全局） | container_tag = {keyId} | {keyId}_project-<dir>（归属×项目隐式编码） | 已有 |
| 静态事实 vs 动态状态 | is_static（画像类静态 vs 动态） | 已有 |
| 原子化 + 来源聚合 | source_count（合并来源数）、metadata.entities / relations | 已有 |
| 按需激活（JIT） | 召回管线（profile/vector/memory_graph/entity_graph/chunks）按 container 检索注入 | 已有 |

### 2.2 缺口（调研结论指向、项目内尚缺）

| 缺口 | 调研依据 | 建议落点（待 ADR） |
|------|---------|-------------------|
| 复用反馈回收缺失（最优先） | ChatGPT（P(future use) 最难，用「复用场景 + 行为反馈」在线校准）；用户此前明确担忧「召回只给用户，未回收命中率」 | 检索命中/采纳写回：召回后记录是否进入最终答案/用户是否采纳 → metadata.reuse_count / last_reused_at（schema 无该字段，需新增或进 metadata JSONB） |
| 无「待确认」状态 | Claude（高风险内容低门槛捕获但标「待确认」，追问/行为验证后提升确信度） | 新增 status（active/pending_review）或 metadata.pending_confirm |
| 无类型标签（统一卡片） | Grok（统一 Knowledge Card + 类型 schema）；Gemini（规则/ADR/playbook 分化） | 项目内 memories 已是统一卡片；可在 metadata 加 memory_type（rule/adr/playbook/lesson/config），类型驱动 schema 扩展——统一捕获层 + 类型元数据为两平台共同方向 |
| 无两级捕获（L1 scratchpad） | Claude / Gemini（轻量随时记录 + 节点批量提炼）；doubao（低置信直接丢弃） | 新记忆默认低置信候选态 → 节点（commit/PR）时批量提炼 + 去重；低置信直接不进检索 |
| 用户确认疲劳 | doubao（置信度分级 + 差异化确认强度：高置信静默候选池、中置信轻量提示、强指令才弹窗） | 产品层交互设计，暂不进 schema |
| 风险信号低门槛通道 | Claude（维度二：祈使禁止/不可逆/安全关键词，独立于复用信号） | 捕获端规则，暂不进 schema |

### 2.3 触发与晋升机制的设计收敛（round-02）

L1 捕获（低门槛） -> L2 提炼（节点闭合时）
信号驱动：显式记住/纠正/重复引用 -> commit/PR/修 bug 后批量：
高风险内容：祈使禁止/安全/不可逆 -> ① 查重（已被 L1 抓过的不重复写）
  （标 pending_review） -> ② 补抓过程信号（反复尝试才解决等）
低置信/临时：直接丢弃 -> ③ 冲突检测（矛盾→updates+降级）
 -> ④ 归档分层（项目级/全局级）

用户闸门（按置信度分级，非阻塞优先）
  高置信 → 静默候选池（7 天过期，侧边批量审阅）
  中置信 → 轻量行内提示可忽略
  强指令 → 才弹窗确认

晋升（已有 create_derived_memory 对应）
  is_inference=True + derives 边 = 提炼产物带回源（「派生不是取代」）
  跨项目升级：复用成功反馈（另一项目采纳）→ 提示用户显式确认，不自动升级

## 三、价值判据的最终表述（供 ADR 引用）

MemoryValue ≈ ReuseOpportunity × FutureValidity × Impact − RecoveryCost − MemoryCost

  ReuseOpportunity : 未来有没有机会用到（future use 概率/跨情境复用/期望频次）——最难估，用「复用场景预测 + 行为反馈」校准
  FutureValidity   : 到时候它还对不对（= Stability / 有效期），建议按记忆类型建先验，而非 LLM 拍连续分数
  Impact           : 用对了能省多少事/避免多大错误（影响决策/踩坑代价）
  RecoveryCost     : 没记住的话，重新得到它要花多少（= 遗忘/重获成本，作决策阈值而非乘法因子）
  MemoryCost       : 记住它本身给未来造成的负担（检索噪声/过期/矛盾/污染）

工程落地：第一版用离散等级（rare/possible/likely/frequent × negligible/useful/important/critical ×
volatile/normal/stable），避免 LLM 伪精确分数（如 0.73×0.81）；通过真实复用/采纳反馈逐步校准。

## 四、与 v1 调研的关系（v1 为何停用、v2 验证了什么）

- v1 的问题：把 value ≈ P×C 写进 prompt、点名 Park/Zettelkasten/DIKW/SECI 等文献，结论被批「题面循环复读 / 锚点诱导」。
- v2 的关键验证：**完全不预设**的情况下，ChatGPT 独立推出 V(m)=P×Benefit×Cost_forget，Claude 独立推出「复用期望×稳定性×修正代价」，
  Grok 独立推出「跨情境价值×检索成本」——「未来价值 × 遗忘/重获成本」方向被多平台独立复现，证明**不是题面诱导，是真实收敛**。
- v2 相对 v1 的新增：①公式从「乘法」演进为「期望净价值 = 乘性因子 − 减性成本」（ChatGPT round-02 主动修正）；
  ②触发机制收敛为「两级捕获」（v1 未覆盖）；③明确「复用反馈回收」是校准 P 的唯一可靠数据源（v1 只提 reuse_count，未点出闭环）；
  ④留存形态收敛为「统一捕获层 + 类型元数据」（Grok 与 Gemini 的共同方向）。
- v1 中仍有效、v2 未推翻的判据清单（future relevance / reuse frequency / reacquisition cost / transferability / atomicity / reliability / reflection / explicit user signal）
  可并入本结论的离散等级框架，作为因子代理。

## 五、回项目内验证后的实施建议（下一步，待用户拍板）

1. **复用反馈闭环（最高优先）**：召回管线记录「命中/采纳」→ 写回 metadata.reuse_count + last_reused_at；这是校准 P(future use) 的唯一可靠数据源，也是用户此前「命中率回收」担忧的解法。
2. **两级捕获最小化**：新记忆写入时按信号来源打 metadata.pending_confirm 或直接低置信不入检索；节点（commit/PR/修 bug）时批量提炼（查重 + 补抓过程信号 + 冲突检测）。复用现有 create_derived_memory 作提炼产物。
3. **记忆类型标签**：metadata.memory_type（rule/adr/playbook/lesson/config），类型驱动 schema 扩展——符合「统一卡片 + 类型元数据」收敛方向，不拆表。
4. **风险信号通道**：捕获端检测祈使禁止/安全/不可逆关键词 → 低门槛捕获 + pending_review。
5. 方向性取舍（判据公式、两级捕获、类型体系）建议另落 ADR（ADR-0011 候选），并在实施前复核 ADR-0009 记忆维护检查点。

## 六、结论可信度与局限

- 可信度：核心方向由五平台无预设独立收敛 + round-02 交叉验证（含两平台主动修正），证据强度高。
- 局限：①公式因子构成仍各平台表述不一（方向一致，形态未统一——本项目落点以 ChatGPT round-02 最终版为准，因它最完整且主动修正过）；
  ②留存形态的「统一 vs 分化」物理实现未由平台裁决，本项目以「统一卡片 + 类型元数据」为落地选择（Grok 方案），因 memories 表本就是统一实体；
  ③「待确认」「置信度分级」等交互机制未在真实系统验证，属设计推断。
