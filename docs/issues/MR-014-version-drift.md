# MR-014: 版本号漂移

> 状态: OPEN · 严重度: P2 · 创建: 2026-08-12

## 问题

`apps/api/main.py` 写 5.0.0、schema.sql 注释 5.1.5、AGENTS.md 写 v5.2.1、
config.py 与 CHANGELOG 为 5.2.3。

## 建议

单一版本源（config.APP_VERSION），其他位置引用或删除；CHANGELOG 与版本发布流程绑定。

## 解决记录

（修复后填写 commit / 版本）
