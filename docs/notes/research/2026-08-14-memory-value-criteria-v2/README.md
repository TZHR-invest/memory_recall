 # 2026-08-14: 记忆价值判据——外部调研（v2 · 无预设重设版）
 
 > 类型: 外部调研 · 状态: 已收敛（round-01 五平台无预设同题 + round-02 交叉追问三分歧收敛 + 回项目内验证；无需 round-03） · 日期: 2026-08-14
 > 归属: [命题晋升总纲](../2026-08-14-proposition-promotion.md)（S0+S1 第一刀：什么值得晋升为知识）
 > 上一版: [2026-08-14-memory-value-criteria](../2026-08-14-memory-value-criteria/)（v1，因「预设方向/答案」已停用，仅留档）
 
 ## 目标（一句话）
 
 搞清楚：在一个 AI 开发助手里，系统应该依据什么判断「哪些信息值得被长期沉淀下来」，以及这些值得
 沉淀的信息应该以什么形态、通过怎样的过程被留存，才能在将来真正需要时被有效复用。
 
 ## 本轮原则（v2 与 v1 的关键差异）
 
 **只提供背景与目标，不拆解、不预设。**
 
 - 不预列「候选判据」清单；
 - 不预给价值定义或公式（v1 曾把 value ≈ P(future need) × C(reacquisition) 写进 prompt，
   导致 Q3 的「结论」其实是题面的循环复读）；
 - 不点名任何文献 / 理论框架让平台去套（v1 曾点 Park 2023 / Forte / Zettelkasten / DIKW / SECI 等，
   答案被锚点诱导）；
 - 不预先拆分问题：**同一个开放问题整体抛给全部平台**，靠各平台自身视角的差异求更完整的答案；
 - 允许并鼓励平台指出「问题本身问偏了」。
 
 ## 执行摘要（round-01 → round-02 → 收敛）
 
 ### round-01（定向轮：五平台无预设同题）
 
 - 执行：codex 操作浏览器，向 ChatGPT / Claude / Grok / Gemini / doubao 各开新会话，整块粘贴同一开放题，原文回填。
 - 结果：**五平台在无预设条件下独立收敛**——未来价值判据 + 非原始存储 + 生命周期 + 用户闸门 + 分层 + 衰减修正。
 - 关键验证：v1 被批「题面循环复读」的 value≈P×C 方向，在 v2 无预设下被 ChatGPT/Claude/Grok 独立复现，证明方向真实收敛。
 - 留下三分歧：公式因子构成 / 触发时机 / 留存形态。
 
 ### round-02（交叉追问：三分歧收敛）
 
 - 执行：在各平台 **round-01 原会话**内追问（保持上下文），只针对各自回答的薄弱点/冲突点，不点名其他平台避免锚点。
 - 分歧 A（公式）**已收敛**：ChatGPT 主动修正为 EV = ReuseOpportunity × FutureValidity × Impact − RecoveryCost − MemoryCost；
   反对伪精确分数，主张离散等级 + 复用反馈校准。
 - 分歧 B（触发）**已收敛**：Claude/Gemini 独立给出「两级捕获」——L1 轻量随时记录（信号驱动 + 高风险低门槛捕获，标待确认）
   + L2 节点批量提炼（commit/PR 后查重 + 补抓过程信号 + 冲突检测）；Claude 主动修正「默认不记」为「复用信号 ∨ 风险信号」两维。
 - 分歧 C（形态）方向收敛：Grok 主张统一 Knowledge Card + 类型 schema，Gemini 主张规则/ADR/playbook 分化存储——
   共同方向是「统一捕获层 + 类型元数据」，物理形态回项目内验证。
 - **无需 round-03**：三分歧均已推进到可回项目内验证状态，继续问平台边际收益递减。
 
 ### 收敛轮（回项目内验证）
 
 - 对照 `schema.sql` v5.1.5 / `relation_service.py` 核对：现有 `memories` 表已具备生命周期、版本链、
   derives/updates/extends、冲突检测、is_static/is_inference/forget、container_tag 分层等大部分机制。
 - 主要缺口：**复用反馈回收缺失**（召回命中/采纳未写回，无法校准 P(future use)——正是用户此前「命中率回收」担忧）；
   无「待确认」状态；无记忆类型标签；无两级捕获的 L1 候选态。
 - 实施建议详见 [99-final-conclusions.md](99-final-conclusions.md)。
 
 ## 核心结论（一句话）
 
 **系统不应在「写入时」一次性判定信息值不值得长期存，而应跑「低门槛捕获 → 用户闸门 → 按需提炼 → 复用反馈校准」生命周期；**
 **判据 = 未来复用机会 × 届时有效性 × 影响 − 维护/遗忘成本，用离散等级而非伪精确分数。**
 
 ## 文件索引
 
 | 文件 | 内容 |
 |------|------|
 | [01-goals.md](01-goals.md) | 背景与目标（开放，无预设） |
 | [02-round-01-prompts.md](02-round-01-prompts.md) | round-01 提示词（全平台同一开放题） |
 | [03-round-01-answers-chatgpt.md](03-round-01-answers-chatgpt.md) | ChatGPT round-01 回答原文 |
 | [03-round-01-answers-claude.md](03-round-01-answers-claude.md) | Claude round-01 回答原文 |
 | [03-round-01-answers-grok.md](03-round-01-answers-grok.md) | Grok round-01 回答原文 |
 | [03-round-01-answers-gemini.md](03-round-01-answers-gemini.md) | Gemini round-01 回答原文 |
 | [03-round-01-answers-doubao.md](03-round-01-answers-doubao.md) | doubao round-01 回答原文 |
 | [04-round-02-prompts.md](04-round-02-prompts.md) | round-02 追问方案（三分歧 × 相关平台） |
 | [05-round-02-answers-chatgpt.md](05-round-02-answers-chatgpt.md) | ChatGPT round-02 回答原文 |
 | [05-round-02-answers-claude.md](05-round-02-answers-claude.md) | Claude round-02 回答原文 |
 | [05-round-02-answers-grok.md](05-round-02-answers-grok.md) | Grok round-02 回答原文 |
 | [05-round-02-answers-gemini.md](05-round-02-answers-gemini.md) | Gemini round-02 回答原文 |
 | [05-round-02-answers-doubao.md](05-round-02-answers-doubao.md) | doubao round-02 回答原文 |
 | [08-round-01-conclusions.md](08-round-01-conclusions.md) | round-01 统一理解（收敛点 + 分歧点） |
 | [09-round-02-conclusions.md](09-round-02-conclusions.md) | round-02 统一理解（三分歧收敛 + 回项目内决策） |
 | [99-final-conclusions.md](99-final-conclusions.md) | 最终结论（判据公式 + 实施映射 + 缺口清单） |
 
 ## 执行方式
 
 走 RESEARCH_GUIDE 的 Human-in-the-Loop 流程：codex 操作浏览器，把
 [02-round-01-prompts.md](02-round-01-prompts.md) 里的同一段文本块整块粘贴到每个平台
 （ChatGPT / Claude / Grok / Gemini / doubao），回答原文回填到 `03-round-01-answers-<platform>.md`，
 不二次概括。纪律不变：出处诚实（事实 / 推理 / 不知道三档 + 给来源）；外部回答是素材不是事实，
 C 类结论回项目内验证后才可进 ADR / 根目录。
 
 ## 下一步
 
 - 按 [99-final-conclusions.md](99-final-conclusions.md) 第五节实施建议推进：复用反馈闭环（最优先）→ 两级捕获 → 类型标签 → 风险信号通道；
 - 方向性取舍（判据公式、两级捕获、类型体系）另落 ADR（ADR-0011 候选），实施前复核 ADR-0009 记忆维护检查点。
