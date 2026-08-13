# MR-002: URL 去重跳过内容更新

> 状态: 已关闭（ADR-0010） · 严重度: P1 · 创建: 2026-08-12 · 关闭: 2026-08-13

## 问题

`apps/api/src/services/core/document_store.py` 的 `create()` 中，URL 去重是
"同 URL 直接返回旧文档，无论内容是否变化"（代码注释即 `same URL, regardless of content`）。

## 后果

用 URL 导入的文档内容变更后永远不更新，知识停留在旧版本。

## 建议

URL 命中后比较 content_hash，变化时走 update 路径（与 source+title 的 3-key 去重行为一致）。

## 解决记录

2026-08-13：随 [ADR-0010](../decisions/0010-remove-document-rag.md)（文档 RAG 移出核心）关闭，本问题随子系统移除不再适用。
