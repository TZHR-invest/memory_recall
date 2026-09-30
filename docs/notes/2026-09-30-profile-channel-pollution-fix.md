# 2026-09-30: 画像通道污染治理（static/dynamic 混装 + dynamic 无闸门 + 写入静默回退用户容器）

> 类型: 修复记录（含根因调研）
> 日期: 2026-09-30
> 参与: 用户（拍板处理范围与数据处置）/ ai-agent(206) 侧 agent
> 关联: [MR-027](../issues/MR-027-profile-channel-pollution.md) · 落地 commit `14923bc` · [MR-017](../issues/MR-017-injection-caps.md)（同类 Pydantic 静默丢字段）· [MR-008](../issues/MR-008-profile-cache.md) · 2026-08-18 画像净化笔记

## 背景

.205 机器的一个 dsh 会话在使用 memory-recall 插件时发现：**每个新会话首轮注入 23,674 字**，
其中 81% 是历史 cron prompt 全量备份，且这些留档显示在「### 永久特征」小节下，
被用户/agent 读成"永久记忆"。.205 侧 agent 把排查写成修复单
（`~/.205:/home/wbaifan/memory-recall-backend-fix-20260930.md`，3+1 处缺陷），交 206 侧处置。

## 调研发现（逐条复现）

| 编号 | 修复单定性 | 复核结论 |
|---|---|---|
| D1 | `### 永久特征` 混装 static + dynamic | **属实**：两桶在 `_collect_items_with_tags` 打成同一 source，标题写死 |
| D2 | dynamic 按时间倒序取 N、无体量约束 | **属实且更严重**：`profile_worthy=false`（08-18 净化引入的"退出画像"开关）**只对 static 生效**，dynamic 完全不认 |
| D3 | `scope=project` 落用户容器，疑后端推导错 | **定性修正**：`POST /memories` 根本没有 `scope` 字段，容器只由 `container_tag` 决定（`container_tag or current_user["container_tag"]`）。真实写入方是 hermes 侧临时脚本（`/tmp/r847_prompt_update.py`，原文在 `~/.hermes/state.db` 的 `tool_calls`）——只发 `metadata.scope` 不发 `container_tag` ⇒ 落用户容器。四端插件映射本身是对的 |
| D4 | `/api/v2/search` 500（`crystal.claim` 不存在） | **属"未部署"非故障**：crystal schema 只在 `memory_recall_test`（9 表），生产库（9,780 条记忆）从未初始化；M4 插件切换本就没做，近 7 天 `/api/v2` 仅 3 次请求 |

关键取证命令（复现用）：`POST /context-inject` 见 MR-027 §验收；写入方取证：

```bash
python3 - <<'PY'
import sqlite3, json
con = sqlite3.connect('file:/home/wbaifan/.hermes/state.db?mode=ro', uri=True)
for mid, sid, ts, tc in con.execute(
    "SELECT id, session_id, timestamp, tool_calls FROM messages WHERE tool_calls LIKE '%cron_prompt_backup%'"
):
    ...
PY
```

## 结论（已实施）

1. **MR-027 D1**：画像分层渲染 —— `### 永久特征`(static) / `### 近期动态`(dynamic)；
   `DedupItem` 增 `bucket` 字段承载来源桶；`sources.profile` **保持字符串数组**（改对象数组会破契约）。
2. **MR-027 D2**：dynamic 桶对称认 `profile_worthy=false`；两桶统一单条长度闸门
   `PROFILE_ITEM_MAX_CHARS=600`（截断 + 标注 + `stats.profile_truncated_count`）。
3. **MR-027 D3**：`POST /memories` 加 fail-closed 一致性闸门（`metadata.scope` 与容器冲突 ⇒ 422，不落库）；
   实测 422 + 零落库。全库仅 2 条记忆用过 `metadata.scope`，无合法调用方会被误伤。
4. **MR-027 D4**：`/api/v2/*` 前置闸门 `guards.require_crystal_schema` —— schema 缺失 ⇒ 503 + 统一信封
   + 处置指引（run `init_crystal_db.py`），不再裸 500；api-contract §3.1 补 503 行。
5. **数据处置**：4 条超长留档（>2,000 字）先导出原文，再 `profile_worthy=false` + 迁到
   **既有** hermes 项目容器 `…_hermes`（**不是**新建 `_project-hermes` —— 后者没有客户端会查，
   等于把数据孤立）。原用户容器画像缓存与 hermes 缓存一并 invalidate。

## 验收数据（2026-09-30 23:46，api 容器重启后实测）

| 指标 | 修复前 | 修复后 |
|---|---|---|
| `context` 总长 | 20,930–23,968 字 | **3,881 字** |
| `### 永久特征` | 20,621 字（含 3 条 cron 备份） | 1,016 字（0 条备份） |
| `### 近期动态` | （无此节，混在永久特征里） | 1,800 字（0 条备份） |
| 用户容器超 1,000 字条目 | 4 | **0** |
| `POST /api/v2/search` | 500 `relation … does not exist` | **503 + 统一信封 + 指引** |
| `metadata.scope=project` 无 tag 写入 | 静默落用户容器 | **422 且不落库** |

回归：CI 命令（`--ignore` 同 CI）194 passed / 15 skipped / **38 errors（基线同样 38，crystal 集成套件
跨 loop 冲突，属 MR-024 系列既有问题）**；新增 3 个测试文件 22 用例全绿。

## 下一步

- 写入侧约定要传达到实际写库的 agent：**别绕过 MCP 工具直接 POST**；直接 POST 时必须带
  `container_tag`；长留档必须带 `metadata.profile_worthy=false`（已写入 `docs/MEMORY_FLOW.md` 写入侧约定）。
- hermes 侧历史脚本（`round=*` 备份模式）若再跑，现在会拿到 422 并停下 —— 这是预期行为（fail loud）。

## 未决问题

- 「长留档」的通用治理（何时该归档、是否该有 TTL/自动降权）未定；
- 迁容器未同步迁移实体行（`memory_entities` 仍指旧容器实体），实体图召回不再覆盖这 4 条 ——
  影响可忽略（它们是历史全文备份），但机制上仍是已知不一致。
