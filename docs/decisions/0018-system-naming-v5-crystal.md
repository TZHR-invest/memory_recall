# ADR-0018: 系统命名与归属标记（旧 v5，新 crystal）

> 状态: Accepted
> 系统: crystal
> 日期: 2026-08-16
> 关联: [目标模型 v1](../designs/target-model/v1.md) · MR-010（命名漂移）

## 背景

目标模型（北极星 = 价值公式；Evidence / Claim / Lineage Edge）将作为一次**大版本重构**替换现有系统。
开发期新旧并存（旧表只读、新表写入），agent / 开发者读 ADR、API、schema 时无法一眼区分某物归属哪套系统。
需要显式命名，让 **adr / api / model / schema 每一项都标明归属**，避免把 crystal 的决策套到 v5 代码上（或反之）。

## 选项

- A: 纯版本号（旧 = v5，新 = v6）。
- B: 纯代号（旧 = 木星，新 = 北极星 / crystal）。
- C: 混合（旧沿用版本号 v5，新用代号 crystal + API 版本前缀 /api/v2）。

## 决策

选择 **C**：

- **旧系统 = `v5`**：现有 Memory Recall 5.x（`memories` 等表、现有无前缀 API、现有插件）。
- **新系统 = `crystal`**：目标模型（`evidence` / `claim` / `lineage_edge`；北极星 = 价值公式）。
- **关系**：crystal 是 v5 的大版本替代；开发期并存（v5 只读、crystal 写入），完成后 v5 退役。
- **API**：crystal = `/api/v2/*`；v5 = 现状无前缀（事实 v1）。
- **schema**：crystal 新表用 PostgreSQL namespace `crystal.*`（或表名前缀 + `schema.sql` 注释分段），v5 表留 `public.*`（落地细节归「渐进迁移路径」文档）。
- **ADR / notes**：头部加 `> 系统: crystal` 或 `> 系统: v5`；`decisions/README.md` 索引加「系统」列。

## 理由

- 纯版本号（v6）与现有 v5.2.x 撞车，且"产品 v6 vs 架构 v2"有歧义；代号（crystal）无版本歧义、可作前缀、好记。
- 旧系统本就有版本号 v5，直接沿用最省事、零歧义，不必为旧系统硬造代号。
- API 保持版本化（`/api/v2`）因为插件消费者约定俗成认版本号；文档用代号因为要区分"语义归属"而非"接口版本"。
- crystal 呼应目标模型的"提炼 / 成熟"（记忆沉淀结晶为知识）。

## 后果

- 正向：新旧产物一眼可辨归属，避免 agent 混用两套决策。
- 需跟进：ADR 0011–0017 与 `designs/target-model/` 文档补 `> 系统: crystal` 标记；ADR 0001–0010 标 `系统: v5`；
  schema 的 `crystal.*` namespace 落库细节归「渐进迁移路径」文档。
- ADR 0011–0017 是 crystal 的语义层决策（目标模型 v1 已拍板项）；ADR 0001–0010 是 v5 的决策，其中被目标模型取代的（如 ADR-0010 文档 RAG、与 `memories`/`is_latest` 相关的）在迁移路径中标注 Superseded。
