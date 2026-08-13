# Round 2 回答：Grok

> 类型: 调研（原始回答归档）
> 调研: 2026-08-12-opencode-compaction-hook
> 说明: 对应 R2-4（hook 异常影响）

#### Grok

## 结论（先说清楚）

在当前实现下，若某个插件在 `experimental.session.compacting` 中**抛出异常或返回 rejected Promise**，该异常会通过 `Plugin.trigger` 以 Effect 失败形式向上传播，**中断本次 compaction**；后续插件钩子不会再执行，总结 LLM 也不会被调用。`Plugin.trigger` 本身**没有** per-hook 兜底；`SessionCompaction.process` 调用处也**没有**针对该 hook 的 `catch` / `ignore`。

---

## 1. `Plugin.trigger` 的实际实现

```ts
// packages/opencode/src/plugin/index.ts
const trigger = Effect.fn("Plugin.trigger")(function* (name, input, output) {
  if (!name) return output
  const s = yield* InstanceState.get(state)
  for (const hook of s.hooks) {
    const fn = hook[name] as any
    if (!fn) continue
    yield* Effect.promise(async () => fn(input, output))  // 无 try/catch
  }
  return output
})
```

关键行为：

| 点 | 说明 |
|----|------|
| 执行方式 | **顺序**、**同步等待**每个 hook |
| 错误包装 | `Effect.promise`：Promise reject / 同步 throw → **Effect 失败** |
| 循环内兜底 | **无**；一旦某个 `fn` 失败，循环立即中断 |
| 后续插件 | **不会**再被调用 |
| 返回值 | 只有全部成功才 `return output` |

对比同文件中其他路径：

- 插件**加载**、`config`、`dispose` 使用 `Effect.tryPromise` + `Effect.tapError` + `Effect.ignore`，失败可吞掉并继续；
- **`trigger` 没有采用同样模式**。

因此：hook 抛错在 `Plugin.trigger` 层是**硬失败**，不是“记日志后继续”。

---

## 2. 对本次压缩的具体影响

调用链：

```text
prompt.ts  (task.type === "compaction")
  → compaction.process(...)
      → plugin.trigger("experimental.session.compacting", ...)
          → 某插件 throw / reject
      → （不会执行）buildPrompt / LLM 总结 / autocontinue / session.compacted
```

源码位置（`packages/opencode/src/session/compaction.ts`）：

```ts
const compacting = yield* plugin.trigger(
  "experimental.session.compacting",
  { sessionID: input.sessionID },
  { context: [], prompt: undefined },
)
const nextPrompt = compacting.prompt ?? buildPrompt(...)  // 抛错时到不了这里
```

影响清单：

1. **总结未生成**：LLM compaction 请求不会发出。  
2. **checkpoint 未完成**：依赖后续步骤写入的 summary / compaction 状态不会按成功路径完成。  
3. **后续插件被跳过**：同一 hook 上排在后面的插件不会执行；`context` / `prompt` 可能只是部分写入（已成功插件的副作用可能已落在共享 `output` 上，但最终不会被使用）。  
4. **auto-continue 不会发生**：`experimental.compaction.autocontinue` 在成功路径更后面，不会触发。  
5. **`session.compacted` 通常不会发出**（该事件在成功完成 compaction 后广播）。  
6. **主循环侧**：`prompt.ts` 对 `compaction.process` 是 `yield* compaction.process(...)`，未在该处单独 catch；Effect 失败会向上冒泡，可能表现为会话错误 / 循环中断（具体取决于更上层的 Effect 运行时与错误上报），而不是“静默跳过压缩继续跑”。

简言之：**一次插件异常 ≈ 本次压缩失败中止**，不是“忽略坏插件、用默认 prompt 继续压”。

---

## 3. 是否有上层兜底？

| 层级 | 是否兜住 compacting 抛错 |
|------|--------------------------|
| `Plugin.trigger` 循环内 | 否 |
| `SessionCompaction.process` 对 `plugin.trigger("…compacting")` | 否（直接 `yield*`） |
| `prompt.ts` 的 compaction 任务分支 | 否（直接 `yield* compaction.process`） |
| 插件加载 / config / dispose | 有（`tryPromise` + `ignore`），与 **trigger 无关** |

因此：**没有针对 `experimental.session.compacting` 的专用上层兜底**。  
这与 `event` 钩子也不同：`event` 用 `void hook["event"]?.(...)` 发起，不阻塞主路径；`trigger` 是关键路径上的 `yield*`。

若自动压缩因 hook 抛错失败，上下文仍可能处于溢出状态，后续可能再次触发压缩或进入错误路径，取决于当时会话状态与错误处理，但**不会**因为该 hook 失败而自动改用“无插件默认压缩”完成一次成功 compaction。

---

## 4. 插件应如何自保

原则：**不要让异常离开钩子函数**。把失败当作“本插件不注入上下文”，让核心继续用默认 prompt 压缩。

推荐写法：

```ts
"experimental.session.compacting": async (input, output) => {
  try {
    // 可能失败的 I/O、解析、状态读取等
    const extra = await loadMyState(input.sessionID)
    if (extra) output.context.push(extra)
  } catch (err) {
    // 记录日志即可，切勿 rethrow
    console.error("[my-plugin] session.compacting failed", err)
    // 可选：通过 client.app.log 做结构化日志
  }
},
```

补充建议：

1. **只改 `output`，不要依赖返回值**（钩子约定是 mutate `output`）。  
2. **避免在钩子里做长时间阻塞**；失败路径要快失败并吞掉。  
3. 若必须区分“可忽略错误”与“应中止压缩”，当前 API **没有**官方 `skip` / `abort` 字段；抛错会中止整次压缩，一般只应在真正希望中止时使用（且需接受对用户不友好）。  
4. 多插件场景下，**你的抛错也会挡住排在后面的插件**；更应本地 try/catch。  
5. 对 `experimental.compaction.autocontinue` 等同为 `Plugin.trigger` 的钩子，同样适用：抛错会打断成功路径上的后续逻辑。

---

## 5. 小结

- `Plugin.trigger` 用裸 `Effect.promise` 顺序执行钩子，**任一插件失败即中断并向上失败**。  
- `experimental.session.compacting` 处于 compaction 关键路径且**无局部 catch**，异常会导致**本次压缩失败中止**。  
- 核心对加载/config/dispose 有容错，对 **trigger 没有对等兜底**。  
- 插件侧应在钩子内 **try/catch 并吞掉可恢复错误**，保证默认压缩仍能进行。

---

### 3. 关键字段说明澄清

1. **`message`**：传入的是压缩完成后刚刚生成并追加到历史记录里的 **Continuation Summary Message** 节点对象，而非压缩前的用户原始消息。
2. **`overflow`**：布尔值（`boolean`），标记本次压缩是否由于 Token 超出模型的 Max Context Limit 强制触发（例如 LLM 抛出 context overflow 错误时为 `true`）。
3. **`enabled`**：在 `autocontinue` 钩子中，只要返回值包含 `{ enabled: false }`，即会触发阻断；若返回空对象 `{}` 或未定义 `enabled`，默认视同允许自动续接。

