# 调研：OpenCode 压缩 hook 机制全景

> 状态: ACTIVE（调研已收敛，可引用）
> 类型: 调研（外部 / 人类搬运）
> 日期: 2026-08-12（三轮收敛至 2026-08-13）
> 关联: [源码核实版](../../2026-08-12-opencode-compaction-hook.md)、ADR-0007/0008、
> [实施计划](../../2026-08-12-core-plugin-refactor-plan.md)

## 目标

借助多模型/多平台信息差交叉验证 opencode 压缩 hook 机制全景，支撑压缩收敛决策（ADR-0007/0008）。

## 使用方法

按 `NN-round-NN-prompts.md` 复制对应平台的提示词块 → 回答原文粘贴进
`NN-round-NN-answers-<platform>.md`（一次粘贴一个文件）→ 告知 Agent 统一理解。

## 结论速查

- 三轮调研全部收敛，与 ADR-0003~0008 无冲突；
- 核心结论：只用 `output.context`、不替换 prompt、不注册 autocontinue；
  hook 内 fail-open（try/catch + 超时 + 大小上限）+ 共存检测（prompt 已被接管则跳过）；
- 平台画像：ChatGPT/Grok 源码级可靠；Claude 诚实但可能漏检；Gemini/doubao 字段易编造；
- 最终统一理解见 [21-final-conclusions.md](21-final-conclusions.md)。

## 文件索引

| 文件 | 内容 |
|------|------|
| [01-goals.md](01-goals.md) | 背景 + 已知源码事实 |
| [02-round-01-prompts.md](02-round-01-prompts.md) | Round 1 提示词（平台分工 + Q1-Q8） |
| [03~07-round-01-answers-*.md](03-round-01-answers-chatgpt.md) | Round 1 五平台回答（Q1/Q2） |
| [08-round-01-conclusions.md](08-round-01-conclusions.md) | Round 1 统一理解 |
| [09-round-02-prompts.md](09-round-02-prompts.md) | Round 2 追问（R2-1~R2-4） |
| [10~14-round-02-answers-*.md](10-round-02-answers-chatgpt.md) | Round 2 回答 |
| [15-round-02-conclusions.md](15-round-02-conclusions.md) | Round 2 统一理解 |
| [16-round-03-prompts.md](16-round-03-prompts.md) | Round 3 去留评估 + R3-1/R3-2 |
| [17~20-round-03-answers-*.md](17-round-03-answers-chatgpt.md) | Round 3 回答 |
| [21-final-conclusions.md](21-final-conclusions.md) | 最终统一理解（Round 3 结论） |

## 待办（项目内验证，不属于调研）

- 构造抛错/超时/超大 context 的 hook 实测；
- 大窗口模型下原生 auto 触发时机观察。
