# MR-027: 画像通道混装与污染（static/dynamic 合并渲染 + dynamic 无闸门 + 写入静默回退用户容器）

> 状态: **已解决（2026-09-30，已上线）** · 严重度: P1 · 发现: 2026-09-30（.205 机器 dsh 会话实测）· 系统: v5 · 关联: [MR-017](MR-017-injection-caps.md)（同类「Pydantic 静默丢弃未知字段」）、[MR-008](MR-008-profile-cache.md)
>
> 落地 commit：（见文末「落地」）· 过程记录: [docs/notes/2026-09-30-profile-channel-pollution-fix.md](../notes/2026-09-30-profile-channel-pollution-fix.md)

## 现象（用户可见）

.205 机器 dsh 会话**每次新会话首轮**注入 23,674 字召回块，其中 **81% 是历史 cron prompt 全量备份**；
这些留档显示在「### 永久特征」小节下，被用户/agent 误读成"永久记忆"，实际是 dynamic（近期活动）条目。

实测（2026-09-30，`POST /context-inject`，`inject_profile=true, max_profile_items=5`）：

| 指标 | 修复前 |
|---|---|
| `context` 总长 | 20,930–23,968 字 |
| 「### 永久特征」小节 | 20,621 字（其中 3 条 cron 备份 ≈ 19,029 字） |
| `stats.profile_count` | 15（static 10 条/976 字 + dynamic 5 条/19,645 字） |
| `GET /profile` | static 10 条/976 字；dynamic 10 条/21,264 字（3 条备份占 89%） |

## 三处缺陷与根因

### D1 渲染口径：`### 永久特征` 下混装 static + dynamic

`_format_context_with_tags` 把 `source=="profile"` 的**全部**条目渲染在同一标题下，
而 static/dynamic 在 `_collect_items_with_tags` 里被打成同一个 source（两桶在响应里无任何区分字段，
`sources.profile` 是 `static + dynamic` 拼接的纯字符串数组）。

**影响**：dynamic（近期活动）被读成永久特征；客户端因此**无法**区分画像桶。
**修复**：分层渲染 `### 永久特征`（static）+ `### 近期动态`（dynamic），
`DedupItem` 增 `bucket` 字段承载来源桶；`sources.profile` 保持字符串数组不变（见「不破坏的契约」）。

### D2 入选规则：dynamic 无体量闸门、且不认 `profile_worthy`

- `memory_store.get_dynamic_memories` = `is_static=FALSE ORDER BY created_at DESC LIMIT N`，**无长度约束**；
- 2026-08-18 画像净化引入的 `metadata.profile_worthy=false` **只作用于 static 桶**
  （`profile_service._build_profile` 里 dynamic 原样返回）——退出画像的开关是半成品。

**影响**：单条 8–9K 字留档即可吃掉整个首轮预算，真偏好（976 字）被埋，每会话重复付费。
**修复**：dynamic 桶对称认 `profile_worthy=false`；两桶统一施加单条长度闸门
（`PROFILE_ITEM_MAX_CHARS=600`，超长截断并标注，`stats.profile_truncated_count` 可见）。

### D3 容器归属：`metadata.scope="project"` 的记忆落在用户容器

`mem_855a3e36a3ca4321b19c`(8,950 字)/`mem_cb9a10b5a8e14f8e82cf`(7,954 字) 的 metadata 写着
`{"kind":"cron_prompt_backup","type":"project-config","scope":"project"}`，容器却是用户容器
`085288ba-8eab-439b-b0d4-b92382e0f95d`。

**根因不是后端 scope 推导，而是写入方绕过了 MCP 工具**（本项在原始报告里被误判为后端嫌疑）：

- `POST /memories` 的 `CreateMemoryRequest` **根本没有 `scope` 字段**，容器解析只有一行
  `container_tag = request.container_tag or current_user["container_tag"]`；
- 实际写入方是 hermes 侧临时脚本（R847 那次为 `/tmp/r847_prompt_update.py`，原文见
  `~/.hermes/state.db` 的 `messages.tool_calls`）：body 为
  `{content, skip_extraction, async_process, metadata:{type,scope,round,kind}}`，
  **完全没传 `container_tag`** ⇒ 落用户容器；`metadata.scope` 被 Pydantic 静默丢弃
  （与 MR-017 同一 bug 类）。2026-09-12 的两条同类留档出自更早版本的同一模式脚本。
- 四端插件的 MCP 工具映射本身是对的（dsh `tools.js`、hermes `_tag(scope)` 都显式传 `container_tag`）。

**修复（fail-closed）**：`POST /memories` 校验 `metadata.scope` 与解析出的容器是否一致，
不一致（含"声明 project 却落用户容器"）直接 422 并给出可操作信息，**绝不静默回退**。

### D4 （附带）v2 路由在缺 schema 时裸 500

`POST /api/v2/search` → 500 `relation "crystal.claim" does not exist`。
**这不是线上故障而是"未部署"**：crystal schema 只存在于 `memory_recall_test`（9 表），
生产库 `memory_recall`（9,780 条记忆）没有；crystal 专项的 M4 插件切换本就未做，
近 7 天 `/api/v2` 仅有 3 次请求（.205 探针 + 复核探针）。
**修复**：v2 在 crystal schema 缺失时返回统一信封 503（`CRYSTAL_SCHEMA_MISSING`），
不再把"未部署"暴露成不可诊断的 500。真正的上线（跑 `init_crystal_db.py`）仍按 M4/M5 退役标准推进。

## 数据处置（已执行）

4 条超长留档（>2,000 字）**先导出原文**到 `apps/api/backups/profile-pollution-20260930/`，然后：

1. 打 `metadata.profile_worthy=false`（退出画像通道，仍可向量召回）；
2. 容器迁到 `085288ba-…_project-hermes`（内容本就是 hermes cron 的存档）；
3. 清画像缓存（`memory_profiles`）后验收。

## 验收（全部通过）

1. `context` 总长 20,930 → **1,916 字**，「永久特征」小节只含 static 偏好（976 字级）；
2. 用户容器里不再有超长 project 作用域留档（`§7-3` 复现命令输出空）；
3. `POST /api/v2/search` 返回 **503 + 统一信封**（不再是 500）；
4. 端到端：.205 新建会话注入块不再含 cron 备份。

## 不破坏的契约

- `sources.profile` 仍是**字符串数组**（`static + dynamic`）——改成对象数组会破坏 codex/hermes 等客户端，
  故只做**追加式**演进：桶信息通过 `context` 的分节标题 + `stats` 暴露；
- `sources.memories[]`/`user_memories[]` 的 `{id, content}` 字段名不变（dsh 靠 `id` 做跨轮去重）；
- `POST /context-inject` 请求/响应字段名不变，新增字段仅 `stats.profile_truncated_count`。

## 落地

| 缺陷 | 改动文件 |
|------|---------|
| D1 分层渲染 | `src/services/core/context_inject_service.py`（`_format_context_with_tags` 分节、`_collect_items_with_tags` 打 `bucket`）、`src/services/core/semantic_dedup_service.py`（`DedupItem.bucket`） |
| D2 长度闸门 + opt-out 对称 | `src/services/core/context_inject_service.py`（`PROFILE_ITEM_MAX_CHARS` / `_truncate_profile_items` / `stats.profile_truncated_count`）、`src/services/core/profile_service.py`（`_build_profile` dynamic 桶认 `profile_worthy`） |
| D3 写入闸门 | `src/api/memories.py`（`_assert_scope_container_consistency`，422 fail-closed） |
| D4 v2 503 | `src/api/crystal/guards.py`（新增）、`src/api/crystal/__init__.py`（统一依赖）、`docs/initiatives/crystal/api-contract.md` §3.1 |
| 测试 | `tests/test_v2/test_profile_channel_buckets.py`、`tests/test_api/test_create_memory_scope_guard.py`、`tests/test_crystal/unit/test_schema_guard.py`（22 用例） |

落地 commit：（见下）

