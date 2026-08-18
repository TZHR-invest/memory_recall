# 2026-08-16: LLM 自报信心的可靠性——外部调研（无预设）

> 类型: 外部调研 · 状态: **已完成（round-01 五平台 + round-02 四平台 + 收敛轮回项目内核对）** · 日期: 2026-08-16
> 归属: [目标模型 v1](../../../designs/crystal/v1.md) 待拍板 B5（[milestone](../../../designs/crystal/milestone.md) §6 决策门 B5）→ **B5 已收敛定案**
> 上游: [memory-confidence](../../2026-08-14-memory-confidence.md)（LLM 自报不可当概率，已定）
> 执行: **人工复制粘贴**（用户操作平台，不用 codex 浏览器）——按 RESEARCH_GUIDE 的 Human-in-the-Loop 流程

## 目标（一句话）

搞清楚：在一个 AI 开发助手的长期记忆系统里，**写入一条记忆时，如何获得一个可靠的"初始可信度"**——
LLM 在写记忆时自报的信心分数在这个问题上到底能不能用、怎么用；如果不可靠，更好的替代思路是什么。

## 最终结论（B5 定案，详见 [99-final-conclusions.md](99-final-conclusions.md)）

**冷启动初始置信度 = 来源分层先验（source_type × claim_type 弱先验，Beta 参数化，不含 LLM 自报）；
LLM 自报信心冷启动完全弃用（仅保留为 V2 校准的潜在 feature）；
真正的置信度靠后续证据更新。**（原始调研还提出了根证据独立性判断 `root_observation_id` 防自我强化，
后经**用户评审缓置**——当前 P0 add + P1 report_effect 采集面不产生复述，防线改为对账规则 + 幂等键，
详见 [99-final-conclusions.md §实施校正](99-final-conclusions.md)。）

五平台共识、无冲突，与项目已拍板（v1 单轴 content_confidence / 砍 valid 区间 / source_kind 弱先验）兼容。
落地：evidence 表保留 `extraction_type`；低置信"假说池"与草稿确认交互进 MR-011；`root_observation_id` 与
EIR 指标缓置（P2/P3 采集扩大时再引入）。

## 调研轨迹

| 轮次 | 内容 | 结果 |
|------|------|------|
| round-01 | 五平台无预设开放题（按画像分配侧重） | 高度收敛：自报不能当概率；冷启动主轴=来源分层先验；置信度=可更新起点 |
| round-02 | 四平台反馈式追问（truth discovery 适用性 / freshness 建模 / 独立性 / 低置信处理） | 全部收敛；ChatGPT 主动修正 round-01 说法；新增 root_observation_id 与 EIR 两个落地需求 |
| 收敛轮 | 回项目内核对（v1 / milestone / entity-attributes / memory-confidence） | 兼容性确认：freshness 概念采纳不新增字段；独立性与复现信号需加 lineage 限定 |

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
| [08-round-01-conclusions.md](08-round-01-conclusions.md) | round-01 统一理解（共识 + 冲突 + 待补） |
| [04-round-02-prompts.md](04-round-02-prompts.md) | round-02 追问（针对冲突点的反馈式追问，按平台打包） |
| [05-round-02-answers-chatgpt.md](05-round-02-answers-chatgpt.md) | ChatGPT round-02 回答原文（已回填） |
| [05-round-02-answers-claude.md](05-round-02-answers-claude.md) | Claude round-02 回答原文（已回填） |
| [05-round-02-answers-grok.md](05-round-02-answers-grok.md) | Grok round-02 回答原文（已回填） |
| [05-round-02-answers-doubao.md](05-round-02-answers-doubao.md) | doubao round-02 回答原文（已回填） |
| [09-round-02-conclusions.md](09-round-02-conclusions.md) | round-02 统一理解（冲突全部收敛 + 新落地需求） |
| [99-final-conclusions.md](99-final-conclusions.md) | **最终结论 + 实施映射（B5 定案）** |

## 平台分配

### round-01（按平台画像分配侧重）

| 平台 | 画像依据 | 分配侧重 |
|------|---------|---------|
| ChatGPT | 最系统、主动修正自身方案、源码级结论可靠 | 主开放题（整体抛给平台，要求系统性 + 落地） |
| Claude | 诚实、会明确说不知道、公式/推理强 | 主开放题 + 明确要求区分"事实/推理/不知道" |
| Grok | 裁决式回答、善于吸收其他框架 | 侧重"自报信心 vs 替代信号"的对比裁决 |
| Gemini | 高层结论可参考、结构最工程化 | 侧重结构化梳理（信号分类/成本/精度） |
| doubao | 中文社区视角、交互设计最落地 | 侧重中文生态 + 工程落地实践 |

### round-02（只发相关平台，针对冲突/薄弱点）

| 平台 | 追问点 |
|------|--------|
| ChatGPT | source reliability 学习在单用户单来源的落地边界 + 独立观察判据 |
| Claude | truth discovery 单用户退化形态 + 一致性信号验证实验设计 |
| Grok | freshness 独立维度建模 + 自报信心启用条件 |
| doubao | 低置信不静默丢弃的平衡 + 草稿确认触发时机 |

## 纪律（RESEARCH_GUIDE）

- 外部回答是素材不是事实；进入 ADR / `docs/` 根目录前必须以项目内源码、官方文档或可执行验证确认；
- 原始回答与链接保留，不删除；正文一个字不改、不二次概括；
- C 类结论回项目内验证后才可进设计文档/ADR。

*状态: 已完成 · 最后更新: 2026-08-16*