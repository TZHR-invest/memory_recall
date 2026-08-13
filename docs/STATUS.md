# Memory Recall 任务状态（实时工作台）

> 状态: ACTIVE · 最后更新: 2026-08-13
>
> 规则：本文件只放"当前活跃工作 + 下一步 + 等待项"；历史一律进 `docs/notes/`；
> 每次任务收尾必须更新；无活跃工作则写"空闲"。

## 活跃任务

| 任务 | 状态 | 入口 |
|------|------|------|
| OpenCode 压缩 hook 外部调研 | 已完成（三轮收敛，结论与 ADR-0003~0008 一致） | [调研目录](notes/research/2026-08-12-opencode-compaction-hook/README.md) |
| 核心服务 + 插件精简实施 | 未开始（下一步） | [实施计划](notes/2026-08-12-core-plugin-refactor-plan.md) |
| AGENTS.md 精炼重构（拆分到 ARCHITECTURE/TESTING/PLUGINS/RESEARCH_GUIDE） | 已完成（2026-08-13） | [记录](notes/2026-08-13-note.md) |
| project-codex / project-.codex 双容器清理 | 已完成（记忆迁移 + opencode 插件点号目录过滤修复，待 opencode 重启生效） | [notes/2026-08-13-note.md](notes/2026-08-13-note.md#project-codex--project-codex-双容器来源解密用户提问排查) |

## ADR 实施跟踪

规则：ADR 只记录决策（Accepted 不代表已实现），实施状态统一在本表跟踪——
每个 Accepted ADR 登记 `未开始 / 部分实现 / 已实现`；新建 ADR 时同步登记，
实施状态变化时更新；实施完成记录 commit/版本后从本表移除（历史进 `docs/notes/`，
有设计文档的在其上标注实现版本）；被 Superseded 的 ADR 不再跟踪。
详见 [DOCUMENTATION_GUIDE.md §2.1](DOCUMENTATION_GUIDE.md#21-adr-与实施状态accepted--已实现)。

| ADR | 决策 | 实施状态 | 说明 / 入口 |
|-----|------|---------|-------------|
| [0001](decisions/0001-product-positioning.md) | 产品定位收敛为 AI Agent 记忆系统 | 部分实现 | PROJECT_PLAN 已按决策重写；README 统一叙事待收尾（[MR-010](issues/MR-010-positioning-drift.md) 仍 OPEN） |
| [0003](decisions/0003-inject-api-convergence.md) | 注入接口收敛为 /context-inject 单一路径 | 未开始 | 插件双注入路径（injectContext/useBackendDedup/semantic-dedup）仍存在；[实施计划](notes/2026-08-12-core-plugin-refactor-plan.md) 阶段 1 |
| [0004](decisions/0004-context-inject-graceful-degradation.md) | /context-inject 子模块优雅降级 | 未开始 | 后端 failed_channels 未实现；[实施计划](notes/2026-08-12-core-plugin-refactor-plan.md) 阶段 1 |
| [0005](decisions/0005-inject-failure-notice-policy.md) | 注入失败提示策略（log + toast 节流） | 未开始 | [实施计划](notes/2026-08-12-core-plugin-refactor-plan.md) 阶段 4 |
| [0006](decisions/0006-session-summary-not-stored-as-memory.md) | 会话摘要不写入记忆库 | 部分实现 | 不写入行为已固化（saveSummaryAsMemory 返回 null）；summary.ts 死代码待删除（[实施计划](notes/2026-08-12-core-plugin-refactor-plan.md) 阶段 2/3） |
| [0007](decisions/0007-compaction-converge-to-official-hook.md) | 压缩机制收敛到官方 hook | 未开始 | 预压缩代码（checkAndTriggerCompaction 等）仍存在；[实施计划](notes/2026-08-12-core-plugin-refactor-plan.md) 阶段 2/3 |
| [0008](decisions/0008-remove-summary-capture-and-scene-recovery.md) | 删除摘要捕获与现场恢复 | 未开始 | waitForSummaryMessage/recoverAgentConfig 等仍存在；[实施计划](notes/2026-08-12-core-plugin-refactor-plan.md) 阶段 2/3 |

## 下一步

1. 按[实施计划](notes/2026-08-12-core-plugin-refactor-plan.md)阶段 1 开始：
   后端 `/context-inject` 优雅降级 + 移除旧 `container_tag` 模式；
2. 阶段 2/3：插件注入收敛、压缩收敛（context-only + fail-open 防御层 + 共存检测）；
3. 阶段 4：toast 节流、版本对齐；
4. 阶段 5：残留检查、测试、手工验证（抛错 hook / 超时 / 共存检测实测）。

## 等待项 / 阻塞

- 暂无（外部调研已完成；等待开始实施）。

*状态: ACTIVE · 最后更新: 2026-08-13*
