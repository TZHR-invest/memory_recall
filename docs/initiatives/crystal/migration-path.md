# 渐进迁移路径（crystal 专项 · 草稿）

> 状态: 草稿 · 系统: crystal · 版本: v1 · 最后更新: 2026-08-16
> 关联: [目标模型](foundation.md) · [实体属性文档](entity-attributes.md) · [ADR-0018 命名](../../decisions/0018-system-naming-v5-crystal.md) · ADR-0010（文档 RAG）

## 0. 目标与原则

- **渐进式、不破坏 v5**：crystal 开发期，v5 继续服务现有插件与开发者；每个阶段都以"v5 不受影响"为前提。
- **命名空间隔离，不是分支隔离**：crystal 用 `crystal.*` schema + `/api/v2` 路由 + 新表名，与 v5（`public.*` + 无前缀路由 + 旧表）物理并存；不做长期 v2-dev 分支。
- **可回退**：任一阶段出问题，删 `crystal.*` 表 + 摘 `/api/v2` 路由即回退，v5 零影响。

## 1. 阶段总览

| 阶段 | 内容 | v5 | crystal |
|------|------|-----|---------|
| **Stage 0** | 命名/规范落地（ADR-0018 打标） | 只读维护 | ✅ 已完成 |
| **Stage A** | `crystal.*` 建表 + `/api/v2` 路由骨架 | 继续服务 | 空表，开始接收写入 |
| **Stage B** | 写路径（对账）+ 召回路径（状态查询）落地 | 继续服务 | 可写可召回 |
| **Stage C** | 旧数据迁移（`memories` → `evidence`） | 转为只读 | 承接旧数据 |
| **Stage D** | 插件切 `/api/v2` | 只读 | 主写入 |
| **Stage E** | v5 退役（DROP 旧表） | 退役 | 唯一系统 |

## 2. Stage A：crystal schema 与 API 骨架

- **建表**：`crystal.evidence` / `crystal.evidence_processing` / `crystal.claim` / `crystal.lineage_edge` / `crystal.claim_evidence` / `crystal.claim_usage`（字段见 [实体属性文档](entity-attributes.md)）。
- **只跑 `init_db.py`（幂等建表，非破坏）**；**绝不跑 `setup_database.py`（全量清库）**。crystal 表加在 `schema.sql` 的 crystal 段 + `init_db.py` 建 crystal schema。
- **API**：新 router 挂 `/api/v2/*`（写=对账、召回=状态查询、evidence 上报）；旧 router 无前缀不动。鉴权沿用 `X-API-Key` + `verify_container_ownership`，crystal 侧映射到 `owner_type/owner_id`。

## 3. Stage B：两链路落地（不迁移旧数据，先跑通）

- 写路径：`/api/v2/evidence` 上报 → `evidence` 落库 + `evidence_processing`（通用状态机）→ 对账生成/更新 `claim`。
- 召回路径：结构化预过滤（scope + status=active）→ 向量粗排 → 精排 → 注入。
- 此阶段 crystal 只处理**新写入**，不碰旧 `memories`，验证两链路正确后再谈迁移。

## 4. Stage C：旧数据迁移（关键决策区）

**语义依据**：旧 `memories` 是"证据与结论混在一起"的文本 + 手工标志位。按 crystal 语义（v1 #3），agent 自陈的记忆本就是**观察（Evidence）**不是结论。故迁移映射天然清晰：

- **`active` 记忆（`is_latest=TRUE`）→ 一条 `evidence`**：`source_kind=agent_add`、`content=memory.content`、`scope/owner` 从 `container_tag` 拆出（见 §7 已拍板 2）。
- **孤儿旧版本（`is_latest=FALSE, root_memory_id=NULL`）不迁移**——它们是历史，v5 里仍可回溯，且本来就是"取代语义"的产物。
- 迁移后**对账重新生成 claim**（不把旧记忆直接当 claim），遵守"结论必须引用证据"。

**迁移触发（已拍板）**：**一次性全量迁移，由开发者自行触发**（提供幂等迁移脚本/接口），**系统不自动迁移**。理由：迁移是一次性操作，且迁移后对账可能产生大量 claim 需人工审一遍，不自动跑。

**不迁移的对象**：
- `documents/chunks/chunk_entities` → 不迁移（ADR-0010：文档系统随 crystal 重构自然废弃）。
- `memory_profiles` → 不迁移（crystal 画像 = Claim 读视图，从 claim 重算）。
- `entities/entity_relations/memory_entities/chunk_entities` → 不迁移（Entity = P2 附属）。
- `memory_relations/recall_traces/recall_embedding_logs` → 不迁移（v5 运维数据，退役即弃）。

## 5. 迁移框架（MR-013 / C 档 8）

**决策：不引入迁移框架**。crystal 是绿地（新表），旧表不动，没有"改现有表"的迁移需求；继续用 `schema.sql` 唯一事实源 + `init_db.py` 幂等建表。将来 crystal 表需要演进（加列等）时，用幂等 `ALTER ... IF NOT EXISTS` 增量段，先观察再决定是否上 Alembic（现在上 = 过度设计）。

## 6. 分支与交付

- **主线增量 + 命名空间隔离**；每阶段一个短命 feature 分支，合入 main 即生效（crystal 表/路由是增量，不破坏 v5）。
- **Stage E（DROP 旧表）单独一个 commit**，留回退窗口（DROP 前备份/可重放）。
- 插件切换（Stage D）四端独立：opencode / codex / hermes / deepseek-tui / dsh 各自拉代码重启，后端访问日志核对不再调旧路由。

## 7. 迁移路径未决点（2026-08-16 已拍板）

1. **迁移粒度**：**一次性全量迁移，由开发者自行触发**（提供幂等迁移脚本/接口），系统不自动迁移。
2. **`container_tag` 拆 owner/scope**：项目容器（`{keyId}_project-<dir>`）→ `scope=<dir>`、`owner_type=personal`、`owner_id=<keyId>`；用户容器（`{keyId}`）→ `scope=NULL`、`owner_type=personal`、`owner_id=<keyId>`。
3. **鉴权映射**：`/api/v2` 沿用 `X-API-Key`；P0 阶段 `owner_type=personal`、`owner_id=keyId` 由鉴权层直接填（P1 团队再扩展 `team`）。
4. **Stage E 退役标准**：crystal 连续 N 天无 P0/P1 + 四端插件全切 + 用户确认无回滚需求，才 DROP 旧表。
