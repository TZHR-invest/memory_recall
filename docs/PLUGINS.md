# Memory Recall 客户端插件

> 状态: ACTIVE · 版本: v1.1 · 最后更新: 2026-08-14
>
> 多个独立子项目，位于 `apps/api/src/plugins/`。构建产物已 gitignore（`dist/`、`*.tgz`、`*.sh`）。

## dsh（DeepSeek Harness，纯 ESM JS）

插件名 `memory-recall-dsh`，目录 `apps/api/src/plugins/dsh/`。

- **无构建步骤**：纯 ESM JavaScript，直接复制到 `~/.dsh/profiles/node_modules/memory-recall-dsh/`
  （loader 解析目录），并在目标 profile 的 `cordis.patch.yml` 追加 insert 接线；
  安装/检查/卸载用 `bash install.sh`（`--profile` 指定目标，默认 web；`--check` 只检查；
  `--restart` 重启 dsh web 并验证）。
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

*状态: ACTIVE · 版本: v1.1 · 最后更新: 2026-08-14*
