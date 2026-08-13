# ADR-0004: /context-inject 子模块优雅降级

> 状态: Accepted
> 日期: 2026-08-12
> 关联: ADR-0003、ADR-0005

## 背景

`/context-inject` 后端聚合五路召回（profile / memory / memory-graph / entity-graph / chunks）。
当前 API 层对 service 调用整体 try/except：任一路失败即整体 500，导致"五路中四路可用"时
客户端什么都拿不到。service 内部各通道已有独立 try/except，但信息没有透出。

## 选项

- A: 保持整体 500，失败对调用方不可见；
- B: 单通道失败返回已成功通道结果，失败写入 trace/stats；仅全失败或请求级错误才 500；
- C: 失败通道静默丢弃，不记录。

## 决策

选择 **B**：单通道失败不拖垮整体请求。

- 每个通道独立 try/except，失败记为 `failed_channels`（trace 与 stats 均包含）；
- 返回所有成功通道的 `context/sources/stats`；
- 仅当全部通道失败、鉴权失败、参数非法或存储不可用等请求级错误时返回 500。

## 理由

- 注入是 best-effort"锦上添花"，部分记忆优于无记忆；
- 失败可见性是可观测性支柱的一部分（trace 可解释"哪条死在哪一环"）；
- 与 ADR-0005 的提示策略配合，用户可感知但不被打扰。

## 后果

- 正面：单通道故障不吞掉整次注入；trace 可定位失败；
- 负面：响应语义变化，调用方需要理解"部分结果 + failed_channels"；
- 跟进：补充单通道失败/全失败/请求级错误的测试用例。

*状态: Accepted · 日期: 2026-08-12*
