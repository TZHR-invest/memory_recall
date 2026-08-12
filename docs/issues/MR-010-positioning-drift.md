# MR-010: 产品定位漂移：文档与代码讲了三套故事

> 状态: OPEN · 严重度: P0 · 创建: 2026-08-12
> 关联: [ADR-0001](../decisions/0001-product-positioning.md)

## 问题

根 README 说"AI 的长期记忆系统"；`docs/archive/requirements.md` 与旧 docs/README 是
"人类记忆 + Agent 记忆"双使命（照片 EXIF、位置、语音、need_confirm）；`apps/api/README.md`
仍停留在 v1 时代（`/api/v1/memories`、`{code,message,data}` 信封，与实际 v5 路由不符）。
人类记忆愿景均未实现，实际产品是 Agent 记忆。

## 建议

以 [PROJECT_PLAN.md](../PROJECT_PLAN.md) 的定位为准（ADR-0001），统一各 README 叙述；
`apps/api/README.md` 按当前 API 重写。

## 解决记录

（修复后填写 commit / 版本）
