# ADR-0019: 置信度收敛为单轴（content）+ 复用/outcome 离散统计

> 状态: Accepted
> Supersedes: 0014
> 系统: crystal
> 日期: 2026-08-16
> 关联: [目标模型 v1](../designs/crystal/v1.md)（已拍板 #8）· [memory-confidence](../notes/2026-08-14-memory-confidence.md)

## 背景

ADR-0014 定「置信度拆两轴（内容∥复用）」。二轮收敛时批判性重论证发现：

- 价值公式三因子（复用机会 × 有效性 × 影响）里，只有「有效性」配得上一个置信度；
  「复用机会」（会不会再用）是频率统计、「影响」（用了多大用）是 outcome 统计，二者够不上置信度。
- `reuse_confidence` 定义 P(useful|M,C) 是上下文相关的，却只能实现成全局标量，自相矛盾。
- reuse 与 content 强相关（对的才更可能被采用且结果好），两轴不正交。
- 冷启动 + P0 无遥测，reuse 长期 UNKNOWN，废字段。

## 决策

- **`content_confidence` 单轴保留**：P(内容为真且当前成立)，连续后验；按 `source_kind` 弱先验、冷启动 UNKNOWN；
  由正确性信号更新（用户确认/纠正 ↑、与新证据冲突 ↓、时间衰减缓↓到下限）。
- **复用/outcome 降级为离散统计，不叫置信度、不物化连续分**：复用频率（近期加权）+ outcome（好/坏计数），
  喂维护（遗忘/晋升）与召回排序的"价值项"，P1 遥测接入后才激活。

## 理由

三信号独立更新、不互相喂（outcome 好不提 content；"有用"≠"正确"）。content 是硬需求（"现在还成立吗" +
错误负价值 + 召回可信先验）；复用/outcome 是价值增强、P1 才有数据，不值得在 P0 占一个置信度字段。

## 后果

- ADR-0014 Superseded（正文保留）。
- Claim 表不再有 `reuse_confidence` 字段；复用/outcome 统计落点（`claim_usage` 表 vs claim 表计数字段）留「实体属性文档」待定项。
- 生命周期四阶段（写入/召回/消费/维护）与 P0/P1 节奏见 [目标模型 v1](../designs/crystal/v1.md) §置信度与价值信号。
