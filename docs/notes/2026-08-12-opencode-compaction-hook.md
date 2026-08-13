# 2026-08-12: OpenCode 压缩 hook（experimental.session.compacting）调研

> 类型: 调研
> 日期: 2026-08-12
> 关联: [2026-08-11_refactor_core_and_plugin.md](../archive/2026-08-11_refactor_core_and_plugin.md)（已归档讨论稿，不可信任，仅作问题索引）

## 背景

插件当前存在两套压缩路径：

- 官方 hook：`experimental.session.compacting` 只向 `output.context` 注入 AI guidance 与项目记忆，
  没有使用 `output.prompt`；
- 预压缩 hack：`checkAndTriggerCompaction` + `injectHookMessage`（直接写 `~/.opencode/messages|parts` 假消息）
  + `createCompactionPrompt`（7 段结构化 prompt）。

讨论稿 2.4 提出三个删除前验证点，其中"官方 hook 是否在插件自己调 summarize 时同样触发"、
"输出 prompt 与 context 的关系"无法靠已装二进制反查确认。本次改用官方源码 + 官方文档核实，
不依赖二进制反查。

## 调研发现

### 1. 官方文档语义（opencode.ai/docs/plugins/，2026-08-12 读取）

- `experimental.session.compacting` 在 LLM 生成续写摘要之前触发，可注入默认压缩 prompt 遗漏的领域上下文；
- 设置 `output.prompt` 时**完全替换**默认压缩 prompt；
- **设置了 `output.prompt` 后，`output.context` 数组会被忽略**。

### 2. 源码核实（官方仓库 anomalyco/opencode，commit 1f94d8a，包版本 v1.18.16）

关键代码位置：

| 事实 | 证据 |
|---|---|
| hook 只有一个处理入口 | `packages/opencode/src/session/compaction.ts` 的 `SessionCompaction.process`：`plugin.trigger("experimental.session.compacting", { sessionID }, { context: [], prompt: undefined })` |
| prompt 替换规则 | 同文件：`const nextPrompt = compacting.prompt ?? buildPrompt({ previousSummary, context: compacting.context })`——与官方文档一致，`prompt` 优先，`context` 只在未设置 prompt 时生效 |
| 默认 prompt 结构 | `packages/core/src/session/compaction.ts` 的 `buildPrompt`：`Create/Update an anchored summary` + `SUMMARY_TEMPLATE`（Objective / Important Details / Work State(Completed/Active/Blocked) / Next Move / Relevant Files + 输出规则） |
| 插件自调 summarize 也触发 hook | HTTP 层 `POST /session/{id}/summarize` → `compactSvc.create(...)` → `promptSvc.loop(...)` → 同一个 `compaction.process`（`packages/opencode/src/server/routes/instance/httpapi/handlers/session.ts`、`packages/opencode/src/session/prompt.ts`）。即 SDK `session.summarize` 与原生自动/手动压缩走同一任务管线，hook 必然触发 |
| 自动压缩触发条件 | `packages/opencode/src/session/overflow.ts`：`isOverflow` 用最近一次 assistant 消息的 token 总量与 `context - reserved` 比较；`compaction.auto` 默认开启（`=== false` 才关闭）；另在 `ContextOverflowError` 时也会触发（processor.ts） |
| agent 状态不丢 | `compaction.create` 把 `lastUser.agent/model` 写在 compaction user 消息上；合成 continue 消息用 `userMessage.agent/model` 重建（compaction.ts）。压缩摘要本身由内置 `compaction` agent 生成，不影响会话 agent |
| todos 不丢 | `packages/core/src/session/todo.ts`：todo 存独立 `TodoTable`；compaction.ts 全程不读不删 todo 表 |
| autocontinue 的真实能力 | `experimental.compaction.autocontinue` 只返回 `{ enabled: boolean }`，仅控制压缩后是否插入合成 "Continue" 用户消息；**不原生恢复 agent/todos**（讨论稿中"已原生化的恢复能力"表述不成立） |

### 3. 插件当前状态

- `apps/api/src/plugins/opencode/src/index.ts` 的 `experimentalSessionCompacting` 只 push `outputData.context`，
  并调用 `captureAgentConfig` / `captureTodos`（现场恢复模块，见压缩重构讨论）。
- 运行环境版本不一致：本机 opencode 二进制 v1.18.16，但 `~/.config/opencode/node_modules` 的
  `@opencode-ai/plugin` / `@opencode-ai/sdk` 为 1.15.13；repo `package.json` 声明 `^1.18.0`。
  两个版本的 Hooks 类型都包含 `experimental.session.compacting` / `experimental.compaction.autocontinue`，
  迁移不阻塞，但升级对齐仍是独立待办。

## 结论

1. **`output.prompt` 是官方唯一"整体替换压缩 prompt"的通道**，语义是"二选一"：
   设置 prompt 后 context 被忽略。因此把 7 段结构化 prompt 迁到 `output.prompt` 时，
   必须把 AI guidance / 项目记忆等原 context 内容合并进 prompt 文本。
2. **插件自调 `session.summarize` 与原生压缩走同一管线，hook 同样触发**——讨论稿 2.4 的
   "删除前唯一硬性阻塞项"解除；预压缩的"保证 hook 生效"动机不成立。
3. **现场恢复可以整体删除**：agent 由消息字段携带、todos 独立存储，压缩不会丢；
   `autocontinue` 也不承担恢复职责。旧恢复代码是为历史版本（旧问题 #10744 等）写的兼容层。
4. 默认 prompt 已经是"锚定摘要更新"结构；若完全替换，需要自行处理"基于上一版摘要更新"
   的语义（可在自定义 prompt 内说明，或通过 SDK 读取历史 compaction 摘要）。

## 下一步

- hook 只保留 `output.context` 注入（AI guidance + 项目记忆），不设置 `output.prompt`
  （用户已确认，见 ADR-0007）；
- 删除预压缩三件套、摘要捕获整套、现场恢复模块（见 ADR-0007 / ADR-0008）；
- 升级并对齐 `@opencode-ai/plugin` / `@opencode-ai/sdk` 到 ^1.18.x 后复测；
- 上线后验证原生 auto 压缩时机是否足够早（`reserved` 默认 20k）。

## 补充：官方压缩机制全景（v1.18.16 源码核实版）

> 本节为源码核实的基础版，待外部调研结果交叉验证，见
> [2026-08-12-opencode-compaction-hook（调研目录）](research/2026-08-12-opencode-compaction-hook/README.md)。

### 触发模式

| 模式 | 触发者 | 条件 / 来源 |
|------|--------|------------|
| 原生自动 | opencode 会话循环 | assistant 消息 finish 后 `isOverflow`：`count >= usable = context - reserved`；`compaction.auto` 默认开启（`=== false` 才关闭）；`reserved` 默认 `min(20_000, maxOutputTokens)` |
| ContextOverflowError | processor halt | 捕获溢出错误后置 `needsCompaction`，再走 `compaction.create(auto, overflow)` |
| 手动 | `/compact` | `compaction.create(auto=false)` |
| 插件触发 | SDK `session.summarize`（`POST /session/{id}/summarize`） | handler 先 `compactSvc.create(...)` 再 `promptSvc.loop(...)`，与上两者同管线，hook 必触发 |
| prune | 独立裁剪 | `cfg.compaction?.prune`（默认关），只裁剪旧 tool 输出，不生成摘要 |

### 配置项（ConfigV2 `compaction`）

- `auto`：默认 true；
- `reserved`：默认 `min(20_000, maxOutputTokens)`，自动压缩触发预留；
- `tail_turns`：默认 2，最近 N 轮尽量保留不压缩；
- `preserve_recent_tokens`：默认 `min(8_000, max(2_000, floor(usable * 0.25)))`；
- `prune`：默认关。

### Hook / 扩展点

- `experimental.session.compacting`：`context` 追加 / `prompt` 整体替换（二选一，prompt 优先）；
- `experimental.compaction.autocontinue`：`enabled` 控制是否合成 continue 用户消息；
- `experimental.chat.messages.transform`：压缩前对消息同样生效（普通轮次与压缩共用）；
- `experimental.text.complete`：压缩摘要流式文本也走统一 processor，理论上同样生效（留意即可）。

### 事件

- `session.compacted`：压缩成功（`result === "continue"`）后发布；
- `session.next.compaction.started / delta / ended`：v2 事件，携带摘要进度；
- `session.status`：`compacting` 状态。

插件现状监听 `message.updated / session.idle / session.deleted / session.compacted`，
事件字段取法不一致（`sessionID` vs `info.id`），重构后若需感知压缩完成，优先
`session.compacted` 或 `session.next.compaction.ended`，避免解析私有字段。

### 内置执行细节

- 摘要由隐藏的 `compaction` agent 生成（`agent/prompt/compaction.txt` 系统提示词：锚定更新、
  按模板输出、不提及压缩、跟随会话语言）；
- 默认模板：Objective / Important Details / Work State(Completed/Active/Blocked) /
  Next Move / Relevant Files；
- 旧 compaction 消息会被隐藏不重复总结，上一版摘要单独传给模型（`previousSummary`）。

### 对重构的映射

- 预压缩删除后依赖原生 auto：`reserved` 默认 20k，需上线后验证"满窗再压"痛点是否复发
  （原讨论稿 2.4 验证点 2）；
- hook 只用 `context`：官方锚定摘要自动生效，无需插件缓存 previous summary；
- 现场恢复删除：agent 由消息字段携带、todos 独立存储；
- 版本对齐：opencode 运行时 1.18.16，`~/.config/opencode/package.json` 中 plugin/sdk 仍是
  1.15.13（install 脚本只新增不更新），升级为 ^1.18.0 是独立待办。

## 未决问题

- opencode 版本升级后，`experimental.` 前缀 API 的稳定性风险如何跟踪（可定期用官方 changelog 核对）。
