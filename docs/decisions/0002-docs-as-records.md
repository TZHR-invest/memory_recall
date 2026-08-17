# ADR-0002: 文档沉淀与生命周期规范（Docs-as-Records）

> 状态: Accepted
> 日期: 2026-08-12
> 系统: v5
> 关联: [DOCUMENTATION_GUIDE.md](../DOCUMENTATION_GUIDE.md), AGENTS.md

## 背景

项目大量工作信息只存在于对话/会议中，"做完就消失"；历史设计散落在
`docs/archive/`（48 篇）但没有统一的管理规则，无法区分"当前为真"与"历史参考"，
后续 Agent 无法可靠复用这些信息。

## 选项

- A: 只在 AGENTS.md 写几条约定，不建目录不立模板；
- B: 建立完整规范：docs 分层（根/decisions/notes/designs/archive）、
  决策 ADR、过程记录、设计版本化，AGENTS.md 记录简要版（选择 B）；
- C: 引入外部工具（Notion/Confluence/独立 wiki），仓库只留链接。

## 决策

选择 **B**：在仓库内建立"文档即记录"规范，所有工作产出落成文档，
规范正文在 `docs/DOCUMENTATION_GUIDE.md`，AGENTS.md 记录强制 checklist。

## 理由

- 仓库内文档与代码同源、同 git 历史、同 review 流程，信息不脱离项目；
- 外部工具与仓库脱节，Agent 无法自动读取，违背"沉淀给后续 Agent"的目标；
- 纯口头约定不可执行，目录 + 模板 + checklist 才能让 Agent 与人都可遵守。

## 后果

- 正面：所有工作信息可追溯；新 Agent 有明确流程；docs 根目录同时成为知识库当前事实；
- 负面：写文档有成本，需要纪律维持（用模板与 checklist 降低门槛）；
- 跟进：新建 `docs/decisions/`、`docs/notes/`、`docs/designs/`；
  AGENTS.md 增加"文档沉淀规范"章节；旧文档按规范逐步迁移。

*状态: Accepted · 日期: 2026-08-12*
