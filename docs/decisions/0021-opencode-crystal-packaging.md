# ADR-0021: Opencode 插件 Crystal 形态 = 共享核 + 薄适配（双包）

> 状态: Accepted · 系统: crystal · 日期: 2026-08-20
> 关联: ADR-0018（系统命名 v5/crystal）· `plugin-migration-contract.md` · `migration-path.md` · `PROJECT_PLAN.md §0` · `notes/2026-08-20-opencode-crystal-v2-upgrade-plan.md §14`
> 决策人: wusisu + Sisyphus
> 取代: 无（新增）

## 背景

- 后端 Crystal 已就绪（`crystal.*` 9表 + `/api/v2` 23路由，M1-M3 全绿），需将 OpenCode Memory Recorder 插件从 v5（`/memories|/search|/context-inject` + `container_tag={keyId}(_project-x)`）切到 Crystal（`/api/v2/evidence|search|context-inject|workbench` + `scope=x|NULL`）。
- 上一版计划提出"全量 `cp -R opencode → opencode-crystal` 新目录"以求物理隔离，用户质疑必要性。需在"隔离度 vs 复用度 vs 维护成本"间拍板。
- 约束：`file://` 直连开发模式（`~/.config/opencode/opencode.jsonc` 指向源码）、`PROJECT_PLAN §0` 破坏性变更需先落 ADR、ADR-0018 命名空间隔离哲学（非分支隔离）。

## 已考虑选项

1. **全量复制新目录** `opencode → opencode-crystal`（1700L 共享代码双份，独立发包）
2. **原地分支/特性开关** 同目录 `git branch crystal` + `config.backend="v5"|"crystal"`
3. **共享核 + 薄适配** 抽 `src/_shared/` 1700L 单源，两插件仅保留 400L 差异层（推荐，见 §14.4）

量化：`wc -l src/*.ts = 4240L`，共享池 2196L (51.8%) 可直接复用，全量复制即冗余 2196L，漂移风险 >70%。

## 决策

**采用选项3的轻量版**：

- 新增 `apps/api/src/plugins/_shared/`（或 `src/plugins/opencode/src/shared/`）承载宿主无关核：`queue.ts` 370L, `tracker.ts` 134L, `logging.ts` 359L, `i18n.ts` 114L, `recall-trigger.ts` 44L, `context-guidance`（`context.ts` 中 AI 指导部分）, `config` 通用阈值关键词表。
- 保留 `apps/api/src/plugins/opencode/` 为 v5 薄适配层（`client-v5.ts`/`tool-v5.ts` 约 400L，re-export shared）。
- 新增 `apps/api/src/plugins/opencode-crystal/` 为 Crystal 薄适配层，仅 `client-crystal.ts`（`/api/v2` 端点映射 + scope + 信封 + 幂等键）、`tool-crystal.ts`（8 mode 语义重映射，删 `extract-memory`，增 `correct/forget/confirm`）、`config-patch.ts`（`getScope` 去 keyId 前缀，`verify_scope_ownership` 拒绝 `uuid_` 前缀）约 400L，其余 `import from "../_shared/*"`。
- 构建保持 `--external @opencode-ai/plugin --external @opencode-ai/sdk`，`tool.schema.*` 约束不变。
- 开发期 `file://` 指向可一键切换（`opencode.jsonc` 改一行），无需维护两套绝对路径；发布期双包并存（`memory-recall-opencode` 1.9.x vs `memory-recall-opencode-crystal` 0.1.0），M5 退役时 crystal 更名为 `memory-recall-opencode@2.x` 并 `git mv opencode → docs/archive/plugins/opencode-v5`。
- 补 `preflight.mjs` 复用 dsh 模式校验 `scope` 语义 + `/api/v2` 可达，CI 必过。

## 理由

- **复用最大化**：58% 代码单源，符合 DRY，dsh 已验证 `shared+生成物+预检` 范式优于复制。
- **契合契约**：`plugin-migration-contract` 逐宿主验证/回退均为包级别操作，无需文件系统分叉；ADR-0018 命名隔离在运行时层落地，非目录分叉。
- **合规**：先落 ADR 满足 `PROJECT_PLAN §0` 三件套，两端一致靠 crystal 薄层显式依赖 shared 版本。
- **成本可控**：一次性抽取 ~1人日，后续维护单点。

## 后果

- 正面：后续 queue/tracker/logging 修 bug 单点生效；M4 切 crystal 逐宿主验证清晰；回退符合契约（换包/换 `file://`）。
- 负面：初期需一次抽取重构，若 shared 仍耦合 `container_tag` 字段名会污染 crystal，需在 shared 中做概念中立化（`buildInjectConfig` 抽象）。
- 不做：全量复制、长期特性开关双路径。

## 实施

- Phase 1：抽 shared（零行为变更单 PR，先让现有 opencode 通过 shared 跑通）
- Phase 2：建 `opencode-crystal` 薄层 + `preflight` + 集成测试（临时库+ASGI，覆盖 scope 403/幂等/explain）
- Phase 3：`file://` 冒烟 `POST /api/v2/evidence 202 → 对账 → search/context-inject` 全链路
- 验证：A10 日志零旧路由 + 回退演练

*Accepted 后更新 `initiatives/crystal/README.md` 文件地图与 `STATUS.md`。*
