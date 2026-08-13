# 归档文档

本目录包含项目历史开发过程中产生的文档，保留作为参考。

## 归档内容

### 早期设计文档
- `agent_memory_design*.md` - 早期记忆系统设计迭代
- `MEMORY_NETWORK_DESIGN_V3.md` - 记忆网络设计

### 服务设计文档
- `SMART_CONFIRMATION_SERVICE_DESIGN.md` - 智能确认服务设计
- `SOFT_FILTER_SERVICE_DESIGN.md` - 软过滤服务设计
- `STORAGE_ARCHITECTURE_DECISION.md` - 存储架构决策
- `PERFORMANCE_OPTIMIZATION.md` - 性能优化
- `VECTOR_STORAGE_OPTIMIZATION.md` - 向量存储优化
- `WEB_SMART_RECALL_INTEGRATION.md` - Web 智能召回集成

### 开发计划
- `development-plan.md` - 早期开发计划
- `phase1_implementation_steps.md` - 第一阶段实现步骤
- `remaining_implementation_plan.md` - 剩余实现计划
- `product-development-hierarchy.md` - 产品开发层次

### 迁移计划
- `MIGRATION_PLAN_V3.md` - V3 迁移计划
- `MIGRATION_V5.md` - V5 迁移计划

### 实现计划
- `unified_dag_implementation_plan.md` - 统一 DAG 实现
- `PHASE3_ASYNC_IMPLEMENTATION_PLAN.md` - 第三阶段异步实现
- `FILESYSTEM_INTERFACE_IMPLEMENTATION_PLAN.md` - 文件系统接口实现

### 研究/分析文档
- `MEM0_RESEARCH.md` - Mem0 调研报告
- `MEM0_SOURCE_CODE_RESEARCH.md` - Mem0 源码研究
- `MEMORY_RECALL_VS_DB9_ANALYSIS.md` - 与 DB9 对比分析
- `dedup_cost_analysis.md` - 去重成本分析
- `user-pain-points.md` - 用户痛点分析
- `requirements.md` - 需求分析文档 (PRD)

### 历史实现文档
- `processing-pipeline.md` - 处理流水线
- `recall-mechanism.md` - 召回机制
- `MEMORY_STORAGE_FLOW.md` - 存储流程
- `MEMORY_POINT_CONTENT_STORAGE.md` - 记忆点内容存储
- `MEMORY_POINT_EXTRACTION.md` - 记忆点提取
- `api-design.md` - API 设计

### 变更日志
- `CHANGELOG_SMART_RECALL.md` - 智能召回变更日志

### 功能实现细节
- `SMART_RECALL_SUMMARY.md` - 智能召回实现总结
- `AUTO_MODE_EXPLAINED.md` - Auto 模式详解
- `AUTO_MODE_MULTI_ENTITY.md` - 多实体 Auto 模式
- `GRAPH_RECALL_FALLBACK.md` - 图谱召回降级
- `GRAPH_ENHANCED_RECALL.md` - 图谱增强召回
- `MULTI_ENTITY_HANDLING.md` - 多实体处理
- `ENTITY_MATCHING_README.md` - 实体匹配功能
- `ENTITY_DICT_UPDATE.md` - 实体字典更新
- `RELATION_TYPE_OPTIMIZATION.md` - 关系类型优化
- `add_relation_by_text.md` - 自然语言添加关系
- `multi_relation_parsing.md` - 多关系解析

### 2026-08-12 新增归档（文档体系重整）

本次归档原因：docs/ 根目录只保留"当前为真"的活文档（见 `docs/README.md` 文档生命周期规范），
以下文档因描述已实现/已废弃的功能而被移入 archive：

| 文档 | 原位置 | 归档原因 |
|------|--------|---------|
| `SMART_RECALL.md` | docs/ | 智能召回路由（Function Calling 选策略）已并入统一 `/context-inject` 召回，文档描述的是旧入口 |
| `MULTI_USER_GUIDE.md` | docs/ | 描述 v1 的 schema 隔离 + `/api/v1/users/init`；当前实现为 container_tag + API Key 隔离（`verify_container_ownership`） |
| `RECALL_TRACE_DESIGN.md` | docs/ | Recall Trace 功能已落地（recall_traces 表 + `/debug/traces` API），设计稿失去"当前为真"地位 |
| `RECALL_TRACE_DEV.md` | docs/ | 同上，落地实现说明见代码 `src/services/core/recall_trace_service.py` |

### 2026-08-12 新增归档（核心重构讨论稿）

| 文档 | 原位置 | 归档原因 |
|------|--------|---------|
| `2026-08-11_refactor_core_and_plugin.md` | docs/ | 核心服务 + 插件精简讨论稿：正文多处结论未经核实、不可信任；已拆解为 notes（讨论/调研/计划）与 ADR-0003~0008，仅作历史参考 |

Recall Trace 的现状入口：`/debug/traces`、`/debug/traces/{id}`、`/debug/traces/run`，
配置项 `TRACE_ENABLED/TRACE_SAMPLE_RATE/TRACE_RETENTION_DAYS/TRACE_CONTENT_MAX_LEN`。

---

*归档日期: 2026-03-31*
*更新: 2026-08-12（新增 4 篇归档 + 核心重构讨论稿归档 + 索引）*
*当前版本: v5.0.0*
