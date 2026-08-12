# MR-016: DATABASE_URL 配置误导

> 状态: OPEN · 严重度: P2 · 创建: 2026-08-12

## 问题

`.env.example` 声明了 `DATABASE_URL`，但 `src/database.py` 只用
`DATABASE_HOST/PORT/NAME/USER/PASSWORD`，`DATABASE_URL` 从未被解析。
新用户按示例填 URL 会连不上库。

## 建议

从 `.env.example` 删除或实现解析，部署文档明确只填五件套。

## 解决记录

（修复后填写 commit / 版本）
