# Round 2 统一理解

> 类型: 调研（统一理解）
> 调研: 2026-08-12-opencode-compaction-hook
> 说明: 第二轮结论

### 第二轮统一结论（2026-08-13）

1. **R2-1（字段核对）收敛**：doubao 勘误、Gemini 与 Claude 均确认——`session.compacting` input
   只有 `sessionID`；`autocontinue` input 为 `sessionID/agent/model/provider/message/overflow`，
   output 只有 `enabled`。注意：Gemini 的"源码调用栈"伪代码（`results` 数组、`findLast`、
   `some(...)`）与真实的 shared-mutable-output 机制不符，**只采信其结论，不采信其实现细节**。
2. **R2-2（prompt/context 关系）收敛**：doubao 与 Gemini 均确认——设置 `output.prompt` 后
   `buildPrompt` 不执行，`output.context` 完全被忽略；doubao 补充最佳实践：只 push context，
   若必须覆盖 prompt 则手动把 context 内联进 prompt。与源码和官方文档一致。
3. **R2-3（Claude）收敛**：Claude 勘误并定位——`experimental.compaction.autocontinue` 存在于
   compaction.ts（dev 约 L501），`@opencode-ai/plugin` Hooks 类型含 JSDoc，v1.4.4 引入。
4. **R2-4（hook 异常）收敛且重要**：ChatGPT 与 Grok 独立得出同一结论——`Plugin.trigger` 对 hook
   调用无 try/catch，hook 抛错 = 本次压缩失败中止（LLM 不调用、后续插件不执行、`session.compacted`
   不发），上层无专用兜底；插件必须自建 error boundary（try/catch + 超时 + context 大小上限，
   fail-open）。Grok 末尾"`message` 是压缩后的 summary 消息"是错的：源码传的是 parent user message
   （`userMessage`），不采信该条。
5. **对实施计划的增量**：压缩 hook 内 try/catch、超时保护、`output.context` 大小上限、
   只 mutate output 不依赖返回值；失败只记日志，让默认压缩继续。

