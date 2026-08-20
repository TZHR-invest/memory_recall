# Memory Recall OpenCode Crystal Plugin

> 系统: crystal · 版本: 0.1.0 · 薄适配层，复用 `../_shared`

复用 `apps/api/src/plugins/_shared/` 单源（queue/tracker/logging/i18n/recall-trigger），仅实现 crystal 差异：`/api/v2` evidence/claim + `scope`（`project-xxx` / `NULL`）+ 信封 `{code,message,data}` + 幂等键 + `verify_scope_ownership` 拒绝 `uuid_` 前缀。

## 与 v5 插件关系

- `opencode/` 保留 v5（`/memories|/search|/context-inject` + `container_tag`），通过 `re-export _shared` 零行为变更
- `opencode-crystal/` 仅 400L 差异（client-crystal/tool-crystal/config-patch/context），其余 `import from "../../_shared/*"`
- 开发期 `file://` 一键切换：`opencode.jsonc` 改一行指向 `opencode-crystal/src/index.ts`
- 发布期双包并存，M5 退役时 crystal 更名为 `memory-recall-opencode@2.x`

## 开发

```bash
cd apps/api/src/plugins/opencode-crystal
bun run build   # 12 modules, 61KB, --external @opencode-ai/plugin/sdk
```

契约见 `docs/initiatives/crystal/api-contract.md v1` + `ADR-0021`。
