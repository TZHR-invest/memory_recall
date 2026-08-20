# _shared 共享核

> 状态: ACTIVE · 版本: v1.0 · 最后更新: 2026-08-20
> 关联: ADR-0021 · `docs/notes/2026-08-20-opencode-crystal-v2-upgrade-plan.md §14` · Phase 1 零行为变更抽取

## 定位

`apps/api/src/plugins/_shared/` 是 opencode 插件的**宿主无关共享核**，承载可跨宿主（opencode / opencode-crystal / 未來宿主）复用的零依赖模块。Phase 1 目标为**零行为变更**：将 `opencode/src` 中 1462L 可直接复用代码抽至单源，现有插件通过 `re-export` 薄包装继续工作，`file://` 开发模式与 `bun run build` 零影响。

```
plugins/
├── _shared/                 # 单源共享核（本目录）
│   ├── queue.ts             # 370L
│   ├── tracker.ts           # 134L
│   ├── logging.ts           # 359L
│   ├── i18n.ts + i18n/*.json # 114L + 词库
│   ├── recall-trigger.ts    # 44L
│   └── summary-extractor.ts # 63L @deprecated
└── opencode/src/
    ├── queue.ts             → export * from "../../_shared/queue.ts"
    ├── tracker.ts           → export * from "../../_shared/tracker.ts"
    ├── logging.ts           → …
    ├── i18n.ts              → …
    ├── recall-trigger.ts    → …
    └── summary-extractor.ts → …
```

`config.ts / client.ts / tool.ts / context.ts / index.ts` 保留在 `opencode` 不动（Phase 2 才迁移），避免本次改动过大。

## 概念中立原则

共享核**不得**出现以下任一宿主/后端绑定概念：

- ❌ `container_tag` / `project_tag` / `keyId` 拼接（改为调用方传入 `containerTag` / `scope` 字符串）
- ❌ `@opencode-ai/plugin` / `@opencode-ai/sdk`（仅宿主适配层依赖）
- ❌ `/memories` / `/api/v2/evidence` 等后端路由字面量（仅 `client.ts` 关心的映射）
- ❌ `src/client.ts` 的 `SearchResult` / `src/context.ts` 的 `ExpandedMemory` 直接导入（共享核内定义 `MemoryLike` 等中立接口，结构兼容即可）

正例：`tracker.ts` 定义 `MemoryLike { id, content, similarity }` 而非 `import type { SearchResult } from "./client"`；`recall-trigger.ts` 自含 `SmartRecallConfig` 与 `DEFAULT_RECALL_KEYWORDS` 而非 `import from "./config"`。

> 若某模块仍需阈值/关键词常量，应在共享核内**独立定义并注释来源**（如 `recall-trigger.ts` 顶部注释"与 opencode config.ts 保持一致"），保持单向可追溯而不产生运行时依赖。

## 模块职责

| 文件 | 行数 | 职责 | 依赖 |
|------|------|------|------|
| `queue.ts` | 370 | 异步任务队列（内存 v1）：并发控制、指数退避重试、状态追踪 | 仅 `crypto.randomUUID` |
| `tracker.ts` | 134 | 注入去重与会话追踪：`InjectedMemoryTracker` / `SessionTrackerManager` / 动态召回尺寸 / 对话历史扫描 | 零外部依赖，`MemoryLike` 中立类型 |
| `logging.ts` | 359 | 结构化 JSON 日志：异步落盘、level 过滤、tool/context/queue 等语义化方法 | `fs / path / os` |
| `i18n.ts` + `i18n/*.json` | 114 | 多语言词库加载与 locale 探测（`en_US` / `zh_CN`），`__dirname` 解析 `i18n/*.json` | `fs / path / url` |
| `recall-trigger.ts` | 44 | 智能召回关键词触发：`shouldTriggerRecall` / `findTriggerKeyword` / `DEFAULT_RECALL_KEYWORDS` | 零外部依赖 |
| `summary-extractor.ts` | 63 | Session Summary 提取（`@deprecated` 保留兼容，Phase 2 后移除） | 零外部依赖 |

## 使用方式

宿主插件**不得**直引 `_shared` 绝对路径发布，仅通过 `src/*.ts` 的 `export * from "../../_shared/xxx.ts"` re-export 访问：

```ts
// 正确：宿主代码保持原有导入不变
import { TaskQueue } from "./queue";
import { SessionTrackerManager } from "./tracker";

// 错误：直接跨包写死路径（发布后失效）
// import { TaskQueue } from "../_shared/queue.ts";
```

- 开发期 `file:// …/opencode/src/index.ts` 由 Bun 原生解析 TS，re-export 链自动追踪至 `_shared`，改 `_shared/*.ts` 保存后重启 opencode 即生效，无需构建。
- 构建期 `bun build src/index.ts --external @opencode-ai/plugin --external @opencode-ai/sdk` 自动打包 `_shared` 内容进 `dist/index.js`（17 modules），`cp -r src/i18n dist/` 仍从 `opencode/src/i18n` 拷贝（与 `_shared/i18n` 双份持有）。

## 演进约束

- **Phase 1（本 PR）**：仅抽完全无关文件，不改 `client/tool/context/config`，不新建 `opencode-crystal` 目录，不改 `package.json` 依赖。
- **Phase 2 预告**：薄 crystal 适配将新增 `opencode-crystal/`，共享核或扩充 `context-guidance` 与通用阈值（当前保留在 opencode）；新增共享模块需通过本 README 的概念中立审查。
- **变更纪律**：修 `queue/tracker/logging` 等 bug 时只改 `_shared` 单源；`opencode/src/*.ts` wrapper 保持一行 re-export，`git log --follow` 仍可追溯。

## 验证

```bash
cd apps/api/src/plugins/opencode
bun run build                 # 17 modules, 61.72KB
bun test test/smart-recall.test.ts  # 15 pass
npx tsc --noEmit --project tsconfig.json  # 仅存 index.ts 既有 Part 类型 1 错误，无新增
```

## 参考

- ADR-0021: Opencode 插件 Crystal 形态 = 共享核 + 薄适配（Proposed）
- `docs/notes/2026-08-20-opencode-crystal-v2-upgrade-plan.md §14.3–14.5`
- `apps/api/src/plugins/opencode/README.md` → 依赖架构
