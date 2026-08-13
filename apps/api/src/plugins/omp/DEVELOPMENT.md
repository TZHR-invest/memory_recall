# Memory Recall omp 插件 — 开发文档（初稿）

> 目标：为 omp（`@oh-my-pi/pi-coding-agent`，Oh My Pi 宿主）提供持久化记忆能力，与现有 opencode / deepseek-tui / hermes / openclaw 插件共享同一套后端（`apps/api`）。
> 本文档记录已确定的设计决策与开发计划；待定事项见文末「待定决策」。

## 1. 背景

项目已支持多款 Agent 的记忆插件，均对接同一后端：

| 插件 | 目录 | 形态 |
|---|---|---|
| opencode | `apps/api/src/plugins/opencode/` | TS/Bun 插件（功能最完整，参考模板） |
| deepseek-tui | `apps/api/src/plugins/deepseek-tui/` | Python MCP stdio server |
| hermes | `apps/api/src/plugins/hermes/` | Python MCP stdio server |
| openclaw | `apps/api/src/plugins/openclaw/` | Python hooks（旧） |
| codex | `apps/api/src/plugins/memory-recall-codex/` | Codex 插件（skills + MCP stdio server） |

现在为 omp 开发对应插件。omp 与 pi 同源（由 pi-mono fork），扩展 API 是 pi 扩展 API 的直接延续，插件形态与 opencode 同为 TypeScript 扩展，可最大程度复用 opencode 插件的实现。

> 注：omp 自带一套内置记忆运行时（`ctx.memory` 与 `memory_edit` / `recall` 等内置工具，走宿主自己的记忆后端）。本插件做的是**跨 Agent 共享的后端记忆**（apps/api，与 opencode / deepseek-tui / hermes 同一份数据），两者定位不同、互不冲突。

## 2. omp 扩展机制（已确认的关键事实）

- omp 扩展是 TS/JS 模块，默认导出 `(pi: ExtensionAPI) => void | Promise<void>` 工厂函数（可 async）。
- **Bun 原生 `import()` 加载 TS 源码，无需构建**。加载带 `?mtime` cache-buster，编辑源码后重载即生效（等价 pi 的 jiti 热重载）。开发时把插件入口指向仓库源码即可。
- 扩展发现位置（自动发现）：
  - 项目级：`<cwd>/.omp/extensions/*.ts` 或 `<cwd>/.omp/extensions/*/index.ts`（仅 cwd，不向上遍历祖先）
  - 用户级：`~/.omp/agent/extensions/`（`--profile <name>` 时为 `~/.omp/profiles/<name>/agent/extensions`，受 `PI_CODING_AGENT_DIR` 影响）
  - 配置：`<cwd>/.omp/config.yml` 或 `~/.omp/agent/config.yml` 的 `extensions:` 数组（旧式 `<cwd>/.omp/settings.json` 亦接受）
  - CLI：`omp -e / --extension ./path.ts`（`--hook` 视为同义，仅快速测试）
  - 插件包：`package.json#omp.extensions` 清单（legacy `pi.extensions` 仍接受；命名目录时识别 `index.{ts,js,mjs,cjs}`）
- **零运行时依赖**：宿主内建 `@oh-my-pi/pi-coding-agent`（含 `ExtensionAPI` 类型与 schema builders），扩展中直接 import；加载器（`legacy-pi-compat.ts`）会把旧 pi 包说明符（`@mariozechner/*`、`@earendil-works/*`）与裸 `@sinclair/typebox` 重写到宿主捆绑副本。工具参数 schema 用注入的 `pi.zod`（omptype 支撑的 Zod 兼容 builder）——与 opencode 插件「勿直接 import zod」同理（避免双实例冲突）；`pi.arktype`（omptype 原生）、`pi.typebox`（legacy shim）亦可用。类型检查需在插件目录放 devDeps（`@oh-my-pi/pi-coding-agent` types）。
- 禁用粒度：`disabledExtensions: ["extension-module:<derivedName>"]`（derivedName = 入口路径名，如 `.../index.ts` → `index`）。
- 事件模型：`session_start` / `session_shutdown`、`session_before_compact` / `session.compacting` / `session_compact`、`turn_start` / `turn_end`、`tool_call` / `tool_result`、`input`、`context`、`before_agent_start`、`agent_start` / `agent_end` 等（命名与 pi 基本一致）。
- 原生工具：`pi.registerTool()` 注册后 LLM 可直接调用；`execute(toolCallId, params, signal, onUpdate, ctx)` 返回 `{ content: [{ type: "text", text }], details }`；`params` 由 `pi.zod.object(...)` schema 静态类型化，参数校验在 agent loop 内完成。
- 上下文注入方式：`before_agent_start` 返回 `{ message: { customType, content, display, details, attribution } }`，custom message 参与 LLM context（多个 handler 时首个返回的 message 生效）。与 opencode 伪造 message parts 相比更干净。
- 状态持久化：`pi.appendEntry("com.memory-recall.state", data)` 写入 custom 会话条目（customType 建议反域名命名），在 `session_start` / `session_branch` / `session_tree` 时用 `ctx.sessionManager.getBranch()` 重建。
- 定时器：后台定时/延时任务**必须**用 `ctx.setInterval` / `ctx.setTimeout`（回调异常被隔离上报，session 不崩；裸 `setInterval` 抛错触发进程级 uncaughtException，会拖垮整个 session）；句柄可传 `ctx.clearTimer`，`session_shutdown` 自动清理。
- 失败语义：单路径加载失败只记录 `{ path, error }` 不阻塞其他扩展；handler 异常被捕获并上报；`tool_call` handler 抛错 fail-closed 阻断工具。
- 扩展在宿主进程内运行、不沙箱；共享同一 EventBus 与 ExtensionRuntime；加载阶段调用 action 方法（`pi.sendMessage` 等）会抛 `ExtensionRuntimeNotInitializedError`——先注册，行为放在事件/工具回调里。

## 3. 事件映射设计（opencode → omp）

| opencode 插件 | omp 扩展 | 用途 |
|---|---|---|
| `chat.message` 钩子（用户消息前插 synthetic parts） | `before_agent_start` 返回 `{ message: { customType: "memory-recall", content, display } }` | 召回上下文注入。custom message 直接参与 LLM context |
| `experimental.session.compacting` | `session_before_compact` / `session.compacting` / `session_compact` | 压缩时注入项目记忆、捕获会话摘要 |
| `event` 钩子（会话生命周期） | `session_start` / `turn_start` / `turn_end` / `session_shutdown` | 会话跟踪、已注入记忆去重 |
| 插件 `tool` | `pi.registerTool()` | 原生工具（`memory_add` / `memory_recall` / `memory_search`） |

## 4. 复用 opencode 插件代码

`opencode/src/client.ts` 与 `opencode/src/config.ts` 为纯 TS + node 内置模块（fetch / fs / path / os），**无 opencode 依赖，可整文件搬用**。后端契约完全一致：

- 认证：`X-API-Key: rk_live_... / rk_test_...`
- `GET /auth/verify` → keyId
- `POST /context-inject`（`user_tag` + `project_tag`）→ 统一召回上下文
- 其余：`/memories`、`/search`、`/documents`、`/graph`、`/profile`、`/extract-memory` 等

复用清单：

| opencode 文件 | 处理 |
|---|---|
| `client.ts` | 整文件复制，不改 |
| `config.ts` | 复制后按待定决策（见 §8）调整配置来源 |
| `context.ts` | 复制，保留 markdown 格式化与 dedup 逻辑 |
| `i18n.ts` + `i18n/*.json`、`semantic-dedup.ts`、`embedding-cache.ts`、`logging.ts`、`queue.ts`、`summary.ts`、`summary-extractor.ts` | `context.ts` / `config.ts` 的纯本地传递依赖，一并复制 |
| `tracker.ts` / `recall-trigger.ts` | 按需移植（注入策略：首条注入 + 关键词触发 + 动态尺寸） |
| `tool.ts` | 改写为 `pi.registerTool()` 形态（schema 用 `pi.zod`） |
| `compaction.ts` | 改写为 `session_before_compact` 钩子形态 |
| `events.ts` | 改写为 omp 事件 handler 形态 |
| `index.ts` | 重写为 omp 入口（工厂函数 + 事件注册） |
| `document-tracker.ts` / `file-watcher.ts` | 暂不移植（见 §8） |
| `cli.ts` | 不移植——omp 安装无需 CLI，symlink / 配置一行即可 |

> 注：`context.ts` 传递依赖 `i18n.ts`、`semantic-dedup.ts`、`embedding-cache.ts` 等均纯本地模块，复制时一并带上；`semantic-dedup.ts` 仅 type-import `ApiClient`，运行时依赖后端 embedding 接口。

## 5. 目录结构

```
apps/api/src/plugins/omp/
├── src/
│   ├── index.ts            # 入口：export default (pi: ExtensionAPI)
│   ├── config.ts           # 配置加载（复用 opencode，来源待定）
│   ├── client.ts           # ApiClient（复用 opencode，不改）
│   ├── context.ts          # 召回结果 → markdown 上下文（复用 opencode）
│   ├── i18n.ts / i18n/     # 文案（context.ts 传递依赖）
│   ├── semantic-dedup.ts / embedding-cache.ts / logging.ts / queue.ts / summary.ts / summary-extractor.ts  # 纯本地模块（传递依赖）
│   ├── tools.ts            # registerTool: memory_add / memory_recall / memory_search
│   ├── tracker.ts / recall-trigger.ts  # 注入策略与会话去重
│   ├── events.ts           # session/turn 生命周期事件
│   └── compaction.ts       # session_before_compact 钩子
├── README.md               # 用户文档（安装/开发模式，参照 opencode README「源码直连」）
├── DEVELOPMENT.md          # 本文档
└── package.json            # 仅类型检查 devDeps（@oh-my-pi/pi-coding-agent types），无运行时依赖
```

## 6. 配置与标签约定

- 标签约定沿用全项目统一规则：
  - `userTag = keyId`（`GET /auth/verify` 返回）
  - `projectTag = {keyId}_project-<dirName>`，其中 `<dirName>` 取 `ctx.cwd` 的目录名（替代 opencode 的 `input.directory`）
- 配置字段（候选）：`baseUrl`、`apiKey`、`language`、注入策略参数（`maxMemories` / `maxChunks` / 关键词列表等），与 opencode 配置项对齐。配置来源见 §8 待定决策；Bun 自动加载 `.env`，环境变量方案零配置成本。

## 7. 开发里程碑

1. **骨架**：建目录；复制 `client.ts` / `config.ts` 及其传递依赖；写最小 `index.ts`（`session_start` notify + 注册一个 `memory_recall` 工具）。
2. **验证加载**：项目级 `.omp/extensions/` symlink 指向 `src/index.ts`（或 `omp -e ./src/index.ts` 快速测试），重启会话确认加载成功；验证 `?mtime` 热重载（改源码后重载即生效）。
3. **上下文注入**：`before_agent_start` 调 `client.injectContext()`，返回 custom message；实现首条注入 + 关键词触发策略（`tracker.ts` / `recall-trigger.ts`）。
4. **原生工具**：`memory_add`（`POST /memories`）、`memory_recall`（显式召回）、`memory_search`（`/search`），schema 用 `pi.zod`，结果走 `{ content, details }` 结构化返回。
5. **压缩钩子**：`session_before_compact` 注入项目记忆、`session.compacting` 捕获会话摘要。
6. **收尾**：README、测试（如适用）、更新 `AGENTS.md` 插件清单。

MVP 范围：**上下文注入 + `memory_add` 工具**，跑通后再补齐其余。

## 8. 待定决策

- [ ] 配置方式：`MEMORY_RECALL_*` 环境变量（与 deepseek-tui/hermes 一致，Bun 自动加载 .env） vs 配置文件（与 opencode 一致） vs 两者都支持
- [ ] 安装方式：项目级 `.omp/extensions/`（进仓库） vs 全局 `~/.omp/agent/extensions/` symlink vs `config.yml#extensions` 指向仓库路径
- [ ] 注入策略：是否完整移植 opencode 的 smart recall（首条注入 + 关键词触发 + 动态尺寸）
- [ ] 工具集范围：MVP 只做 `memory_add`，还是同时做 `memory_recall` / `memory_search`
- [ ] 是否移植文档跟踪（`document-tracker.ts` / `file-watcher.ts`）——omp 侧优先不移植（`resources_discover` 事件目前无调用点），如需再议
- [ ] 与宿主内置记忆（`ctx.memory` / `memory_edit` / `recall`）的交互：是否在召回结果中融合或提示宿主内置记忆，避免重复注入
