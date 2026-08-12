# 2026-08-13: 实体图"路径有但无注入"第三次验证（trace_172576184dc84b2d97d1d488793706bd）

> 类型: 调研
> 日期: 2026-08-13
> 关联: 前两次同类调查 #902fc2fe（notes 2026-08-12 / commit c167bd6）、fd3d796（截断修复）
> 结论: 正确行为，无需修复

## 背景

用户报告 trace_172576184dc84b2d97d1d488793706bd 显示 entity_graph 6 但实际注入 0，
追问"这是正确的吗"。第一轮答复结论为"正确"，但用户质疑"实体图找到的记忆全部被 vector
提前召回——这个确定吗"。追问暴露第一轮验证不完整：只查了 user scope 的实体关联记忆，
漏了 project scope 的 `memory_recall` 实体。

## 验证过程（完整证据链）

query=`test`，tags 模式双容器调用（user_tag=keyId，project_tag=keyId_project-memory_recall）。

### trace 数据

- `summary.entity_graph: 6` = 6 条 **entity_paths**（recall_trace_service.py L246 统计
  memories + paths），非记忆数；`entity_graph.memories: []` 为空数组。
- vector 命中 5 条（user 4 + project 1）；dedup dropped=0；final 28 = 23 profile + 5 记忆。

### 实体图分支执行链（_get_memories L433-513）

实体图起点是 **vector 已命中的记忆**（`get_entities_for_memories(memory_ids)`），不是全库实体。
两条 scope 各自独立执行：

**user scope**（vector 命中 4 条 user 记忆）：
1. 起点记忆关联实体 → `async test` / `commit` / `timeout test`（DB 实测）
2. `traverse_entity_relations` → 5 条 entity_paths（async test↔commit 互连、timeout test 自环）
3. `find_memories_by_entities` 完整 SQL（is_latest/is_forgotten 过滤）→ 只返回 2 条：
   mem_50edd59e(async test from commit)、mem_58dd80ea(timeout test)
4. 两条都已在 vector 命中列表（0.623 / 0.68）→ `new=0`

**project scope**（vector 命中 1 条 project 记忆 mem_e0026f67）：
1. 起点记忆关联实体 → `memory_recall`(b02803d7)（DB 实测）
2. `traverse_entity_relations` → 1 条自环路径（memory_recall→memory_recall）——
   **该实体在 entity_relations 表没有任何边（孤立节点，SQL 实测 0 行）**
3. `find_memories_by_entities([b02803d7])` → 只返回 mem_e0026f67 本身
4. 已在 vector 命中 → `new=0`

两条 scope 的 `find_memories_by_entities` 返回记忆**全部命中 seen_ids**（被 vector 提前召回），
无增量 → memories 空 → 注入 0。**正确行为**。

### 复现验证

用相同 query/config 重放 `/context-inject`（include_trace=true），结果与原始 trace 完全一致
（memories 空、paths 6 条）——非偶发。

## 新发现（可观测性小问题）

容器 root logger 是 **WARNING 级别且无 handler**——c167bd6 加的
`logger.info("entity_graph: %d entity_ids -> %d memories (%d new: ...)")` **永远不会输出**。
容器内实测：root level=30、handlers=0、module logger propagate=True。
即"实体图失败无痕迹"的问题实际仍存在（info 级日志被过滤），但不影响功能判定。

## 结论

1. "实体图 6 路径 0 注入"是**正确行为**——实体图能到达的记忆恰是 vector 已召回的，无增量可补。
2. 第一轮回答不严谨的教训：验证 trace 渠道空命中，**必须覆盖所有 scope**（user+project），
   只验证一条 scope 就下结论会留漏洞（本轮 project scope 的 memory_recall 实体几乎推翻结论）。

## 下一步

- （可选）修 logger 配置：给 context_inject_service 加独立 handler 或降 root level，
  让实体图 info 日志真正可观测。低优先级，不影响功能。

## 未决问题

- 无
