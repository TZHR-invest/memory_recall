# 2026-08-14: 记忆价值判据——外部调研

> 类型: 外部调研 · 状态: round-01 已完成（五平台回填 + 收敛，待回项目内验证） · 日期: 2026-08-14
> 归属: [命题晋升总纲](../2026-08-14-proposition-promotion.md)（S0+S1 第一刀：什么值得晋升为知识）
> ⚠️ 已重做：本版（v1）因「预设价值锚点 / 预设判据」被判定带偏向性，已由
> [v2 无预设重设版](../2026-08-14-memory-value-criteria-v2/) 取代，本目录仅留档。

## 目标（一句话）

搞清楚：**在一个 agent 开发助手里，判断"一条信息值不值得记住、值不值得从临时记录晋升为可复用知识"的
判据是什么，以及这些判据能否变成可操作 / 可计算的信号。**

## 锚点（价值的定义，来自用户）

- 场景：agent 做项目开发，很多用户已知的信息不应重复输入；
- 记忆对象：项目产生的信息、用户输入、项目现状 / 规划设计、开发环境等，甚至跨项目复用的项目无关知识；
- **价值 = 未来还会被需要，且忘记会导致重复成本（用户重新输入 / agent 重新查·推）**；
- 两层范围：项目内 + 跨项目（项目无关、可迁移）。

## 产出规格

一张「候选判据对照表」：每条 = 名称 + 通俗含义 + 出处（链接）+ 怎么操作化 + 适用层级（项目内 / 跨项目）+
证据强度（原文事实 / 推断）。外加每问的"原文事实 / 推断 / 不知道"标注。

## 平台分配（round-01，每题 2-3 个，C 类）

| 题 | 平台 |
|----|------|
| Q1 判据本体 | ChatGPT / Claude / Grok |
| Q2 项目内 vs 跨项目 | ChatGPT / doubao |
| Q3 价值度量 | ChatGPT / Grok / doubao |
| Q4 晋升 / 抽象时点 | Claude / Gemini |
| Q5 负例 / 污染 | Claude / Gemini |

## 文件索引

| 文件 | 内容 |
|------|------|
| [01-goals.md](01-goals.md) | 背景、锚点、已知源码事实、研究问题清单 |
| [02-round-01-prompts.md](02-round-01-prompts.md) | round-01 提示词（按平台打包，codex 逐平台复制粘贴） |
| [03-round-01-answers-chatgpt.md](03-round-01-answers-chatgpt.md) | ChatGPT 回答原文（Q1/Q2/Q3） |
| [04-round-01-answers-claude.md](04-round-01-answers-claude.md) | Claude 回答原文（Q1/Q4/Q5） |
| [05-round-01-answers-grok.md](05-round-01-answers-grok.md) | Grok 回答原文（Q1/Q3） |
| [06-round-01-answers-gemini.md](06-round-01-answers-gemini.md) | Gemini 回答原文（Q4/Q5） |
| [07-round-01-answers-doubao.md](07-round-01-answers-doubao.md) | doubao 回答原文（Q2/Q3） |
| [08-round-01-conclusions.md](08-round-01-conclusions.md) | round-01 统一理解（五平台收敛 + 假设验证） |
| [99-final-conclusions.md](99-final-conclusions.md) | 最终对照表与决策映射（候选判据表 + 源码落点） |

## 执行方式

走 RESEARCH_GUIDE 的 Human-in-the-Loop 多模型流程：**codex 操作浏览器**，把
[02-round-01-prompts.md](02-round-01-prompts.md) 里各平台文本块整块粘贴到对应平台，回答原文回填到
`NN-round-01-answers-<platform>.md`。纪律不变：原文事实 / 推断 / 不知道三档 + 给链接；C 类结论回项目内
验证后才能进 ADR / 根目录。

## round-01 执行记录（2026-08-14）

- ChatGPT / Claude / Grok / Gemini / doubao 五平台均已粘贴对应题组并回填原文（Chrome 浏览器自动化）。
- 统一理解与收敛见 [08-round-01-conclusions.md](08-round-01-conclusions.md)；
  候选判据对照表 + 决策映射见 [99-final-conclusions.md](99-final-conclusions.md)。
- 关键结论：value ≈ P(future need) × C(reacquisition)；项目内/跨项目是 scope 差异非价值差异；
  晋升触发用意外性/冲突（prediction error）而非定时摘要；四类失效（幻觉/过时/漂移/投毒）防护机制不同。
- 下一步：按 [99-final-conclusions.md](99-final-conclusions.md) 决策映射回项目内验证/实现（进 ADR 前置条件）。
- ChatGPT（Q1/Q2/Q3）：会话已归档原文（03 文件）；
- Claude（Q1/Q4/Q5）：[会话](https://claude.ai/chat/1c3a61b5-0239-4112-afa3-621930e4893e)；
- Grok（Q1/Q3）：[会话](https://grok.com/c/bc7ed28f-0121-4f27-b75c-b9089dd7b2ba)；
- Gemini（Q4/Q5）：[会话](https://gemini.google.com/app/74c5daeb0f98df07)；
- doubao（Q2/Q3）：[会话](https://www.doubao.com/chat/38437745338304514)。
