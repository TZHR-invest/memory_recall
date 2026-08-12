# Memory Recall 领域模型与实体设计

> 状态: ACTIVE · 版本: v1.0 · 最后更新: 2026-08-12
>
> 本文档解释当前领域模型（以 `apps/api/schema.sql` v5.1.5 为唯一事实源），
> 历史设计稿（agent_memory_design_v3、MEMORY_NETWORK_DESIGN_V3 等）已归档，仅作参考。

## 1. 领域概念总览

```mermaid
erDiagram
    CONTAINER ||--o{ MEMORY : owns
    CONTAINER ||--o{ DOCUMENT : owns
    CONTAINER ||--o{ ENTITY : owns
    DOCUMENT ||--o{ CHUNK : contains
    ENTITY ||--o{ ENTITY_RELATION : from
    ENTITY ||--o{ ENTITY_RELATION : to
    ENTITY }o--o{ MEMORY : "memory_entities"
    ENTITY }o--o{ CHUNK : "chunk_entities"
    MEMORY ||--o{ MEMORY_RELATION : from
    MEMORY ||--o{ MEMORY_RELATION : to
    CONTAINER ||--|| PROFILE : caches
```

核心概念：

| 概念 | 说明 | 对应表 |
|------|------|--------|
| 容器 container_tag | 数据归属边界：用户级 `{keyId}` / 项目级 `{keyId}_project-<dir>` | 分散在各表 |
| 记忆 memory | 一条事实/事件，可版本化、可遗忘 | `memories` |
| 文档 document | 导入的项目文档元数据，正文在 chunks | `documents` |
| 分块 chunk | 文档正文片段，带 embedding，可被召回 | `chunks` |
| 实体 entity | 知识图谱节点（person/location/org/topic/...） | `entities` |
| 实体关系 entity_relation | 实体间语义关系（works_at/friend/...） | `entity_relations` |
| 记忆关系 memory_relation | 记忆演进关系（updates/extends/derives） | `memory_relations` |
| 画像 profile | 容器级 static/dynamic 记忆聚合缓存 | `memory_profiles` |
| 召回 trace | 一次召回的完整链路记录（可观测） | `recall_traces` |

## 2. 记忆模型

`memories` 关键字段与语义：

| 字段 | 语义 |
|------|------|
| `is_static` | 静态事实（画像类） vs 动态状态 |
| `is_latest` | 是否"当前版本"（检索过滤依据） |
| `version` / `root_memory_id` | 显式版本链（`POST /memories/{id}/update`） |
| `is_inference` / `source_count` | 推理记忆 / 合并来源数 |
| `is_forgotten` / `forget_after` | 软删除 / 定时遗忘 |
| `metadata.relations` | 内嵌记忆关系索引（JSONB） |

### 两种"取代"语义（勿混淆）

1. **自动关系检测**（`relation_service.auto_create_relations`）：
   检测到 contradiction/update 时把旧记忆置 `is_latest=FALSE`，**不建版本链**，
   一条新记忆可同时取代多条旧记忆（N:1）。被降级的旧记忆仍可通过 updates 边追溯。
2. **显式更新**（`create_update_version`）：建完整版本链（version+1、root_memory_id），1:1 修订。

已知问题：语义 1 会产生大量 `is_latest=FALSE, version=1, root_memory_id=NULL` 的孤儿旧版本，
且不同召回路径对 `is_latest` 的过滤不一致（见 [ISSUES.md](ISSUES.md)）。

## 3. 文档与分块模型

| 表 | 关键点 |
|----|--------|
| `documents` | 元数据：title/url/source/doc_type/status/content_hash；正文不落此表 |
| `chunks` | 正文片段：position 排序、content_hash 增量更新、embedding、embedded_content（上下文增强后文本） |
| `chunk_entities` | 文档摘要提取的实体 → 包含该实体文本的 chunk（v5.2.1） |

生命周期：

- 导入去重：source+title（3-key）→ URL → content_hash，命中即复用；
- 变更更新：位置化 diff，替换变更 chunk、删除尾部多余 chunk；
- 已知问题：URL 去重跳过内容更新、无版本历史、删除链路断裂（见 ISSUES MR-001/002/003）。

## 4. 实体与图谱模型

### 实体（entities）

- 唯一约束：`(name, type, container_tag)`，命中即 `mention_count + 1`；
- `normalized_name` 预留归一化合并位，但目前**无系统化合并流程**（见 MR-009）；
- 实体来源：记忆创建时 LLM/NER 提取、文档摘要 NER 提取。

### 实体关系（entity_relations）

- 唯一约束 `(from, to, type, container)`，`weight` 随多次提及累加；
- `source_memory_id` 记录关系来源记忆，但 chunk 来源无反向追溯；
- 类型示例：friend / colleague / works_at / lives_at / prefers / uses ...

### 记忆关系（memory_relations）

- 固定三类：`updates`（更新）、`extends`（补充）、`derives`（推断）；
- 约束 `(from, to, type)` 唯一，`confidence` 记录 LLM 置信度；
- 由批量 LLM 检测生成，失败降级到规则检测。

## 5. 召回路径（context-inject）

```
profile（画像） → vector（记忆向量） → memory graph（记忆演进）
→ entity graph（实体关系） → chunks（文档分块） → 语义去重 → 格式化注入
```

- 各通道独立拉取，靠 `max_*` 上限截断，最后统一语义去重（优先级 profile > projectMemories > userMemories > chunks）；
- 没有真正的融合排序/加权，README 中的 50/30/20 是示意（见 [ISSUES.md](ISSUES.md)）；
- 每次召回可记录 trace（`recall_traces`），用于定位"哪条记忆死在哪一环"。

## 6. 当前设计矛盾与演进方向

| 矛盾 | 现状 | 方向 |
|------|------|------|
| 多套知识生命周期 | 记忆版本链、文档 chunk 替换、实体累积、画像缓存四套规则 | 统一"知识对象"（当前状态+来源+时间） |
| 文档与图谱割裂 | chunk 只靠向量，实体映射来自摘要近似 | chunk 级实体/关系提取 |
| 画像缓存一致性 | profile 独立缓存，靠调度/哨兵补丁 | 画像由统一知识对象派生 |

详见 [ISSUES.md](ISSUES.md)。历史设计参考：`docs/archive/agent_memory_design_v3.md`、
`docs/archive/MEMORY_NETWORK_DESIGN_V3.md`、`docs/archive/STORAGE_ARCHITECTURE_DECISION.md`。

*状态: ACTIVE · 版本: v1.0 · 最后更新: 2026-08-12*
