# 退役检查单 v1（v5 退役，M5 前置产物）

> 状态: 草稿（M5 前置，退役条件未满足） · 系统: crystal · 版本: v1 · 最后更新: 2026-08-19
> 关联: [迁移路径](migration-path.md)（Stage E）· [插件切换契约](plugin-migration-contract.md)（Stage D）·
> [里程碑](milestone.md)（M5）· [PRD](prd.md)（A10）
> 定位: 本文是 M5（v5 退役 DROP 旧表）的**检查单**——退役标准、备份/可重放、监控确认、执行步骤。
> **退役条件当前未满足**（crystal 运行不足 + 插件未切），本文先落检查项，条件满足后按此执行。

## 0. 一句话

**v5（public.* 旧表 + 无前缀路由）退役 = DROP 旧表（单独 commit）**，仅在退役标准全部满足后执行；
DROP 前备份 + 可重放；DROP 后 crystal 是唯一系统。

## 1. 退役标准（migration-path §7 已拍板 4）

| # | 标准 | 当前状态（2026-08-19） | 达成条件 |
|---|------|----------------------|---------|
| 1 | crystal 连续 N 天无 P0/P1 | ❌ crystal 上线仅 1 天 | N 天（建议 ≥14）无 P0/P1 事故 |
| 2 | 四端插件全切 /api/v2 | ❌ 切换延后（M4 用户拍板） | 插件切换执行完成（见 [plugin-migration-contract](plugin-migration-contract.md)） |
| 3 | 用户确认无回滚需求 | ❌ 未确认 | 用户在退役前明确确认 |
| 4 | 访问日志无旧路由调用 | ❌ 插件仍在调 v5 | 切换后日志核对（A10） |

## 2. 备份与可重放（DROP 前必做）

- [ ] **全库备份**：`pg_dump -d memory_recall`（或 docker `pg_dump`）→ 备份文件留存（含 v5 表 + crystal 表）。
- [ ] **备份验证**：备份文件可 `pg_restore --list` 列出（完整性抽查）。
- [ ] **可重放确认**：迁移幂等已验证（M3）；备份还原后 crystal 数据一致。
- [ ] **迁移状态留存**：`crystal.migration_state` 记录已迁 27 条（evidence 幂等键可溯源）。

## 3. DROP 前检查（执行当天）

- [ ] 退役标准 §1 全部达成（逐项勾选）。
- [ ] `memories` 中剩余数据核对：377 条 active 中 27 条已迁，350 条 test_perf_container 测试残留
  （**确认不需要迁移**——测试数据，退役即弃）。
- [ ] `documents/chunks/entities/memory_profiles/recall_traces/recall_embedding_logs`
  （migration-path §4 不迁移对象）确认可弃。
- [ ] 插件已全切（无 v5 调用），或已确认 v5 停用。
- [ ] 备份已完成并验证（§2）。

## 4. 执行步骤（DROP 当天）

```bash
# 1. 备份
cd apps/api
docker exec memory_recall-postgres-1 pg_dump -U postgres -d memory_recall > /backup/memory_recall_pre_drop_$(date +%Y%m%d).sql

# 2. DROP 旧表（单独 commit，代码侧移除 v5 路由 + schema.sql v5 段）
#    旧表清单（public.*）：
#    api_keys memories memory_relations memory_profiles documents chunks entities
#    entity_relations memory_entities chunk_entities recall_traces recall_embedding_logs

# 3. 摘 v5 路由（main.py 移除 memories/graph/embed/context_inject/debug/stats router）
#    —— 保留 auth（/api/v2 鉴权复用）与 health

# 4. 验证
#    - /api/v2 全路由正常
#    - crystal 读写闭环正常（写 evidence → 对账 → 召回）
#    - 无旧路由调用（访问日志）
```

## 5. 回退方案（DROP 后 7 天窗口）

- **备份还原**：`pg_restore` 全库还原（v5 + crystal 都在备份里）。
- **git revert**：单独 commit 可 revert（v5 路由/schema 恢复）。
- **crystal 数据**：不受影响（备份包含）。

## 6. 退役后清理（M5 收尾）

- [ ] `docs/ENTITY_DESIGN.md` 更新为 crystal 领域模型（v5 现状文档 → 被取代标注）。
- [ ] AGENTS.md 关键约束更新（无 v5 路由、schema 唯一事实源 = crystal 段）。
- [ ] 测试清理：v5 测试（test_v2 等）按退役情况归档/精简。
- [ ] crystal 专项里程碑 M5 标记完成，专项归档 `docs/archive/initiatives/`。

## 7. 验收（PRD A10 延伸）

- [ ] DROP 后 crystal 是唯一系统；v5 表 0 残留。
- [ ] 回退演练过（备份还原验证）。
- [ ] 用户确认无回滚需求。

*状态: 草稿 · 最后更新: 2026-08-19*
