# Crystal 专项文档包（initiatives/crystal/）

> 状态: ACTIVE · 系统: crystal · 最后更新: 2026-08-18
> 关联: [目标模型](foundation.md)（语义裁判）· [ADR-0018](../../decisions/0018-system-naming-v5-crystal.md)（系统命名）· [PROJECT_PLAN](../../PROJECT_PLAN.md)（阶段四）

## 本目录是什么

**本目录是 crystal 专项（目标模型迭代替换 v5）的全部设计与规划文档包。**
crystal = 本次迭代的系统代号（ADR-0018）：**北极星（价值公式）+ 两层对象模型（Evidence / Claim / Lineage Edge）**，
以命名空间隔离（`crystal.*` + `/api/v2`）渐进接管 v5。
原目录名 `target-model`（目标模型）于 2026-08-16 更名为 `crystal`，二者指同一主题。

> 专项规范见 [initiatives/README.md](../README.md)：一个专项一个子目录；
> 目录内文档按"语义 / 落库 / 工程 / 需求 / 规划"分层（见下表），**各自独立版本化**，
> 不设 LATEST 指针；专项整体一致性由下方「当前配套版本」声明维护。

## 语义摘要（北极星）

目标模型把记忆系统重定义为两层——
**不可再生核心（Evidence，用户纠正 = 特权 Evidence）→ 派生层（Claim / Lineage Edge / Entity）**；
北极星是**价值公式**（复用机会 × 有效性 × 影响 − 维护/遗忘成本，错误信息按负价值计）；
Evidence = agent 生命周期输入（含 agent 自行蒸馏 = 观察），Claim = 系统理解 + 碰撞后的结论，二者多对多；
Claim 只存简单断言、推理放谱系边；演变只做推导记录、不做审计回溯。
（语义正文唯一裁判：[foundation.md](foundation.md)。）

## 当前配套版本（包级一致性）

> 每个里程碑（M1–M5）开工前核对：下表为该里程碑所需文档的**当前生效配套版本**。
> 任一文档升级到新版本时，若影响配套，同步更新本表并记录变更说明。

| 里程碑 | 配套文档（当前版本） | 说明 |
|--------|----------------------|------|
| **M1 建表 + API 骨架** | [foundation](foundation.md)（草稿） · [entity-attributes](entity-attributes.md)（定稿） · [api-contract](api-contract.md) v1 | entity-attributes 已定稿，M1 可照此建表 |
| **M2 两链路 + 工作台** | [workbench](workbench.md) v1 · [reconciliation-design](reconciliation-design.md) v1 · [recall-design](recall-design.md) v1 · [test-strategy](test-strategy.md) v1 | 前置文档已全部落稿（2026-08-18） |
| **M3–M5 迁移收尾** | [migration-path](migration-path.md) · M3 迁移脚本设计 / M4 插件切换契约 / M5 退役检查单（**待落**） | 迁移路径已定 Stage A–E |

## 文件地图（各层职责）

| 文件 | 层 | 角色 | 版本化 |
|------|----|------|--------|
| [foundation.md](foundation.md) | **语义** | 目标模型本体：北极星 + 对象模型 + 两链路 + 已拍板 35 项；**唯一裁判** | 独立版本（当前 v1 草稿） |
| [entity-attributes.md](entity-attributes.md) | 落库 | crystal schema（evidence/claim/lineage_edge/claim_evidence/claim_usage/claim_activity 表字段/索引/枚举）**3 待定项已定案（2026-08-18）** | 独立草稿，**已定稿**（M1 可照此建表） |
| [api-contract.md](api-contract.md) | 工程 | **crystal API 契约 v1**（/api/v2 路由表、鉴权映射、错误规范、幂等） | 独立草稿（M1 前置，已落） |
| [workbench.md](workbench.md) | 工程 | **workbench (MR-011) 设计 v1**（裁决面+洞察面双轨 API/权限） | 独立草稿（M2 前置，已落） |
| [reconciliation-design.md](reconciliation-design.md) | 工程 | **对账技术设计 v1**（worker/事务/retry/reinforce 计分强度权重表） | 独立草稿（M2 前置，已落） |
| [recall-design.md](recall-design.md) | 工程 | **召回技术设计 v1**（三级管道/精排公式/截断/trace 契约） | 独立草稿（M2 前置，已落） |
| [test-strategy.md](test-strategy.md) | 工程 | **crystal 测试策略**（分层/矩阵/每 M 出口） | 独立草稿（M2 前置，已落） |
| [migration-path.md](migration-path.md) | 工程 | 渐进迁移 Stage A–E：命名空间隔离、迁移策略、退役标准 | 独立草稿 |
| [milestone.md](milestone.md) | 规划 | 能力范围 / 节奏 / 研发流程门槛（§3.5） | 独立草稿 |
| [prd.md](prd.md) | 需求 | 用户故事（US-*）+ 能力验收（A1–A11）+ In/Out 范围 | 独立草稿 |

## 使用规则

1. **每份文档独立版本化**：各自带 `状态: 草稿/生效/被取代` + 版本 + 最后更新；
   专项不设 LATEST 指针（避免给整个专项强造单一版本线）。包级配套版本见上表。
2. **每 M 的前置产物是文档门槛**：见 [milestone.md §3.5](milestone.md)。缺文档不动代码（DOCUMENTATION_GUIDE §5 流程）。
3. **待落文档进度（2026-08-18）**：M1 前置（API 契约）+ M2 前置（workbench / 对账 / 召回 / 测试策略）
   **已全部落稿**；剩 M3 迁移脚本设计、M4 插件切换契约、M5 退役检查单（迁移收尾阶段前置）。
4. 新增本主题文档时更新本文文件地图与「当前配套版本」表。
5. 专项生命周期：立项 → 推进（本目录）→ 交付 → 整目录归档 `docs/archive/initiatives/`。

## 与根目录领域文档的分工

- `docs/ENTITY_DESIGN.md` = **v5 现状**领域模型（以 `schema.sql` 为准）；crystal 落地后由其取代。
- `entity-attributes.md` = **crystal 新领域** schema；落地后更新 ENTITY_DESIGN 或标注取代关系。
- `schema.sql` 已含 crystal 段（Stage A 草稿，2026-08-18）：`crystal.*` 六表 + 索引 + 约束，
  临时库验证通过（建表 + insert 冒烟）。

*状态: ACTIVE · 最后更新: 2026-08-18*
