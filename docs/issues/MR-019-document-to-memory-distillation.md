# MR-019: 文档 → 记忆蒸馏是否值得做

> 状态: OPEN · 严重度: P2 · 创建: 2026-08-13
> 关联: ADR-0010（文档 RAG 移出核心）

## 问题

ADR-0010 决定文档 RAG 移出核心，但把"文档作为记忆入站源"留作开放问题：
文档内容（README、部署指南、API 契约、决策记录）是否值得经 LLM 蒸馏为 memories
（`document → extract-memory → memories(source=doc_id)`），而不是让 agent 直接读文件。

## 评估触发条件

出现以下任一情况时启动评估（否则保持冻结）：

- agent 无文件系统访问权（纯对话 agent 场景）；
- 文档语料规模大到磁盘检索不可行、语义检索收益成立；
- 出现多用户共享知识库需求；
- 实测出现"文档中的结论反复未被 agent 记住"的失败案例。

## 评估要点（启动时）

- 与 extract-memory 的重复度：文档蒸馏与"会话摘要提取"是否同一能力；
- 溯源设计：memories 增加 source（doc_id/path/hash）的 schema 与维护语义；
- 外部调研：mem0 / Letta / Zep 的文档入站处理模式（按 RESEARCH_GUIDE 流程）；
- 成本：蒸馏 LLM 调用量与触发时机（入站时一次性 vs 召回时按需）。

## 建议

冻结。等触发条件出现再评估，不占用当前记忆主线排期。
