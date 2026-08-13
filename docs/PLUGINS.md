# Memory Recall 客户端插件

> 状态: ACTIVE · 版本: v1.0 · 最后更新: 2026-08-13
>
> 三个独立子项目，位于 `apps/api/src/plugins/`。构建产物已 gitignore（`dist/`、`*.tgz`、`*.sh`）。

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

- `userTag = keyId`（跨项目），`projectTag = {keyId}_project-<dirName>`。
- 后端契约：`X-API-Key` 头，`GET /auth/verify` → keyId；统一召回 `POST /context-inject`
  带 `user_tag` + `project_tag`。

*状态: ACTIVE · 版本: v1.0 · 最后更新: 2026-08-13*
