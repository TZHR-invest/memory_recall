# 2026-08-13: ADR-0010 优先级与推进方式讨论

> 类型: 讨论 · 日期: 2026-08-13
> 关联: [ADR-0010](../decisions/0010-remove-document-rag.md)、[MR-006](../issues/MR-006-knowledge-object.md)、[MR-011](../issues/MR-011-knowledge-ui.md)、[MR-019](../issues/MR-019-document-to-memory-distillation.md)
> 前置: [2026-08-13-document-rag-removal-discussion.md](2026-08-13-document-rag-removal-discussion.md)（决策讨论）

## 背景

ADR-0010 已 Accepted（2026-08-13），STATUS 下一步 #1 为"实施排期"。
本次讨论确认：实施 ADR-0010 是否为当前最优先工作，以及如何推进。

## 讨论要点

### 优先级论证（结论：是最优先）

- **纯执行、无设计悬念**：ADR-0010 是已定决策，剩下的是减法；真正的 P0（MR-006 知识对象、
  MR-011 知识 UI）是设计问题。先做掉"答案已知的机械活"，再集中脑力做设计；
- **缩小其他 P0 的问题空间**：MR-006 要统一三条召回路径的"最新"语义，chunks 是第四条通道，
  且去重/cap/trace/阈值每条新特性都要为它多写一套分支。先删，MR-006 的统一工作少一个维度，
  MR-011 的 UI 也不用为文档做界面。与 ISSUES.md 优先行动建议第 1 条一致；
- **维护税乘性**：近 20 个 commit 文档相关修复密集（URL 去重、HTML 噪音、实体图谱恒 0），
  越晚删越贵；
- **与 MR-019 正交**：文档→memories 蒸馏只需 LLM 提取 + 溯源字段，不需要 chunks/RAG，
  MR-019 有明确触发条件、保持冻结，不构成"等等再删"的理由。

### 反面论点评估

- MR-006 更深，但正因是架构级关键决策才应后做：先清场（删文档通道）再定模型，
  避免知识对象设计时还要考虑"第四通道如何统一"；
- 删除无用户可见价值，但 PROJECT_PLAN §0 当前阶段策略就是"功能收敛与简化"，符合阶段判断依据。

### 删除清单规模（盘点）

- 后端约 3700 行：`document_store.py`(952) + `document_processor.py`(483) +
  `document_chunker.py`(424) + `chunking/` 包 10 文件(~1840)；
- 关联清理：`context_inject_service.py` chunks 通道、`memories.py` hybrid search、
  `stats.py`/`debug.py`/`client.py`/`models/api.py` 引用、schema 三表 + 索引 + 注释；
- 插件 4 个面：opencode `document-tracker.ts`(463) + hermes / deepseek-tui /
  memory-recall-codex 三插件 server 的 document tools；
- 测试 5 个文件：`test_document_deduplication`、`test_v2/test_document_chunker`、
  `test_v2/test_chunks_search`、`test_chunking_performance`、`test_opencode/test_document_tracker`。

### 实施前提与风险

- **存量文档数据**：生产库 documents/chunks/chunk_entities 随实施删除。
  **用户已拍板：直接删、不导出**（文档内容都在磁盘上，chunk 数据无独立价值）；
- **无迁移框架（MR-013）**：schema.sql 是唯一事实源，删表后部署库需手动
  `DROP TABLE IF EXISTS documents, chunks, chunk_entities CASCADE;`；
- **插件多端联动**：四端插件同步删，否则会调不存在的接口。

## 结论

1. **ADR-0010 是最优先工作**：排在 MR-006/008、MR-011 之前（与 ISSUES.md 优先行动建议一致）；
2. 存量文档数据**直接删除、不导出**（用户拍板，实施时无需再确认）；
3. **本次不实施**，实施另行排期（用户选择）。

## 下一步

实施时按 3 个 commit 分层推进（每层测试验证后提交）：

1. **后端核心**：schema 删表 → 删三个 service + chunking 包 → 删 /documents* 路由 →
   摘除 context-inject chunks 通道 → 清理 hybrid/模型/调试引用 → 单元 + 集成测试；
2. **插件**：四端插件删除 document tools + 对应插件测试；
3. **收尾**：README 叙事修正（README.md 34/38 行仍在宣传"文档记忆/全文搜索"，
   顺带完成 ADR-0001"部分实现"剩余项）、STATUS.md ADR 表登记"已实现"、ISSUES.md 更新、
   部署库执行 DROP。

实施完成后：ADR-0009 检查点（检索修正"文档知识闭环/文档支柱"类过时记忆）；
MR-019 保持冻结。

## 未决问题

- 实施时机：另行排期（待定，触发条件：用户发起实施）。
