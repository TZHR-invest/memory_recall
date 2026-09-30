# Memory Recall 客户端插件

> 状态: ACTIVE · 版本: v1.1 · 最后更新: 2026-08-14
>
> 多个独立子项目，位于 `apps/api/src/plugins/`。构建产物已 gitignore（`dist/`、`*.tgz`、`*.sh`）。

## dsh（DeepSeek Harness，纯 ESM JS）

插件名 `memory-recall-dsh`，目录 `apps/api/src/plugins/dsh/`。

- **无构建步骤**：纯 ESM JavaScript，直接复制到 `~/.dsh/profiles/node_modules/memory-recall-dsh/`
  （loader 解析目录），并在目标 profile 的 `cordis.patch.yml` 追加 insert 接线；
  安装/检查/卸载用 `bash install.sh`（`--profile` 指定目标，默认 web；`--check` 只检查；
  `--smoke` headless 试启动冒烟；`--restart` 冒烟通过后重启 dsh web 并验证）。
- **防崩基础设施共享**（MR-022/023 教训，新 dsh 插件复用）：`apps/api/src/plugins/_dsh-common/`
  提供通用 `preflight.mjs`（manifest/classic-script 契约预检）与 `install-template.sh`
  （通用安装器：契约预检 + headless 冒烟 + 幂等接线 + 回滚），见其 README。
- 能力：5 个记忆工具（`memory_store`/`memory_search`/`memory_profile`/`memory_list`/`memory_forget`）、
  自动召回（`agent/pre-step` + `POST /context-inject`，策略 once/smart/always，`<system-reminder>` 框定注入）、
  自动捕获（`turn/end` 摘要落库，extract 蒸馏 / raw 原文）。
- **依赖契约**：只 import `@deepseek-ai/schemastery`（Config）、`@deepseek-ai/dsh-llm`
  （createUserMessage）、`@deepseek-ai/dsh-tools`（defineTool）；声明 `inject: ["agents", "tools"]`。
- 标签约定：`userTag = keyId`，`projectTag = {keyId}_project-<cwd 目录名>`（按 agent 会话 cwd 推导）；
  API Key 写 profile patch `config.apiKey` 或环境变量 `MEMORY_RECALL_API_KEY`。
- 测试：`node --test`（单元 + 集成，集成连真实后端、缺 Key 自动跳过）。详见插件 README.md。

## opencode（TypeScript/Bun）

插件名 `memory-recall-opencode`，主入口 `dist/index.js`。

- 构建用 `bun run build`（**不是 tsc**，tsconfig 有 `noEmit: true`）；安装用 `bunx memory-recall-opencode install`。
- 配置写到 `~/.config/opencode/memory-recall.jsonc`。
- **依赖契约**：运行时只 import `@opencode-ai/plugin`（工具注册 + `tool.schema.*` 定义参数，
  **绝不直接 import `zod`**，会造成双实例崩溃）与 `@opencode-ai/sdk`（仅类型）；构建时两者都要
  `--external`，不要把插件或 `zod` 打进包。
- `install --dev`（symlink 模式）已废弃，只打印提示。
- npm 插件缓存：opencode 自 v1.4.3 起用 `@npmcli/arborist` 装到 `~/.cache/opencode/packages/<pkg>@latest/`
  （官方文档 "node_modules/" 表述滞后，描述的是 v1.4.3 前旧机制，以源码为准）。
  详见 `apps/api/src/plugins/opencode/README.md` → 依赖架构。

## deepseek-tui / hermes（Python MCP stdio server）

独立 Python MCP stdio 服务（`python server.py`），用 `MEMORY_RECALL_*` 环境变量配置。
`deepseek-tui` 文档里的 `install.sh` 被 gitignore 且缺失 —— 只有手动配置可用。

## 标签约定与后端契约

- `userTag = keyId`（跨项目），`projectTag = {keyId}_project-<dirName>`（dsh/opencode/codex 一致）。
- 后端契约：`X-API-Key` 头，`GET /auth/verify` → keyId；统一召回 `POST /context-inject`
  带 `user_tag` + `project_tag`。
- 写入注意：`POST /memories` 同步含 embedding + LLM 实体提取 + 关系检测，实测 25s+；
  插件写入超时（`writeTimeoutMs`）需单独放宽（dsh 插件默认 90s）。

### 写入契约（⚠️ MR-027 教训，写脚本直连 API 前必读）

- **容器只由 `container_tag` 决定，`scope` 不是 API 字段**。插件的工具签名里有 `scope`
  （`user`/`project`），但那是**工具层**参数，由插件翻译成 `container_tag`；
  直接 `POST /memories` 时若只把 `scope` 塞进 `metadata` 而不传 `container_tag`，
  记忆会**静默落用户容器**（Pydantic 丢弃未知字段，与 MR-017 同一 bug 类）。
  现在后端会 **422 fail-closed**（`metadata.scope` 与解析出的容器冲突时拒绝写入）。
- **长留档（prompt 全文备份 / 日志快照 / 大段粘贴）必须带 `metadata.profile_worthy=false`**：
  画像通道（`/context-inject` 的 static + dynamic 两桶）会把它排除，但 `search` 仍可召回。
  不带该标记的长文本会随画像进**每个新会话首轮**（MR-027 实测：3 条 8–9K 字留档占注入块 81%）。
  **各端可达性见下表**——此前四端工具都传不出去（开关存在但不可达），2026-10-01 起 hermes 端已补齐。
- 画像单条超过 `PROFILE_ITEM_MAX_CHARS`(600) 会被截断并标注，条数见 `stats.profile_truncated_count`。

#### `profile_worthy` 各端可达性（2026-10-01 实测）

| 端 | 工具参数 | 能否设 `profile_worthy=false` | 生效方式 |
|---|---|---|---|
| **hermes**（`plugins/hermes/server.py`） | `add(profileWorthy=…)` | ✅ 已支持（缺省不下发该键 = 后端默认 true，零行为变化） | MCP server 从仓库路径加载 ⇒ **下一个会话即生效**，无需分发 |
| dsh（`plugins/dsh/tools.js`） | 无该参数（底层 `client.addMemory` 已支持 `metadata` 透传，仅工具未暴露） | ❌ | 待需要时加参数 + `install.sh` 分发到各机 profile 并重启 dsh |
| codex / opencode / openclaw | 无该参数（payload 只拼 `{"type": …}`） | ❌ | 同上 |
| 直连 HTTP 写脚本 | `metadata: {"profile_worthy": false}` | ✅ | 即刻 |

> 缺口背景：后端 2026-08-18 就有 `profile_worthy` 开关，但**客户端工具层一直没有出口**，
> 于是"退出画像"只能靠直连脚本 —— 这正是 MR-027 里长留档反复进画像的原因之一。
> hermes 端补齐后，进化流程的"旧 prompt 备份"类写入可直接用工具参数表达。

*状态: ACTIVE · 版本: v1.3 · 最后更新: 2026-10-01*
