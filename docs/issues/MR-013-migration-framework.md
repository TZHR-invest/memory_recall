# MR-013: 无迁移框架，schema 双源

> 状态: OPEN · 严重度: P1 · 创建: 2026-08-12

## 问题

`apps/api/schema.sql` 是唯一事实源，但 `docker-entrypoint-initdb.d/schema.sql` 需要手工同步，
历史上出过"schema 双执行导致初始化失败""Docker 初始化 schema 未同步"等问题；
改 schema 后需手工 re-init，无迁移路径。

## 建议

引入轻量迁移（版本化 SQL 文件），docker 入口只执行迁移；或至少加一个"两份 schema 一致"的 CI 检查。

## 解决记录

（修复后填写 commit / 版本）
