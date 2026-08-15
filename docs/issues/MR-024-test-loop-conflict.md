# MR-024: 测试文件全局 db 连接跨 asyncio loop 冲突（两文件不能同跑）

> 状态: OPEN · 严重度: P2 · 创建: 2026-08-15

## 问题

`test_document_deduplication.py` 与 `test_source_deduplication.py` 一起跑必失败（互相失败 18/26）：
根因是全局 `db` 单例 asyncpg 连接跨 pytest-asyncio module loop 冲突（"attached to a different loop"）。
非顺序问题——`pytest-order` 无法解决，`asyncio_default_test_loop_scope=session` 也会变成 "Event loop is closed"。

单独跑各自全绿。彻底修复需重构测试连接管理（每文件独立连接 / session fixture 统一管理），属测试基建改造。

## 建议

测试连接管理重构（per-file 独立连接或 session fixture 统一管理）。低优先级，未排期；
当前工作方式为两个文件分开单独跑（见 [TESTING.md](../TESTING.md)）。

## 解决记录

（修复后填写 commit / 版本）
