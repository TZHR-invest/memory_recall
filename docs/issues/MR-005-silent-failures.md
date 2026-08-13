# MR-005: 文档处理失败静默

> 状态: 已关闭（ADR-0010） · 严重度: P2 · 创建: 2026-08-12 · 关闭: 2026-08-13

## 问题

文档处理链路大量 `except Exception: pass`（LLM 摘要、实体提取、embedding 失败时静默降级），
用户看到的是"没召回"，而不是"处理失败"。部分路径已把 error 写入 metadata，
但未形成统一可观测口径。

## 建议

统一失败语义：status=failed + error 字段 + stats/仪表盘暴露失败数。

## 解决记录

2026-08-13：随 [ADR-0010](../decisions/0010-remove-document-rag.md)（文档 RAG 移出核心）关闭，本问题随子系统移除不再适用。
