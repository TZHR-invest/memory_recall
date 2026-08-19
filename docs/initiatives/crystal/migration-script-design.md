# 迁移脚本设计 v1（memories → evidence，M3 前置产物）

> 状态: 已定稿（M3 已按此实现，2026-08-19） · 系统: crystal · 版本: v1 · 最后更新: 2026-08-19
> 关联: [迁移路径](migration-path.md)（Stage C）· [实体属性文档](entity-attributes.md)（evidence 表）·
> [对账技术设计](reconciliation-design.md)（迁移后重生成 claim）· [API 契约](api-contract.md)（§2.5 migrate）·
> [PRD](prd.md)（US-M1 / A9）
> 定位: 本文是 M3（旧数据迁移）的**实现设计**——迁移脚本形态、映射规则、幂等/断点续传/回放、
> 对账重生成 claim、验收。迁移触发 = 开发者一次性手动（迁移路径 §7 已拍板 1）。

## 0. 一句话

**`memories`（v5 active 记忆）→ `crystal.evidence`（agent_add）→ 对账重生成 claim**，
一次性全量、开发者触发、幂等可回放、断点续传；孤儿旧版本（v5 取代语义产物）不迁移。

## 1. 映射规则（migration-path §4 语义依据）

| v5 `memories` | crystal `evidence` | 说明 |
|---------------|-------------------|------|
| `is_latest=TRUE` | 迁 | active 记忆 = 观察（Evidence），不是结论（v1 #3） |
| `is_latest=FALSE, root_memory_id=NULL` | **不迁** | 孤儿旧版本 = v5 取代语义产物，历史留在 v5 可回溯 |
| `is_latest=FALSE, root_memory_id IS NOT NULL` | **不迁** | 显式版本链旧版本，同样留在 v5 |
| `is_forgotten=TRUE` | **不迁** | 已遗忘，无迁移价值 |
| `content` | `content` | 原样 |
| `container_tag = {keyId}` | `scope=NULL, owner_type=personal, owner_id=keyId` | 用户级容器 |
| `container_tag = {keyId}_project-<dir>` | `scope='project-<dir>', owner_type=personal, owner_id=keyId` | 项目级容器 |
| `container_tag` 非以上形态 | **跳过 + 告警** | 无法归属（旧测试容器等），不迁移 |
| `metadata.type` | 对账时判 claim_kind | preference/constraint/learned-pattern 原样，未知归 fact（entity-attributes §4.1） |
| `confidence` / `is_inference` | 对账时计分输入 | evidence 不落 confidence；对账按 B5 网格初值（source_kind=agent_add） |

**关键决策**：迁移后**对账重生成 claim**（不把旧记忆直接当 claim），遵守"结论必须引用证据"（migration-path §4）。

## 2. 迁移脚本形态（migration-path §5：不引入迁移框架）

- **独立脚本 `migrate_memories.py`**（apps/api/，类比 init_crystal_db.py），幂等可重放：
  - `--dry-run`：只统计不写入（默认推荐先跑）
  - `--owner <key_id>`：限定单个 key 迁移（测试/灰度）
  - 无参：全量迁移
- **admin 端点** `/api/v2/migrate/run` + `/api/v2/migrate/status`（api-contract §2.5）：
  - 封装同一迁移逻辑，供 web/运维调用；admin 权限（is_test 或 debug）
- 迁移状态落 `crystal.migration_state`（见 §4）

## 3. 幂等 / 断点续传 / 回放

### 3.1 幂等键（防重复迁移）

- 每条迁移的 evidence 幂等键 = `sha256("migrate:" + memory_id)` 前 32 位（`idempotency_key` 列）。
- 重跑时按幂等键查重：同键已有 evidence → 跳过（不重复落库、不重复对账）。

### 3.2 断点续传

- `crystal.migration_state` 表记录进度：
  `{run_id, owner_id?, total, migrated, skipped, failed, last_memory_id, status(running/done/failed), created_at, updated_at}`
- 中断后重跑：从 `last_memory_id` 续传（按 memory id 排序分批）；已完成批次跳过。

### 3.3 回放

- 幂等重放 = 重跑脚本/端点，已迁移的 evidence 幂等命中跳过，未迁移的补齐。
- **不删已有 crystal 数据**（迁移只增不改）；误迁清理 = admin 按幂等键前缀删 evidence + 级联 claim。

## 4. 数据落点（新增表，M3）

```sql
CREATE TABLE IF NOT EXISTS crystal.migration_state (
    run_id TEXT PRIMARY KEY,
    owner_id TEXT,                    -- NULL = 全量
    total INTEGER NOT NULL DEFAULT 0,
    migrated INTEGER NOT NULL DEFAULT 0,
    skipped INTEGER NOT NULL DEFAULT 0,
    failed INTEGER NOT NULL DEFAULT 0,
    last_memory_id TEXT,
    status TEXT NOT NULL DEFAULT 'running',  -- running/done/failed
    error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

## 5. 迁移流程（单条）

```text
1. 读 v5 memory（按 id 排序，分批 100 条）
2. 归属解析：container_tag → (scope, owner_type=personal, owner_id)
   - 无法解析 → skipped + 告警日志
3. 幂等查重：evidence.idempotency_key = sha256("migrate:"+memory_id)
   - 命中 → skipped（已迁移）
4. 落 evidence（agent_add, observed_at=memory.created_at 或 updated_at? 见 §5.1）
   + evidence_processing(pending)
5. 立即对账（同步）或入队给 worker → 生成 claim
6. 更新 migration_state
```

### 5.1 observed_at 语义（拍板）

- **用 `memory.created_at`**（记忆创建时刻 = 观察发生时刻）；`valid_from/valid_until` 不迁移
  （crystal 用 supersede 承载时间失效，v1 #24 砍 valid_*）。

### 5.2 对账时机（拍板）

- 迁移脚本**同步逐条对账**（不是丢给异步 worker）：迁移是开发者手动一次性操作，
  同步对账可即时看到 claim 生成结果与失败，便于抽查；batch 内串行。
- 复用 `reconcile_service.reconcile_evidence()`；失败记 failed + 重试（attempts<3）。

## 6. 验收标准（对应 PRD A9 / US-M1）

- [ ] **幂等重放**：跑两次结果一致（第二次 migrated=0，全部 skipped）。
- [ ] **断点续传**：中途 kill 后重跑，从断点继续（不重复迁移已完成部分）。
- [ ] **抽样核对**：抽 ≥5%（或 ≥100 条）核对 claim 关联（claim_evidence 指向对应 evidence；
  scope/owner 映射正确；claim_kind 合理）。
- [ ] **孤儿不迁**：is_latest=FALSE 的记忆不产生 evidence（v5 历史保留）。
- [ ] **v5 零影响**：迁移只读 v5 memories，不修改；v5 服务正常。
- [ ] **admin 端点**：/api/v2/migrate/run 幂等可重放；/api/v2/migrate/status 报告进度。

## 7. 未决 / 后续

- **迁移后 v5 转只读**（Stage C → D 衔接）：migration-path Stage C 后 v5 只读、crystal 承接写入；
  插件切换（Stage D）时 v5 停写。
- **claim 重生成的质量**：迁移后大量 claim 需人工审一遍（迁移路径 §4 已说明"迁移后对账可能
  产生大量 claim 需人工审一遍"）——workbench 假说池/低置信视图承接。

*状态: 草稿 · 最后更新: 2026-08-19*
