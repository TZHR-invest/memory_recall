# ADR-0007: 压缩机制收敛到官方 hook（废弃预压缩，仅用 context 注入）

> 状态: Accepted
> 日期: 2026-08-12
> 关联: ADR-0008、[2026-08-12-opencode-compaction-hook.md](../notes/2026-08-12-opencode-compaction-hook.md)

## 背景

插件存在两套压缩路径：

- 官方 hook：`experimental.session.compacting`，只向 `output.context` 注入内容；
- 预压缩 hack：token ≥80% 时插件主动调 `session.summarize`，并直接写
  `~/.opencode/messages|parts` 假消息注入 7 段结构化 prompt（`injectHookMessage` +
  `createCompactionPrompt`）。

官方源码（v1.18.16）证明：插件自调 `session.summarize`、手动 `/compact`、原生自动压缩
都走同一个 `compaction.process`，`experimental.session.compacting` 必然触发；
且设置 `output.prompt` 时 `output.context` 被忽略、官方默认"锚定摘要更新"语义丢失。

## 选项

- A: 保留预压缩，改为可选开关；
- B: 删除预压缩，hook 用 `output.prompt` 整体替换默认 prompt（需要复刻锚定）；
- C: 删除预压缩，hook 只用 `output.context` 追加 AI guidance + 项目记忆。

## 决策

选择 **C**：

- 删除 `checkAndTriggerCompaction`（触发决策）、`injectHookMessage`（私有格式写入）、
  `createCompactionPrompt`（7 段 prompt）；
- `experimental.session.compacting` 只 push `output.context`，不设置 `output.prompt`；
- 压缩触发完全交给原生 `compaction.auto`（默认开）+ 手动 `/compact`。

## 理由

- 官方同管线：预压缩"保证 hook 生效"的动机不成立；
- 默认 prompt 已带锚定摘要更新与结构化模板（Objective / Important Details / Work State /
  Next Move / Relevant Files），context 追加保留全部官方语义；
- 删除对 `~/.opencode/messages|parts` 私有存储格式的写入依赖，升级不炸。

## 后果

- 正面：compaction.ts 大幅缩小；opencode 存储升级兼容；
- 负面：失去"提前压缩"能力，依赖原生 auto 时机（`reserved` 默认 20k，需上线后验证
  "满窗再压"痛点是否复发）；
- 跟进：升级并对齐 `@opencode-ai/plugin` / `@opencode-ai/sdk` 到 ^1.18.x。

*状态: Accepted · 日期: 2026-08-12*
