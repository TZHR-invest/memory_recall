 # 2026-08-14: 记忆价值判据——外部调研（v2 · 无预设重设版）
 
 > 类型: 外部调研 · 状态: round-01 已完成（2026-08-14：五平台无预设同题回填 + 统一理解），待 round-02 追问 / 回项目内验证 · 日期: 2026-08-14
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
 
 ## round-01 执行摘要
 
 - 执行方式：codex 操作浏览器，向 ChatGPT / Claude / Grok / Gemini / doubao 各开新会话，
   整块粘贴同一开放题（[02-round-01-prompts.md](02-round-01-prompts.md)），回答原文回填、不二次概括。
 - 核心结果：**五平台在无预设条件下独立收敛**——未来价值判据 + 非原始存储 + 生命周期 + 用户闸门 + 分层 + 衰减修正。
 - 关键验证：v1 被批「题面循环复读」的 value≈P×C 方向，在 v2 无预设下被 ChatGPT/Claude/Grok 独立复现，
   证明方向真实收敛；但公式因子构成、触发时机、统一留存形态仍有分歧（详见 [08-round-01-conclusions.md](08-round-01-conclusions.md)）。
 
 ## 文件索引
 
 | 文件 | 内容 |
 |------|------|
 | [01-goals.md](01-goals.md) | 背景与目标（开放，无预设） |
 | [02-round-01-prompts.md](02-round-01-prompts.md) | round-01 提示词（全平台同一开放题） |
 | [03-round-01-answers-chatgpt.md](03-round-01-answers-chatgpt.md) | ChatGPT 回答原文 |
 | [03-round-01-answers-claude.md](03-round-01-answers-claude.md) | Claude 回答原文 |
 | [03-round-01-answers-grok.md](03-round-01-answers-grok.md) | Grok 回答原文 |
 | [03-round-01-answers-gemini.md](03-round-01-answers-gemini.md) | Gemini 回答原文 |
 | [03-round-01-answers-doubao.md](03-round-01-answers-doubao.md) | doubao 回答原文 |
 | [08-round-01-conclusions.md](08-round-01-conclusions.md) | 各平台视角差异点 + 收敛状态（round-01 统一理解） |
 | `99-final-conclusions.md` | 最终结论（待回项目内验证后生成） |
 
 ## 执行方式
 
 走 RESEARCH_GUIDE 的 Human-in-the-Loop 流程：codex 操作浏览器，把
 [02-round-01-prompts.md](02-round-01-prompts.md) 里的同一段文本块整块粘贴到每个平台
 （ChatGPT / Claude / Grok / Gemini / doubao），回答原文回填到 `03-round-01-answers-<platform>.md`，
 不二次概括。纪律不变：出处诚实（事实 / 推理 / 不知道三档 + 给来源）；外部回答是素材不是事实，
 C 类结论回项目内验证后才可进 ADR / 根目录。
 
 ## 下一步（round-02 / 收敛轮）
 
 - round-02 追问轮：针对三大分歧（价值公式因子构成、触发时机、统一留存形态）发 1-4 条追问，不再增加平台；
 - 收敛轮：回项目内验证（`apps/api/src/models/` 实体、`schema.sql`、`relation_service` 版本链映射），
   然后落 `99-final-conclusions.md`；
 - 方向性取舍按文档规范另落 ADR。
