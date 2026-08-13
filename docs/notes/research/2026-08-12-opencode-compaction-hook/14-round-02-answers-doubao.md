# Round 2 回答：doubao

> 类型: 调研（原始回答归档）
> 调研: 2026-08-12-opencode-compaction-hook
> 说明: 对应 R2-1/R2-2（字段与 prompt/context 关系）

#### doubao
# ✅ 直接基于 `dev` 分支 `packages/opencode/src/session/compaction.ts`（上游 anomalyco/opencode，原始行号来自上面 raw fetch）

> 
> 下面全部是**源码里 `plugin.trigger` 实参字面量**，不是TS注释/文档推测；同时对齐 `@opencode-ai/plugin` 类型契约。

## 1）`experimental.session.compacting`

### 源码调用位置（compaction.ts）

```
const compacting = yield* plugin.trigger(
  "experimental.session.compacting",
  { sessionID: input.sessionID },  // ✅ input 只有这一个字段
  { context: [], prompt: undefined },
)
```

> 
> ✅ 结论：**`input` 确实只有 `sessionID`，没有 messages / tokenStats / model 等**（我上一轮回答里写的 `tokenStats, messages` 是错误推演，此处纠正）

- Input：`{ sessionID: SessionID }`
- Output：`{ context: string[]; prompt?: string }`

> 
> 类型包 `@opencode-ai/plugin` `hooks.ts` 原始签名（PR#5698 定型、dev 当前未扩input）：

```
"experimental.session.compacting"?: (
  input: { sessionID: string },
  output: { context: string[]; prompt?: string }
) => Promise<void>
```

## 2）`experimental.compaction.autocontinue`

### 源码调用位置（compaction.ts，processCompaction 内部）

```
yield* plugin.trigger(
  "experimental.compaction.autocontinue",
  {
    sessionID: input.sessionID,
    agent: userMessage.agent,
    model: yield* provider.getModel(userMessage.model.providerID, userMessage.model.modelID).pipe(Effect.orDie),
    provider: {
      source: info.source,
      info,
      options: info.options,
    },
    message: userMessage,
    overflow: input.overflow === true,
  },
  { enabled: true }, // ✅ output 只有 enabled: boolean
)
```

> 
> ✅ 结论：
> 
> 
> - input **包含**：`sessionID / agent / model / provider / message / overflow`，和你列出的集合完全吻合
> - output **只有** `enabled`（boolean，默认true），无其他可写字段

### 各input字段字面释义（来自调用传参）

- `sessionID`：会话ID
- `agent`：本次压缩归属agent名字（取自userMessage.agent）
- `model`：Provider.Model 对象（完整模型元数据）
- `provider`：provider 结构体 `{source, info, options}`
- `message`：`userMessage`（压缩父节点user消息）
- `overflow`：boolean，本次压缩是否由溢出触发（`input.overflow` 布尔投影）

## 3）时序重申（从本次精确源码修正版）

1. `experimental.session.compacting`（仅 `{sessionID}`，改context/prompt）
2. 执行摘要LLM生成summary
3. 进入auto-continue判定分支 → **`experimental.compaction.autocontinue`（带完整agent/model/provider/message/overflow输入，仅能写enabled）**
4. 按autocontinue.enabled决定是否注入 synthetic continue 用户消息
5. 派发 `session.compacted` 事件（只读通知）

## 4）关键修正声明（对上一轮回答勘误）

> 
> 之前我写 `experimental.session.compacting` input 包含 `messages,tokenStats,model` —— **这是错的**；dev主干 compaction.ts 里传给该钩子的input字面量**只传了 `{sessionID}`**，没有附加消息/令牌统计，这点必须严格按源码trigger实参为准。

## 5）直接可复制锚点链接（dev分支当前）

[https://github.com/anomalyco/opencode/blob/dev/packages/opencode/src/session/compaction.ts](https://github.com/anomalyco/opencode/blob/dev/packages/opencode/src/session/compaction.ts)

- `experimental.session.compacting` trigger：**约L404**（在 `processCompaction` 内部，select之后、buildPrompt之前）
- `experimental.compaction.autocontinue` trigger：**约L484**（在 `if (!replay)` 块内、合成continue消息之前）

## 一句话极简核对结论

1. ✅ `experimental.session.compacting` input **只有 `sessionID`**
2. ✅ `experimental.compaction.autocontinue` input 确实包含 `sessionID / agent / model / provider / message / overflow`；output **仅有 `enabled`**

如果你需要，我可以把**修正后、完全贴合dev源码**的完整生命周期+多插件覆盖规则重写一版正式文档化摘要，替换掉上一版带错误推演的版本。

#### doubao
# ✅ 直接基于你给出的这一行源码表达式做结论（dev 分支 `packages/opencode/src/session/compaction.ts`）
> ```ts
> nextPrompt = compacting.prompt ?? buildPrompt({ previousSummary, context: compacting.context })
> ```
**核心结论（和这行源码严格对齐）：**
1. 只要插件赋值了 `compacting.prompt`（`output.prompt` 非 `undefined`）→ **`buildPrompt` 完全不会执行** → **`compacting.context` 不会被传入、不会被拼进最终 prompt**
2. 只有当**插件不设置 `output.prompt`（`compacting.prompt === undefined`）**，才会调用 `buildPrompt`，并把 `compacting.context` 传给它渲染进原生压缩提示词
> 👉 **官方文档说「设置 prompt 时 context 被忽略」是符合这行短路逻辑的；我上一轮说「context 仍生效」是错误，在此纠正。**

## 拆解这个 `??` 短路运算符（TypeScript 空值合并）
`a ?? b`：**仅当 `a` 是 `null` / `undefined` 才执行、返回 b；否则直接返回 a，b 分支完全不跑**
- 分支A（插件设置 `output.prompt = "xxx"`）：
  - `compacting.prompt` 有值 → `nextPrompt = "xxx"`
  - `buildPrompt(...)` **不调用**
  - `compacting.context` 根本不会进入 buildPrompt，**直接丢弃、不追加**
- 分支B（插件不碰 `output.prompt`，保持 `undefined`）：
  - 走右侧 `buildPrompt({ previousSummary, context: compacting.context })`
  - buildPrompt 内部会把 `compacting.context` 数组拼进原生压缩模板末尾

## 源码位置锚点（dev 分支 anomalyco/opencode）
文件：`packages/opencode/src/session/compaction.ts`
- 钩子触发：先执行 `plugin.trigger("experimental.session.compacting", {sessionID}, {context:[], prompt:undefined})`（L404 附近）
- 紧接着就是这一行 `nextPrompt = compacting.prompt ?? buildPrompt({ previousSummary, context: compacting.context })`（**L406**，你引用的这行）
- `buildPrompt` 是原生压缩提示词模板渲染函数，**只有进入这个函数，context 才有机会被拼接**

## 和官方文档说法对齐
> 官方文档原文语义：If you supply a custom `prompt`, the `context` array is ignored.
- 本质不是「buildPrompt 拿到 context 但故意不渲染」，而是**短路直接跳过 buildPrompt，context 参数根本没机会被消费**

## 一句话修正之前的错误
> ❌ 旧错误说法：设置 output.prompt 后，context 仍然追加在新prompt后面
> ✅ 源码真实行为：设置 output.prompt → 短路、buildPrompt 不执行 → context 直接丢弃、完全不参与最终摘要提示词

## 插件开发最佳实践（基于这个硬规则）
- 只想追加约束、不改原生模板：**只 push `output.context`，不要赋值 `output.prompt`**
- 一旦你赋值 `output.prompt`，如果你还想带附加上下文，**必须自己在你写的 prompt 字符串里手动拼接 compacting.context 数组内容**（框架不会帮你拼）

如果你需要，我可以把两个钩子（`experimental.session.compacting` / `experimental.compaction.autocontinue`）+ 这行短路逻辑 + 多插件覆盖规则，整理成一份可直接复制进插件文档的权威版本，不再包含推演错误。


