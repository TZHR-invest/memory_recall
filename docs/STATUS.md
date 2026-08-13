# Memory Recall 任务状态（实时工作台）

> 状态: ACTIVE · 最后更新: 2026-08-13
>
> 规则：本文件只放"当前活跃工作 + 下一步 + 等待项"；历史一律进 `docs/notes/`；
> 每次任务收尾必须更新；无活跃工作则写"空闲"。

## 活跃任务

| 任务 | 状态 | 入口 |
|------|------|------|
| OpenCode 压缩 hook 外部调研 | 已完成（三轮收敛，结论与 ADR-0003~0008 一致） | [调研目录](notes/research/2026-08-12-opencode-compaction-hook/README.md) |
| 核心服务 + 插件精简实施 | 已完成（阶段 1~5 全量实施，见 commit） | [实施计划](notes/2026-08-12-core-plugin-refactor-plan.md) |
| AGENTS.md 精炼重构（拆分到 ARCHITECTURE/TESTING/PLUGINS/RESEARCH_GUIDE） | 已完成（2026-08-13） | [记录](notes/2026-08-13-note.md) |
| project-codex / project-.codex 双容器清理 | 已完成（记忆迁移 + opencode 插件点号目录过滤修复，待 opencode 重启生效） | [notes/2026-08-13-note.md](notes/2026-08-13-note.md#project-codex--project-codex-双容器来源解密用户提问排查) |
| 记忆维护闭环（ADR-0009） | 已完成（注入陈旧标注 + 规则检查点，API 已重启生效） | [ADR-0009](decisions/0009-memory-maintenance-loop.md) |
| 文档 RAG 移出核心（ADR-0010） | 决策已定（2026-08-13，文档配套已落地）；代码删除待排期（已确认存量数据直接删不导出） | [ADR-0010](decisions/0010-remove-document-rag.md) · [实施讨论](notes/2026-08-13-adr0010-implementation-discussion.md) |
| 全量测试验证 + 回归修复 | 已完成（2026-08-13）：修复 16f3b8f 引入的 Entity 测试回归（user_tag/project_tag→container_tag，2 测试）+ performance 测试 LLM 依赖隔离（extract_entities=False，1 测试）；单元 383 + 集成 7 + 性能 5 + 去重 26 全绿 | 见 commit |

## ADR 实施跟踪

规则：ADR 只记录决策（Accepted 不代表已实现），实施状态统一在本表跟踪——
每个 Accepted ADR 登记 `未开始 / 部分实现 / 已实现`；新建 ADR 时同步登记，
实施状态变化时更新；实施完成记录 commit/版本后从本表移除（历史进 `docs/notes/`，
有设计文档的在其上标注实现版本）；被 Superseded 的 ADR 不再跟踪。
详见 [DOCUMENTATION_GUIDE.md §2.1](DOCUMENTATION_GUIDE.md#21-adr-与实施状态accepted--已实现)。

| ADR | 决策 | 实施状态 | 说明 / 入口 |
|-----|------|---------|-------------|
| [0001](decisions/0001-product-positioning.md) | 产品定位收敛为 AI Agent 记忆系统 | 部分实现 | PROJECT_PLAN 已按决策重写；README 统一叙事待收尾（[MR-010](issues/MR-010-positioning-drift.md) 仍 OPEN） |
| [0003](decisions/0003-inject-api-convergence.md) | 注入接口收敛为 /context-inject 单一路径 | 已实现 | 前端复合注入路径/semantic-dedup/embedding-cache/useBackendDedup 已删除 |
| [0004](decisions/0004-context-inject-graceful-degradation.md) | /context-inject 子模块优雅降级 | 已实现 | 后端 failed_channels + 单通道降级 + 全失败 500 已落地 |
| [0005](decisions/0005-inject-failure-notice-policy.md) | 注入失败提示策略（log + toast 节流） | 已实现 | toast 节流（每会话不超过 3 次）+ session.deleted 清理已落地 |
| [0006](decisions/0006-session-summary-not-stored-as-memory.md) | 会话摘要不写入记忆库 | 已实现 | summary.ts 死代码已删除 |
| [0007](decisions/0007-compaction-converge-to-official-hook.md) | 压缩机制收敛到官方 hook | 已实现 | 预压缩/私有存储写入已删除；官方 hook 仅 push context |
| [0008](decisions/0008-remove-summary-capture-and-scene-recovery.md) | 删除摘要捕获与现场恢复 | 已实现 | 摘要捕获/现场恢复/summary.ts 已删除 |
| [0009](decisions/0009-memory-maintenance-loop.md) | 记忆维护闭环：注入可见性 + 规则约束，不做自动写库 | 已实现 | commit 见 2026-08-13-note；MR-011 UI 主体仍 OPEN |
| [0010](decisions/0010-remove-document-rag.md) | 文档 RAG 移出核心，文档不再是并行召回语料 | 未开始 | 删除清单实施计划待排期；MR-019 蒸馏评估冻结 |


## 下一步

1. ADR-0010 实施排期：文档 RAG 删除清单（表/代码/路由/插件/测试）拆分任务；
   已确认：存量数据直接删不导出；建议按 后端核心 → 插件 → 收尾 三个 commit 推进（[讨论记录](notes/2026-08-13-adr0010-implementation-discussion.md)）；
2. ADR-0009 检查点：检索并修正"文档知识闭环/文档支柱"类过时记忆（服务可用后执行，见等待项）；
3. 手工验证项（需真实 opencode 运行时，可延后）：
   - 压缩 hook 抛错 / 超时 / 共存检测实测；
   - /context-inject 单通道失败返回部分结果 + failed_channels；
   - 注入失败 toast 不超过每会话 3 次。

## 等待项 / 阻塞

- 记忆维护检查点延后：本地 API/DB 未运行（无 venv/.env，Postgres 未启动），
  ADR-0010 相关的过时记忆检索与修正待服务可用后执行（检索主题：文档知识闭环、chunks 通道、产品支柱）；
- 手工验证需真实 opencode 运行时，可延后。
- test_document/source_deduplication 两个文件一起跑必失败（全局 db 连接跨 asyncio loop 冲突，
  非顺序问题，pytest-order/改 loop scope 均无法解决），单独跑各自全绿；彻底修复需测试
  连接管理重构（TESTING.md 已记录根因，未排期）。

*状态: ACTIVE · 最后更新: 2026-08-13*
