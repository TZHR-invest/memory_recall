# round-01 · Gemini 回答原文

> 执行日期: 2026-08-14 · 会话: 新会话（无预设同题） · 平台画像: 高层结论可参考，具体字段容易编造；仅作广谱参考
> 提示词: [02-round-01-prompts.md](02-round-01-prompts.md) 同一开放题

---

这个问题切中了 AI Agent（尤其是长周期伴随型 Dev Agent）落地中最核心的难点之一：如何避免 Agent 随着使用时间变长，上下文从「越用越聪明」变成「越来越臃肿混乱（Context Pollution）」。

先给出我对这个问题本身的破局判断：如果只把这个问题看作「写入时的筛选（Filter at Write）」问题，可能方向就走偏了。

真实的记忆沉淀，不是在发生当下做一次“要不要存”的硬性二选一，而是一个「渐进式抽象（Progressive Abstraction）与生命周期管理（Lifecycle Management）」的过程。

以下是我综合学术界 Memory 机制研究、工业界代码助手（如 Cursor / Claude Rules / MemGPT 等）实践以及个人推理，总结出的本质与完整图景。

1. 判断标准：依据什么确定「信息价值」？

并非所有信息都处在同一个维度。我们可以依据 空间作用域（Scope） 和 抽象层级（Abstraction Level），将 Dev 过程中的信息划分为三个阶梯：

[高阶/长效] 习惯与全局准则 (Cross-Project Invariants)
    ▲
[中阶/项目] 架构决策与本地坑点 (Project-Bound Context & ADR)
    ▲
[低阶/临时] 具体 Execution & Debug Trace (Ephemeral Session)


判断一条信息是否值得“沉淀”以及“沉淀多久”，核心看四个维度：

重构/重搜成本（Cost of Re-derivation）：
如果重新推演或寻找这个答案需要耗费大量时间（例如：排查了 3 小时才发现某个特定版本的库在 macOS M 系列芯片上的 CGo 编译 bug），这类信息的沉淀价值极高。

复现频率（Frequency & Recurrence）：
同一个错误提示或编码习惯在 3 次会话中重复出现，无论它看起来多微小，都必须沉淀。

决策意图与约束（Intent & Non-functional Constraints）：
代码本身只体现了“How”，没有体现“Why”。诸如“为什么这里不用 Redis 而是用 SQLite”这类架构决策记录（ADR），如果丢弃，后续 Agent 极易做出破环原架构的提议。

抽象潜力（Generalizability）：
它是一个特例修补（Specific Patch），还是能提炼成通用规范（Generic Pattern）？

2. 留存形态：值得留存的信息应长成什么样？

信息不能以“原始对话 Run Log”的形式留存（极度浪费 Token 且噪点极高）。它必须经历形态转换，通常分为三种形态：

形态 A：声明式规则（Declarative Rules / Guidelines）

面向对象： 编码偏好、技术栈约束、特定库的 Avoid List。

形态呈现： 类似 .cursorrules 或 CLAUDE.md 的 Markdown 结构化清单，语言精准、非黑即白。

示例： “项目内部统一使用 Zod 进行 Type Safety 校验，禁止引入 Joi。”

形态 B：架构与意图图谱（Architectural Intent & Domain Model）

面向对象： 模块边界、数据流走向、遗留代码的历史原因（Why）。

形态呈现： Lightweight ADR（架构决策记录）或 Task-Knowledge Graph（任务-知识图谱）。

示例： “组件 X 故意没有做防抖，是因为上层调度器已经实现了流量整形。”

形态 C：程序化 SOP / 排坑剧本（Procedural Memory / Playbooks）

面向对象： 复杂的环境配置步骤、特定的 Debug 诊断流程。

形态呈现： 可被 Agent 工具调用的 Workflow 模板或脚本。

示例： “当数据库迁移报 Error Code 1215 时，依次执行检查排错脚本 A 和 B。”

3. 沉淀过程：从「发生」到「有效复用」的完整生命周期

好的沉淀不是一次性的“写入”，而是“捕获 ➔ 提炼 ➔ 激活 ➔ 衰减”的闭环。

[原始交互 / Debug]
       │
       ▼ (触发：任务结束/踩坑修复)
[反思与提炼 (Reflection)] ───► [用户无感/有感 确认]
       │
       ▼
[分级存储 (Rule / ADR / Playbook)]
       │
       ▼ (运行时 JIT 检索)
[按需激活 (Just-In-Time Activation)] ───► [更新 / 废弃 (Decay/Invalidation)]

过程一：捕获与提炼（Reflexion & Distillation）

触发时机： 不要在每一句话交互时实时存储。最适合的触发点是“任务节点结束时”（如 Git Commit、PR 生成、或解决了一个长 Trace 的 Bug）。

提炼机制： 引入独立后台 Agent（Memory Agent），在后台运行“自我反思”（Self-Reflection），对比任务开始时的 Input 和最终的 Fix，问自己：“这次解决过程中，有哪些规则/知识是全局通用的？有哪些是用户特有的习惯？”

过程二：写入与确认（Human-in-the-loop）

隐式写入 vs 显式确认：

强偏好/高确定性信息（如用户明确说“以后别用 var”）：隐式直接写入。

架构级规则/通用模式提炼：显式轻量确认。在任务结束时抛出极简 Prompt：“我注意到你在项目中将 API 请求都抽离到了 service 层，是否需要将此记入项目开发规范？”

过程三：复用与激活（Just-In-Time Retrieval）

不要把所有记忆塞进 System Prompt： 这会导致 Prompt 膨胀和模型注意力分散。

按需激活（JIT Context）：

当用户打开 auth.ts 时，仅挂载与 Auth/Security 相关的 Memory。

当 Agent 捕获到 Terminal 报错 EADDRINUSE 时，通过向量或关键词检索激活对应的 Debug Playbook。

过程四：衰减与失效（Decay & Invalidation）

代码在变，记忆会过期。如果框架从 Vue2 升级到了 Vue3，旧的 Vue2 记忆就变成了毒素。

失效机制： 记忆必须附带 Last Verified Version 或 Source Hash。当被依赖的代码文件发生巨大变更，或记忆在多次检索后被用户拒绝（Negative Feedback），该记忆应被降级（Eviction）或提醒用户重新验证。

4. 观点与出处说明

为了保证回答的严肃性，以下是上述观点的来源与理论/实践映射：

观点 / 机制	出处 / 来源类型	具体文献或实践依据
MemGPT / 主从记忆分层	具体文献	Packer et al. (2023) 《MemGPT: Towards LLMs as Operating Systems》。提出了类似 OS 的内存/外存管理机制，强调 Working Context 与 Archival Memory 的分离。
Reflexion 反思提炼	具体文献	Shinn et al. (2023) 《Reflexion: Language Agents with Verbal Reinforcement Learning》。证明了 Agent 在任务结束后通过文本“自我反思”并提取经验，能显著提升后续同类任务成功率。
Generative Agents 记忆流	具体文献	Park et al. (2023) 《Generative Agents: Interactive Simulacra of Human Behavior》。提出了 Memory Stream，以及依据 Recency (时效)、Importance (重要度)、Relevance (相关度) 三要素进行记忆提取与反思的机制。
声明式规则文件 (.cursorrules 等)	工业界实践	借鉴自 Cursor、Windsurf、Claude Code (CLAUDE.md) 的实践。证明了 Markdown 格式的静态声明规则是目前对 LLM 约束效果最好、最易读写的形式。
架构决策记录 (ADR) 转化为 Agent 记忆	自己推理 / 综合	结合传统软件工程（Architecture Decision Records, Michael Nygard）与 LLM 上下文管理推导而来。代码本身丢失了 Intent，ADR 是补充“Why”的最优形态。
衰减机制与 JIT 挂载策略	自己推理 / 综合	基于认知心理学 Tulving 的语义/情景记忆理论，结合 RAG 系统中解决 Context Saturation（上下文饱和）问题的工程实践提炼。
总结与建议

如果你要立刻落地这个系统，建议分为三步走：

先做轻量级的规则提炼（Rule-based Memory）： 在每次 Prompt 执行或任务结束时，让后台模型提取“用户偏好”与“代码约束”，写入一个可随项目代码一同版本控制的文件（如 .agent/rules.md）。

再做排坑与技巧的向量/图检索（Procedural Memory）： 将复杂的 Debug 记录提炼成 SOP 脚本或案例，放在外部存储中，通过向量/关键词在报错时主动 Hook 检索。

建立 Memory 维护的控制权： 一定要给用户提供一个 "Memory Dashboard"，让用户可以看见 Agent 记住了什么，并能一键删除/修改错误的记忆。
