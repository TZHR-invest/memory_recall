# 2026-08-19: Claim 原子化粒度判据——外部调研（无预设）

> 类型: 外部调研 · 状态: **已完成（round-01 五平台 + round-02 五平台 + 收敛轮回项目内核对）** · 日期: 2026-08-19
> 归属: [crystal 专项 M2.1 claim 原子化](../../../initiatives/crystal/README.md)（对账写路径语义补全）·
> 上游: foundation 已拍板「一次 Evidence 可衍生 0..N 个 Claim」但实现只有 0..1；现实库 22 条 claim 粒度跨 15 字 ~ 2383 字
> 执行: **人工复制粘贴**（用户操作平台，不用 codex 浏览器）——按 RESEARCH_GUIDE 的 Human-in-the-Loop 流程

## 目标（一句话）

搞清楚：在「证据→结论」两层记忆系统（Evidence 不可再生，Claim 是对账派生的结论）里，
**一条 Claim 应该多"原子"才算一条？拆条（一条证据拆成多条 Claim）该怎么做、判据是什么？
拆条后对置信度 / 冲突裁决 / 召回分别意味着什么？**

## 最终结论（M2.1 原子判据定案，详见 [99-final-conclusions.md](99-final-conclusions.md)）

**粒度 = 独立生命周期（非字数）：两个部分未来可能被分别裁决（一个被纠正/失效，另一个仍成立）→ 是则拆。**
配套定案：整篇文档是证据不是结论（分层错误）；拆条 = 平行原子 Claim + 轻量 `event_key`（不做 Group 实体）；
宁可多拆（错误可恢复性不对称）；拆条/碰撞判定分步（LLM ① 拆条 → 检索 → LLM ② 碰撞批处理）；
claim_kind 无硬上限但有软规则（learned-pattern 保留"条件-做法-结果"因果）；evidence_quote 原文子句引用
（拆条解决置信度污染，片段引用主要为 UX）；个人规模不做延迟提升（拆条立即做）。

五平台收敛、无实质冲突，与项目已拍板（0..N 拆条 / 适用条件折入句子 / Entity P2 不进核心 /
claim_evidence 关系表）兼容。落地：claim 加 `event_key` + claim_evidence 加 `quoted_text` +
拆条 prompt 落地 + 存量 19 条 active 宽 claim 清理重建（等用户确认）。

## 背景（项目内已确认的判断，供后续收敛轮对照）

> 背景里的判断是**我们自己的想法**，不是要平台认同的预设——round-01 提示词**不带这些**，
> 只带系统客观描述。它们在收敛轮才用于对照平台回答是否覆盖/挑战了我们的盲区。

- 现实库 22 条 claim：15 字（"张三喜欢喝咖啡"）到 2383 字（整篇文档原文照抄），无统一原子性标准；
- 一条 evidence 只产出一条 claim，与 foundation「0..N 拆条」相悖；多条独立结论被塞进一条（430 字 claim 含 4 条决策）；
- reinforce 把 statement 未体现的 evidence 吸进来计分 → 置信度虚高（5 条不同主题文档 reinforce 进 1 条 claim）；
- 粒度粗导致裁决只能整条 supersede，正确子结论被连带误杀。

## 调研轨迹

| 轮次 | 内容 | 结果 |
|------|------|------|
| round-01 | 五平台无预设开放题（按画像分配侧重） | **高度收敛**：粒度 = 可独立证伪单元（非字数）；整篇文档是证据不是结论；原子存储+聚合消费；需组织层解决碎片化；证据支持关系必须精确；原子性=生命周期性质非语言学性质。分歧 5 点 → 进 round-02 |
| round-02 | 五平台反馈式追问（针对 D1–D5，背景带项目约束） | **D1–D5 收敛**：event_key 弱字段（非 Group 实体）；evidence_quote 原文子句引用；宁可多拆（错误可恢复性不对称）+ 拆条/碰撞分步；claim_kind 无硬上限有软规则；个人规模不做延迟提升。新增 11 条落地需求（R1–R11） |
| 收敛轮 | 回项目内核对（foundation / reconciliation-design / 当前实现 / schema） | 兼容性确认：C1 判据与 foundation 一致；event_key 不违反 Entity P2；对账当前已分步（LLM ① 提炼 + LLM ② 碰撞）只改批处理；存量重建需用户确认。**已定案，见 [99-final](99-final-conclusions.md)** |

## 文件索引

| 文件 | 内容 |
|------|------|
| [01-goals.md](01-goals.md) | 背景与目标（开放，无预设） |
| [02-round-01-prompts.md](02-round-01-prompts.md) | round-01 提示词（按平台画像分配，各平台一个可复制文本块） |
| [03-round-01-answers-chatgpt.md](03-round-01-answers-chatgpt.md) | ChatGPT 回答原文（已回填） |
| [03-round-01-answers-claude.md](03-round-01-answers-claude.md) | Claude 回答原文（已回填） |
| [03-round-01-answers-grok.md](03-round-01-answers-grok.md) | Grok 回答原文（已回填） |
| [03-round-01-answers-gemini.md](03-round-01-answers-gemini.md) | Gemini 回答原文（已回填） |
| [03-round-01-answers-doubao.md](03-round-01-answers-doubao.md) | doubao 回答原文（已回填） |
| [08-round-01-conclusions.md](08-round-01-conclusions.md) | round-01 统一理解（共识 6 点 + 分歧 5 点 + 项目内对照 + 出处清单） |
| [04-round-02-prompts.md](04-round-02-prompts.md) | round-02 追问（针对 D1–D5，按平台打包，背景带项目约束） |
| [05-round-02-answers-chatgpt.md](05-round-02-answers-chatgpt.md) | ChatGPT round-02 回答原文（待回填） |
| [05-round-02-answers-claude.md](05-round-02-answers-claude.md) | Claude round-02 回答原文（待回填） |
| [05-round-02-answers-grok.md](05-round-02-answers-grok.md) | Grok round-02 回答原文（待回填） |
| [05-round-02-answers-gemini.md](05-round-02-answers-gemini.md) | Gemini round-02 回答原文（待回填） |
| [05-round-02-answers-doubao.md](05-round-02-answers-doubao.md) | doubao round-02 回答原文（待回填） |
| [09-round-02-conclusions.md](09-round-02-conclusions.md) | round-02 统一理解（D1–D5 收敛 + 落地需求 R1–R11 + 未决点） |
| [99-final-conclusions.md](99-final-conclusions.md) | **最终结论 + 实施映射（M2.1 原子判据定案）** |

## 平台分配

### round-01（按平台画像分配侧重）

| 平台 | 画像依据 | 分配侧重 |
|------|---------|---------|
| ChatGPT | 最系统、主动修正自身方案、源码级结论可靠 | 主开放题（整体抛给平台，要求系统性 + 落地） |
| Claude | 诚实、会明确说不知道、公式/推理强 | 主开放题 + 明确要求区分"事实/推理/不知道" |
| Grok | 裁决式回答、善于吸收其他框架 | 侧重"粒度粗细的取舍"对比裁决 |
| Gemini | 高层结论可参考、结构最工程化 | 侧重结构化梳理（判据分类/拆条流程/成本收益） |
| doubao | 中文社区视角、交互设计最落地 | 侧重中文生态 + 工程落地实践 |

### round-02（只发相关平台，针对分歧/薄弱点）

| 平台 | 追问点 |
|------|--------|
| ChatGPT | 组织层形态定案（在"Entity/主题 P2 不进核心"约束下，决策分组 vs 动态聚合）+ 拆条 JSON schema 落地版 |
| Claude | LLM 拆条质量保障（反向合成校验/漏拆 vs 多拆取舍/一步 vs 两步）+ 延迟提升在个人规模是否务实 |
| Grok | 组织层取舍裁决（A 分组层 vs B 动态聚合 vs C）+ claim_kind 4 值类型差异化粒度裁决 |
| Gemini | claim_kind 类型差异化粒度映射表 + 证据片段级引用增益/最小实现/拆条后还剩多少虚高 |
| doubao | 证据片段引用中文工程落地（span 定位坑/分块粒度）+ 批量演化触发条件与召回缺口 |

## 纪律（RESEARCH_GUIDE）

- 外部回答是素材不是事实；进入 ADR / `docs/` 根目录前必须以项目内源码、官方文档或可执行验证确认；
- 原始回答与链接保留，不删除；正文一个字不改、不二次概括；
- C 类结论回项目内验证后才可进设计文档/ADR。

*状态: 已完成 · 最后更新: 2026-08-19*
