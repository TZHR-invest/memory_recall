# 插件信号面盘点（复用反馈回收 · C 类验证项 #1）

> 类型: 调研（回项目内验证，代码事实） · 调研: 2026-08-14-reuse-feedback-signals
> 目的: 回答 99-final-conclusions 第六节验证项 #1——"插件实际能观测到的信号面（最终输出？工具调用？用户动作？），
> 决定哪些信号根本采不到"。据此校准 S-pre 阶段 1 的埋点范围。
> 纪律: 只依据代码事实；宿主 SDK 能力以插件实际 import 的 `.d.ts` / 类型定义为准。区分两种"能采到"：
> **① SDK 能力存在但插件当前未接线**（记为「能力在，需接线」）；**② 当前已采集**。

## 一句话结论

**7 个插件里只有 opencode 与 dsh 两个端能"被动收到宿主全量事件"，从而采到开发结果痕迹（真实代码 diff / 命令 / 退出码）；**
MCP 四端（codex / hermes / deepseek-tui / openclaw-半）基本只能在自己 tool 被调用时触发，采不到注入后的采纳/结果。
**最底层缺口是全端都没有「注入记忆清单 → 会话 outcome」的配对索引**——opencode 只有内存 tracker，dsh 甚至
`include_trace:false`，后端 `recall_traces` 到注入为止。这是 outcome 遥测首先要补的一层。

## 一、总览表

| 插件 | 形态 | 被动收事件 | 能采信号 A–E | 最弱/采不到 | 注入后闭环能力 |
|---|---|---|---|---|---|
| **opencode** | TS plugin（tool + chat.message + experimental.session.compacting + event） | ✅ `Hooks.event` 收全量 `Event` | A✅ B✅（message.part.updated/message.updated）C部分✅（消息/错误/`session.diff` 回滚）**D✅最强**（`session.diff` FileDiff、`command.executed`、`tool.execute.after`、`pty.exited` 退出码）E❌ | E 无赞踩；对话隐式信号需从文本推断；D 类**当前未接线**（event hook 只处理 session.deleted） | 强：`tracker.addMany` 记注入 ID；但无"采纳/结果"回写 |
| **dsh**（DSH，当前宿主） | JS Cordis 插件（inject: agents+tools） | ✅ `session/event` firehose + `agent/pre-step` 等 Cordis 事件 | A部分✅ B✅（assistant/message）C部分✅（turn/end.reason、chunk）D✅（tool/call+tool/result，`dsh-tool-fs` 在 meta 挂**真实 FileDiff**；todo/write）**E✅唯一结构化赞踩**（dsh-message-feedback rating+note） | 无显式 exit code 字段；revert 无独立事件；注入清单未持久化 | 中：turn/end 自动 extract-memory 落库；但无"采纳/结果 quality"回写 |
| **memory-recall-codex** | Codex 插件（skills + MCP stdio） | ❌ 纯 MCP，仅 tool 触发 | A部分✅（返回记忆 ID 给模型，插件不落 trace）B❌ C❌ D❌ E部分✅（模型调 add/update/forget） | 只能靠模型自觉调 tool | 弱：无回写，靠 SKILL.md 指令 |
| **hermes** | Python MCP stdio（11 工具） | ❌ 纯 MCP | 同 codex：A部分 B❌ C❌ D❌ E部分 | 同上 | 弱 |
| **deepseek-tui** | Python MCP stdio（11 工具） | ❌ 纯 MCP | 同 hermes | 同上 | 弱 |
| **openclaw** | Python 插件（kind:"memory" + 事件钩子 + 工具） | ✅ 但只订阅 2 个（before_agent_start / agent_end） | A部分✅ B❌（只收 prompt 不收最终输出）C❌ D❌（agent_end 只有 messages 文本）E部分（工具 store/forget） | 事件面极窄；拿不到 diff/exit code | 弱：agent_end 把整段对话原文 store，最粗糙 |
| **omp** | 无实现（仅 DEVELOPMENT.md 初稿） | — | 无 | 无 | 无 |

## 二、逐插件要点（文件:函数/事件 证据）

### 1. opencode（功能最全，D 类主力端）
- 形态：TS plugin，`export default server` 返回 `{tool, "chat.message", "experimental.session.compacting", event}`（`src/index.ts:292-297`）。
- 被动收事件：`Hooks["event"]`（`src/index.ts:247`）收宿主全量 `Event`；`SKIP_EVENTS` 只跳过 tui.* UI 事件（`:238-245`）。
- SDK 事件源清单（`@opencode-ai/sdk/dist/gen/types.gen.d.ts` 的 `Event` union，约 :602 起）：
  `session.idle` / `session.compacted` / `session.diff`（携 `FileDiff[]`=file/before/after/additions/deletions）/
  `session.updated`（携 `Session.summary.additions/deletions/diffs`）/ `session.error` / `session.deleted` /
  `message.updated` / `message.part.updated`（`Part` 含 text）/ `command.executed`（name/arguments）/
  `pty.created/updated/exited`（exitCode）/ `file.edited` / `todo.updated` / `permission.*`。
  工具级另有 `tool.execute.before/after`（after 拿到 args + output title/output/metadata）。
- 五类：A）`src/index.ts:194 tracker.addMany(result.injectedMemoryIds)` 显式记注入 ID；B）能，message.part.updated/message.updated 读最终 assistant 文本；C）部分能，session.error/消息流推断，但"重复陈述/撤销"无原生事件；D）**最强但当前未接线**——event hook 现在只处理 `session.deleted`（`src/events.ts:50-54`），`session.diff`/`command.executed`/`pty.exited` 都未订阅；E）❌ 无赞踩（v1 Event union 无 feedback 事件）。
- 闭环：`SessionTrackerManager`（`src/tracker.ts:4-86`）会话内记忆注入 ID，`session.deleted` 时清理；**无任何"采纳/结果"回写后端**。

### 2. dsh（DeepSeek Harness，当前运行时宿主）
- 形态：Cordis 插件，`inject=["agents","tools"]`，`apply(ctx)` 注册 `ctx.on("session/event")` 捕获、`ctx.on("agent/pre-step")` 召回（`index.js:140,143`）。
- 被动收事件：✅。`session/event` 是 append-only firehose，事件全表见 `@deepseek-ai/dsh-session/lib/types/types.d.ts` 的 `SessionEventMap`。
- 事件源（含**插件尚未使用**但可订阅的）：`turn/start`/`turn/end`（携 `reason`=completed/aborted/blocked/error/max-tokens/interrupted）、`step/start`/`step/end`、`user/message`、`assistant/chunk`、`assistant/message`（携 message+usage token）、`tool/call`（name+raw arguments）、`tool/result`（携 message+error{name,code}+meta）、`todo/write`、`request/header`、`request/context`；agent 级 Cordis 事件 `agent/pre-step`/`agent/request-error`/`agent/turn-stopping`/`agent/error` 等。
- 关键 D 类证据：`dsh-tool-fs` 在 `tool/result.meta` 挂 `FileDiff[]`（`dsh-tool-fs/lib/types/diff.d.ts`，write/edit 的 applied contextual-diff hunks）→ dsh 能采真实代码 diff；但**无显式 exit code 字段**。
- 关键 E 类证据：`@deepseek-ai/dsh-message-feedback` 持久化每条 assistant 消息的 `rating: positive|negative` + 可选 `note`——**7 端里唯一宿主原生赞踩**。
- 五类：A）部分——注入后只算 `contextDigest` 内存去重（`index.js:188`），**不落"注入哪几条 ID"**，且 `client.injectContext` 显式 `include_trace:false`（`client-lib.js:189`）；B）✅；C）部分 ✅（turn/end.reason=aborted/error）；D）✅（diff + tool/result + todo）；E）✅（message-feedback）。
- 闭环：`turn/end` 已自动 extract-memory 蒸馏落库（`capture.js:17-58`，captureMode extract/raw）——是"注入后回写"的一部分，但**无"采纳/结果 quality"遥测**。

### 3. memory-recall-codex
- 形态：`.codex-plugin/plugin.json`（skills + MCP）+ `.mcp.json` 注册 `python3 server.py`（`server.py:829-836` stdio MCP）。
- 仅 tool 被调用才触发（`@app.call_tool()`，`server.py:438-470`），无被动事件。11 个 tool（`server.py:133-434`）。
- 五类：A）部分（`context-inject`/`search` 返回记忆 ID 给**模型**，插件自身不落 trace）；B/C/D）❌；E）部分（模型显式调 add/update/forget/restore 即管理动作）。
- 闭环：无回写通道；全靠 `skills/memory-recall/SKILL.md` 指令让 Codex 自觉"任务完成后必须存储"。

### 4. hermes
- 与 codex 几乎逐行一致的 MCP stdio server（`server.py` 11 工具），仅环境变量配置。纯 tool 触发。信号面同 codex（A部分 B❌ C❌ D❌ E部分），无闭环通道。

### 5. deepseek-tui
- Python MCP stdio server（`server.py` 11 工具），纯 tool 触发。`context-inject` 返回给模型。信号面同 hermes/codex。附 `skill.md`/`skills/memory-recall/SKILL.md` 指导模型自觉存取。无闭环通道。

### 6. openclaw
- 形态：Python 插件 `kind:"memory"`（`plugin.json`），`create_plugin().register()` 里 `@api.on("before_agent_start")` 召回、`@api.on("agent_end")` 捕获（`__init__.py:17-27`），另注册 memory_store/search/profile/forget 工具（`tools.py`）。
- 被动收事件：✅ 但**只订阅 2 个**。`before_agent_start` 拿 `event.prompt`（`hooks.py:106`）；`agent_end` 拿 `event.messages`（`hooks.py:136` 拼文本）。
- 五类：A）部分（`recall_handler` 注入 `prependContext` 但不记 ID）；B）❌（无 assistant 最终输出回传）；C）❌；D）❌（agent_end 只有 messages 文本，无 diff/exit code）；E）部分（工具 store/forget）。
- 闭环：`capture_handler`（`hooks.py:127-147`）在 agent_end 把整段对话原文 `client.store(...)` 落库——最粗糙的回写，**无质量/采纳语义**。

### 7. omp
- 无实现，仅 `DEVELOPMENT.md` 初稿。文中记其 TS 扩展事件模型已"确认"含 session/turn/tool_call/tool_result/compact/agent_start/end 等，但**尚无代码落地**——按纪律判"无实现/无法确认"，仅作未来参考。

## 三、结尾两个清单

### 全端都采不到的信号（需宿主扩展或换方案）
1. **「注入记忆清单 → 会话 outcome」配对索引**：opencode 有内存 tracker、dsh 有一次 digest，但**没有任何端把 `{sessionID, injectedMemoryIds}` 持久化 trace 并与后续结果关联**（后端 `recall_traces` 只到注入；dsh 甚至 `include_trace:false`）。→ outcome 遥测最底层缺口，S-pre 第一步。
2. **注入记忆的"采纳/引用"直接证据**：没有任何宿主提供"记忆引用标注"显式通道；只能靠解析最终 assistant 文本推断（opencode/dsh 有文本，MCP 端连文本都拿不到）。
3. **对话隐式信号的结构化事件**（重复陈述/反驳纠正/继续追问/撤销回滚）：无宿主原生结构化事件，只能从消息流/diff 文本推断；5 个 MCP 端完全采不到。
4. **命令 exit code / 测试结果 / CI / git commit / 坑复现的结构化推送**：任何宿主都不直接推送。opencode `command.executed`+`pty.exited` 能拿到"执行+退出码"（dsh 缺 exit code 字段）；CI、git commit、测试结果全端拿不到。

### 仅个别端能采到的信号
- **真实代码 diff / 编辑结果**：仅 **opencode**（session.diff/session.updated.summary 的 FileDiff[]）与 **dsh**（tool/result.meta 的 dsh-tool-fs FileDiff）两端；其余 5 端采不到。
- **用户显式赞踩（结构化分+注）**：仅 **dsh**（dsh-message-feedback rating+note）；其余端无。
- **命令执行 + 退出码**：仅 **opencode**（command.executed + pty.exited.exitCode）；dsh 有 tool/call+tool/result 但缺 exit code 字段。
- **被动收到"对话/轮次结束"触发回写**：仅 **opencode**（session.idle/compacted/deleted）、**dsh**（turn/end）、**openclaw**（agent_end）三端；4 个 MCP 端靠模型自觉。
- **token/usage 与模型错误**：opencode 与 dsh 两端有；MCP 端仅工具返回文本。

## 四、对 S-pre 阶段 1 埋点的直接结论

1. **遥测先行只落在两端**：D 类（开发结果痕迹，最强信号）与 B/E 类只能在 opencode + dsh 上埋；MCP 四端在宿主扩展前无法采 outcome，S-pre 阶段 1 不勉强它们。
2. **第一步补配对索引**：先让 opencode 落 `{sessionID, injectedMemoryIds}` trace（把内存 tracker 持久化/上报），dsh 打开 `include_trace`（`client-lib.js:189`）——否则下游"证据归组 → 单条"无从谈起。
3. **opencode 的 D 类需接线**：`session.diff` / `command.executed` / `pty.exited` 能力已在 SDK，但 `events.ts` 当前只处理 session.deleted，阶段 1 需订阅并回传（退出码是"坑复现/测试成败"的最干净代理）。
4. **dsh 是唯一能采显式赞踩（E）的端**，应优先接线 `dsh-message-feedback` 作为黄金标签来源；opencode 无此信号，只能靠文本推断或放弃赞踩、改用"未被纠正/代码被采纳"等结果层信号。
