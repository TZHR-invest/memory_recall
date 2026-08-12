# MR-015: 死代码与设计残留

> 状态: OPEN · 严重度: P2 · 创建: 2026-08-12

## 问题

`src/models/`、`src/services/prompts.py`、`embedding_cache.py` 为死代码；
`memory_store.get_version_chain` 零调用（真实历史走 `relation_service.get_version_history`）。
维护者靠 AGENTS.md 记录才知道哪些不能碰。

## 建议

删除或标注 deprecated；AGENTS.md 内容逐步迁入 docs/。

## 解决记录

（修复后填写 commit / 版本）
