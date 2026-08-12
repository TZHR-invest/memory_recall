# MR-005: 文档处理失败静默

> 状态: OPEN · 严重度: P2 · 创建: 2026-08-12

## 问题

文档处理链路大量 `except Exception: pass`（LLM 摘要、实体提取、embedding 失败时静默降级），
用户看到的是"没召回"，而不是"处理失败"。部分路径已把 error 写入 metadata，
但未形成统一可观测口径。

## 建议

统一失败语义：status=failed + error 字段 + stats/仪表盘暴露失败数。

## 解决记录

（修复后填写 commit / 版本）
