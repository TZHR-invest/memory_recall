# Round 2 回答：ChatGPT

> 类型: 调研（原始回答归档）
> 调研: 2026-08-12-opencode-compaction-hook
> 说明: 对应 R2-4（hook 异常影响）

#### ChatGPT

是的，你抓到的这个点很关键。**`Plugin.trigger()` 本身没有针对 hook 异常做隔离；因此 `experimental.session.compacting` 某个插件如果直接 throw，这个异常会作为 Effect failure 向上冒泡，原则上会让本次 compaction 失败。**

但这里要区分两件事：

1. **`Plugin.trigger` 有没有兜底？——没有。**
2. **OpenCode 更上层有没有把整个 compaction failure 吃掉？——不能把它理解成有一个“插件异常专用兜底”；最终会进入 compaction / prompt 的错误处理路径，而不是继续正常压缩。**

我把调用链拆开。

---

## 1. `Plugin.trigger()` 的真实语义

当前源码：

```ts
const trigger = Effect.fn("Plugin.trigger")(function* (...) {
  if (!name) return output

  const s = yield* InstanceState.get(state)

  for (const hook of s.hooks) {
    const fn = hook[name] as any
    if (!fn) continue

    yield* Effect.promise(async () => fn(input, output))
  }

  return output
})
```

[Plugin.trigger 源码](https://github.com/anomalyco/opencode/blob/dev/packages/opencode/src/plugin/index.ts?utm_source=chatgpt.com)

关键是：

```ts
yield* Effect.promise(async () => fn(input, output))
```

没有：

```ts
try {
  ...
} catch {
  ...
}
```

也没有：

```ts
Effect.catch(...)
```

因此：

```text
plugin hook
   │
   │ throw Error
   ▼
Promise reject
   │
   ▼
Effect.promise failure
   │
   ▼
Plugin.trigger failure
```

而不是：

```text
plugin hook
   │
   │ throw
   ▼
log error
   │
   ▼
继续执行下一个 plugin
```

**所以一个 hook 抛异常，会中断 `for` 循环。**

---

# 2. 多插件场景尤其值得注意

假设：

```ts
Plugin A → 正常
Plugin B → throw
Plugin C → 正常
```

执行：

```text
A
 ↓
B → throw
 ↓
trigger 失败
```

**C 不会执行。**

因为：

```ts
for (const hook of s.hooks) {
    ...
    yield* Effect.promise(...)
}
```

是串行的。

所以 `Plugin.trigger()` 的错误语义实际上是：

> **fail-fast，而不是 best-effort。**

这和你上一问得到的：

> `context` 累加、`prompt` last-writer-wins

组合起来，就意味着这个 hook 本身是一个相当“强侵入性”的扩展点。

---

# 3. 放到 `session.compacting` 里面，会发生什么？

关键调用在：

```ts
const compacting = yield* plugin.trigger(
  "experimental.session.compacting",
  { sessionID: input.sessionID },
  { context: [], prompt: undefined },
)
```

它位于：

```text
processCompaction()
   │
   ├─ 找 parent
   ├─ 处理 overflow/replay
   ├─ 找 compaction model
   ├─ select history
   │
   ▼
Plugin.trigger(
  "experimental.session.compacting"
)
   │
   ▼
构造 compaction prompt
   │
   ▼
调用 compaction LLM
```

[compaction.ts 源码](https://github.com/sst/opencode/blob/dev/packages/opencode/src/session/compaction.ts?utm_source=chatgpt.com)

因此如果插件：

```ts
"experimental.session.compacting": async (input, output) => {
  throw new Error("boom")
}
```

那么执行根本到不了：

```ts
const defaultPrompt = ...
const prompt = ...
```

更不会到：

```ts
processor.process(...)
```

也就是说：

> **compaction LLM 根本不会被调用。**

这点非常重要。

---

# 4. 所以不是“summary 生成失败”，而是“compaction 尚未开始就失败”

时间线上：

```text
正常 Agent
    │
    ▼
检测到需要 compact
    │
    ▼
processCompaction()
    │
    ├─ history selection
    │
    ▼
experimental.session.compacting
    │
    └── Plugin B throw ❌
             │
             ▼
        Effect failure
             │
             ▼
       processCompaction 失败
             │
             X
       compaction LLM
       没有执行
```

因此不要把这个异常理解成：

> “summary 模型生成了一个坏 summary”。

实际上：

> **summary 根本没有生成。**

---

# 5. `session.compacted` 会不会发？

**不会。**

这是另一个非常关键的后果。

当前代码最后才有：

```ts
if (processor.message.error) return "stop"

if (result === "continue") {
  yield* bus.publish(Event.Compacted, {
    sessionID: input.sessionID
  })
}

return result
```

所以正常情况下：

```text
compaction LLM
   ↓
result = continue
   ↓
session.compacted
```

而插件在前面就 throw：

```text
plugin hook
   ↓
throw
   ↓
processCompaction failure
   ↓
没有 result
   ↓
没有 session.compacted
```

所以：

**`session.compacted` 不是 finally 类型的通知。**

它不是：

```ts
try {
  compact()
} finally {
  publish("session.compacted")
}
```

而是：

```ts
const result = compact()

if (result === "continue") {
  publish("session.compacted")
}
```

这两者语义完全不同。

---

# 6. 有没有“上层兜底”？

这里要谨慎说：

### 有上层错误处理机制，但不是针对 Plugin Hook 的专门 fallback。

OpenCode 大量使用 Effect。

因此：

```text
Plugin.trigger
      │
      ▼
Effect failure
      │
      ▼
processCompaction failure
      │
      ▼
调用它的 prompt/session execution
      │
      ▼
更上层的 Effect error handling
```

会进入 OpenCode 自己的错误处理/消息状态机制，而不是 Node.js 进程简单地因为一个 Promise rejection 直接裸崩。

但这个机制的目的主要是：

> **把 agent/session 执行错误转化为 OpenCode 的错误状态。**

不是：

> **“插件坏了没关系，继续执行 compaction。”**

所以从插件作者角度，千万不要因为 OpenCode 使用 Effect，就认为：

```ts
throw new Error(...)
```

会被 OpenCode 自动隔离。

**不会。**

---

# 7. 这和 `processor.process()` 的错误处理要区分

这里很容易被源码里的 `catch` 混淆。

`packages/opencode/src/session/processor.ts` 的确有比较完整的：

```text
retry
catch
cleanup
```

之类机制。

但：

```text
Plugin.trigger()
```

发生在：

```text
processor.process()
```

**之前**。

`session.compacting` 的调用点是在：

```ts
processCompaction()
```

内部。

所以不能用：

> “processor 有 catch，所以 plugin throw 没事。”

来推断。

更准确的是：

```text
                    prompt/session
                         │
                         ▼
                  processCompaction
                         │
             ┌───────────┴───────────┐
             │                       │
       plugin.trigger            processor.process
             │                       │
             │                       ├─ retry/catch
             │                       └─ cleanup
             │
             └─ Effect.promise
                  │
              hook throw
                  │
                  ▼
             failure 向上
```

也就是说，**插件异常和 compaction LLM 异常处在不同的位置。**

---

# 8. 一个更隐蔽的问题：`Effect.promise` 只负责“把 Promise 转成 Effect”

这句：

```ts
Effect.promise(async () => fn(input, output))
```

不要理解成：

> “Effect.promise 会保护这个 Promise。”

它真正做的是：

```text
Promise
   ↓
Effect
```

如果 Promise：

```ts
Promise.reject(error)
```

那么 Effect：

```text
Effect.fail(error)
```

所以：

```ts
async () => {
  throw new Error("boom")
}
```

本质上就是：

```text
Promise rejection
      ↓
Effect failure
```

而不是：

```text
Promise rejection
      ↓
Effect.catch
```

必须显式加：

```ts
Effect.tryPromise({
  try: ...,
  catch: ...
})
```

或者：

```ts
yield* Effect.promise(...).pipe(
  Effect.catch(...)
)
```

才是真正的错误隔离。

---

# 9. 插件应该如何自保？

我的建议非常明确：

## **Plugin hook 最外层一定要自己 catch。**

尤其是：

```ts
experimental.session.compacting
```

这种**位于核心控制流上的 hook**。

例如：

```ts
export const MyPlugin = async () => ({
  "experimental.session.compacting": async (input, output) => {
    try {
      const memory = await buildMemory(input.sessionID)

      if (memory) {
        output.context.push(memory)
      }
    } catch (error) {
      console.error("[my-plugin] compaction hook failed", error)

      // 不要 throw
    }
  },
})
```

这样：

```text
memory plugin failure
        │
        ▼
    log error
        │
        ▼
hook 正常返回
        │
        ▼
OpenCode 继续
        │
        ▼
default compaction
```

这是我认为目前最稳妥的策略。

---

# 10. 尤其不要这样写

```ts
"experimental.session.compacting": async (input, output) => {
  const memory = await fetchMemoryFromDatabase(input.sessionID)

  output.context.push(memory)
}
```

因为这里至少有：

```text
DB failure
network failure
JSON parse failure
filesystem failure
SDK failure
unexpected null
```

任何一个：

```ts
throw
```

都会把 OpenCode 的 compact 流程一起拖进去。

---

# 11. 更好的设计：Fail Open

对于这种 hook，我建议采用：

> **Fail Open，而不是 Fail Closed。**

也就是：

```text
插件成功
  → 注入 memory
  → compact

插件失败
  → 记录错误
  → 不注入 memory
  → 仍然 compact
```

而不是：

```text
插件失败
  → 阻止 compact
  → session 卡住
```

因为 memory plugin 的价值是：

```text
提升 compaction quality
```

而不是：

```text
compaction 的必要依赖
```

---

# 12. 如果你的插件本身有多个阶段，更应该隔离

例如你以后做一个：

```text
OpenCode Memory Plugin
```

可能会：

```text
session.compacting
      │
      ├─ 读取 memory DB
      ├─ 查询 session
      ├─ semantic search
      ├─ LLM extraction
      ├─ 构造 context
      └─ output.context.push()
```

不要：

```ts
async (...) => {
  const x = await step1()
  const y = await step2()
  const z = await step3()

  output.context.push(z)
}
```

而应该：

```ts
async (...) => {
  try {
    const z = await buildCompactionContext(...)

    output.context.push(z)
  } catch (error) {
    logError(error)

    // fail open
  }
}
```

甚至进一步：

```text
hook
 │
 ├── timeout
 ├── error boundary
 ├── output validation
 └── size limit
```

---

# 13. 我甚至建议加 timeout

因为这里还有一个比 throw 更隐蔽的问题：

> **插件不 throw，但一直不 resolve。**

例如：

```ts
await fetch(...)
```

网络连接卡死。

那么：

```text
Plugin.trigger
    ↓
await plugin
    ↓
一直 pending
    ↓
compaction 一直 pending
```

这甚至比 throw 更糟。

因此一个可靠插件应该：

```ts
const result = await Promise.race([
  buildMemory(),
  timeout(3000),
])
```

超时：

```text
timeout
  ↓
log
  ↓
return
  ↓
OpenCode继续 compact
```

---

# 14. 还要限制 `output.context` 的大小

这个是你做 Memory Plugin 时尤其值得注意的。

假设：

```ts
output.context.push(await hugeMemoryDump())
```

插件本身没有 throw。

但是：

```text
plugin 正常
   ↓
context = 80k tokens
   ↓
compact prompt
   ↓
compaction model context overflow
```

于是你从：

> plugin exception

变成：

> plugin-induced compaction failure

所以自保策略应该包括：

```text
┌──────────────────────────┐
│ Compaction Hook          │
├──────────────────────────┤
│ try/catch                │
│ timeout                  │
│ output size limit        │
│ null/undefined handling  │
│ logging                  │
└──────────────────────────┘
```

---

# 15. 如果多个插件同时存在，风险会叠加

结合你上一问的结论：

```text
Plugin A
   ↓
Plugin B
   ↓
Plugin C
```

`trigger()` 是：

```ts
for (...) {
  yield* Effect.promise(...)
}
```

所以：

```text
A throw
 ↓
B/C 都不会运行
```

因此一个“第三方 memory plugin”如果写得不好，不只是：

> 它自己的功能坏了。

而是：

> **它可以阻断其他插件的 `session.compacting` hook。**

甚至最终阻断 OpenCode compaction。

这就是为什么我认为这个 hook 当前的插件隔离性其实比较弱。

---

# 16. 这也解释了为什么我不建议把核心能力放在一个 hook 上

如果你的目标是：

> OpenCode + 长期 Memory / Harness

我会设计成：

```text
                 OpenCode
                    │
                    ▼
       experimental.session.compacting
                    │
              ┌─────┴─────┐
              │           │
          Memory      normal default
          Plugin       compaction
              │
          try/catch
          timeout
          size limit
              │
              ▼
          context.push()
```

**Memory 是 enhancement，不是 dependency。**

这样即使：

```text
Memory DB 挂了
embedding 服务挂了
SQLite 锁了
LLM extraction 超时
```

OpenCode 仍然可以：

```text
正常 compact
```

只是这一次没有额外 memory。

---

## 最终结论

你看到的：

```ts
yield* Effect.promise(async () => fn(input, output))
```

确实意味着一个重要事实：

> **`Plugin.trigger()` 对插件 hook 是 fail-fast 的；它不会自动 catch 单个插件异常，也不会跳过失败插件继续执行后续插件。**

对于 `experimental.session.compacting`：

```text
plugin throw
    ↓
Plugin.trigger 失败
    ↓
processCompaction 失败
    ↓
compaction LLM 不会调用
    ↓
本次 compaction 不会成功完成
    ↓
session.compacted 不会正常发布
```

上层 Effect/runtime **有错误处理机制，但不是“插件异常隔离器”**；它不会把这个 hook 的失败转换成“忽略插件、继续 compact”。

所以插件作者的最佳实践应该是：

> **对位于核心控制流的 hook 自己建立 error boundary，并采用 fail-open：异常/超时/非法输出 → log + return，让 OpenCode 使用默认行为继续。**

官方源码入口：

* [Plugin.trigger：packages/opencode/src/plugin/index.ts](https://github.com/anomalyco/opencode/blob/dev/packages/opencode/src/plugin/index.ts?utm_source=chatgpt.com)
* [Compaction：packages/opencode/src/session/compaction.ts](https://github.com/anomalyco/opencode/blob/dev/packages/opencode/src/session/compaction.ts?utm_source=chatgpt.com)
* [相关 pre-compact 设计讨论 #24958](https://github.com/anomalyco/opencode/issues/24958?utm_source=chatgpt.com)

另外，源码里已经存在不少 compaction 本身失败的实际 issue，这也说明不要把“compaction 有上层错误处理”理解成“compaction 一定会自动恢复”。例如 context 超过模型限制导致 compact 失败的 issue #17340。([github.com][1])

[1]: https://github.com/anomalyco/opencode/issues/17340?utm_source=chatgpt.com "Session compaction fails with \"context exceeds model limit\" error · Issue #17340 · anomalyco/opencode · GitHub"


