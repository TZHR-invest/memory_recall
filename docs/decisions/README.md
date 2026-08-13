# 决策记录（ADR）

> 状态: ACTIVE · 最后更新: 2026-08-13

本项目使用 ADR（Architecture Decision Records）记录所有方向性决策。
规则见 [docs/DOCUMENTATION_GUIDE.md](../DOCUMENTATION_GUIDE.md#2-决策记录adr)。

## 编号规则

- 文件名：`NNNN-短横线slug.md`，编号从 0001 递增，不回收；
- 每个 ADR 一个决策；一次讨论产生多个决策时拆多条；
- 已 Accepted 的 ADR 不可修改正文；改变决策时写新 ADR 并声明 `Supersedes`。

## 模板

```markdown
# ADR-NNNN: 决策标题

> 状态: Accepted | Superseded
> Supersedes: 00XX（可选，本 ADR 取代谁）
> Superseded by: 00XX（可选，本 ADR 被谁取代，状态变为 Superseded 时填写）
> 日期: YYYY-MM-DD
> 关联: MR-xxx / docs/xxx（可选）

## 背景
为什么需要这个决策？当前的问题/矛盾是什么？

## 选项
- A: 方案 A（一句话）
- B: 方案 B（一句话）
- C: 方案 C（一句话）

## 决策
选择了哪个选项，一句话说清。

## 理由
为什么选它：证据、权衡、代价。

## 后果
正面影响 / 负面影响 / 需要后续跟进的事。
```

## 状态机说明

ADR 只记录**已定**的决策，没有 Proposed / Rejected 状态：

- **Accepted**：已接受，当前有效，决策正文冻结；
- **Superseded**：被后续新 ADR 取代（新 ADR 声明 `Supersedes: 00XX`），
  旧 ADR 同时更新头部为 `Superseded by: 00XX`（双向链接），
  不再有效但正文保留——历史决策不删除。状态变更是状态机的一部分，
  不受"正文冻结"限制。
- 讨论过程放 `docs/notes/`；讨论后否决的方案若值得记录，
  写一条 Accepted 的"不采用 X" ADR（决策本身是"不做 X"），否则留在 notes。
- **实施状态不进 ADR**：Accepted 只代表"决策已定"，不代表"已实现"；
  尚未实现的 Accepted ADR 由 `docs/STATUS.md` 的"ADR 实施跟踪"表跟踪
  （规则见 [DOCUMENTATION_GUIDE.md §2.1](../DOCUMENTATION_GUIDE.md#21-adr-与实施状态accepted--已实现)）。

## 索引

| 编号 | 标题 | 状态 | 日期 |
|------|------|------|------|
| [0001](0001-product-positioning.md) | 产品定位收敛为 AI Agent 记忆系统 | Accepted | 2026-08-12 |
| [0002](0002-docs-as-records.md) | 文档沉淀与生命周期规范（Docs-as-Records） | Accepted | 2026-08-12 |
| [0003](0003-inject-api-convergence.md) | 注入接口收敛为 /context-inject 单一路径 | Accepted | 2026-08-12 |
| [0004](0004-context-inject-graceful-degradation.md) | /context-inject 子模块优雅降级 | Accepted | 2026-08-12 |
| [0005](0005-inject-failure-notice-policy.md) | 注入失败提示策略（log + toast，每会话最多 3 次） | Accepted | 2026-08-12 |
| [0006](0006-session-summary-not-stored-as-memory.md) | 会话摘要不写入记忆库 | Accepted | 2026-08-12 |
| [0007](0007-compaction-converge-to-official-hook.md) | 压缩机制收敛到官方 hook（废弃预压缩） | Accepted | 2026-08-12 |
| [0008](0008-remove-summary-capture-and-scene-recovery.md) | 删除摘要捕获与现场恢复 | Accepted | 2026-08-12 |

*状态: ACTIVE · 最后更新: 2026-08-13*
