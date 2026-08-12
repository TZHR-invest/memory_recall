# ADR-0001: 产品定位收敛为 AI Agent 记忆系统

> 状态: Accepted
> 日期: 2026-08-12
> 关联: [ISSUES.md MR-010](../ISSUES.md), [PROJECT_PLAN.md](../PROJECT_PLAN.md)

## 背景

早期 PRD（`docs/archive/requirements.md`）定位为"人类记忆 + AI Agent 记忆"双使命，
规划了照片 EXIF、位置记忆、语音输入、人脸识别、need_confirm 等人类记忆功能。
截至 v5.2.3，这些功能均未实现；实际用户与使用场景全部来自 AI Agent 记忆
（OpenCode / DeepSeek TUI / Hermes 插件 + `/context-inject` 召回）。
同时，根 README、docs/README、apps/api/README 对产品讲了三套不同的故事，造成定位漂移。

## 选项

- A: 保持"人类记忆 + Agent 记忆"双使命叙事，文档继续覆盖两套愿景；
- B: 收敛为"AI Agent 长期记忆系统"，人类记忆愿景冻结为"明确不做"，统一文档叙事；
- C: 彻底删除人类记忆相关设计历史（不可逆，破坏可追溯性）。

## 决策

选择 **B**：产品叙事收敛为 Agent 记忆系统；人类记忆愿景冻结，
除非重新立项（届时需新 ADR 解除冻结）。

## 理由

- 代码、插件、用户场景全部面向 Agent 记忆，双使命叙事与实现严重脱节；
- 双使命导致文档漂移（MR-010）与产品失焦：资源会被"未来可能做"的功能稀释；
- 人类记忆设计历史有参考价值，保留在 archive 但不再进入当前叙事（选项 C 过激）。

## 后果

- 正面：文档与实现一致；路线图聚焦；后续 Agent 不会按过时 PRD 设计功能；
- 负面：若未来真要转向人类记忆，需要重新研究相关场景（历史已归档可复用）；
- 跟进：[PROJECT_PLAN.md](../PROJECT_PLAN.md) 已按本决策重写；
  README/`apps/api/README.md` 统一叙事（见 MR-010）。

*状态: Accepted · 日期: 2026-08-12*
