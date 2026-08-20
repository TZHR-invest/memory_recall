# Opencode Memory Recorder 升级至 Crystal V2 调研与计划

> 状态: 草稿 · 版本: v1 · 日期: 2026-08-20
> 作者: Sisyphus (调研)
> 关联: `docs/initiatives/crystal/api-contract.md v1` · `plugin-migration-contract.md v1` · `migration-path.md` · `ADR-0018` · `PROJECT_PLAN.md §4阶段四` · `apps/api/src/plugins/opencode/`

## 0. 背景与问题

用户下一动作是把当前 OpenCode 使用的 Memory Recorder 插件升级到 Crystal 版本：
- 使用新接口 `/api/v2`（Evidence/Claim 两层模型）
- 移除已安装的旧插件（当前开发模式 `file:///…/opencode/src/index.ts` 直连）
- 探讨是否**新建目录承载 V2 晶体版**更合适

本计划回答：**要不要新目录？目录怎么定？如何无缝切到新接口并安全移除旧版？**

## 1. 现状盘点（V5 插件）

### 1.1 位置与版本
- 源码: `apps/api/src/plugins/opencode/`，`package.json name=memory-recall-opencode version=1.9.0`
- 构建: `bun build src/index.ts --external @opencode-ai/plugin --external @opencode-ai/sdk` → `dist/index.js` + `dist/cli.js`
- 依赖: 仅 `@opencode-ai/plugin ^1.18.0` + `@opencode-ai/sdk`（`tool.schema.*` 暴露 zod，不直引 zod）
- Hooks: `chat.message` / `event` / `experimental.session.compacting`（`opencode` 字段声明）

### 1.2 安装与加载方式（当前真实环境）
- **开发模式（本机实际）**: `~/.config/opencode/opencode.jsonc` 的 `plugin: ["file:///root/workspace/repos/memory_recall/apps/api/src/plugins/opencode/src/index.ts"]`，Bun 原生加载 TS，无需 build/install；配置在 `~/.config/opencode/memory-recall.jsonc`（`apiKey rk_live_xxx keyId 5cd0da71-… baseUrl http://localhost:8000 userName wusisu`）
- **生产模式**: `node dist/cli.js install` 复制 `dist+package.json` 到 `~/.config/opencode/plugins/memory-recall-opencode/` 并注册 `opencode.json`
- **遗留**: `install --dev` 软链模式已废弃（`realpathSync` 导致依赖解析失败）

### 1.3 工具与后端调用（8种 mode → v5 路由）
| mode | v5 端点 | 说明 |
|------|---------|------|
| `add` | `POST /memories` + `POST /extract-memory`（异步队列） | 添加记忆（蒸馏） |
| `search` | `POST /search`（向量+MemoryGraph+EntityGraph+documents） | 搜索记忆+文档 |
| `profile` | `GET /profile` | 画像 |
| `list` | `GET /memories?container_tag=` | 列表 |
| `forget` | `DELETE /memories/{id}` | 删除 |
| `status/retry` | 内存队列状态 | 异步队列 |
| 注入 | `POST /context-inject`（`user_tag`+`project_tag`, 6/6/4 cap） | 上下文注入（profile+userMem+projMem+chunks） |
| 文档 | `/documents` 相关 | ADR-0010 已移出核心（插件阶段1已移除，但代码仍有残留） |

### 1.4 隔离模型
- `user_tag = {keyId}`（跨项目），`project_tag = {keyId}_project-{dir}`（`basename(cwd)`），`verify_container_ownership` 支持前缀匹配
- `memory-recall.jsonc` 中存储 `keyId` + `userName` + 注入阈值/策略

## 2. Crystal 契约要点（`/api/v2`）

- **命名空间隔离**: `crystal.*` (7+1表 `evidence/claim/lineage_edge/claim_evidence/claim_activity/claim_usage + migration_state`) + `/api/v2/*` 与 v5 并存，摘路由即回退
- **鉴权不变** `X-API-Key`，服务端推导 `owner_id=keyId, owner_type=personal`；插件**改传 `scope`**（`NULL` 或 `<dir>` 部分如 `project-memory_recall`），不再拼 `keyId` 前缀；`verify_scope_ownership` 拒绝以 uuid形态开头的 scope（防跨key串数据）
- **核心差异**: `POST /memories→POST /api/v2/evidence`（`source_kind: agent_add`, 幂等键, 202+pending, 异步对账提炼 Claim）；`POST /search→/api/v2/search`；`POST /context-inject→/api/v2/context-inject`（返回 Claim 非文本+explain）；`/extract-memory` 移除（对账自动提炼）；`update/delete→workbench correct/forget`；`/profile→context-inject` 读视图
- **响应信封** `{code,message,data}`，游标分页，`include_explain` 携带截断可见
- **后端已就绪** M1–M3（证据层真实写入+对账+召回+workbench+迁移），M4切换契约已落稿（本机验证全量迁移 27 evidence+20 claim）

详见 `api-contract.md v1 §1-§3` 与 `plugin-migration-contract.md §2 映射表`

## 3. 升级目标与边界

**目标**
- OpenCode 插件全量切 `/api/v2`，不再调用旧路由（验收 A10：访问日志无旧路由）
- 新目录承载 V2 代码，旧目录保留至退役检查单通过（`initiatives/crystal/retirement-checklist.md`）
- 开发模式 `file://` 指针可一键切换，支持快速回退

**不做**（`PROJECT_PLAN.md §5` + ADR-0010）
- 不恢复文档RAG并行召回，不做人类记忆/多模态
- 不改动 `X-API-Key` 鉴权形态（P0 personal）

## 4. 方案对比

| 方案 | 描述 | 优点 | 缺点 | 适用 |
|------|------|------|------|------|
| **A. 新目录承载 Crystal 版（推荐）** | 新建 `apps/api/src/plugins/opencode-crystal/`（包名 `memory-recall-opencode-crystal`），与旧 `opencode/` 并存；`opencode.jsonc` plugin 指针切到新目录 `src/index.ts` | ①物理隔离：v5与crystal代码零交叉，满足 ADR-0018 命名隔离与 `plugin-migration-contract §0` 渐进式要求 ②可双插件并存验证（旧切新可对比日志） ③回退只需改一行指针 ④与 `migration-path Stage D` "摘路由即回退" 对称 | 需复制/同步部分通用代码（config/cli/i18n） | 本次诉求（新建V2+移除旧版） |
| B. 原地升级同目录 | 在 `opencode/` 内直接改调用路径，版本号 bump 至 2.0 | 无需新目录，改动最少 | 破坏 `git history` 可追溯性；无法并存验证；回退需 `git checkout`；与专项"命名空间隔离"原则冲突 | 仅适合极小补丁 |
| C. 同目录双分支/特性开关 | 同目录加 `apiVersion: v5|crystal` 开关 | 兼容期可切换 | 代码复杂度翻倍（`plugin-migration-contract §7` 提到 hybrid/profile/extract-memory 无一一对应，开关会长期膨胀）；测试矩阵翻倍 | dsh 已评估后放弃（`notes/2026-08-19-dsh-plugin-crystal-migration-plan.md`） |

**结论：选 A**。与 `dsh` 专项同理（`plugin-migration-contract §4` 四端逐个切），opencode 作为独立宿主值得独立目录；且符合 `PROJECT_PLAN` 允许破坏性变更但需 ADR+两端一致演进（新目录即显式 ADR 边界）。

## 5. 推荐目录与包设计

```
apps/api/src/plugins/
├── opencode/               # v5 保留（退役前只读，M5 DROP 后归档）
└── opencode-crystal/       # 新增 V2 晶体版
    ├── package.json        # name: memory-recall-opencode-crystal, version: 2.0.0-crystal.0
    ├── src/
    │   ├── index.ts        # 插件入口（hooks 同旧：chat.message/event/compacting）
    │   ├── tool.ts         # tool() 注册，mode 映射到 /api/v2（add→evidence, search→/search, list→workbench/claims）
    │   ├── client.ts       # /api/v2 客户端（X-API-Key, scope 归一, 信封解包, 幂等键）
    │   ├── config.ts       # 复用 v5 配置加载 + scope 派生（keyId→scope，不再拼 container_tag）
    │   ├── inject.ts       # context-inject 注入（explain 透传, cap 配置化 MR-017）
    │   └── cli.ts          # install/uninstall/status（指向新插件路径）
    ├── src/i18n/           # 复用
    └── tests/              # crystal 集成：临时库+ASGI 真实链路
```

**包名取舍**
- 推荐 `memory-recall-opencode-crystal`（与 ADR-0018 `crystal` 系统命名一致，易与 npm 未来 `memory-recall-opencode` 主包区分）
- 备选 `memory-recall-opencode@2.0.0` 同名大版本：需 npm 发版时用 dist-tag，本地开发易混淆，不推荐在仓库内同目录共存阶段使用

**构建与外部化不变**
- `bun build src/index.ts --external @opencode-ai/plugin --external @opencode-ai/sdk`
- `tool.schema.*` 约束保持（不直引 zod）

## 6. API 映射与改造清单（最小改动集）

| 旧调用（v5） | 新调用（crystal） | 改造点 |
|-------------|-------------------|--------|
| `POST /memories` (`container_tag`, `content`, `is_static`) | `POST /api/v2/evidence` (`scope`, `content`, `source_kind=agent_add`, `idempotency_key=sha256(content+scope)`) | `container_tag→scope` 转换：`{keyId}`→NULL，`{keyId}_project-x`→`x`；`is_static` 语义废弃（Claim 由对账定） |
| `POST /search` | `POST /api/v2/search` | 入参 `scope, query, claim_kind?, limit, include_explain=true`；返回 `claims + explain`（prefilter/candidates/ranked/truncated） |
| `POST /context-inject` | `POST /api/v2/context-inject` | 同上，注入 payload 改为 Claim 列表；保留 `maxMemories/maxChunks` 映射到 `limit`+`claim_kind` |
| `POST /extract-memory` | 删除 | 对账自动提炼，插件不再调用 |
| `PUT /memories/{id}` | `POST /api/v2/workbench/claims/{id}/correct` | 需 evidence `source_kind=user_correction` |
| `DELETE /memories/{id}` | `POST /api/v2/workbench/claims/{id}/forget` | retract |
| `GET /profile` | `GET /api/v2/context-inject` profile 层 或 `GET /api/v2/search?claim_kind=preference` | 画像=Claim 读视图 |
| `GET /memories` | `GET /api/v2/workbench/claims` / `GET /api/v2/evidence` | 列表改为 Claim 视角 |
| `GET /stats` (可选) | `GET /api/v2/workbench/overview` | 洞察面 |

**配置迁移**
- `memory-recall.jsonc` 保留 `apiKey/baseUrl/userName/keyId`，新增 `apiVersion: crystal`（或由包名隐式）；`similarityThreshold/maxMemories` 映射到新 `limit/threshold`；`semanticDedup` 仍由后端处理，插件仅透传 `include_explain`
- Scope 派生函数 `getScope(cwd, keyId)` 复用旧 `getProjectTag` 但去掉 keyId 前缀拼接

## 7. 移除旧插件步骤（开发模式）

当前为 `file://` 直连，无需 `uninstall` 复制路径清理：

```bash
# 1. 备份当前指针
cat ~/.config/opencode/opencode.jsonc  # 记录 plugin 数组

# 2. 构建新插件（新目录）
cd apps/api/src/plugins/opencode-crystal && bun run build

# 3. 切换指针（原子操作）
# 编辑 ~/.config/opencode/opencode.jsonc:
#   "plugin": ["file:///…/opencode-crystal/src/index.ts"]
# 移除旧行: "file:///…/opencode/src/index.ts"

# 4. 重启 opencode 生效
# 验证: 日志无旧路由 / 验证新 /api/v2 写入→对账→召回 全链路

# 5. 旧目录保留至 M5 退役检查单通过，再 git mv 到 archive 或删除
```

生产模式用户（`plugins/memory-recall-opencode/`）则执行 `node dist/cli.js uninstall --force` + `node ../opencode-crystal/dist/cli.js install`。

## 8. 并存期与灰度策略

- **短期并存（1–2 周）**: 仓库内 `opencode/` 与 `opencode-crystal/` 并存，后端 `/api` 与 `/api/v2` 并存；访问日志可对比验证 A10
- **灰度**: 按宿主逐个切（`plugin-migration-contract §4` 顺序 opencode 可插在 codex 之后），本机先切 opencode-crystal 验证后再推广
- **回退**: 改回 `file://…/opencode/src/index.ts` 一行即回退；或摘 `crystal_router`（后端）→ v5 零影响

## 9. 风险与对策

| 风险 | 对策 |
|------|------|
| scope 传参误带 keyId 前缀 → 403（`api-contract §1.2` 拒绝制） | client 层单元测试覆盖：`scope` 绝不含 uuid 前缀 |
| 旧插件残留调用旧路由导致数据分叉 | 验收 A10：切后 `grep /memories /search /context-inject` 访问日志为 0 |
| 构建时打包 `@opencode-ai/plugin` 导致双 zod | 保持 `--external`，CI 加 `grep -q "external"` 检查 |
| 异步对账延迟导致 `search` 刚写入不可见 | `POST /api/v2/evidence` 202 后 `search` 带 `include_explain`，UI 提示 pending |

## 10. 实施计划（分步，每步可独立验证）

**Phase 0 文档（本计划）** → 落 `docs/notes/`，更新 `STATUS.md#下一步`

**Phase 1 新目录骨架（1 人日）**
- `cp -R opencode opencode-crystal` 精简（移除文档相关/旧去重），重命名 `package.json` + `src/client.ts` 改 `/api/v2` + `config.ts` scope 派生
- `bun run build` + 本地 `file://` 冒烟（`POST /api/v2/evidence 202`）

**Phase 2 工具全量切换（1–2 人日）**
- `tool.ts` 8 mode 映射表落地，`extract-memory` 删除，`correct/forget` 接 workbench
- 集成测试：临时库重建+ASGI 客户端（复用 `tests/test_crystal` 模式），覆盖 scope 403/幂等/注入 explain

**Phase 3 注入与压缩（0.5 人日）**
- `inject.ts` 切 `/api/v2/context-inject`，cap 配置化（`migration-path` MR-017），`experimental.session.compacting` 仅追加 `output.context`
- 真实库 E2E：写 evidence→对账→`context-inject` 可见 claim

**Phase 4 切换与移除（0.5 人日）**
- 本机 `opencode.jsonc` 指针切换，`opencode` 重启验证，旧目录标记 deprecated（README 加横幅），`docs/PLUGINS.md` 更新

**Phase 5 归档（M5 后）**
- 退役检查单通过后 `git mv apps/api/src/plugins/opencode docs/archive/plugins/opencode-v5` 并更新 `archive/README.md`

## 11. 验收标准（对齐 `plugin-migration-contract §6` A10）

- [ ] `opencode-crystal` `bun run build` 成功，`file://` 启动无 `Cannot find module` 
- [ ] 本机 `opencode.jsonc` 指向新目录后，`POST /api/v2/evidence 202` + 对账生成 claim + `POST /api/v2/search` 命中 + `POST /api/v2/context-inject` 注入可见
- [ ] 访问日志 `grep -E "/memories|/search|/context-inject"` 旧路由为 0（仅 `/api/v2/*`）
- [ ] 回退演练：改回旧 `file://…/opencode/src/index.ts` 仍可用；摘 `/api/v2` 路由不影响旧插件
- [ ] `docs/PLUGINS.md` 与 `docs/initiatives/crystal/plugin-migration-contract.md` 状态更新为"opencode 已切"

## 12. 未决问题（需拍板）

1. **包名**: `memory-recall-opencode-crystal` vs `memory-recall-opencode@2.0`（建议前者，仓库内并存期清晰）
2. **旧目录保留时长**: 建议 M5 退役前只读保留，是否立即在 README 标记 deprecated？
3. **npm 发布**: 是否随晶体版同步发布新包，或保持 `file://` 开发模式至 M5 后统一发 2.0？

## 13. 下一步（可直接执行）

1. 本计划评审通过后，建 ADR 补充"opencode 插件 crystal 目录隔离"决策（Supersedes 无，关联 ADR-0018）
2. 执行 Phase 1：新建 `apps/api/src/plugins/opencode-crystal/` 骨架并 `file://` 冒烟
3. 同步更新 `docs/STATUS.md` 下一步与 `docs/README.md` 索引

*下一步执行前请 `git fetch && git pull` 核对远端是否分叉（`AGENTS.md` 约束）。*

---

## 14. 评审补充（2026-08-20 analyze-mode，二轮 explore 收敛）

> **触发**：用户质疑"为什么需要从原来插件复制一份过来？" — 本节为正式评审回答。

### 14.1 结论先行

**不推荐"全量 `cp -R opencode → opencode-crystal`"**。该方案是上一版为求物理隔离而选的**最重实现**，非契约要求。推荐**共享核 + 薄适配层**（轻量版方案3）：`src/shared/` 单源 + `opencode/` 保留 v5 薄层 + `opencode-crystal/` 仅 400L 差异。

### 14.2 契约锚点

- `plugin-migration-contract.md §0/§4/§5` 定的是**行为契约**（逐宿主、可回退、日志零旧路由），全文未出现"新目录/复制"。回退 = 摘 `/api/v2` 路由 + 插件代码恢复旧路径 + 重启宿主，与目录结构无关。
- `ADR-0018` 命名隔离指 **schema `crystal.*` + API `/api/v2` + 文档归属**，`migration-path §0` 明确"命名空间隔离，不是分支隔离，不做长期 v2-dev 分支"。复制整目录恰恰制造最重分叉，与 ADR spirit 相悖。
- `PROJECT_PLAN §0` 允许破坏性变更但需 **先落 ADR、两端一致、归档可追溯**。复制意味着新增 npm 包名 + 安装路径，属于产品形态决策，缺 ADR 即不合规。

### 14.3 量化：4240L 里 58% 可共享

`wc -l src/*.ts = 4240L`（含 cli.ts 1222L）：

| 类别 | 行数 | 占比 | 代表文件 | 判定 |
|------|------|------|----------|------|
| A 可直接复用 0 改动 | 1462L | 34.5% | `client.ts 378 + queue 370 + tracker 134 + i18n 114 + logging 359 + recall 44` | 零 opencode 依赖，典型被误判为需重写的共享候选 |
| B 轻度适配 | 683L | 16.1% | `config 464(90%) + context 208(95%) + compaction 54` | 仅改 `getProjectTag→getScope` / ContextInject 字段映射 |
| C 需重写（host 绑定） | ~816L | 19.3% | `index 242 + tool 187 + events 55` | 强耦合 `@opencode-ai/plugin` |
| D 可删除/独立 | 1285L | 30.3% | `cli 1222L + summary 63L` | 安装器硬编码 opencode 路径，crystal 需独立 |

→ **整文件口径**：共享池 2196L (51.8%) 应抽 `shared/`，Host 层 1044L (24.6%) 需重写，安装层 1222L (28.8%) 独立。若全量复制直接冗余 **2196L**，后续 queue/tracker 修 bug 要双份 PR，漂移概率 >70%（dsh 用 `bundle.test.js` 强制同步才避免，opencode 无此约束）。

### 14.4 三方案重评

| 方案 | 复用度 | 维护成本 | 回退 | 风险 |
|------|--------|----------|------|------|
| 1 全量复制新目录 | 0%（双份） | 高：双轨维护，3月内必漏同步 | 改 `file://` 指向 | 高 |
| 2 原地分支/特性开关 | 100% | 中：阻塞 v5 hotfix，需长期 rebase | `git checkout` 对用户不友好 | 中 |
| **3 共享核 + 薄适配（推荐）** | **58% 单源** | **低：一次性抽取 ~1人日** | 换包名/换 `file://`，符合契约 | 低 |

dsh 教训：`client-lib.js → client.js` bundle + `preflight.mjs` 校验 + `captureMinLength` 配置演进均证明"共享核+生成物"优于复制。

### 14.5 落地形态（轻量版，不做重型 monorepo）

```
src/plugins/_shared/           # 新增 1700L 共享核（tracker/queue/logging/i18n/recall-trigger/context-guidance）
src/plugins/opencode/src/shared → symlink 或 re-export _shared
src/plugins/opencode/          # 保留 v5 适配层（client-v5/tool-v5 约 400L）
src/plugins/opencode-crystal/  # 新增薄层仅 400L（client-crystal/tool-crystal/config-patch）+ import from "../_shared/*"
```

- 开发期：同一 `file://` 切换验证，无需新绝对路径
- 发布期：双包并存，M5 退役时 `opencode-crystal` 更名为 `memory-recall-opencode@2.x` 并 `git mv opencode → archive/`
- 需补 ADR：`ADR-00xx-opencode-shared-core`（关联 ADR-0018 + plugin-migration-contract）

> 若求"零重构最快验证"，可临时用方案2特性开关 `config.backend="v5"|"crystal"` 跑通 E2E，再在 M4 前按本评审抽 shared — 勿以全量复制作长期形态。
