# Round 3 回答：Grok

> 类型: 调研（原始回答归档）
> 调研: 2026-08-12-opencode-compaction-hook
> 说明: 对应 R3-1（生态共存/最佳实践）

#### Grok
以下基于公开文档、npm 说明与源码引用，梳理会触及 `experimental.session.compacting` / `experimental.compaction.autocontinue` 的已知项目，以及与“只 push `context`”插件的共存要点。

---

## 核心规则（共存的前提）

最终 prompt 选择逻辑为：

```ts
const nextPrompt = compacting.prompt ?? buildPrompt({ previousSummary, context: compacting.context })
```

因此：

| 行为 | 效果 |
|------|------|
| 仅 `output.context.push(...)` | 与其他 context 累积，追加到默认 prompt |
| 任一插件设置 `output.prompt` | **整段替换**默认 prompt；**全部 `context` 被忽略**（含你的 push） |
| 多个插件都设 `prompt` | **后执行者覆盖**先执行者（按插件加载顺序） |

---

## 已知会注册相关钩子的项目

### A. 使用 `experimental.session.compacting`

#### 1. Oh-My-OpenCode（`oh-my-opencode`）

- 链接：https://github.com/code-yeongyu/oh-my-opencode  
- 相关：`src/hooks/compaction-context-injector/`（见 PR #1557）  
- **行为**：**`output.context.push(...)`**，注入结构化总结要求（User Requests、Final Goal、Work Completed、Remaining Tasks、Active Working Context 等）。  
- **不设** `output.prompt`（至少在公开的 injector 实现中为 append 模式）。  
- 另有 **preemptive compaction**、DCP 等，走配置/内部逻辑，不是这两个实验钩子本身。

#### 2. opencode-goal-plugin / `@prevalentware/opencode-goal-plugin`

- 链接：https://www.npmjs.com/package/opencode-goal-plugin  
- **compacting**：向 compaction **注入 goal 摘要**（objective、status、budget、checkpoints 等），文档描述为注入 compaction context，属于 **context 向**（保活 goal 状态）。  
- **autocontinue**：有活跃 goal 时 **关闭** OpenCode 内置合成 continue（`enabled: false`），避免与插件自身 idle 续写抢跑。

#### 3. hashpress-opencode

- 链接：https://npm.io/package/hashpress-opencode  
- **compacting**：**设置 `output.prompt`** 为分段 prose（Goal / Where you are / What shipped / What remains / Constraints / Paths…），并在后续压缩中合并上一轮 summary。  
- **autocontinue**：短窗口内多次 compact 后 **关闭** 合成 continue，打断 overflow→compact→continue 风暴。  
- **对你的影响**：若与你同装，且它设了 `prompt`，**你的 `context` 会被忽略**。

#### 4. opencode-plugin-compaction-prompt

- 链接：https://npm.io/package/opencode-plugin-compaction-prompt  
- 明确使用 `experimental.session.compacting`，按配置自定义压缩策略（`memoryFile`、`mode: append` 等）。  
- 名称与文档指向“自定义 compaction prompt”；`mode: "append"` 暗示可走追加路径，但**仍可能写入完整 prompt**。与“只 push context”并存时，需按版本核对源码是否设 `output.prompt`。

#### 5. opencode-swarm 系（钩子设计动机）

- 引入 PR：https://github.com/anomalyco/opencode/pull/5698  
- 设计用例：多代理 swarm（beads、mail、文件预留）在压缩时 **`output.context.push`** 注入协调状态。  
- 后续 PR #5907 才增加 `output.prompt` 全量替换能力。

#### 6. session-learn / oc-tweaks 类（社区文档）

- DeepWiki 等文档记载 `compactionPlugin`、`autoMemoryPlugin` 注册 `experimental.session.compacting`，向总结提示注入语言/风格偏好或 memory checkpoint reminder，倾向 **context append**。

#### 7. `@comfanion/usethis_compaction`

- 链接：https://www.npmjs.com/package/@comfanion/usethis_compaction  
- 描述为 agent-aware 的 session compaction 定制；具体是 context 还是 prompt 需查包内实现，但明确属于 compaction 定制类插件。

---

### B. 使用 `experimental.compaction.autocontinue`

| 项目 | 行为 |
|------|------|
| **opencode-goal-plugin** | 活跃 goal 时 `enabled = false` |
| **hashpress-opencode** | 短时多次 compact 后 `enabled = false`（防风暴） |

`opencode-auto-continue`（https://github.com/developing-today/opencode-auto-continue）主要靠 **session.error / idle + promptAsync**，一般**不**占用上述两个钩子，但会与“压缩后是否继续”在产品层叠加，需注意重复 continue。

---

### C. 压缩相关但通常不抢这两个钩子

| 项目 | 说明 |
|------|------|
| **opencode-compaction-guard** | 用 `experimental.chat.messages.transform` + `session.error` 修 orphan tool_use，不改 compacting prompt |
| **opencode-openai-compact** | 走 OpenAI `/responses/compact` 原生路径，绕开文本总结 prompt |
| **magic-compact** | 自有 `/magic-compact` 流程，非标准 LLM 总结钩子 |
| **opencode-session-store** | 监听 `session.compacted` 做落盘，不改 prompt |
| **opencode-agent-skills** | 在 `session.compacted` 后重注入 skills |

---

## 只 push `context` 时的冲突与最佳实践

### 已知冲突

1. **`output.prompt` 覆盖（最严重）**  
   与 **hashpress-opencode**、以及任何设置 `output.prompt` 的插件共存时，**你的 context 全部失效**。

2. **多个 `prompt` 互相覆盖**  
   后加载插件的 `prompt` 胜出；加载顺序：全局 config → 项目 config → 全局 plugins → 项目 plugins。

3. **autocontinue 被关掉**  
   goal / hashpress 可能关掉合成 continue；你的插件若依赖“压缩后自动 Continue…”，在 goal 活跃时可能拿不到内置 continue。

4. **context 膨胀**  
   Oh-My-OpenCode + goal + 你的插件都会 push，总结指令变长，极端情况影响压缩请求体积。

5. **钩子抛错**  
   任一插件在 compacting 中 throw 会中断整次压缩（此前已分析）。

### 最佳实践（你的插件只 push context）

1. **优先只 `context.push`，不要设 `prompt`**，与 Oh-My / goal / swarm 设计一致，可叠加。  
2. **文案短、结构化、可去重**（固定标题如 `## MyPlugin State`），避免与 OMO 的长模板重复。  
3. **钩子内 try/catch**，失败只记日志，勿向上抛。  
4. **与 hashpress / compaction-prompt 类同装时**：  
   - 二选一；或  
   - 确认对方未设 `prompt`；或  
   - 你改为在确认无人设 `prompt` 时再 push（无法可靠探测他插件是否已设 `prompt`，实践上仍以配置互斥更稳）。  
5. **需要强制保留你的状态且面对 prompt 覆盖时**：只能自己也设 `prompt`，并在其中**手工嵌入**你的状态与默认/他插件关心的要点（会变成“独占总结指令”）。  
6. **goal 活跃时**：续写交给 goal 插件，不要再依赖内置 autocontinue。  
7. 安装列表中标注依赖：`experimental.session.compacting`；避免与已知 `prompt` 替换插件默认同开。

---

## 简要对照表

| 项目 | compacting | autocontinue | 对“只 push context” |
|------|-----------|--------------|---------------------|
| Oh-My-OpenCode | **context.push** | 未强调 | 可共存（累加） |
| opencode-goal-plugin | **context 注入 goal** | **常关** | context 可共存；continue 可能被关 |
| hashpress-opencode | **`output.prompt` 替换** | 防风暴时关闭 | **context 被忽略** |
| opencode-plugin-compaction-prompt | 自定义 prompt 策略 | — | 视是否写 `prompt` |
| swarm 用例 / 文档示例 | **context.push** | — | 可共存 |
| opencode-compaction-guard | 不占用该钩子 | — | 无直接冲突 |

**结论**：生态里多数“状态保活”类插件（OMO、goal、swarm）走 **context 追加**，与你的策略兼容；真正会**吃掉你的 context** 的是会设置 **`output.prompt`** 的增强器（以 **hashpress-opencode** 为明确代表）。共存时默认假设“只 append context”，与 prompt 替换类插件做配置级互斥。

