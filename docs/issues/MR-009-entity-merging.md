# MR-009: 实体合并靠字符串唯一约束

> 状态: OPEN · 严重度: P2 · 创建: 2026-08-12

## 问题

`entities` 以 `(name, type, container_tag)` 唯一，`normalized_name` 字段存在但无系统化合并流程
（只有一次性 `scripts/cleanup_entities.py`）。同实体不同写法会累积为多个节点。

## 建议

后台合并任务（规则 + LLM 判定），合并时保留 mention_count/source 追溯。

## 解决记录

（修复后填写 commit / 版本）
