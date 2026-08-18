# ADR-0014: 置信度拆两轴（内容∥复用），由证据推导

> 状态: Superseded
> Superseded by: 0019
> 日期: 2026-08-14
> 系统: crystal
> 关联: [目标模型 v1](../designs/crystal/v1.md) · [memory-confidence](../notes/2026-08-14-memory-confidence.md) ·
> [复用反馈回收 Q2 调研](../notes/research/2026-08-14-reuse-feedback-signals/99-final-conclusions.md)

## 背景

现状 `confidence` 是写入时一次性设定的 FLOAT（默认 0.8），无证据累积、无负反馈区分。
调研指出：召回分高 ≠ 记忆好；负反馈必须三轴区分（"没用" ≠ "有害" ≠ "错"）；置信度应由证据推导，
冷启动一律 UNKNOWN。

## 选项

- A: **单一 confidence 标量，写入时设定**（现状）。
- B: **两轴**——`content_confidence`（内容：correctness/staleness/harmfulness）+ `reuse_confidence`（复用：P(useful|M,C)），由证据推导。
- C: **多维**（事实性 / 稳定性 / 时效性细分）。

## 决策

选 **B**。

- 两轴由证据累积推导（Beta-Bernoulli），**写入时不再一次性设死**，冷启动一律 UNKNOWN。
- **内容内部不细分**（事实性/稳定性/时效性仍单一值），避免过度设计。

## 理由

- 两轴对应价值公式里两个不同因子：内容轴 = "对不对"（状态有效性），复用轴 = "用了有没有用"（价值）。
- 单次"没用"永不降内容轴（只调检索范围）；Stale 需强负证据；Harmful 需因果归因（M→Decision→Negative Outcome）。
- "内容内部不细分"继承 memory-confidence 早期"避免过度设计"的倾向。

## 后果

- 正面：置信度不再是死值；负反馈能按轴区分，避免把"没被召回/没用上"误判成内容问题。
- 负面：需要证据累积机制 + 时间衰减 + 硬下限（S2 细化，未排期）。
- 跟进：衰减曲线、冷启动 UNKNOWN 到 active 的过渡、与 is_static（性质分类）的字段级关系。
