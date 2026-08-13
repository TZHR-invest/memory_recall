# 2026-08-12: 核心服务 + OpenCode 插件精简实施计划

> 类型: 讨论 / 计划
> 日期: 2026-08-12
> 关联: ADR-0003~0008、[2026-08-12-core-plugin-refactor-discussion.md](2026-08-12-core-plugin-refactor-discussion.md)、
> [2026-08-12-opencode-compaction-hook.md](2026-08-12-opencode-compaction-hook.md)

## 背景

讨论稿 [2026-08-11_refactor_core_and_plugin.md](../archive/2026-08-11_refactor_core_and_plugin.md)（已归档，内容不可信任）
提出精简方向；经代码核查与官方源码调研，用户确认以下决策（ADRs 已落）：

- 注入只走 `/context-inject`（ADR-0003）；
- `/context-inject` 单通道优雅降级（ADR-0004）；
- 失败提示 log + toast ≤3/会话（ADR-0005）；
- 会话摘要不进记忆库（ADR-0006）；
- 压缩收敛到官方 hook、只用 context 注入（ADR-0007）；
- 删除摘要捕获与现场恢复（ADR-0008）。

## 实施顺序

### 阶段 1：后端 /context-inject

1. 优雅降级（ADR-0004）：
   - service 各通道失败收集为 `failed_channels`（trace + stats）；
   - API 层不再整体 500；单通道失败返回成功通道结果，全失败/请求级错误才 500；
   - 补测试：单通道失败 / 全失败 / 请求级错误。
2. 移除旧 `container_tag` 模式（ADR-0003）：
   - `apps/api/src/api/context_inject.py` 删除旧字段与 `inject()` 分派路径；
   - `tests/test_v2/test_context_inject_api.py` 全套旧模式用例改写为 `user_tag/project_tag`。

### 阶段 2：插件注入收敛（ADR-0003）

3. `context.ts` 删除前端复合注入路径：`injectContext` / `formatContext` /
   `traverseFromSeeds` / `deduplicateAcrossScopes`；
4. 删除 `semantic-dedup.ts`、`embedding-cache.ts`、`client.embedBatch` 及相关测试；
5. `config.ts` 删除 `useBackendDedup`、`userContainerTag/projectContainerTag`；
6. `index.ts` 注入只走 `injectContextFromBackend`。

### 阶段 3：压缩收敛（ADR-0007 / ADR-0008 / ADR-0006）

7. `index.ts` 的 `experimentalSessionCompacting` 精简：
   - 删除 `markSummarized` / `captureAgentConfig` / `captureTodos`；
   - 保留 `output.context` 注入（AI guidance + 项目记忆），不设置 `output.prompt`；
   - **hook 内 fail-open 防御层**（第二轮调研结论，源码核实 `Plugin.trigger` 无 try/catch）：
     - 整体 try/catch：fetch 项目记忆等所有可能抛错的调用必须兜住，失败只记日志；
     - 超时保护：单个 I/O 用 `Promise.race` 限制（约 3s），不 resolve 也按失败处理；
     - `output.context` 大小上限：防止注入内容过大导致压缩模型溢出；
     - 只 mutate `output`，不依赖返回值。
   - **共存检测**（第三轮调研结论）：hook 开头检查 `output.prompt !== undefined`，
     若已被其他插件接管则记 warn 并跳过注入，避免静默失效；
   - 注入文案短、结构化、可去重（固定标题如 `## Persistent Memory`），避免 context 膨胀；
   - README 增加兼容性声明：本插件只 push context、不设置 prompt、不注册 autocontinue；
     若同时启用任何设置 `output.prompt` 的压缩插件/开关（如 OMO 的 customCompactionPrompt），
     本插件注入会失效。
8. `compaction.ts` 删除：
   - 预压缩：`checkAndTriggerCompaction` / `injectHookMessage` / `createCompactionPrompt` /
     `getOrCreateMessageDir` 等写文件路径；
   - 摘要捕获：`waitForSummaryMessage` / `handleSummaryMessage` / `saveSummaryAsMemory` /
     `latestSummaries` / `summarizedSessions` / `savedSummarySessions`；
   - 现场恢复：`captureAgentConfig` / `recoverAgentConfig` / `captureTodos` / `restoreTodos` /
     `agentConfigCheckpoints` / `todoSnapshots`；
   - 仅服务于预压缩的 `modelContextCache` / `resolveContextLimit` 一并删除。
9. `events.ts`：删除 `session.compacted` 恢复处理与摘要相关触发；保留 `session.deleted` 清理；
   事件字段取法收敛到官方事件结构。
10. 删除 `src/summary.ts` 死代码（ADR-0006）。

### 阶段 4：提示策略与版本（ADR-0005）

11. 注入失败提示：log + toast，按 `sessionID` 每会话最多 3 次；第 3 次提示
    "后续错误不再显示，详情见 ~/.memory-recall-opencode.log"；错误不写入对话消息；
    `session.deleted` 时清理节流状态。
12. 版本对齐：
    - `~/.config/opencode/package.json` 中 `@opencode-ai/plugin` / `@opencode-ai/sdk` 更新到 `^1.18.0` 并 `bun install`；
    - 安装脚本 `registerPluginToPackageJson` 改为"已存在依赖也更新版本"（当前只新增不更新）；
    - `bun run build` 验证。

### 阶段 5：验证

13. 残留检查（应全部为空）：
    `checkAndTriggerCompaction|injectHookMessage|createCompactionPrompt|waitForSummaryMessage|
    captureAgentConfig|captureTodos|useBackendDedup|SummaryCapture|injectContext\b`；
14. 后端 fast unit loop 全绿（见 AGENTS.md Testing），新增降级用例；
15. 插件 `bun test` 更新后全绿；
16. 手工验证：`/context-inject` 单通道失败返回部分结果；注入失败 toast ≤3；压缩 hook 只追加 context。

## 风险与验证点

- **原生 auto 压缩时机**（原讨论稿 2.4 验证点 2，第三轮调研补充）：删除预压缩后依赖
  `compaction.auto`，`reserved` 默认 `min(20000, maxOutputTokens)`；大窗口模型（如 1M context）
  下 20k 占比仅 ~2%，存在"快满才压"风险（issue #27706/#11314）。上线后观察，必要时 README
  给调参指引（显式调大 `reserved`；注意无 `limit.input` 的模型该字段被忽略，issue #13980）；
- **V1/V2 配置并存**：`reserved/buffer`、`preserve_recent_tokens/keep.tokens` 字段名不同，
  本项目按当前运行时 v1.18.16 的 V1 字段为准，社区示例先确认版本；
- **事件字段兼容**：删除恢复逻辑后不再依赖 `session.compacted` 字段细节，风险下降；
- **外部调研交叉验证**：外部结果回来后由 Agent 统一理解；若与 ADR 冲突，
  先开新讨论/新 ADR 再动代码，不静默改决策。

## 验收标准

- 无上述残留代码与测试；相关单测全绿；
- `/context-inject`：单通道失败仍返回部分结果且带 `failed_channels`；
- 插件：注入失败不阻塞对话，toast ≤3/会话，对话消息无错误注入；
- 压缩：hook 只追加 context，无私有存储写入，无 agent/todos 恢复逻辑；
- 压缩 hook 抛错实测：构造抛错场景，压缩流程不受影响（hook 内已 try/catch）；
- 压缩 hook 超时/超限实测：模拟慢 I/O 与超大 context，压缩仍能继续；
- 共存检测实测：前置一个设置 `output.prompt` 的模拟插件，本插件 warn + 跳过，不写坏 output；
- 文档：本文档与 ADR 已同步；README（插件）更新压缩与依赖说明。

## 未决问题

- 外部调研结果可能补充/修正细节（Q3 原生压缩调参、Q5 summarize 语义等），待结果回来更新。
