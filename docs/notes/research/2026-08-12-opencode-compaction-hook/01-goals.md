# 调研目标与已知事实

> 类型: 调研（背景/基线）
> 调研: 2026-08-12-opencode-compaction-hook

## 背景

已基于官方源码（v1.18.16，commit 1f94d8a）核实了压缩 hook 的关键结论，但"官方压缩机制全景"
希望借助多模型/多平台的信息差交叉验证：官方文档之外的社区实践、历史 issue、版本演进、多插件共存坑。

## 已知源码事实（仅供对照，不要作为提示词内容，避免诱导回答）

- hook 触发：`plugin.trigger("experimental.session.compacting", { sessionID }, { context: [], prompt: undefined })`，
  `prompt` 优先于 `context`；`buildPrompt` 支持 previousSummary 锚定 + context 追加；
- 插件自调 `session.summarize` 与手动/自动压缩走同一 `compaction.process`，hook 都会触发；
- 自动压缩：`isOverflow` 按 `count >= context - reserved` 判断，`compaction.auto` 默认开启，
  默认 `reserved = min(20000, maxOutputTokens)`；`ContextOverflowError` 也会触发压缩；
- 配置项：`auto / prune / tail_turns（默认 2）/ preserve_recent_tokens / reserved`；
- agent 由用户消息字段保留、todos 存独立表，压缩不删改；`autocontinue` 只控制合成 continue 消息；
- 默认 prompt 为锚定摘要更新 + 结构化模板（Objective / Important Details / Work State / Next Move / Relevant Files）；
- 事件：`session.compacted`（成功后）、`session.next.compaction.started/delta/ended`（v2）、
  `session.status` 的 compacting 状态。
