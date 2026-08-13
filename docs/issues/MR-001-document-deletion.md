# MR-001: 文档删除链路断裂：源文件删除后知识残留

> 状态: 已关闭（ADR-0010） · 严重度: P1 · 创建: 2026-08-12 · 关闭: 2026-08-13

## 问题

opencode 插件的 file-watcher 收到 deleted 事件后**只打日志，不调用后端删除 API**
（`apps/api/src/plugins/opencode/src/file-watcher.ts`）；`.memory-recall-docs.json` 中
已删除文件的条目也永不清除。后端有 `DELETE /documents/{id}`，但没有任何调用方。

## 后果

源文件删除后，其 chunk 仍被召回——用户以为删了，系统还在"记着"。

## 建议

watcher 删除事件 → 调后端删除 API 并清理本地 state；后端删除文档时级联删
chunks/chunk_entities；必要时增加"孤儿文档"统计。

## 解决记录

2026-08-13：随 [ADR-0010](../decisions/0010-remove-document-rag.md)（文档 RAG 移出核心）关闭，本问题随子系统移除不再适用。
