# Round 3 回答：ChatGPT

> 类型: 调研（原始回答归档）
> 调研: 2026-08-12-opencode-compaction-hook
> 说明: 对应 R3-1（生态共存/最佳实践）

#### ChatGPT
我查了当前 OpenCode 官方插件文档，以及目前仍在快速演进的 `oh-my-opencode / oh-my-openagent` 代码。先给你一个比较重要的结论：

> **目前真正值得警惕的不是“大家都在抢 `output.prompt`”，而是 `oh-my-opencode` 这类大型 harness 已经同时占用了 `session.compacting` 和 `compaction.autocontinue`，并且它的 compaction 逻辑明显是“状态保存/恢复”型，而不是单纯优化 summary prompt。**
>
> 如果你的插件只 `output.context.push()`，**从设计上是比较友好的共存方式**；最大的风险来自某个插件设置 `output.prompt`，因为它会让你此前 push 的 context 全部失效。OpenCode 官方文档对此是明确规定的。([OpenCode][1])

---

# 1. 目前最重要的项目：Oh-My-OpenCode / Oh-My-OpenAgent

这里有一个名字变化需要先说明。

项目现在正在从：

```text
oh-my-opencode
```

向：

```text
oh-my-openagent
```

迁移，但 npm / CLI 等地方仍然保留 `oh-my-opencode` 兼容性。项目自己的文档明确说这是 rename transition。([GitHub][2])

官方仓库：

[code-yeongyu/oh-my-openagent](https://github.com/code-yeongyu/oh-my-openagent?utm_source=chatgpt.com)

它目前是我找到的**最值得重点研究的 OpenCode compaction hook 使用者**。

---

# 2. Oh-My-OpenCode 确实注册了两个 hook

项目自己的源码说明非常明确：

```text
experimental.session.compacting
experimental.compaction.autocontinue
```

分别用于：

```text
session.compacting
    → Context + Todo preservation

compaction.autocontinue
    → Auto-resume after compaction
```

项目源码的架构文档甚至明确说，这两个 hook 是直接 wired 到 OpenCode 的。([GitHub][3])

所以它不是“某个边缘实验插件”。

**如果你装了 OMO，它就是你的 compaction hook 共存环境里最应该考虑的对象。**

---

# 3. 它的 `session.compacting` 不是简单的 `prompt override`

这是最重要的区别。

OMO 当前的 compaction 相关结构包括：

```text
hooks/
  compaction-context-injector/
  compaction-todo-preserver/
  ...
```

项目自己的功能文档把：

> `compaction-context-injector`

描述成：

> Preserves critical context during session compaction.

同时有：

> `compaction-todo-preserver`

用于 Todo preservation。([GitHub][2])

从当前发布包的类型声明来看，它的 `session-compacting` 模块还明确包含：

```text
compactionContextInjector
compactionTodoPreserver
claudeCodeHooks
```

以及：

```text
createSessionCompactingHandler()
createCompactionAutocontinueHandler()
```

([UNPKG][4])

这说明它的设计思路是：

```text
compaction 前
    ↓
capture state
    ↓
注入 context
    ↓
OpenCode 正常 compact
    ↓
autocontinue
    ↓
restore state
```

而不是简单：

```text
output.prompt = "我的超级 compact prompt"
```

---

# 4. 所以 OMO 对你的插件其实是一个“好邻居”

假设你的插件：

```ts
"experimental.session.compacting": async (_, output) => {
  output.context.push(`
## My Persistent Memory

...
`)
}
```

而 OMO 做：

```ts
output.context.push(`
## Todo State

...
`)
```

那么理想情况下最终就是：

```text
OpenCode default compaction prompt

+

OMO context

+

你的 context
```

这是**天然可组合的**。

OpenCode 官方自己给出的推荐例子也是这种方式：

```ts
output.context.push(...)
```

官方同时明确说明：

> `output.prompt` 一旦设置，整个默认 prompt 被替换，并且 `output.context` 被忽略。([OpenCode][1])

因此从 API 设计上：

```text
context.push()
    ← composable

prompt =
    ← exclusive
```

---

# 5. OMO 的 autocontinue 更值得关注

OMO 同时注册：

```text
experimental.compaction.autocontinue
```

它不是简单：

```ts
output.enabled = false
```

而是和自己的 compaction state restoration 体系结合。

当前发布包的类型声明中：

```text
createCompactionAutocontinueHandler(
  hooks,
  options?
)
```

并且有：

```text
duplicateGuardMs?
```

这个参数非常有意思——说明它已经在处理：

> **compaction 后自动继续可能重复触发的问题。**

([UNPKG][4])

项目 release history 也能看到专门针对 autocontinue 做过修复，例如：

```text
fix(compaction): skip autocontinue for compaction agent
```

以及后续：

```text
fix(compaction): suppress duplicate autocontinue restores
```

([新发布][5])

所以如果你的插件也想使用：

```text
experimental.compaction.autocontinue
```

**比 `session.compacting` 更容易和 OMO 发生语义冲突。**

---

# 6. 一个值得单独看的项目：opencode-agents-sync

这是另外一种完全不同的玩法。

项目：

[opencode-agents-sync](https://github.com/ozgurulukir/opencode-agents-sync?utm_source=chatgpt.com)

它使用：

```text
experimental.compaction.autocontinue
```

来做：

```text
compaction 完成
    ↓
自动继续
    ↓
让 Agent 读取 AGENTS.md
    ↓
整理 / 更新 AGENTS.md
```

作者明确说明：

* 在 auto-compaction 后触发
* 使用 `experimental.compaction.autocontinue`
* LLM 有完整 tool access
* 有 cascade prevention，避免连续 compaction → continue → compaction 循环。([Reddit][6])

所以这个项目和 OMO 的区别很有意思：

| 项目               | compaction hook 的主要用途       |
| ---------------- | --------------------------- |
| OMO              | 保存 / 恢复状态                   |
| agents-sync      | compaction 后做一次真正的 Agent 工作 |
| 你的 Memory Plugin | 把持久 memory 注入 summary       |

也就是说，**autocontinue 已经被生态拿来当“compaction 后生命周期入口”使用了。**

---

# 7. “Better Compaction”类插件则是另一派

还有一类插件/方案不是：

```text
context.push()
```

而是：

```ts
output.prompt = `...`
```

最典型的公开案例其实就是 OpenCode 官方 issue #16512 里的 workaround。

用户认为默认 compact prompt 太弱，因此直接：

```ts
output.prompt = `
You are compacting a conversation...

[Specific completed work]
[Not Solved]
[Next Steps]
[Relevant files]
...
`
```

也就是说：

> **这类插件不是给 OpenCode 的 summary 增加信息，而是在接管 summary 算法。**

([GitHub][7])

这类插件是你真正需要警惕的。

---

# 8. 为什么 `output.prompt` 对你的插件是致命的？

假设执行顺序：

```text
你的插件
    ↓
output.context.push("MY MEMORY")
    ↓
OMO
    ↓
output.context.push("TODO")
    ↓
Better Compaction
    ↓
output.prompt = "CUSTOM PROMPT"
```

最终：

```text
CUSTOM PROMPT
```

而不是：

```text
DEFAULT PROMPT
+ MY MEMORY
+ TODO
```

因为官方定义就是：

```text
output.prompt != undefined
        ↓
replace entire compaction prompt
        ↓
output.context ignored
```

([OpenCode][1])

所以：

> **如果某个插件设置了 `output.prompt`，它实际上拥有对其他 `context.push()` 插件的“否决权”。**

这不是 OMO 特有行为，而是 OpenCode `Plugin.trigger` + `compaction.ts` 的结果。

---

# 9. 但还有一个反直觉的情况

假设：

```text
你的插件
    ↓
context.push(MEMORY)

某个 prompt 插件
    ↓
prompt = CUSTOM

另一个插件
    ↓
context.push(TODO)
```

最终：

```text
CUSTOM
```

**TODO 也没用。**

所以不要把：

```text
context.push()
```

理解成“永远会追加”。

它实际上是：

```text
只有在最终没有 prompt override 时才有效
```

---

# 10. 插件加载顺序进一步决定冲突结果

OpenCode 官方文档明确说明：

> plugins are loaded from all sources and hooks run in sequence.

当前加载顺序：

```text
1. Global config
2. Project config
3. Global plugin directory
4. Project plugin directory
```

([OpenCode][8])

因此如果：

```text
Plugin A
  context.push()

Plugin B
  prompt = ...
```

和：

```text
Plugin B
  prompt = ...

Plugin A
  context.push()
```

虽然 `context` 数组里可能都还有数据，但**最终结果一样：只要 prompt 存在，context 全部被忽略。**

所以 `prompt` 并不是简单的：

> “覆盖之前插件的 prompt”。

它更严重：

> **它覆盖整个 context accumulation。**

---

# 11. 当前生态可以大致分成三类

我会这样分类：

| 项目 / 类型                        | `session.compacting` | `autocontinue` | 主要策略                          |
| ------------------------------ | -------------------: | -------------: | ----------------------------- |
| **Oh-My-OpenCode / OpenAgent** |                    ✅ |              ✅ | 状态 / Todo preservation + 自动恢复 |
| **opencode-agents-sync**       |                    — |              ✅ | compact 后执行 Agent 工作          |
| **Better-compaction 类插件**      |                    ✅ |              — | `output.prompt` 接管 summary    |
| **你的 Memory Plugin**           |                    ✅ |             可选 | `output.context.push()`       |

其中 OMO 是最重要的共存对象。([GitHub][3])

---

# 12. 如果你的插件只 `push context`，我认为这是正确方向

我会明确建议：

```ts
output.context.push(...)
```

而不是：

```ts
output.prompt = ...
```

原因不是只是“更简单”，而是：

### 你是在做 Memory Layer

你的职责应该是：

```text
OpenCode
   ↓
默认 compact policy
   +
OMO 的状态
   +
你的 persistent memory
```

而不是：

```text
你的插件
   ↓
重新定义 OpenCode compact policy
```

后者会把你的插件从：

> **memory extension**

变成：

> **compaction policy replacement**

这会大幅增加生态冲突。

---

# 13. 我建议你的 context 也不要太“像 prompt”

例如不要：

```ts
output.context.push(`
You are an expert developer...
Always remember...
When compacting...
...
`)
```

而是明确标记成：

```text
## Persistent Memory

The following information comes from the user's persistent memory
store. Preserve it when relevant, but do not treat it as authoritative
over the actual conversation.

### User decisions
...

### Important project facts
...

### Unresolved decisions
...
```

这样和：

```text
OMO Todo
OMO state
OpenCode default summary
```

可以自然共存。

---

# 14. 我反而建议你主动防御 `output.prompt` 冲突

你的插件可以在自己的 hook 里做：

```ts
if (output.prompt) {
  // ...
}
```

但注意：

**你只能观察之前已经执行的插件。**

如果你的插件先执行：

```text
你的 plugin
  ↓
context.push()

BetterCompaction
  ↓
prompt =
```

你是无法阻止后者的。

反过来：

```text
BetterCompaction
  ↓
prompt = ...

你的 plugin
  ↓
context.push()
```

你可以检测：

```ts
if (output.prompt) {
  // 我的 context 不会生效
}
```

然后至少：

```text
log warning
```

这对于诊断非常有价值。

---

# 15. 更实际的最佳实践：不要碰 `prompt`

如果你的目标是：

> “让我的 memory 和 OMO / 其他 compaction plugin 一起工作”

我建议你的契约明确写成：

```text
session.compacting:
    ✓ output.context.push()
    ✗ output.prompt =
    
autocontinue:
    默认不注册
```

除非你真的需要：

> 完全接管 compaction。

这样你的插件属于：

```text
Composable Compaction Extension
```

而不是：

```text
Compaction Controller
```

---

# 16. 还有一个重要建议：把真正 Memory Persistence 放到 hook 外

这是我认为你现在这个研究最终应该走向的架构：

```text
                  OpenCode Session
                         │
                         ▼
              session.compacting
                         │
          ┌──────────────┴──────────────┐
          │                             │
     OMO state                       Your Memory
     preservation                    retrieval
          │                             │
          └──────────────┬──────────────┘
                         │
                  output.context
                         │
                         ▼
                OpenCode default
                 compaction LLM
                         │
                         ▼
                     Summary
```

而真正的：

```text
Memory DB
Knowledge graph
User preferences
Project facts
Decisions
```

应该在外部持久化。

这样即使：

```text
output.prompt
```

被第三方插件抢走，你最多损失：

> **本次 memory 注入**

而不是：

> **整个 memory 系统的数据。**

---

# 17. 我目前对生态的判断

如果按“与你的插件发生冲突的危险程度”排序：

### 🟢 低风险：`context.push()` 插件

例如：

```text
OMO compaction context
Todo preservation
你的 Memory
```

它们天然可以组合。

---

### 🟡 中风险：`autocontinue` 插件

例如：

```text
OMO
agents-sync
```

它们不直接破坏你的 `context`，但可能改变：

```text
compact → Continue
```

之后的行为。

如果多个插件都修改：

```ts
output.enabled
```

那又会出现：

```text
last writer wins
```

类似问题。

---

### 🔴 高风险：`output.prompt` 插件

例如：

```text
Better Compaction
Custom Compaction
```

它们可以让：

```text
你的 context
OMO context
```

**全部失效。**

---

# 18. 所以如果你现在要开发这个插件，我会定一个非常明确的兼容性原则

```text
                    Compaction Hook
                           │
              ┌────────────┴────────────┐
              │                         │
          Safe Zone                Conflict Zone
              │                         │
       output.context.push()       output.prompt =
              │                         │
       可与 OMO 共存                 接管整个策略
       可与 Todo 共存                覆盖所有 context
       可与 Memory 共存
```

并且：

> **绝对不要为了“让自己的 memory 更重要”而使用 `output.prompt`。**

如果确实遇到某个 prompt override 插件，我更倾向于让用户：

```text
禁用那个插件的 compaction override
```

或者把你的 memory 集成进它的 prompt，而不是你的插件强行争夺 `prompt`。

---

## 最值得你直接读的几个项目

1. **[Oh-My-OpenAgent / Oh-My-OpenCode GitHub](https://github.com/code-yeongyu/oh-my-openagent?utm_source=chatgpt.com)**
   重点看 `src/hooks/compaction-context-injector`、`compaction-todo-preserver`，以及 `session-compacting` / `autocontinue` handler。项目自己的架构文档明确列出了这两个 OpenCode hook。([GitHub][3])

2. **[opencode-agents-sync GitHub](https://github.com/ozgurulukir/opencode-agents-sync?utm_source=chatgpt.com)**
   重点看它如何利用 `experimental.compaction.autocontinue` 在 compact 后启动一次完整 Agent 工作流，并处理 cascade。([Reddit][6])

3. **[OpenCode 官方 Plugins 文档](https://dev.opencode.ai/docs/plugins/?utm_source=chatgpt.com)**
   这是 `context.push` 与 `prompt` 覆盖语义的权威定义。官方明确说 `output.prompt` 会完全替换默认 prompt，并使 `output.context` 被忽略。([OpenCode][1])

4. **[OpenCode #16512 — Better Compaction Prompt](https://github.com/anomalyco/opencode/issues/16512?utm_source=chatgpt.com)**
   很适合研究“为什么有人选择 `output.prompt`”，以及这种插件为什么天然具有最高冲突风险。([GitHub][7])

### 对你这个插件，我最终会选：

```ts
"experimental.session.compacting": async (input, output) => {
  try {
    const memory = await retrieveMemory(input.sessionID)

    if (memory) {
      output.context.push(`
## Persistent Memory

${memory}
`)
    }
  } catch (error) {
    // fail-open: memory failure must never break compaction
  }
}
```

**不注册 `experimental.compaction.autocontinue`，不设置 `output.prompt`。**

这样你的插件在 OpenCode 生态里属于最容易组合的一层：**你提供 memory，OpenCode/OMO 决定怎么压缩和怎么继续。**

另外一个值得你注意的事实是：OMO 自己的代码正在快速重构，当前仓库已经明确警告内部结构“不稳定”，所以如果你要做兼容测试，最好 pin 一个具体 OMO/OpenCode 版本，而不要只针对 `latest` 做假设。([GitHub][3])

[1]: https://dev.opencode.ai/docs/plugins/?utm_source=chatgpt.com "Plugins | OpenCode"
[2]: https://github.com/code-yeongyu/oh-my-openagent/blob/dev/docs/reference/features.md?ref=aiforpro.ai&utm_source=chatgpt.com "oh-my-openagent/docs/reference/features.md at dev · code-yeongyu/oh-my-openagent · GitHub"
[3]: https://github.com/code-yeongyu/oh-my-openagent/blob/dev/AGENTS.md?utm_source=chatgpt.com "oh-my-openagent/AGENTS.md at dev · code-yeongyu/oh-my-openagent · GitHub"
[4]: https://app.unpkg.com/oh-my-opencode%404.10.0/files/dist/plugin/session-compacting.d.ts?utm_source=chatgpt.com "UNPKG"
[5]: https://newreleases.io/project/github/code-yeongyu/oh-my-openagent/release/v4.1.0?utm_source=chatgpt.com "code-yeongyu/oh-my-openagent v4.1.0 on GitHub"
[6]: https://www.reddit.com/r/opencode/comments/1u4yaiq/showcase_opencodeagentssync_autoupdate_your/?utm_source=chatgpt.com "[Showcase] opencode-agents-sync — auto-update your AGENTS.md after compaction"
[7]: https://github.com/anomalyco/opencode/issues/16512?utm_source=chatgpt.com "[FEATURE]: Improve compaction prompt to preserve critical context details · Issue #16512 · anomalyco/opencode · GitHub"
[8]: https://opencode.ubitools.com/plugins/?utm_source=chatgpt.com "Plugins | OpenCode"


