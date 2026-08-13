# Round 1 回答：Grok

> 类型: 调研（原始回答归档）
> 调研: 2026-08-12-opencode-compaction-hook
> 说明: 对应 Q1/Q2；原文粘贴，未概括

### Grok

**Q1**

基于 OpenCode 官方文档与源码，对 `experimental.session.compacting` 插件钩子的能力梳理如下。

## 1. 触发时机

该钩子在**会话压缩（compaction）真正开始、LLM 生成 continuation summary 之前**触发。

- 调用点位于 `packages/opencode/src/session/compaction.ts`：在完成历史消息筛选（`select`）之后、构建最终 compaction prompt 并送入 processor 之前，通过 `plugin.trigger("experimental.session.compacting", ...)` 调用。
- 官方文档描述：*“The `experimental.session.compacting` hook fires before the LLM generates a continuation summary.”*
- 适用场景包括自动压缩（上下文溢出预检触发）与手动压缩（如 `/compact`、`/summarize` 或 API 调用）。

钩子签名（类型定义）：

```ts
"experimental.session.compacting"?: (
  input: { sessionID: string },
  output: { context: string[]; prompt?: string },
) => Promise<void>
```

源码路径：
- 类型定义：`packages/plugin/src/index.ts`（Hooks 接口）
- 调用逻辑：`packages/opencode/src/session/compaction.ts`（约第 379–384 行）

## 2. `output.context` 与 `output.prompt` 的区别与优先级

| 字段 | 行为 | 优先级 |
|------|------|--------|
| `output.context: string[]` | 向**默认** compaction prompt 追加额外上下文字符串 | 较低 |
| `output.prompt?: string` | 若被设置，**完全替换**默认 prompt | 最高 |

具体逻辑（源码）：

```ts
const compacting = yield* plugin.trigger(
  "experimental.session.compacting",
  { sessionID: input.sessionID },
  { context: [], prompt: undefined },
)
const nextPrompt = compacting.prompt ?? buildPrompt({ previousSummary, context: compacting.context })
```

- 当 `output.prompt` 有值时：直接使用该字符串，**忽略** `output.context`。
- 当 `output.prompt` 未设置时：使用默认 prompt（由 `buildPrompt` 生成，会纳入 `previousSummary` 与 `context`），并将 `context` 数组中的字符串追加进去。

官方文档明确说明：

> When `output.prompt` is set, it completely replaces the default compaction prompt. The `output.context` array is ignored in this case.

典型用法：

- 仅注入领域状态（swarm 协调、文件预留、任务状态等）→ 使用 `output.context.push(...)`。
- 完全重写总结指令（多代理续写提示等）→ 设置 `output.prompt`。

## 3. 多个插件同时注册时的合并 / 覆盖规则

OpenCode 的插件触发机制是**共享同一个 `output` 对象、按加载顺序顺序执行**：

```ts
// packages/opencode/src/plugin/index.ts
for (const hook of s.hooks) {
  const fn = hook[name]
  if (!fn) continue
  await fn(input, output)   // 同一 output 对象被依次传入
}
return output
```

因此：

- **`context`**：所有插件对 `output.context` 的 `push` 会累积（append-only 合并）。后加载的插件看到的是已包含先前插件追加内容的数组。
- **`prompt`**：后执行的插件若设置 `output.prompt`，会覆盖先前插件设置的值。最终以**最后一个**设置了 `prompt` 的插件为准。
- 插件加载顺序（文档）：全局 config → 项目 config → 全局 plugin 目录 → 项目 plugin 目录。同一名称 npm 包去重；本地与 npm 同名则都会加载。

注意：若某个插件设置了 `prompt`，后续插件即使只操作 `context`，该 `context` 最终也会被忽略（因为最终选择了 `prompt` 分支）。

## 4. `experimental.` 前缀带来的兼容性风险

- 钩子以 `experimental.` 开头，明确标记为实验性 API。
- 官方与社区文档均提示：API **可能在未来版本变更**，不保证稳定契约。
- 设计意图（来自引入 PR 讨论）：先以实验性形式发布，收集真实用例后再决定是否升格为稳定钩子（例如最初仅支持 append，后续才增加 `prompt` 全量替换）。
- 实际风险包括：
  - 签名、字段名或行为变更；
  - 被重命名或移除；
  - 与其他实验钩子（如 `experimental.chat.messages.transform`、`experimental.compaction.autocontinue`）的交互方式调整。

建议：在生产插件中做好版本兼容判断，或关注 changelog；若依赖强，可考虑在本地锁定 OpenCode 版本。

## 5. 官方文档与关键源码路径

**官方文档**

- Plugins 文档（含 Compaction hooks 小节）：https://opencode.ai/docs/plugins/  
- Compaction 总体说明：https://opencode.ai/v2/docs/compaction  

**源码路径**

| 内容 | 路径 |
|------|------|
| 钩子类型定义 | `packages/plugin/src/index.ts`（`Hooks` 接口中的 `experimental.session.compacting`） |
| 触发与 prompt 组装 | `packages/opencode/src/session/compaction.ts` |
| 插件触发实现（顺序执行、共享 output） | `packages/opencode/src/plugin/index.ts`（`Plugin.trigger`） |
| 文档源 | `packages/web/src/content/docs/plugins.mdx` |

**相关历史 PR**

- 初始引入（append context）：https://github.com/anomalyco/opencode/pull/5698  
- 支持 `output.prompt` 全量替换：https://github.com/anomalyco/opencode/pull/5907  

以上为当前（dev 分支）实现下的完整能力边界。

**Q2**

基于源码与类型定义，`experimental.compaction.autocontinue` 的完整语义如下。

## 钩子签名

```ts
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

类型定义见：`packages/plugin/src/index.ts`。

## 触发时机

该钩子在 **compaction 已成功完成、准备插入合成“继续”用户消息之前** 触发。

具体位置在 `packages/opencode/src/session/compaction.ts` 的 `process` 流程中：

1. 执行 LLM 总结（compaction summary）
2. 写回 checkpoint / 相关消息
3. 若不是 replay 路径，则调用  
   `plugin.trigger("experimental.compaction.autocontinue", …, { enabled: true })`
4. 若最终 `output.enabled === true`，再创建合成 user 消息并写入 continue 文本

官方注释原文：

> Called after compaction succeeds and before a synthetic user auto-continue message is added.

注意：

- 仅在 compaction **成功** 之后才会走到该钩子；
- 历史上曾限制为仅在 `auto: true`（自动压缩）时插入 continue；当前实现以钩子结果为准，由插件决定是否继续；
- 若存在 overflow 恢复后的 **replay** 路径，源码中 `if (!replay)` 会跳过该钩子（不插入合成 continue，而由 replay 逻辑处理）。

## `enabled: false` 的效果

默认 `output.enabled = true`。

若插件将其设为 `false`：

- **不会**创建合成的 user “continue” 消息；
- 会话在 compaction 结束后停留在 summary 状态，**不会**自动再跑一轮 assistant 续写；
- 需要用户手动输入，或由其他插件（例如 goal / auto-continue 类插件）自行决定后续 prompt。

典型用例：目标驱动插件在有活跃 goal 时关闭内置 continue，避免与自身的续写逻辑抢跑。

## 输入参数含义

| 字段 | 含义 |
|------|------|
| `sessionID` | 当前会话 ID |
| `agent` | 触发 compaction 时关联的 agent 名称（来自 parent user message） |
| `model` | 当前使用的模型信息 |
| `provider` | Provider 上下文（`source`、`info`、`options`） |
| `message` | 触发 compaction 的那条 **user** 消息（parent） |
| `overflow` | 是否因 context overflow（含大附件等）触发的恢复压缩 |

当 `overflow === true` 时，若仍允许 auto-continue，合成文本会额外带上关于附件过大、已压缩并移除 media 的说明，再接上默认 continue 提示。

## 默认合成 continue 文本

当 `enabled` 保持为 `true` 时，系统会插入一条 **synthetic** user 文本，大致为：

- 普通情况：  
  `"Continue if you have next steps, or stop and ask for clarification if you are unsure how to proceed."`
- overflow 情况：在上述内容前追加关于 media 过大、已压缩并建议缩小附件的说明。

该 part 带有 `synthetic: true`，并可能带有内部元数据 `metadata: { compaction_continue: true }`（源码注释标明这不是稳定插件契约，可能变更或移除）。

## 与 `session.compacted` 事件的关系

两者处于 **同一 compaction 生命周期的不同阶段**，职责不同：

| 机制 | 类型 | 时机 | 作用 |
|------|------|------|------|
| `experimental.compaction.autocontinue` | **同步钩子**（可改 `output`） | compaction **成功后、插入 continue 消息前** | 决定是否自动续写 |
| `session.compacted` | **事件**（通知） | compaction **完成后**对外广播 | 通知 UI / 插件“压缩已完成” |

关系可概括为：

1. Compaction 总结生成并落库成功；
2. 触发 `experimental.compaction.autocontinue`（可拦截合成 continue）；
3. 视结果决定是否插入 continue 消息；
4. 对外发出 `session.compacted`（payload 通常含 `sessionID`），供 UI 与插件做后续反应（例如重新注入 skills、记录时间戳、全量同步会话存储等）。

`session.compacted` **不能**控制是否 auto-continue；它只是完成通知。  
若要阻止内置 continue，必须使用 `experimental.compaction.autocontinue` 并将 `enabled` 设为 `false`。

## 多插件时的合并规则

与其他 `(input, output)` 钩子相同：所有注册该钩子的插件按加载顺序共享同一个 `output` 对象。后执行的插件可以覆盖先前插件对 `enabled` 的设置；最终以最后一个写入的值为准。

## 相关源码路径

- 类型定义：`packages/plugin/src/index.ts`
- 调用逻辑：`packages/opencode/src/session/compaction.ts`（`experimental.compaction.autocontinue` 触发处）
- 引入提交：`feat: add experimental.compaction.autocontinue hook…`（commit `34e2429`）

该钩子同样带有 `experimental.` 前缀，API 可能在未来版本变更，生产插件应做好兼容准备。

**Q3**

**Q4**

**Q5**

**Q6**

**Q7**

**Q8**

