# Round 2 回答：Claude

> 类型: 调研（原始回答归档）
> 调研: 2026-08-12-opencode-compaction-hook
> 说明: 对应 R2-3（autocontinue 源码复核）

#### Claude
这次直接拉取了 `dev` 分支源码验证，我之前的判断是错的——**这个 hook 确实存在，且有明确类型定义**。以下是核实结果。

## 1. 精确位置：`packages/opencode/src/session/compaction.ts`

用 `curl` 拉取 `https://raw.githubusercontent.com/anomalyco/opencode/dev/packages/opencode/src/session/compaction.ts` 并 `grep -n` 定位，三个相关钩子的触发行号分别是：

```
374:        "experimental.session.compacting",
379:      yield* plugin.trigger("experimental.chat.messages.transform", {}, { messages: msgs })
501:              "experimental.compaction.autocontinue",
```

`experimental.compaction.autocontinue` 的完整调用（第 495-511 行左右，`processCompaction` 函数内 `if (result === "continue" && input.auto)` 分支、`if (!replay)` 子分支中）：

```ts
if (!replay) {
  const info = yield* provider.getProvider(userMessage.model.providerID)
  if (
    (yield* plugin.trigger(
      "experimental.compaction.autocontinue",
      {
        sessionID: input.sessionID,
        agent: userMessage.agent,
        model: yield* provider
          .getModel(userMessage.model.providerID, userMessage.model.modelID)
          .pipe(Effect.orDie),
        provider: {
          source: info.source,
          info,
          options: info.options,
        },
        message: userMessage,
        overflow: input.overflow === true,
      },
      { enabled: true },
    )).enabled
  ) {
    // 构造并写入合成的 "Continue if you have next steps..." 用户消息
    ...
  }
}
```

（GitHub 网页视图路径：`anomalyco/opencode` → `dev` 分支 → `packages/opencode/src/session/compaction.ts`，可用 Raw 链接 `https://github.com/anomalyco/opencode/raw/refs/heads/dev/packages/opencode/src/session/compaction.ts` 直接核对。）

## 2. `@opencode-ai/plugin` 的 `Hooks` 类型是否包含该钩子

**包含**。拉取 `packages/plugin/src/index.ts`（`dev` 分支）确认其类型定义（约第 310-322 行）：

```ts
/**
 * Called after compaction succeeds and before a synthetic user
 * auto-continue message is added.
 *
 * - `enabled`: Defaults to `true`. Set to `false` to skip the synthetic
 *   user "continue" turn.
 */
"experimental.compaction.autocontinue"?: (
  input: {
    sessionID: string
    agent: string
    model: Model
    provider: ProviderContext
    message: UserMessage
    overflow: boolean
  },
  output: { enabled: boolean },
) => Promise<void>
```

这纠正了我上一轮的结论——它**不是**未类型化的野生钩子，而是有官方 JSDoc 注释和明确 `input`/`output` schema 的正式钩子。它是在 **v1.4.4**（release notes: "Added the experimental `compaction.autocontinue` hook to stop auto-continuing after compaction"）引入的；只要你使用的版本号 ≥ v1.4.4（包括你问的 1.15.13+），该类型定义应该都在。

## 3. 完整语义

**触发时机**：在 `processCompaction`（对应上一轮讨论的 `experimental.session.compacting` 所在函数）内，顺序是：

```
压缩摘要生成成功（result === "continue"）
  → 判断 input.auto 是否为 true
    → 如果本次是 replay（溢出重放）分支：不触发 autocontinue，直接重放原消息
    → 如果不是 replay：触发 experimental.compaction.autocontinue
        → 根据 output.enabled 决定是否写入合成 "Continue..." 消息
  → events.publish(Event.Compacted, { sessionID })  ← 即 session.compacted 事件
```

即：**先触发这个 hook，再（可能）注入合成续接消息，最后无条件发布 `session.compacted` 事件**（只要 `result === "continue"` 且没有 `processor.message.error`）。

**输入参数含义**（对照源码逐字段）：
- `sessionID`：当前会话 ID
- `agent`：触发压缩前最后一条用户消息所用的 agent 名
- `model`：解析后的完整 `Model` 对象（来自 `provider.getModel(...)`，不是原始 providerID/modelID 字符串）
- `provider`：`{ source, info, options }`，`info` 是 `provider.getProvider(userMessage.model.providerID)` 返回的完整 provider 对象，`source`/`options` 从中取出
- `message`：触发本次压缩的原始 `UserMessage`（`userMessage`，即 parent 消息的 `.info`）
- `overflow`：布尔值，对应 `input.overflow === true`，标记本次压缩是否由"硬性上下文溢出"触发（而非常规的比例阈值预防性压缩）

**`enabled: false` 的效果**：
- 默认值是 `{ enabled: true }`（`plugin.trigger` 调用的第三个参数，即初始 output）。
- 若插件把 `output.enabled` 设为 `false`，`if (...).enabled` 判断为假，直接**跳过**后面构造 `continueMsg` 和写入合成文本 part 的整段代码——也就是**不会**自动生成那条 "Continue if you have next steps, or stop and ask for clarification..." 的用户消息。
- 效果等价于旧版本 issue #11301/#13217/#12780 里用户抱怨的"压缩后停下来等你手动敲 continue"的那种行为——只是从"bug/不可控"变成了插件可以**显式控制**的行为。
- 需要注意：`enabled: false` 只是不生成这条合成续接消息，并**不影响** `events.publish(Event.Compacted, ...)` 的发布——`session.compacted` 事件在这段判断之后、且只要求 `result === "continue"`，与 `autocontinue` 的 `enabled` 取值无关，二者是解耦的。

**和 `session.compacted` 事件的关系**：
- 二者不是同一层级的机制：`experimental.compaction.autocontinue` 是**可修改行为的干预钩子**（`plugin.trigger`，同步等待 `output` 被插件填充后再决定后续分支);`session.compacted`（对应源码里的 `Event.Compacted`，来自 `SessionCompactionEvent`）是**只读的事件广播**（`events.publish`，通过通用 `event` 钩子订阅，插件不能修改任何行为，只能被通知"压缩已完成"）。
- 顺序上，`session.compacted` **在 `experimental.compaction.autocontinue` 判断完成之后**发布，所以如果你的插件同时监听 `event`（拿到 `session.compacted`）和 `experimental.compaction.autocontinue`，你会先经历 autocontinue 的干预窗口，再收到 compacted 通知——此时续接消息（如果 `enabled` 未被设为 false）已经写入完毕。
- 二者共同覆盖了压缩前（`experimental.session.compacting`）→ 压缩后是否自动续接（`experimental.compaction.autocontinue`）→ 压缩完成通知（`session.compacted`）这条完整链路。

