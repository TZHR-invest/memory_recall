# Memory Recall 任务状态（实时工作台）

> 状态: ACTIVE · 最后更新: 2026-08-15
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
| 文档 RAG 移出核心（ADR-0010） | 阶段 1 已完成（2026-08-14：四端插件移除文档功能，opencode 1.9.0 待分发）；阶段 2 用户升级待通知 | [实施计划](notes/2026-08-13-adr0010-implementation-plan.md) · [ADR-0010](decisions/0010-remove-document-rag.md) |
| 全量测试验证 + 回归修复 | 已完成（2026-08-13）：修复 16f3b8f 引入的 Entity 测试回归（user_tag/project_tag→container_tag，2 测试）+ performance 测试 LLM 依赖隔离（extract_entities=False，1 测试）；单元 386（14 skip）+ 集成 7 + 性能 5 + 去重 26 全绿 | commit 6724313 |
| 记忆维护检查点（ADR-0009） | 已完成（2026-08-13：语义检索 5 主题 × 5 容器 + SQL 关键词预检；版本化修正 1 条过时记忆 `mem_12490fb23d474aa1996e` → `mem_a716b54e449a4003beef`） | [ADR-0009](decisions/0009-memory-maintenance-loop.md) |
| codex 插件容器探测启动竞态修复（MR-021） | 已完成（2026-08-14：config.py 惰性重探测 ensure_project_tag；同日补充修复 context-inject 直用冻结 PROJECT_TAG 的遗漏路径；重启 codex 会话使 MCP server 重生后全量生效） | [MR-021](issues/MR-021-codex-mcp-container-race.md) |
| dsh 客户端插件（memory-recall-dsh） | 已完成（2026-08-14：5 工具 + 自动召回注入 + 自动捕获；21 测试全绿（含 bundle 生成/注册测试）；headless E2E + 无头 Chrome web 实测通过；修复 MR-022 平台元数据、MR-023 生成式 classic-script bundle，dsh web 正常） | [dsh 插件](../apps/api/src/plugins/dsh/README.md) |
| 记忆价值判据外部调研（S0+S1 第一刀） | 已收敛（v2：round-01 五平台无预设同题 + round-02 交叉追问三分歧收敛 + 回项目内验证；结论：判据 = 复用机会×有效性×影响−维护/遗忘成本，生命周期式沉淀，最大缺口为复用反馈回收） | [v2 调研卡](notes/research/2026-08-14-memory-value-criteria-v2/README.md) · [最终结论](notes/research/2026-08-14-memory-value-criteria-v2/99-final-conclusions.md) |
| 复用反馈回收外部调研（Q2） | 已完成（round-01 五平台无预设同题 + round-02 交叉追问三分歧收敛，各平台主动修正；结论：缺的不是评分是 outcome 遥测，需建 Memory→Decision→Action→Outcome 事件链；实施待回项目内验证后进 ADR） | [调研卡](notes/research/2026-08-14-reuse-feedback-signals/README.md) · [最终结论](notes/research/2026-08-14-reuse-feedback-signals/99-final-conclusions.md) |
| 测试记忆清理 | 已完成（2026-08-14：软删除 20 条散落测试记忆（主容器/hermes/memory_recall 容器）+ 7 类测试专用容器 95 条全部遗忘；含 capture-test 系列、e2e-test、recall-test、update-test、latency-probe、test_integration_*、test_perf_container；可经 restore 恢复） | 本次会话 |
| 测试容器删除 | 已完成（2026-08-14：用户要求删掉容器，**物理删除不可逆**。删除 28 个测试专用容器全部数据：memories 106 条 + 关联实体 33 个 + memory_profiles 1 + memory_relations 10 + recall_traces 130 + recall_embedding_logs 1586；另清孤儿测试容器（project_test/user_test/test_integration_*/test_merge/test_selfmatch 等）的 traces/emb_logs 残留；测试容器在各表 0 残留；真实容器 3068 条 active 不受影响，服务健康） | 本次会话 |
| 0有效记忆容器清理 | 已完成（2026-08-14：用户确认『没有的容器就删』。按用户指令物理删除 444 个 0 有效记忆的测试残留容器：文档去重/分块/优先级/生命周期单元测试生成的 url_dedup_*/hash_dedup_*/priority_*/container1_2_a_*/changed_*/more_fewer_chunks_*/lifecycle_*/preserve_*/source_*/no_source_*/find_source_*/rechunk_*/chunk_link_*/unchanged_*/SAME 等 442 个 + project-codex/latency-probe 孤儿测试实体容器 2 个；删除 documents 470 + entities 232 + memories 2 + traces 6 + emb_logs 14（级联清 chunks 与实体关联）。**保留** b262d2f1 旧 user_id 真实实体容器 5 个（1602 实体：stock_selection/memory_recall/hermes/shuihu_card_game）与默认兜底容器。现 0 有效记忆容器仅剩上述 6 个保留项；全库记忆 3157 条 active 1931，服务健康） | 本次会话 |
| dsh 插件跨轮注入去重（exclude_memory_ids + per-agent LRU） | 已完成（2026-08-15：后端 /context-inject 支持 exclude_memory_ids（seen_ids 预置，向量/图谱/实体全链路生效）；插件 per-agent LRU 容量 100 跟踪已注入记忆 ID，注入成功后记录、后续召回排除；bundle 重建 + 36 pytest 全绿 + bundle 防漂移过）。**2026-08-15 已拉取远端代码并重启 API（docker compose restart api，健康 + exclude_memory_ids 实测生效）；dsh web 已由用户在终端 `install.sh --restart` 成功重启（新 PID 1420081，bundle 含 exclude_memory_ids，跨轮去重全链路激活）；期间修复 install.sh pkill 模式匹配不到实际 cmdline 的 bug（commit 86ded26）** | [dsh 插件](../apps/api/src/plugins/dsh/README.md) |

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
| [0010](decisions/0010-remove-document-rag.md) | 文档 RAG 移出核心，文档不再是并行召回语料 | 部分实现 | 阶段 1 完成（[commit 1282354](https://github.com/TZHR-invest/memory_recall/commit/1282354)：四端插件移除文档功能）；阶段 3 后端删除待排期；MR-019 蒸馏评估冻结 |


## 下一步

1. ADR-0010 实施（[计划](notes/2026-08-13-adr0010-implementation-plan.md)）：
   - ~~阶段 1 已完成~~（commit 1282354：四端插件移除文档功能，opencode 1.9.0）；
   - 阶段 2：通知 1-2 个在用用户升级插件（opencode 拉代码 bun run build + install CLI；codex 拉代码重启；hermes/deepseek-tui 同步 server.py），以后端访问日志核对不再调用 /documents API；
   - 阶段 3：后端一次删除（schema 三表/服务/路由/chunks 通道/引用/测试/根目录文档），DROP TABLE 最后单独执行；
2. 手工验证项（需真实 opencode 运行时，可延后）：
   - 压缩 hook 抛错 / 超时 / 共存检测实测；
   - /context-inject 单通道失败返回部分结果 + failed_channels；
   - 注入失败 toast 不超过每会话 3 次。

## 等待项 / 阻塞

- 手工验证需真实 opencode 运行时，可延后。
- test_document/source_deduplication 两个文件一起跑必失败（全局 db 连接跨 asyncio loop 冲突，
  非顺序问题，pytest-order/改 loop scope 均无法解决），单独跑各自全绿；彻底修复需测试
  连接管理重构（TESTING.md 已记录根因，未排期）。
- 讨论中 topic（2026-08-14 重定位，围绕 [命题晋升总纲](notes/2026-08-14-proposition-promotion.md) 展开）：
  - S0 命题 6 维度 + S1 提炼机制（情景→语义）—— 灵魂；首轮讨论见 [promotion-judgment](notes/2026-08-14-promotion-judgment.md)（价值/触发/去向/安全门四桶），新调研已重启
  - S2 置信度涨落（[memory-confidence](notes/2026-08-14-memory-confidence.md)）
  - S3 触发 + 判定（[workbench](notes/2026-08-14-workbench-vs-debug-roles.md) 裁决 + layering 触发）
  - S4 归属迁移（[personal-vs-shared-boundary](notes/2026-08-14-personal-vs-shared-boundary.md)）
  - S5 召回消费端（[memory-layering-and-recall](notes/2026-08-14-memory-layering-and-recall.md)）

*状态: ACTIVE · 最后更新: 2026-08-14*
