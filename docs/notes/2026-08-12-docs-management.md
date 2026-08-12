# 2026-08-12: 文档管理规范讨论（Docs-as-Records）

> 类型: 讨论
> 日期: 2026-08-12
> 关联: [ADR-0002](../decisions/0002-docs-as-records.md), [DOCUMENTATION_GUIDE.md](../DOCUMENTATION_GUIDE.md)

## 背景

用户提出：项目里所有工作信息（功能讨论、方向探讨、调研、决策、设计）都容易"做完就消失"，
只存在于对话里。希望建立一套管理规范，让信息全部沉淀在仓库中，并提示后续 Agent 遵守。

## 讨论要点

- 过程内容（讨论/调研/方向）需要存档，但不要求成熟；
- 决策应该有决策文档（ADR 风格），记录背景、选项、理由、后果；
- 产品设计应该有版本，且同一主题只有一个"当前生效"版本；
- 规范必须写进 AGENTS.md，让后续 Agent 一进仓库就能读到并执行；
- docs/ 根目录会被 opencode 插件导入为知识，子目录不会——这是需要明说的边界。

## 结论

建立 Docs-as-Records 规范：

- `docs/` 根目录 = 当前为真的知识（会进入知识库）；
- `docs/decisions/` = ADR 决策记录（追加制，Accepted 后不可变）；
- `docs/notes/` = 过程记录（日期命名，永久保留）；
- `docs/designs/` = 设计文档（版本化，LATEST 指向当前生效）；
- `docs/ISSUES.md` = 问题清单（修复后标记已解决，不删条目）；
- `docs/archive/` = 过时内容（git mv 归档并登记原因）。

规范正文：`docs/DOCUMENTATION_GUIDE.md`；简要版 + 强制 checklist：`AGENTS.md`。

## 下一步

1. 本规范在真实工作中运行一段时间，验证是否"低成本、可执行"；
2. 旧文档（archive 48 篇）无需批量迁移，按需引用时再整理；
3. 用户 review 两条示范 ADR（0001 产品定位、0002 本规范），不认可就修订后再 Accepted。

## 未决问题

- 过程文档是否需要定期"升格"为正式设计/决策？（当前策略：notes 只留过程，升格靠新文档）
- 是否需要把 `docs/decisions/` 加入 opencode 知识导入 patterns，让 Agent 召回历史决策？
  当前倾向：不进注入上下文，需要时搜索。

*状态: ACTIVE · 版本: v1.0 · 最后更新: 2026-08-12*
