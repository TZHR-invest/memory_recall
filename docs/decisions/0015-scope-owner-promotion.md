# ADR-0015: scope 与 owner 归属 + 提权机制

> 状态: Accepted
> 日期: 2026-08-14
> 关联: [目标模型 v1](../designs/target-model/v1.md) · [personal-vs-shared-boundary](../notes/2026-08-14-personal-vs-shared-boundary.md) · MR-011

## 背景

归属维度此前混乱：container_tag 把"项目"焊进容器语义、S4 的 `owner×project + visibility` 语义不清。
需要定三件事：数据归属（谁能读写）、项目作用域（在哪生效）、以及记忆如何"晋升"到更广作用域 / 更大归属。

## 选项

- A: **owner(人) × project 单维度焊死 + visibility 字段**（S4 旧草案）。
- B: **scope（项目作用域）+ owner（个人/团队）两正交维度**；项目不作为 owner。
- C: 在 B 上再加 visibility 三维。

## 决策

选 **B**。

- **scope = 项目作用域**（适用条件里最重要、最结构化的一维）；Evidence 通常有 scope（继承采集上下文），
  Claim 继承 scope、**可经提权变无 scope**。
- **owner = access control（数据归属）**：个人 / 团队，**v1 只做个人**；**砍掉"项目"作为 owner**（项目是 scope 不是归属）。
- `owner × scope` 取代 S4 的 `owner×project + visibility`（visibility 被 owner 的"个人/团队" + scope 的"项目"分解）。
- **提权两条，审批机制按风险分**：

| 提权 | 含义 | 对应 | 机制 |
|------|------|------|------|
| scope 提权 | 有 scope → 无 scope（项目内知识 → 全局知识） | S1 质变（`generalizes` 边） | **系统主动 + 用户审计**（事后） |
| owner 提权 | 个人 → 团队（个人知识 → 团队知识） | S4 迁移 | **系统建议 + 用户审批**（事前） |

## 理由

- 项目不是"谁能读写"的归属概念，是"在哪生效"的作用域；两轴正交，避免把容器语义焊成单维度（S4 已论证）。
- 审批差异源于风险：scope 提权最坏是"一条略错的全局 Claim"（可 supersede 纠正，风险低）→ 事后审计；
  owner 提权是把私人数据共享给团队（不可逆，风险高）→ 事前审批。

## 后果

- 正面：归属语义清晰，提权有明确的触发与审批通道；scope 提权正是"情景→语义"质变（S1）的落点。
- 负面：两条提权都依赖 workbench（MR-011）作"审计面 / 审批面"；团队场景（owner=team）v1 不做，先做个人。
- 跟进：scope 提权的判定（何时可去掉 scope）、owner 提权的建议触发、审计/审批的 UI 形态（挂 MR-011）。
