# Round 1 回答：ChatGPT

> 类型: 调研（原始回答归档）
> 调研: 2026-08-12-opencode-compaction-hook
> 说明: 对应 Q1/Q2；原文粘贴，未概括

### ChatGPT

**Q1**

我基于 **OpenCode 当前官方文档 + `dev` 分支源码**核了一遍。这个 hook 的实际能力比“给 compact prompt 加一点上下文”要更值得注意：**它本质上是一个共享可变 `output` 的串行 middleware**，因此多个插件之间存在明确的先后覆盖关系。

## 先给结论

`experimental.session.compacting` 当前可以理解成：

```ts
(input: { sessionID: string }, output: {
  context: string[]
  prompt?: string
}) => Promise<void>
```

它有两个模式：

1. **`output.context.push(...)`**

   * 在 OpenCode 默认 compact prompt 后面追加额外内容。
   * 多个插件可以累加。
   * 适合“我只想增加一些必须保留的信息”。

2. **`output.prompt = "..."`**

   * **完全替换 OpenCode 默认 compact prompt**。
   * 一旦最终 `output.prompt` 有值，`output.context` 整个都会被忽略。
   * 多个插件都设置 `prompt` 时，**后执行的插件覆盖前一个插件**。

而且这些 hook **不是并行执行，而是严格按照插件注册顺序串行执行，共享同一个 `output` 对象**。所以它实际上具有 middleware / interceptor 的语义。([GitHub][1])

---

# 1. 触发时机

官方文档的定义非常明确：

> `experimental.session.compacting` fires before the LLM generates a continuation summary.

也就是：

```text
正常对话历史
    ↓
判断需要 compact
    ↓
选择要压缩的历史
    ↓
experimental.session.compacting   ← 这里
    ↓
生成 compact prompt
    ↓
调用 compaction agent / LLM
    ↓
生成 summary
    ↓
session.compacted
```

官方插件文档：

[OpenCode Plugins 官方文档](https://opencode.ai/docs/plugins/?utm_source=chatgpt.com)

源码真正的调用点在：

[packages/opencode/src/session/compaction.ts](https://github.com/anomalyco/opencode/blob/dev/packages/opencode/src/session/compaction.ts?utm_source=chatgpt.com)

核心代码逻辑是：

```ts
const compacting = yield* plugin.trigger(
  "experimental.session.compacting",
  { sessionID: input.sessionID },
  { context: [], prompt: undefined },
)
```

然后才构造真正给 compact LLM 的 prompt。([GitHub][2])

特别值得注意的是：**hook 不是在“summary 已经生成之后”触发，而是在 summary LLM 调用之前修改 summary 的输入 prompt。**

---

# 2. `input` 实际能拿到什么？

目前这个 hook 的 input 极其简单：

```ts
{
  sessionID: string
}
```

也就是说，它**没有直接把当前 messages/history 作为 input 暴露给 hook**。

源码调用点明确只有：

```ts
{ sessionID: input.sessionID }
```

([GitHub][2])

这点非常重要。

如果你想做：

> “根据当前 session 的实际内容，动态生成需要保留的 memory/context”

那么 hook 本身没有直接给你：

```ts
messages
parentID
auto
model
```

你需要通过 `sessionID` 再调用 OpenCode SDK/API 去读取 session 内容。

这也是为什么有人提出新的：

`experimental.session.pre-compact`

hook，希望直接拿到完整 history，并允许在 compact 前做一次有工具权限的 state migration；但这个需求目前只是 feature request，并不是现有 hook 的能力。([GitHub][3])

---

# 3. `output.context` 到底是什么？

默认情况下，OpenCode 会先建立：

```ts
{
  context: [],
  prompt: undefined
}
```

然后插件可以：

```ts
output.context.push(`
## Important State

- Current task...
- Important decisions...
- Files...
`)
```

OpenCode 最终构造：

```ts
const prompt =
  compacting.prompt ??
  [defaultPrompt, ...compacting.context].join("\n\n")
```

也就是说默认情况下实际等价于：

```text
[OpenCode 默认 compact prompt]

+

[plugin A context]

+

[plugin B context]

+

[plugin C context]
```

([GitHub][2])

所以 `context` 的语义非常准确：

> **Additional context appended to the default prompt**

而不是“修改默认 prompt”。

---

# 4. `output.prompt` 的优先级更高

这是这个 hook 最关键的地方。

源码：

```ts
const prompt =
  compacting.prompt ??
  [defaultPrompt, ...compacting.context].join("\n\n")
```

因此：

```text
prompt != undefined
        ↓
直接使用 prompt
        ↓
context 完全不参与
```

而不是：

```text
defaultPrompt
+ context
+ prompt
```

官方文档也明确写了：

> When `output.prompt` is set, it completely replaces the default compaction prompt. The `output.context` array is ignored in this case.

([OpenCode][4])

所以优先级可以画成：

```text
                output.prompt
                     │
                     │ 有值？
                     ▼
              ┌──────────────┐
              │ 完全使用它    │
              │ context 被忽略 │
              └──────────────┘
                     │
                  否 │
                     ▼
       defaultPrompt + context[]
```

### 一个很容易踩的坑

假设：

```ts
output.context.push("A")
output.prompt = "B"
```

最终不是：

```text
default + A + B
```

而是：

```text
B
```

`A` 被完全丢弃。

---

# 5. 多个插件同时注册时，到底怎么合并？

这里源码比文档更重要。

OpenCode 的 plugin service 保存：

```ts
hooks: Hooks[]
```

每个插件注册出来的 hook object 都进入这个数组。

然后：

```ts
for (const hook of s.hooks) {
  const fn = hook[name] as any
  if (!fn) continue

  yield* Effect.promise(async () => fn(input, output))
}
```

也就是说：

**顺序执行 + 同一个 output 引用。**

([GitHub][1])

---

## 情况 A：多个插件都 `push context`

例如：

### Plugin A

```ts
output.context.push("A")
```

### Plugin B

```ts
output.context.push("B")
```

### Plugin C

```ts
output.context.push("C")
```

最终：

```ts
context = [
  "A",
  "B",
  "C",
]
```

prompt：

```text
defaultPrompt

A

B

C
```

所以 **context 是 additive / append-only 风格的累积**。

---

# 6. 多个插件都设置 `output.prompt` 呢？

这就完全不同了。

假设：

### Plugin A

```ts
output.prompt = "PROMPT A"
```

执行完：

```ts
output.prompt === "PROMPT A"
```

然后 Plugin B：

```ts
output.prompt = "PROMPT B"
```

最终：

```ts
output.prompt === "PROMPT B"
```

Plugin C 再设置：

```ts
output.prompt = "PROMPT C"
```

最终：

```text
PROMPT C
```

所以是：

> **last writer wins**

而不是：

> first plugin wins

也不是：

> prompts automatically merge

源码没有任何 merge 逻辑，就是同一个 JS object 被依次 mutation。([GitHub][1])

---

# 7. 更有意思的是：`context` 和 `prompt` 的组合也会产生“覆盖”

比如：

### Plugin A

```ts
output.context.push("A")
```

### Plugin B

```ts
output.prompt = "B"
```

最终：

```ts
{
  context: ["A"],
  prompt: "B"
}
```

但是最终生成：

```text
B
```

因为：

```ts
compacting.prompt ??
[defaultPrompt, ...compacting.context].join(...)
```

所以 A 的 context 虽然**还存在于 output 对象里**，但已经没有任何效果。

反过来：

### Plugin A

```ts
output.prompt = "A"
```

### Plugin B

```ts
output.context.push("B")
```

最终：

```ts
{
  prompt: "A",
  context: ["B"]
}
```

但仍然只使用：

```text
A
```

所以一旦任何插件设置了 `prompt`，**后续插件如果只操作 `context`，也无法让 context 生效。**

这是设计上非常重要的一个性质。

---

# 8. 插件执行顺序从哪里来？

当前源码还专门写了注释：

```ts
// Keep plugin execution sequential so hook registration and execution
// order remains deterministic across plugin runs.
```

也就是说这是**有意设计成 deterministic ordering**，不是偶然实现。

插件加载后依次：

```ts
for (const load of loaded) {
  ...
  applyPlugin(load, input, hooks)
}
```

然后：

```ts
hooks.push(...)
```

最后 trigger 再按照：

```ts
for (const hook of s.hooks)
```

执行。([GitHub][1])

官方文档也说明插件来自多个来源，并按顺序加载：

1. global config
2. project config
3. global plugin directory
4. project plugin directory

([OpenCode][5])

所以如果你真的在多个插件里使用这个 hook，**插件加载顺序就会成为 prompt 覆盖语义的一部分。**

---

# 9. `output` 是“返回值”，还是必须原地修改？

这里容易产生误解。

hook 类型是：

```ts
(input, output) => Promise<void>
```

也就是说：

```ts
return {
  context: [...]
}
```

这种思路是不对的。

正确方式是：

```ts
output.context.push(...)
```

或者：

```ts
output.prompt = "..."
```

因为 `Plugin.trigger()`：

```ts
await fn(input, output)
```

最后：

```ts
return output
```

它依赖的是**共享 output 对象的 mutation**。([GitHub][1])

这和 OpenCode 其他 transform hook 的设计也是一致的；源码近期甚至专门补充文档，强调某些 experimental transform hook 的 output array 是 live payload，需要原地修改。([GitHub][6])

---

# 10. 它能不能访问/修改真正的 compact history？

**不能直接通过 hook output 做到。**

当前 compact 流程其实是：

```text
history
   ↓
select()
   ↓
selected.head
   ↓
experimental.session.compacting
   ↓
生成 prompt
   ↓
MessageV2.toModelMessagesEffect(selected.head)
   ↓
compaction LLM
```

源码中 `selected.head` 是在 hook **之前**选出来的。然后：

```ts
const msgs = structuredClone(selected.head)

yield* plugin.trigger(
  "experimental.chat.messages.transform",
  {},
  { messages: msgs }
)
```

再转成 model messages。([GitHub][2])

所以这个 hook 的定位其实非常清晰：

> **控制“让 LLM 如何总结”，而不是控制“哪些历史进入总结”。**

当然，插件可以通过其他 API 读取 session，然后把某些东西塞进 `output.context`，间接实现类似效果。

---

# 11. 它甚至不能让 compact LLM 调工具

这是理解这个 hook 边界的关键。

compact processor 最终调用：

```ts
processor.process({
  ...
  tools: {},
  system: [],
  messages: [...]
})
```

也就是说 compact LLM 是一个**纯 summary generation**阶段，没有工具。([GitHub][2])

这也是为什么 GitHub 上后来有人提出 `experimental.session.pre-compact`：

```text
普通 Agent
   ↓
pre-compact
   ↓   ← 可以读写文件、迁移 memory
compact
   ↓   ← 纯文本总结
继续
```

当前 `experimental.session.compacting` 做不到这个事情。([GitHub][3])

如果你是在研究 **OpenCode 长期 memory / knowledge base / harness**，这一点其实非常重要。

---

# 12. `experimental.` 前缀意味着什么？

这个风险我建议分成 **API 风险** 和 **语义风险** 两层。

## API 风险：明确存在

OpenCode 官方对 experimental 能力的描述非常直接：

> Experimental options are not stable. They may change or be removed without notice.

([OpenCode][7])

虽然这里文档针对的是 configuration 中的 `experimental`，但 `experimental.session.compacting` 本身采用相同的命名约定，实际上就是在告诉你：

```text
这不是稳定 API contract
```

因此你不能假设：

```ts
"experimental.session.compacting"
```

永远存在。

更不能假设：

```ts
output.context: string[]
output.prompt?: string
```

永远保持不变。

---

# 13. 这个 hook 的历史其实已经证明了这种风险

这个 hook 本身就发生过 API 扩展。

最初是：

```ts
output: {
  context: string[]
}
```

后来才增加：

```ts
prompt?: string
```

并加入“完全替换默认 compact prompt”的能力。

对应的官方代码变更记录：

[feat(plugin): allow compaction hook to replace prompt entirely (#5907)](https://git.joshthomas.dev/mirrors/opencode/commit/eab177f5e7ae91bdd7679867b43f77a479aefb74?utm_source=chatgpt.com)

这非常有代表性：

```text
旧版：

context only
       ↓
default prompt + context

新版：

prompt ────────────────→ replace everything
context ───────────────→ append to default
```

所以如果你写一个长期维护的插件，**不能把这个 hook 当作稳定 ABI。**

---

# 14. 还有一个更隐蔽的兼容性风险：不仅名字可能变，语义也可能变

比如未来完全可能出现：

```ts
experimental.session.compacting
```

变成：

```ts
session.compacting
```

或者：

```ts
output.prompt
```

从“完全替换”变成其他语义。

甚至 input 可能增加：

```ts
{
  sessionID,
  auto,
  parentID,
  messages
}
```

这种变化并不违反 OpenCode 对 experimental API 的承诺。

事实上，目前社区提出的 `pre-compact` proposal 就是在说明现有 hook 暴露的信息不足。([GitHub][3])

---

# 15. 所以如果你现在要写一个 Compaction Plugin，我建议这样设计

### 最稳妥

```ts
"experimental.session.compacting": async (input, output) => {
  output.context.push(`
## Persistent State

Preserve:
- ...
- ...
- ...
`)
}
```

优点：

```text
OpenCode 默认 prompt
        +
你的增强
```

OpenCode 即使改进默认 compact prompt，你也自动获得改进。

---

### 风险更高

```ts
output.prompt = `
You are compacting...

...
`
```

因为你实际上是在：

> **fork OpenCode 的 compact prompt**

以后 OpenCode 默认 prompt 增加：

* 新的 metadata
* 新的文件信息
* 新的状态
* 新的安全约束
* 新的 compact 策略

你都不会自动获得。

GitHub issue #16512 就恰好说明了有人因为默认 prompt 太弱而采用 `output.prompt` 完全替换的 workaround。([GitHub][8])

---

# 16. 如果多个插件共存，我会特别警惕这一点

假设你装了：

```text
Plugin A: memory
Plugin B: todo
Plugin C: better-compaction
Plugin D: some-agent-framework
```

如果：

```text
A → context.push(memory)
B → context.push(todo)
C → prompt = custom
D → context.push(...)
```

最终：

```text
C 的 prompt
```

**A/B/D 全部白做。**

所以对于一个插件生态而言，`output.prompt` 实际上是一个具有**全局 veto / override 效果**的能力。

这也是我认为这个 hook 最值得注意的设计缺陷之一：

```text
context
   ↓
可组合

prompt
   ↓
不可组合
   ↓
last writer wins
```

---

# 17. 关键源码路径

我建议你以后直接盯这几个文件：

| 文件                                            | 作用                                                 |
| --------------------------------------------- | -------------------------------------------------- |
| `packages/plugin/src/index.ts`                | **Hook 类型定义**，包括 `experimental.session.compacting` |
| `packages/opencode/src/plugin/index.ts`       | **Hook 注册、加载、串行执行机制**                              |
| `packages/opencode/src/session/compaction.ts` | **真正触发 compact hook + prompt 构造 + compact LLM 调用** |
| `packages/opencode/src/session/processor.ts`  | compact agent 最终如何执行 LLM processing                |

最核心的两个：

[plugin/src/index.ts](https://github.com/anomalyco/opencode/blob/dev/packages/plugin/src/index.ts?utm_source=chatgpt.com)

[opencode/src/plugin/index.ts](https://github.com/anomalyco/opencode/blob/dev/packages/opencode/src/plugin/index.ts?utm_source=chatgpt.com)

[session/compaction.ts](https://github.com/anomalyco/opencode/blob/dev/packages/opencode/src/session/compaction.ts?utm_source=chatgpt.com)

---

## 最后压缩成一张“心智模型”

```text
                 OpenCode Session
                       │
                       ▼
                需要 Compact？
                       │
                       ▼
                  select history
                       │
                       ▼
        ┌──────────────────────────────┐
        │ experimental.session.compacting
        │                              │
        │ Plugin A ──┐                │
        │ Plugin B ──┼── same output  │
        │ Plugin C ──┘                │
        └──────────────────────────────┘
                       │
             ┌─────────┴─────────┐
             │                   │
      prompt 有值             prompt 无值
             │                   │
             ▼                   ▼
      完全使用 prompt       defaultPrompt
             │                   +
             │                context[]
             │                   │
             └─────────┬─────────┘
                       ▼
                 compact LLM
                       │
                  tools = {}
                       │
                       ▼
                  summary
```

**一句话概括：**

> `experimental.session.compacting` 不是一个“compact 生命周期事件”，而是一个**在 compact LLM 调用前，对 continuation-summary prompt 进行 middleware 式修改的 experimental hook**；`context` 是可累加的，`prompt` 是全量覆盖的，多个插件按注册顺序串行执行且共享同一 output，因此 `prompt` 本质上是 **last-writer-wins**。

如果你是在考虑用它做你前面一直在研究的那种 **OpenCode 长期记忆 / knowledge accumulation / harness**，那么我会特别建议把 **`context` 注入、`prompt` override、session 外部持久化** 三者分开设计——不要把真正的 memory persistence 全压在这个 experimental hook 上。 ([GitHub][3]) 

[1]: https://github.com/anomalyco/opencode/blob/dev/packages/opencode/src/plugin/index.ts "opencode/packages/opencode/src/plugin/index.ts at dev · anomalyco/opencode · GitHub"
[2]: https://github.com/sst/opencode/blob/dev/packages/opencode/src/session/compaction.ts?utm_source=chatgpt.com "opencode/packages/opencode/src/session/compaction.ts at dev · anomalyco/opencode · GitHub"
[3]: https://github.com/anomalyco/opencode/issues/24958?utm_source=chatgpt.com "Feature Request: experimental.session.pre-compact Hook for Plugin-Controlled Context Transition · Issue #24958 · anomalyco/opencode · GitHub"
[4]: https://dev.opencode.ai/docs/plugins/?utm_source=chatgpt.com "Plugins | OpenCode"
[5]: https://opencode.ai/docs/zh-cn/plugins/?utm_source=chatgpt.com "插件 | OpenCode"
[6]: https://github.com/anomalyco/opencode/issues/33026?utm_source=chatgpt.com "docs(plugin): document in-place mutation requirement for experimental.chat.{system,messages}.transform · Issue #33026 · anomalyco/opencode · GitHub"
[7]: https://opencode.ai/docs/config/?utm_source=chatgpt.com "Config | OpenCode"
[8]: https://github.com/anomalyco/opencode/issues/16512?utm_source=chatgpt.com "[FEATURE]: Improve compaction prompt to preserve critical context details · Issue #16512 · anomalyco/opencode · GitHub"

https://chatgpt.com/s/t_6a7c7646f4648191870e82f72e215ab3

**Q2**

可以。这个 hook 和你上一问的 `experimental.session.compacting` **处在同一个 compaction 流程里，但职责完全不同**：

* `experimental.session.compacting`：**决定“怎么总结”**
* `experimental.compaction.autocontinue`：**决定“总结完成后要不要自动再发一轮 Continue”**
* `session.compacted`：**通知“这次 compaction 已经完成”**

我按当前 OpenCode `dev` 源码梳理。

## 1. 它究竟在什么时候触发？

关键代码在：

[packages/opencode/src/session/compaction.ts](https://github.com/anomalyco/opencode/blob/dev/packages/opencode/src/session/compaction.ts?utm_source=chatgpt.com)

`processCompaction()` 的核心流程大致是：

```text
LLM 正常工作
    │
    ├─ 正常完成
    │
    └─ 发现需要 compaction
             │
             ▼
      processCompaction()
             │
             ├─ 选择需要压缩的 history
             │
             ├─ experimental.session.compacting
             │
             ├─ compaction LLM
             │
             ├─ 得到 summary
             │
             └─ result === "continue" && input.auto
                    │
                    ▼
          experimental.compaction.autocontinue
                    │
              enabled ?
               ┌────┴────┐
              yes        no
               │          │
               ▼          ▼
        创建 synthetic     不创建
        "Continue..."      Continue
               │
               ▼
        publish session.compacted
```

所以它**不是在 compaction 开始时触发**，而是在：

> **compaction LLM 已经完成，并且 OpenCode 判断这次 compaction 后原本应该继续执行时**

才触发。

源码中的精确条件是：

```ts
if (result === "continue" && input.auto) {
  ...
  if (!replay) {
    ...
    if (
      (yield* plugin.trigger(
        "experimental.compaction.autocontinue",
        ...
        { enabled: true },
      )).enabled
    ) {
      // 创建 synthetic "Continue..." user message
    }
  }
}
```

([GitHub][1])

---

# 2. 它控制的到底是什么？

默认情况下，OpenCode 在 compaction 后会自己发一个**合成的 user message**：

```text
Continue if you have next steps, or stop and ask for clarification if you are unsure how to proceed.
```

也就是说：

```text
原来的任务
     ↓
context 太长
     ↓
compact
     ↓
summary
     ↓
synthetic user message:
"Continue if you have next steps..."
     ↓
Agent 再跑一轮
```

这个 synthetic message **不是用户真的输入的**。

源码还明确给它打了：

```ts
metadata: { compaction_continue: true }
```

并标记：

```ts
synthetic: true
```

而且源码注释特别说明：

> This is not a stable plugin contract and may change or disappear.

([GitHub][1])

所以 `autocontinue` hook 本质上就是：

> **是否允许 OpenCode 创建这个 synthetic continuation turn。**

---

# 3. `enabled: false` 会发生什么？

这是最简单也最重要的一点：

```ts
"experimental.compaction.autocontinue": async (input, output) => {
  output.enabled = false
}
```

那么：

```text
compaction
    ↓
summary 已生成
    ↓
不创建 "Continue..." synthetic message
    ↓
不会自动再跑下一轮
```

也就是说：

### `enabled: false` 不会：

* 取消已经发生的 compaction
* 删除 summary
* 修改 summary
* 阻止 `session.compacted`
* 把 compaction 回滚
* 让 session 报错

它**只阻止 compaction 后面的自动继续 turn**。

Kilo 的官方插件文档也对这个语义做了非常明确的说明：默认会发送 synthetic `"continue"` turn，而这个 hook 可以针对特定 session/provider 禁用它。([Kilo][2])

---

# 4. 为什么默认值是 `true`？

源码直接：

```ts
{ enabled: true }
```

然后插件可以修改：

```ts
output.enabled = false
```

所以它是一个典型的 **gate hook**：

```text
              output.enabled
                    │
          ┌─────────┴─────────┐
          │                   │
        true                false
          │                   │
          ▼                   ▼
   synthetic Continue       不继续
```

而不像上一问的：

```ts
output.context
output.prompt
```

那样是“给数据增加/替换内容”。

---

# 5. 输入参数有哪些？

这是当前源码里非常值得注意的一点。

Hook：

```ts
"experimental.compaction.autocontinue": async (input, output) => {}
```

其中：

```ts
input = {
  sessionID,
  agent,
  model,
  provider,
  message,
  overflow
}
```

源码实际传入的是：

```ts
{
  sessionID: input.sessionID,

  agent: userMessage.agent,

  model: yield* provider.getModel(
    userMessage.model.providerID,
    userMessage.model.modelID
  ),

  provider: {
    source: info.source,
    info,
    options: info.options,
  },

  message: userMessage,

  overflow: input.overflow === true,
}
```

([GitHub][1])

逐个看。

---

## `sessionID`

```ts
sessionID: string
```

当前 session。

它主要用于：

* 判断/记录哪个 session
* 如果你需要进一步通过 SDK 查询 session 状态，可以拿它作为索引

例如：

```ts
if (input.sessionID === someSession) {
  output.enabled = false
}
```

---

## `agent`

```ts
agent: userMessage.agent
```

表示**触发这次 compaction 的原始 user message 所使用的 agent**。

例如：

```text
build
plan
explore
```

或者你的自定义 agent。

所以可以做：

```ts
if (input.agent === "some-special-agent") {
  output.enabled = false
}
```

---

# 6. `model`

这里的 `model` 是一个完整的：

```ts
Provider.Model
```

也就是这次任务使用的模型信息，而不是简单的：

```ts
"claude-opus"
```

这让你可以根据模型做策略：

```ts
if (input.model.providerID === "...") {
   ...
}
```

或者根据模型的 context / capabilities 等属性判断。

---

# 7. `provider`

这个参数比 `model` 更值得关注：

```ts
provider: {
  source: info.source,
  info,
  options: info.options,
}
```

也就是说 hook 可以知道：

```text
provider
 ├─ source
 ├─ info
 └─ options
```

因此它非常适合解决：

> 某些 provider/model 不适合 compaction 后自动继续。

例如社区插件实际就这么使用：

```ts
if (input.overflow) {
  output.enabled = false
}
```

([Kilo][2])

---

# 8. `message`

这是：

```ts
message: userMessage
```

注意它是**触发 compaction 的 user message**，不是 compaction 生成出来的 summary。

所以你可以把它理解成：

```text
message
  ↓
导致这次 compaction 的那条 user message
```

这对于判断任务上下文很有用。

例如：

```ts
if (input.message.agent === "xxx") {
  output.enabled = false
}
```

---

# 9. `overflow`

这个参数非常关键：

```ts
overflow: boolean
```

它表示：

> **这次 compaction 是否是因为 context / provider size overflow 而触发。**

源码：

```ts
overflow: input.overflow === true
```

所以：

```text
overflow = true
```

和：

```text
overflow = false
```

实际上代表两种不同场景。

### overflow = true

```text
模型请求太大
    ↓
触发 compaction
    ↓
compact
    ↓
自动继续
```

OpenCode 甚至有专门的 replay 逻辑处理 overflow 场景。

### overflow = false

可能是：

* 手动 `/compact`
* 其他自动 compaction
* 正常的 context management

所以这个字段特别适合：

```ts
if (input.overflow) {
  output.enabled = false
}
```

即：

> **“如果这是一次被 context overflow 强制打断的 compact，就不要再自动 Continue。”**

---

# 10. 一个非常重要的细节：`autocontinue` 并不是每次 compaction 都会触发

源码里有一个：

```ts
if (replay) {
   ...
}
```

只有：

```ts
if (!replay) {
   plugin.trigger("experimental.compaction.autocontinue", ...)
}
```

才触发这个 hook。([GitHub][1])

也就是说 **overflow 场景下，如果 OpenCode 需要 replay 原来的 user message，就不会走这个 autocontinue hook，而是走专门的 replay 路径。**

这是很容易被只看文档的人忽略的。

可以画成：

```text
compaction 完成
      │
      ▼
 result === "continue" && auto ?
      │
     yes
      │
      ▼
   有 replay ?
    /     \
  yes     no
   │       │
   │       ▼
   │   autocontinue hook
   │       │
   │   enabled ?
   │    /     \
   │  yes     no
   │   │       │
   │   ▼       ▼
   │ Continue  停
   │
   ▼
 replay 原始 user message
```

所以不要简单理解成：

> “每次 compact 完都会调用 `experimental.compaction.autocontinue`。”

**不是。**

---

# 11. 它和 `session.compacted` 到底是什么关系？

这是最值得区分的地方。

## `experimental.compaction.autocontinue`

是：

> **控制流程的 hook**

发生在：

```text
compaction summary 已完成
        ↓
是否自动继续？
```

它可以：

```ts
output.enabled = false
```

改变接下来的行为。

---

## `session.compacted`

是：

> **一个事件**

源码定义：

```ts
export const Event = {
  Compacted: BusEvent.define(
    "session.compacted",
    z.object({
      sessionID: SessionID.zod,
    }),
  ),
}
```

([GitHub][1])

它不让你决定是否继续。

它只是告诉其他消费者：

```text
“这次 compaction 完成了。”
```

---

# 12. 两者的时间关系

当前源码的顺序非常明确：

```text
                Compaction
                    │
                    ▼
             summary generated
                    │
                    ▼
          autocontinue hook
                    │
             ┌──────┴──────┐
             │             │
          enabled        disabled
             │             │
             ▼             │
     create Continue       │
             │             │
             └──────┬──────┘
                    │
                    ▼
          session.compacted
```

更准确地说，源码最后是：

```ts
if (processor.message.error) return "stop"

if (result === "continue")
  yield* bus.publish(Event.Compacted, {
    sessionID: input.sessionID
  })

return result
```

([GitHub][1])

因此：

> **`session.compacted` 是 compaction 流程完成后的通知，而不是 autocontinue 的替代品。**

---

# 13. `enabled: false` 会不会阻止 `session.compacted`？

**不会。**

这是最容易误解的地方。

假设：

```ts
"experimental.compaction.autocontinue": async (input, output) => {
  output.enabled = false
}
```

实际：

```text
compact LLM
   ↓
summary 成功
   ↓
autocontinue
   ↓
enabled = false
   ↓
不创建 Continue
   ↓
session.compacted
   ↓
结束
```

所以：

```text
autocontinue.enabled
       ↓
只影响“是否再跑一轮”

session.compacted
       ↓
仍然可以发生
```

---

# 14. 这两个 hook 最好的理解方式

我建议你把 OpenCode compaction API 理解成三个层次：

```text
① experimental.session.compacting

   “怎么生成 summary？”

       ↓

② experimental.compaction.autocontinue

   “summary 生成后，要不要继续执行？”

       ↓

③ session.compacted

   “刚才的 compaction 已经完成了。”
```

也就是：

| API                                    | 类型    | 时机                               | 能否改变流程             |
| -------------------------------------- | ----- | -------------------------------- | ------------------ |
| `experimental.session.compacting`      | hook  | compact LLM **之前**               | ✅ 改 summary prompt |
| `experimental.compaction.autocontinue` | hook  | compact LLM **之后、Continue 创建之前** | ✅ 禁止自动 Continue    |
| `session.compacted`                    | event | compaction 完成时                   | ❌ 主要是通知            |

---

# 15. 对你正在研究的「长期 Memory / Harness」特别有价值

如果你的目标是给 OpenCode 做一个真正的 persistent memory/harness，我反而认为：

```text
experimental.session.compacting
```

和：

```text
experimental.compaction.autocontinue
```

应该承担完全不同的职责。

### `session.compacting`

负责：

```text
当前 session
     ↓
提取 / 重组
     ↓
重要状态
决策
任务进度
文件状态
用户偏好
下一步
     ↓
summary
```

### `autocontinue`

负责：

```text
compact 后
     ↓
是否允许 Agent 自动继续？
```

比如你检测到：

```text
compact
→ Continue
→ 很快再次 overflow
→ compact
→ Continue
→ overflow
```

形成：

```text
compact → continue → compact → continue → ...
```

这其实就是一个 **compaction storm**。

社区已经出现专门利用 `experimental.compaction.autocontinue` 来打断这种循环的插件。([Socket][3])

因此它更像一个：

> **compaction circuit breaker / continuation gate**

而不是 memory hook。

---

## 最后给你一个非常简洁的源码级结论

当前 `compaction.ts` 的语义可以压缩成：

```ts
// 1. 生成 summary
const result = await compact(...)

// 2. 如果 OpenCode 原本准备继续
if (result === "continue" && input.auto) {

  // 某些 overflow replay 走自己的路径
  if (!replay) {

    // 询问插件：是否允许 synthetic Continue？
    const { enabled } = await plugin.trigger(
      "experimental.compaction.autocontinue",
      {
        sessionID,
        agent,
        model,
        provider,
        message,
        overflow,
      },
      { enabled: true },
    )

    if (enabled) {
      // 创建 synthetic user message
      // "Continue if you have next steps..."
    }
  }
}

// 3. compaction 完成
if (result === "continue") {
  publish("session.compacted", { sessionID })
}
```

所以**最核心的一句话是**：

> `experimental.compaction.autocontinue` 是一个 **“compaction 完成后是否创建 synthetic Continue turn” 的 gate**；`enabled:false` 只取消自动继续，不取消 compaction 本身，也不取消 `session.compacted` 事件。并且它并非所有 compaction 路径都会触发，当前源码中 `replay` 分支会绕过它。 ([GitHub][1])

### 官方/源码入口

* [OpenCode Plugins 官方文档](https://opencode.ai/docs/plugins/?utm_source=chatgpt.com)
* [compaction.ts（核心实现）](https://github.com/sst/opencode/blob/dev/packages/opencode/src/session/compaction.ts?utm_source=chatgpt.com)
* [OpenCode Agents 文档（compaction agent）](https://opencode.ai/docs/agents/?utm_source=chatgpt.com)

其中真正要读懂这个 hook，**最重要的是 `packages/opencode/src/session/compaction.ts`，而不是插件文档**。文档告诉你“能干什么”，源码才揭示了 `result === "continue" && input.auto`、`replay` 分支以及 `session.compacted` 的精确先后关系。 ([GitHub][1])

[1]: https://github.com/sst/opencode/blob/dev/packages/opencode/src/session/compaction.ts?utm_source=chatgpt.com "opencode/packages/opencode/src/session/compaction.ts at dev · anomalyco/opencode · GitHub"
[2]: https://kilo.ai/docs/automate/extending/plugins?utm_source=chatgpt.com "Plugins"
[3]: https://socket.dev/npm/package/hashpress-opencode/overview/0.6.3?utm_source=chatgpt.com "hashpress-opencode - npm Package Security Analysis - Socket"

https://chatgpt.com/s/t_6a7c75e528108191be455eb6043fd478


**Q3**

**Q4**

**Q5**

**Q6**

**Q7**

**Q8**

