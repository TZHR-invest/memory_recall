# Round 2 提示词（追问轮：R2-1~R2-4）

> 类型: 调研（提示词）
> 调研: 2026-08-12-opencode-compaction-hook
> 说明: 仅追分歧点

## 第二轮提示词（Agent 按需追加）

> 状态：R2-1~R2-4 已全部回填并统一理解（见上），本节省略原文占位，保留历史。

本轮只追分歧点，不再全量跑：

| 提示词 | 平台 | 目的 |
|--------|------|------|
| R2-1 | doubao + Gemini | 核对两个钩子的 input/output 精确字段 |
| R2-2 | doubao + Gemini | 核对 `output.prompt` 设置后 context 是否被忽略 |
| R2-3 | Claude | 重新检索 `experimental.compaction.autocontinue` 的源码与类型 |
| R2-4 | ChatGPT（Grok 可选） | 分析 hook 抛异常对压缩流程的影响与插件自保方式 |

**R2-1（doubao / Gemini）**

> 请基于 opencode dev 分支源码 `packages/opencode/src/session/compaction.ts` 与
> `@opencode-ai/plugin` 的类型定义，重新核对两个钩子的 input/output 精确字段：
> 1) `experimental.session.compacting` 的 input 是否只有 `sessionID`？
> 2) `experimental.compaction.autocontinue` 的 input 是否包含
> `sessionID / agent / model / provider / message / overflow`，output 是否只有 `enabled`？
> 请给出源码行号，不要推测。

**R2-2（doubao / Gemini）**

> 请对照源码 `nextPrompt = compacting.prompt ?? buildPrompt({ previousSummary, context: compacting.context })`：
> 当插件设置 `output.prompt` 后，`output.context` 是否仍会拼进最终 prompt？
> 官方文档说此时 context 被忽略；你上一轮说 context 仍生效/被传入渲染器，请给出一致结论并引用源码。

**R2-3（Claude）**

> 请重新在 opencode 仓库 dev 分支检索 `experimental.compaction.autocontinue`：
> 它位于 `packages/opencode/src/session/compaction.ts` 的哪一行？
> `@opencode-ai/plugin` 1.15.13+ 的 Hooks 类型是否已包含该钩子？
> 你上一轮说找不到源码，请用具体检索方式或链接复核。

**R2-4（ChatGPT / Grok）**

> 请分析 opencode `Plugin.trigger` 的实现（`packages/opencode/src/plugin/index.ts`，
> 循环内 `Effect.promise(async () => fn(input, output))` 无 try/catch）：
> 如果某个插件在 `experimental.session.compacting` 钩子里抛异常，会对本次压缩造成什么影响？
> 是否有上层兜底？插件应如何自保？


