# Crystal 专项文档包（designs/crystal/）

> 状态: ACTIVE · 系统: crystal · 最后更新: 2026-08-16
> 关联: [目标模型 v1](v1.md)（语义裁判）· [ADR-0018](../decisions/0018-system-naming-v5-crystal.md)（系统命名）· [PROJECT_PLAN](../PROJECT_PLAN.md)（阶段四）

## 本目录是什么

**本目录是 crystal 专项（目标模型迭代替换 v5）的全部设计与规划文档包。**
crystal = 本次迭代的系统代号（ADR-0018）：**北极星（价值公式）+ 两层对象模型（Evidence / Claim / Lineage Edge）**，
以命名空间隔离（`crystal.*` + `/api/v2`）渐进接管 v5。
原目录名 `target-model`（目标模型）于 2026-08-16 更名为 `crystal`，二者指同一主题。

> 按 [designs/README.md](../README.md) 规范，一个主题一个子目录；本目录的主题 = **crystal 专项（一个主题）**，
> 目录内的文档按"语义 / 落库 / 工程 / 需求 / 规划"分层（见下表），是**专项文档包**而非单个设计。

## 文件地图（各层职责）

| 文件 | 层 | 角色 | 版本化 |
|------|----|------|--------|
| [v1.md](v1.md) | **语义** | 目标模型本体：北极星 + 对象模型 + 两链路 + 已拍板 33 项；**唯一裁判** | 语义设计主文档（LATEST 指向） |
| [LATEST.md](LATEST.md) | 指针 | 指向当前生效语义版本（v1） | 指针 + 摘要 |
| [entity-attributes.md](entity-attributes.md) | 落库 | crystal schema（evidence/claim/lineage_edge…表字段/索引/枚举） | 独立草稿，evidence 定稿 |
| [migration-path.md](migration-path.md) | 工程 | 渐进迁移 Stage A–E：命名空间隔离、迁移策略、退役标准 | 独立草稿 |
| [milestone.md](milestone.md) | 规划 | 能力范围 / 节奏 / 研发流程门槛（§3.5） | 独立草稿 |
| [prd.md](prd.md) | 需求 | 用户故事（US-*）+ 能力验收（A1–A11）+ In/Out 范围 | 独立草稿 |

## 使用规则

1. **版本化只作用于语义设计**：`LATEST.md` 只指 v1.md；其余文档是**独立草稿**，各自带
   `状态: 草稿` + 版本 + 最后更新，**不参与 LATEST 指针**（避免给整个专项强造单一版本线）。
2. **每 M 的前置产物是文档门槛**：见 [milestone.md §3.5](milestone.md)。缺文档不动代码（DOCUMENTATION_GUIDE §5 流程）。
3. **待落文档**（M2 前置，尚未创建）：workbench(MR-011) 设计、crystal API 契约、对账技术设计、
   召回技术设计、crystal 测试策略；M3 迁移脚本设计；M4 插件切换契约。
4. 新增本主题文档时更新本文文件地图。

## 与根目录领域文档的分工

- `docs/ENTITY_DESIGN.md` = **v5 现状**领域模型（以 `schema.sql` 为准）；crystal 落地后由其取代。
- `entity-attributes.md` = **crystal 新领域** schema；落地后更新 ENTITY_DESIGN 或标注取代关系。

*状态: ACTIVE · 最后更新: 2026-08-16*