# 2026-08-19: memory-recall-dsh 新插件建设计划（crystal /api/v2 迁移）

> 类型: 计划 · 日期: 2026-08-19
> 关联: [crystal 插件切换契约](../../docs/initiatives/crystal/plugin-migration-contract.md)（M4）·
> [api-contract](../../docs/initiatives/crystal/api-contract.md)（§6 v5→crystal 映射）·
> [dsh 插件 README](../../../apps/api/src/plugins/dsh/README.md) ·
> [PLUGINS.md](../../docs/PLUGINS.md)
> 定位: 本文是 **dsh 端插件从 v5 路由切到 crystal `/api/v2` 的建设计划**——
> 现状盘点、切换设计、分步实施、验证与回退。dsh 是四端中影响面最大的一端（web 端），
> 按 [plugin-migration-contract §4](../../docs/initiatives/crystal/plugin-migration-contract.md) 顺序④ 最后切，
> 但**计划先行**，等 crystal 稳定观察期结束（M5 退役前）统一执行。

## 0. 一句话

**memory-recall-dsh 插件把 6 个记忆工具 + 自动召回 + 自动捕获的 v5 调用路径改为 `/api/v2`**：
`/memories` → `/api/v2/evidence`（写）+ `/api/v2/workbench/claims`（读），
`/search` → `/api/v2/search`，`/context-inject` → `/api/v2/context-inject`，
`/extract-memory` 移除（对账自动提炼取代），`/profile` → context-inject 画像层，
tag 语义（container_tag 全名）→ scope（项目部分或 NULL）；**切换动作延后**（用户拍板：
避免半切换两套逻辑并存，等 crystal 完整后统一做），本文先落计划。

## 1. 现状盘点（2026-08-19）

### 1.1 插件能力与调用点

| 能力 | 实现文件 | v5 调用 | 调用点数量 |
|------|---------|---------|-----------|
| 记忆工具 `memory_store` | tools.js | `POST /memories` | 1 |
| `memory_update` | tools.js | `POST /memories/{id}/update` | 1 |
| `memory_forget` | tools.js | `POST /memories/{id}/forget` | 1 |
| `memory_search` | tools.js | `POST /search` | 1 |
| `memory_profile` | tools.js | `GET /profile` | 1 |
| `memory_list` | tools.js | `GET /memories` | 1 |
| 自动召回 | index.js（agent/pre-step） | `POST /context-inject` | 1 |
| 自动捕获（extract） | capture.js | `POST /extract-memory` | 1 |
| 自动捕获（raw 回退） | capture.js | `POST /memories` | 1 |
| keyId 解析 | index.js / client.js | `GET /auth/verify` | 1（v5 保留） |

- 客户端封装集中在 `client.js` / `client-lib.js`（两份：`client.js` 是工具链入口，
  `client-lib.js` 是 bundle 用生成式副本，见 MR-023）；**改调用路径要两处同步改**。
- tag 语义：`userTag = keyId`，`projectTag = {keyId}_project-<cwd 目录名>`
  （config.js `projectTagFor`），全名拼在调用里。

### 1.2 与 crystal 的语义差异（关键）

| 维度 | v5 | crystal |
|------|----|---------|
| 写入 | `POST /memories`（同步落库 + embedding + 实体提取） | `POST /api/v2/evidence`（202 + pending，异步对账） |
| 容器 | `container_tag` 全名（`{keyId}` / `{keyId}_project-x`） | `owner`（鉴权层填）+ `scope`（项目部分或 NULL） |
| 读取 | `GET /memories` 返回文本记忆 | `GET /api/v2/workbench/claims` 返回"当前为真"Claim |
| 搜索 | `POST /search` 相似文本 | `POST /api/v2/search` 三级管道 + explain |
| 画像 | `GET /profile` 独立端点 | context-inject 画像层（claim_kind=preference） |
| 蒸馏 | `POST /extract-memory` 独立蒸馏 | 对账自动提炼（无独立端点） |
| 更新 | `PUT /memories/{id}/update` 版本链 | `POST /api/v2/workbench/claims/{id}/correct`（supersede 谱系） |
| 删除 | `DELETE /memories/{id}` 物理删 | `POST /api/v2/workbench/claims/{id}/forget`（retract 逻辑删） |
| 幂等 | 无（客户端去重） | evidence 幂等键（idempotency_key，sha256(session\|message\|content)） |

## 2. 切换设计

### 2.1 API 映射（client.js / client-lib.js 逐方法）

| 现有方法 | v5 路径 | crystal 路径 | 请求/响应变化 |
|---------|---------|-------------|--------------|
| `createMemory` | `POST /memories` | `POST /api/v2/evidence` | body：`container_tag` → `scope`（项目部分/NULL）；`+ idempotency_key`；响应：`{evidence_id, processing_state, accepted}` |
| `updateMemory` | `POST /memories/{id}/update` | `POST /api/v2/workbench/claims/{id}/correct` | body：`new_statement` + `reason` + `source_ref` |
| `forgetMemory` | `POST /memories/{id}/forget` | `POST /api/v2/workbench/claims/{id}/forget` | body：`reason` |
| `searchMemory` | `POST /search` | `POST /api/v2/search` | body 加 `scope`；响应 `results[].claim_id/statement/scores`；可带 `include_explain` |
| `profileMemory` | `GET /profile` | `POST /api/v2/context-inject`（无 query，读画像层） | 响应 `profile[]` 替代 `profile.static/dynamic` |
| `listMemories` | `GET /memories` | `GET /api/v2/workbench/claims` | 响应 `items[].claim_id/statement/status`；游标分页 `next_cursor` |
| `injectContext` | `POST /context-inject` | `POST /api/v2/context-inject` | `container_tag` → `scope`；`exclude_memory_ids` → `exclude_claim_ids` |
| `extractMemory` | `POST /extract-memory` | **移除**（对账自动提炼） | capture extract 模式改为：摘要 → `POST /api/v2/evidence`（source_kind=agent_add） |
| `verify` | `GET /auth/verify` | 保留（v5 鉴权端点，M5 前仍在） | 不变 |

### 2.2 关键设计决策（切换时拍板）

1. **capture extract 模式改道**：v5 是先蒸馏（LLM 判定值得保存）再落库；
   crystal 语义下对账自动提炼——**捕获改直接 `POST /api/v2/evidence`**（摘要原文 + source_kind=agent_add），
   值得不值得由对账 LLM 判定。`captureMinLength` 门槛保留（抑制碎片），
   `captureMinIntervalMs` 节流保留。**副作用**：对账判定"无值得保存"的 evidence 不会产生 claim，
   与 v5"蒸馏判定静默不存"语义对齐（不再需要 extract 回退 raw 分支）。
2. **tag → scope 转换**：`resolveTags` 返回 `{user, project}` 改为返回 `{scope}`——
   项目容器 → `scope=<cwd 目录名>`（去掉 keyId 前缀），用户容器 → `scope=null`。
   `projectTagOverride` 语义改为 scope 覆盖。
3. **幂等键**：capture 用 `sha256(session_id|message_id|content)` 前 32 位（evidence 幂等键契约），
   与 v5 插件侧去重（LRU/summary digest）并存——双保险。
4. **跨轮去重**：`exclude_memory_ids` → `exclude_claim_ids`（字段名对齐 crystal 契约）；
   per-agent LRU 逻辑不变。
5. **注入渲染**：crystal context-inject 返回 Claim（statement + scores），
   渲染文本由 `buildInjectionText` 适配（statement 替代 v5 content，可带置信度徽标）。
6. **`memory_store` 返回语义**：evidence 202 异步，返回 `evidence_id` + `accepted`；
   v5 返回 `id` + `status` 的工具 schema 字段名要对齐（工具契约变化提示给用户）。
7. **`memory_list`**：claims 列表 active 优先 + 游标分页；一期插件侧只取第一页（limit=100），
   分页按钮后续按需。

### 2.3 兼容策略（渐进不破坏）

- **配置开关**：加 `apiVersion: "v5" | "crystal"`（默认 `v5`），切换时设为 `crystal`，
  回退改回 `v5` 即恢复旧调用路径——避免"改代码即永久切"的风险。
- **双路径实现**：client.js 内每个方法按 `apiVersion` 分支（v5 路径保留不删，直到 M5 退役）。
- **启动自检**：`/auth/verify` 保留；crystal 模式加 `GET /api/v2/evidence?limit=1` 冒烟（401/403 检测鉴权）。

## 3. 分步实施（任务分解）

> 步骤 1–3 是代码改动（本地可完成）；步骤 4–5 需要宿主环境（用户在终端操作）。

| 步骤 | 内容 | 验收 | 依赖 |
|------|------|------|------|
| 1 | client.js / client-lib.js 加 `apiVersion` 分支 + 8 个方法改 `/api/v2` 路径（映射见 §2.1） | 单元测试 mock 断言路径/参数/响应解析 | 无（后端已就绪 M1–M3） |
| 2 | capture.js extract 模式改 `POST /api/v2/evidence`（幂等键 + agent_add）；移除 extractMemory 调用 | capture 集成测试：落 evidence 202 + 幂等命中 accepted=false | 步骤 1 |
| 3 | 工具层 tools.js 适配新响应字段（claim_id / evidence_id / scores）+ 工具描述更新 | 6 工具 E2E 测试全绿（连真实后端） | 步骤 1–2 |
| 4 | 注入渲染 buildInjectionText 适配 Claim 文本 + `exclude_claim_ids` | 自动召回注入测试：claim 文本折入 + 跨轮去重生效 | 步骤 1–3 |
| 5 | **宿主切换**：`bash install.sh --restart` + patch 设 `apiVersion: crystal` + 真实会话验证 | 访问日志无旧路由调用（A10）；功能冒烟（写 evidence → 对账 → 召回） | 用户在终端操作 |
| 6 | 回退演练：`apiVersion` 改回 v5 + 重启 | v5 插件路径恢复可用 | 步骤 5 后 |

## 4. 验证矩阵

| 验证项 | 方法 | 期望 |
|--------|------|------|
| 单元测试 | `node --test test/config.test.js` 等 | 配置/映射/边界全绿 |
| 集成测试（真实后端） | `node --test`（连 rk_live，缺 Key 自动跳过） | store→update→search→forget 全链路 claim 化 |
| 幂等 | 同一 session/message/content 连发两次 capture | 第二次 accepted=false |
| 跨轮去重 | 会话两轮同 query | 第二轮 exclude_claim_ids 生效，无重复注入 |
| fail-open | 后端不可达 | 插件不崩，仅日志（v5 既有保障） |
| A10 | 访问日志 grep `/memories` `/search` `/profile` `/extract-memory` | crystal 模式 0 命中 |
| 回退 | apiVersion=v5 重启 | v5 路径可用（契约 §5） |

## 5. 未决问题

1. **capture extract 改道后 "值得保存" 判定质量**：对账 LLM 判定 vs v5 蒸馏 LLM 判定，
   需观察一段时间的 claim 产出率（建议切换后对照 workbench 假说池/claim 生成率）。
2. **`memory_profile` 工具语义**：v5 返回独立画像；crystal 画像 = context-inject 画像层，
   工具是否保留（内部改调 context-inject 无 query）还是废弃（画像随注入自动给）——
   倾向保留工具（用户显式查画像），实现改调 context-inject。
3. **`memory_list` 分页**：游标分页是否在插件侧做完整 UI，还是仅第一页。
4. **切换时机**：按 plugin-migration-contract §4 顺序④（最后切），
   等 crystal 稳定观察期结束 + 退役标准部分达成（crystal 上线 ≥14 天无 P0/P1）后执行。

## 下一步

1. 等 crystal 稳定观察期（M5 退役条件未满足，2026-08-19 起 ≥14 天）。
2. 观察期结束、用户确认后：按本计划步骤 1–4 实施代码改动 + 测试（本地可先做）。
3. 宿主切换（步骤 5–6）由用户在终端执行 `install.sh --restart`。

## 结论

dsh 插件 crystal 迁移**设计已就绪、实施延后**：API 映射完整（§2.1）、
双版本兼容开关（§2.3）、分步任务（§3）、验证矩阵（§4）齐备；
唯一阻塞是切换时机（crystal 稳定观察期未满 + 用户拍板延后），非技术阻塞。
