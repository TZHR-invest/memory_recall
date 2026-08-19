# 插件切换契约 v1（M4 前置产物）

> 状态: 草稿（M4 开工依据） · 系统: crystal · 版本: v1 · 最后更新: 2026-08-19
> 关联: [迁移路径](migration-path.md)（Stage D）· [API 契约](api-contract.md)（v5→crystal 映射 §6）·
> [里程碑](milestone.md)（M4）· [PRD](prd.md)（A10）· [PLUGINS.md](../../../docs/PLUGINS.md)
> 定位: 本文是 M4（插件切 /api/v2）的**接入/回退契约**——四端各自接入方案、映射、
> 切换顺序、回退演练、验收。**切换动作涉及真实插件宿主环境，按宿主逐个进行、逐个验证**。

## 0. 一句话

**四端插件（opencode / codex / hermes / deepseek-tui / dsh）从 v5 路由切到 `/api/v2`**，
按「渐进式、逐个宿主、可回退」推进：后端契约已就绪（M1–M3），插件侧逐个改调用路径，
每个宿主验证后再切下一个；任一宿主出问题即回退该宿主（摘路由/恢复旧调用）。

## 1. 插件清单与宿主环境

| 插件 | 目录 | 宿主 | 调用点 | 状态 |
|------|------|------|--------|------|
| memory-recall-codex | `src/plugins/memory-recall-codex/` | codex CLI/VSCode | ~10（memories/search/profile/extract-memory/context-inject/update/forget/restore） | 待切 |
| hermes | `src/plugins/hermes/` | hermes（Python MCP stdio） | ~9 | 待切 |
| deepseek-tui | `src/plugins/deepseek-tui/` | deepseek-tui（Python MCP stdio） | ~9 | 待切 |
| memory-recall-opencode | `src/plugins/opencode/` | opencode（TS/Bun） | ~10 | 待切 |
| memory-recall-dsh | `src/plugins/dsh/` | dsh web（ESM JS） | ~10（5 工具 + 自动捕获/注入） | 待切 |

> omp/openclaw 为实验/遗留，不在本期切换范围（migration-path §6 四端 = codex/hermes/deepseek-tui/opencode/dsh）。

## 2. API 映射（api-contract §6 速查）

| v5 调用 | crystal 调用 | 变化 |
|---------|-------------|------|
| `POST /memories` | `POST /api/v2/evidence` | container_tag → scope + owner（鉴权层填）；异步对账 |
| `GET /memories?container_tag=` | `GET /api/v2/workbench/claims`（+ `GET /api/v2/evidence`） | 返回"当前为真"Claim 列表，非文本记忆 |
| `POST /search` | `POST /api/v2/search` | + explain / + active 预过滤；`claim_kind` 过滤 |
| `POST /context-inject` | `POST /api/v2/context-inject` | 同语义 + explain；返回 Claim 非相似文本 |
| `POST /extract-memory` | （crystal 对账自动提炼） | 无独立端点；证据采集走 evidence 上报 |
| `PUT /memories/{id}/update` | `POST /api/v2/workbench/claims/{id}/correct` | 版本链 → supersede 谱系 |
| `DELETE /memories/{id}` | `POST /api/v2/workbench/claims/{id}/forget` | 物理删 → retract 逻辑删 |
| `GET /profile` | `GET /api/v2/context-inject`（profile 层） | 画像 = Claim 读视图（claim_kind=preference） |

**鉴权**：`X-API-Key` 不变；owner 由服务端解析（插件不再传 container_tag 全名，改传 scope 部分）。

## 3. 接入方案（每端通用步骤）

```text
1. 后端就绪（已完成 M1–M3：/api/v2 全路由 + 迁移）
2. 插件侧：改 api_request 路径 + 参数语义
   - container_tag（{keyId} 或 {keyId}_project-<dir>）→ scope（<dir> 部分或 NULL）
   - /memories → /api/v2/evidence（写）/ /api/v2/workbench/claims（读）
   - /search → /api/v2/search；/context-inject → /api/v2/context-inject
   - /extract-memory 调用移除（对账自动提炼）
   - update/delete → workbench correct/forget
3. 宿主重启生效（各插件 install.sh / --restart / MCP 重启）
4. 验证：访问日志核对无旧路由调用（A10）；回退演练过
```

## 4. 切换顺序（渐进式）

| 顺序 | 宿主 | 理由 | 回退方案 |
|------|------|------|---------|
| ① | **codex** | 用户主用端之一，验证最快 | 恢复旧 api_request 路径 + 重启 |
| ② | **hermes / deepseek-tui** | Python MCP stdio，同构 | 同左 |
| ③ | **opencode** | TS/Bun 构建 | 同左 |
| ④ | **dsh** | web 端，影响面最大 | 同左 |

> 每个宿主切完即验证（访问日志 + 功能冒烟），再切下一个；任一失败即回退，不阻塞其余。

## 5. 回退演练

- **摘 /api/v2 路由**（migration-path §0）：删 `crystal_router` 注册 → v5 零影响（v5 路由从未移除）。
- **插件回退**：恢复该宿主插件代码中 v5 调用路径 → 重启宿主。
- **数据回退**：迁移幂等可重放（M3）；误迁 claim 可经 workbench forget 清理。

## 6. 验收标准（对应 PRD A10 / US-M*）

- [ ] **A10**：四端切 /api/v2 后访问日志无旧路由调用（`/memories`、`/search`、`/context-inject` 等）。
- [ ] **回退演练过**：摘路由后 v5 插件正常；插件回退路径可复现。
- [ ] **功能冒烟**：每端写入一条 evidence → 对账 → 召回（注入/搜索）可见 claim。
- [ ] **v5 零影响**：切换期间 v5 插件（未切端）持续可用。

## 7. 未决 / 后续

- **extract-memory 移除**：v5 蒸馏端点（/extract-memory）在 crystal 语义下被对账提炼取代；
  插件端移除调用后，v5 端点保留（回退兼容）直到 M5 退役。
- **dsh 插件自动捕获**：capture 工具改 POST /api/v2/evidence（幂等键防重），
  注入改 POST /api/v2/context-inject（explain 可观测）。
- **各端真实切换时机**：依赖宿主环境可用性（用户在终端操作），按 §4 顺序逐个推进。

*状态: 草稿 · 最后更新: 2026-08-19*
