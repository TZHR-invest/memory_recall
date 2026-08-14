# Memory Recall 文档中心

> 本文档是项目文档的唯一入口。docs/ 下的活文档遵循统一生命周期，过时内容一律移入 `docs/archive/`。

## 为什么有这个目录

Memory Recall 的知识库本身会被 opencode 插件自动导入（默认 `trackedDocPatterns` 包含 `docs/*.md`），
所以 **docs/ 里的内容既是给人看的文档，也是给系统学的人工知识**。因此这里只放"当前为真"的文档；
过时或未落地的设计稿必须归档到 `docs/archive/`，否则系统会持续把过时内容当作知识召回。

## 目录结构

```
docs/
├── README.md            # 本文档：索引 + 维护规范
├── DOCUMENTATION_GUIDE.md # 文档沉淀规范（Docs-as-Records，Agent 必读）
├── STATUS.md            # 实时任务状态：活跃工作/下一步/等待项
├── PROJECT_PLAN.md      # 项目/产品长期规划（定位、路线图、不做清单）
├── ENTITY_DESIGN.md     # 领域模型与实体设计（以 schema.sql 为准）
├── MEMORY_FLOW.md       # 核心数据流：写入 → 处理 → 召回/注入 → 消费
├── ARCHITECTURE.md      # 架构与模块地图（后端分层、核心服务、惰性导入、死代码清单）
├── TESTING.md           # 测试指南（三层分级、环境注意点、常用命令）
├── PLUGINS.md           # 客户端插件（opencode / deepseek-tui / hermes）
├── RESEARCH_GUIDE.md    # 外部调研工作流（Human-in-the-Loop Research）
├── ISSUES.md            # 已知问题索引（open 清单，详情在 issues/）
├── issues/              # 问题详情（MR-xxx，每问题一文件）
├── DEPLOYMENT.md        # 部署与运维（Docker / 手动 / 备份）
├── decisions/           # 决策记录 ADR（追加制，不可修改）
├── notes/               # 过程记录：讨论/调研/方向（按日期命名）
├── designs/             # 产品/功能设计（版本化，当前生效唯一）
└── archive/             # 过时文档归档（不被知识库导入）
```

## 文档生命周期

| 状态 | 位置 | 含义 |
|------|------|------|
| ACTIVE | `docs/` 根目录 | 当前为真，可被插件导入为知识 |
| ARCHIVED | `docs/archive/` | 已被实现/废弃/取代，仅保留参考价值，**不会被知识库导入** |

### 规则

1. **只写当前为真的内容**。设计稿、讨论稿、计划中的功能，不要直接放进 docs/ 根目录；
   落地后再作为 ACTIVE 文档写入，或先在根目录标注 `状态: 草稿` 并在落地后及时更新。
2. **过时即归档**。功能已被替代/实现/废弃时，把文档 `git mv` 到 `docs/archive/`，
   并在 `docs/archive/README.md` 的索引中补充一行"为什么归档"。
3. **命名约定**：文件名用大写蛇形（如 `PROJECT_PLAN.md`、`ENTITY_DESIGN.md`），内容用中文；
   归档文件保留原文件名，便于追溯。
4. **状态与日期**：每个 ACTIVE 文档头部标注 `状态: ACTIVE` 和 `最后更新`；每次实质修改都更新日期。
5. **新增文档前先想清楚读者**：规划 → `PROJECT_PLAN.md`；领域模型 → `ENTITY_DESIGN.md`；
   已知问题 → `ISSUES.md`；部署运维 → `DEPLOYMENT.md`；都不适合再新建文件，并同步更新本文索引。
6. **文档即知识**：docs/ 根目录的 Markdown 会被 opencode 插件导入，
   不要放个人草稿、临时笔记或敏感内容；不想进入知识库的内容放 archive 或仓库外。

## 文档索引

| 文档 | 状态 | 最后更新 | 说明 |
|------|------|---------|------|
| [DOCUMENTATION_GUIDE.md](DOCUMENTATION_GUIDE.md) | ACTIVE | 2026-08-13 | 文档沉淀规范：所有工作信息必须落档，含 Agent checklist |
| [decisions/README.md](decisions/README.md) | ACTIVE | 2026-08-13 | 决策记录（ADR）索引与模板 |
| [notes/README.md](notes/README.md) | ACTIVE | 2026-08-12 | 过程记录约定与模板（讨论/调研/方向） |
| [designs/README.md](designs/README.md) | ACTIVE | 2026-08-12 | 设计文档版本化约定与模板 |
| [STATUS.md](STATUS.md) | ACTIVE | 2026-08-14 | 实时任务状态：活跃工作/下一步/等待项；ADR 实施跟踪 |
| [PROJECT_PLAN.md](PROJECT_PLAN.md) | ACTIVE | 2026-08-14 | 项目定位、产品支柱、路线图、不做清单 |
| [ENTITY_DESIGN.md](ENTITY_DESIGN.md) | ACTIVE | 2026-08-12 | 记忆/文档/实体/图谱领域模型，schema 为准 |
| [ISSUES.md](ISSUES.md) | ACTIVE | 2026-08-13 | 已知问题索引（open 清单）；详情在 [issues/](issues/) |
| [DEPLOYMENT.md](DEPLOYMENT.md) | ACTIVE | 2026-08-12 | Docker Compose / 手动部署 / 备份恢复 |
| [MEMORY_FLOW.md](MEMORY_FLOW.md) | ACTIVE | 2026-08-12 | 核心数据流：写入 → 处理 → 召回/注入 → 消费（含 /context-inject 契约） |
| [ARCHITECTURE.md](ARCHITECTURE.md) | ACTIVE | 2026-08-13 | 架构与模块地图：后端分层、核心服务、惰性导入、死代码清单 |
| [TESTING.md](TESTING.md) | ACTIVE | 2026-08-13 | 测试指南：三层分级、环境注意点、常用命令 |
| [PLUGINS.md](PLUGINS.md) | ACTIVE | 2026-08-13 | 客户端插件：opencode / deepseek-tui / hermes |
| [RESEARCH_GUIDE.md](RESEARCH_GUIDE.md) | ACTIVE | 2026-08-13 | 外部调研工作流（Human-in-the-Loop Research） |
| [archive/README.md](archive/README.md) | ACTIVE | 2026-08-12 | 归档索引：为什么归档、历史文档在哪 |

> 完整的文档分类与生命周期规则见 [DOCUMENTATION_GUIDE.md](DOCUMENTATION_GUIDE.md)。

## 与代码的关系

- 数据库结构以 `apps/api/schema.sql` 为唯一事实源，`docs/ENTITY_DESIGN.md` 是对它的领域层解释；
  两者不一致时以 schema.sql 为准，并顺手更新 ENTITY_DESIGN。
- 已知问题以 `docs/ISSUES.md` 为清单，修复后把对应条目标记为 `已解决` 并记录 commit/版本。
- 版本号以 `apps/api/src/config.py` 的 `APP_VERSION` 为准（见 [ISSUES.md](ISSUES.md) 中版本漂移问题）。

*状态: ACTIVE · 版本: v1.0 · 最后更新: 2026-08-13*
