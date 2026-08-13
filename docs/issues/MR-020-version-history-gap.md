# MR-020: /history 端点对显式版本链返回空（版本历史双路径不一致）

> 状态: OPEN · 严重度: P2 · 创建: 2026-08-13
> 关联: MR-006（同一根源：最新语义多路径不一致）· 发现于 ADR-0009 记忆维护检查点

## 问题

显式 `POST /memories/{id}/update` 建立的版本链（1:1 修订）无法通过 `GET /memories/{id}/history` 读取：

- `create_update_version`（memory_store）只把 updates 关系写入新记忆的
  `metadata.relations.updates` + memories 表的 `version` / `root_memory_id` 列，
  **不写 `memory_relations` 表**；
- `get_version_history`（relation_service）**只读 `memory_relations` 表**
  （`from_memory_id` + `relation_type='updates'`）；
- 实测（2026-08-13 检查点修正 `mem_12490fb23d474aa1996e` → `mem_a716b54e449a4003beef`）：
  对链上两个 id 查 history 均返回 `[]`；表内现存 113 行 updates 关系全部来自自动关系检测路径。

与 AGENTS.md「真实历史走 `relation_service.get_version_history`」的表述不符；
版本链本身未损坏（`version`/`root_memory_id`/`is_latest` 均正确），损坏的是**可读性**。

## 建议（任选其一）

1. `create_update_version` 同步调用 `relation_service.create(new→old, "updates")` 写表
   （与自动检测路径一致），metadata 记录保留作冗余；
2. 或 `get_version_history` 改为以 `root_memory_id` / `version` 列为主回溯，不依赖表；
3. 或 history 端点合并 metadata.relations 与表两种来源。

## 解决记录

（修复后填写 commit / 版本）
