# Round 1 提示词（定向轮：平台分工 + Q1-Q8）

> 类型: 调研（提示词）
> 调研: 2026-08-12-opencode-compaction-hook
> 说明: 拆分自单文件调研记录（2026-08-12），内容对应原记录第 23-103 行

## 平台分工（避免全量重复）

原则：每个问题至少 1 个平台回答；我们已有源码证据的问题只留 1-2 个平台交叉；
信息差大的问题（社区/历史）给 2-3 个平台。第二轮只追问分歧点，不重新全量跑。

| 问题 | 建议平台 | 理由 | 备注 |
|------|---------|------|------|
| Q3 原生压缩配置/阈值 | Claude + Gemini | 源码与公式推理强 | 我们已有默认值，外部补调参经验 |
| Q4 agent/todos 历史演进 | ChatGPT + Grok | web/issue 与社区信息差大 | 我们只有当前版本结论，外部补历史 |
| Q5 summarize 与 hook 异同 | Claude + Gemini | 管线/API 语义推理强 | 我们已有同管线结论 |
| Q6 压缩相关事件 | ChatGPT（Gemini 可选） | SDK/类型与文档检索 | 我们已有事件列表 |
| Q7 锚定摘要语义 | Claude（doubao 可选） | prompt 语义推理强；doubao 提供不同语料视角 | 我们已有 buildPrompt 结论 |
| Q8 注入记忆最佳实践/坑 | Grok + ChatGPT（doubao 可选） | 社区/X/web 信息差最大 | 无源码强证据 |

各平台工作量（推荐）：

- ChatGPT：Q4、Q6、Q8；
- Claude：Q3、Q5、Q7；
- Gemini：Q3、Q5；
- Grok：Q4、Q8；
- doubao：Q7 或 Q8（中文社区视角，可选）。

## 问题清单（提示词）

每条可直接复制。若平台回答太长，可以只取与问题相关部分，但请保留原链接。

### Q1 能力全景

> 请基于 opencode 官方文档和源码，系统梳理 `experimental.session.compacting` 插件钩子的全部能力：
> 触发时机、`output.context` 与 `output.prompt` 的区别和优先级、多个插件同时注册该钩子时的合并/覆盖规则、
> `experimental.` 前缀带来的兼容性风险。请给出官方文档链接和关键源码路径。

### Q2 autocontinue

> 请解释 opencode `experimental.compaction.autocontinue` 钩子的完整语义：在什么时机触发、
> `enabled: false` 会产生什么效果、输入参数各代表什么、它和 `session.compacted` 事件有什么关系。

### Q3 原生自动压缩与配置

> opencode 原生自动压缩的触发逻辑和配置项（`compaction.auto` / `reserved` / `tail_turns` /
> `preserve_recent_tokens` / `prune` 等）：默认值是什么、触发阈值公式是什么、预留 buffer 的用途、
> 社区通常如何调参来避免"上下文快满才压缩"。

### Q4 agent / model / todos 保留

> opencode 压缩后，会话的 agent、model、todos 是否会保留？历史上是否有丢失问题（例如 GitHub issue
> 提到 todo/model/agent 不持久）？现在的版本如何保证？插件还需要自己做"现场恢复"吗？

### Q5 summarize 与 hook

> 插件通过 SDK 调用 `session.summarize`，与用户手动 `/compact`、原生自动压缩相比，在钩子触发、
> 消息生成、事件发布上有何异同？`session.summarize` 是否支持传入自定义 prompt？

### Q6 压缩相关事件

> opencode 与压缩相关的事件（`session.compacted`、`session.next.compaction.started/delta/ended`、
> `session.status` 的 compacting 状态）各自语义是什么？插件想感知"压缩完成"应该监听哪个事件最可靠？

### Q7 默认 prompt 与锚定摘要

> opencode 默认压缩 prompt 的"锚定摘要更新"机制：previous summary 如何传递、多轮压缩如何累积、
> 插件设置 `output.prompt` 完全替换后会丢失什么？社区有哪些自定义压缩 prompt 的最佳实践？

### Q8 注入记忆的最佳实践

> 在 opencode 压缩钩子中注入项目记忆 / AI guidance 的社区最佳实践与常见坑，包括与
> Oh-My-OpenCode 等压缩相关插件共存的注意事项；官方文档或 issue 中的推荐写法。
