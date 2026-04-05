# Changelog

All notable changes to Memory Recall will be documented in this file.

## [5.1.9] - 2026-04-05

### Changed
- Session Summary 提取优化：移除【偏好/约束】部分，仅保留【发现/决策】和【明确约束】
- 减少上下文存储冗余：避免保存用户偏好重复信息（用户偏好已存储在 Profile 中）

## [5.1.8] - 2026-04-05

### Added
- 实体过滤机制：多层过滤（黑名单 + 格式校验 + 长度校验）
- 扩展黑名单至 80+ 词（泛指名词、语言名称、动词状态等）
- 格式过滤函数 `should_skip_entity()`（跳过文件路径、纯数值、长度异常）
- 清理脚本 `scripts/cleanup_entities.py`（dry-run 预览 + 备份 + 清理）
- 恢复脚本 `scripts/restore_entities_backup.py`（从备份恢复）

### Changed
- 优化中文实体提取 Prompt：添加"【不要提取】"和"【边界规则】"章节
- 配置项新增：`ENTITY_FILTER_MIN_LENGTH`, `ENTITY_FILTER_MAX_LENGTH`, `ENTITY_FILTER_SKIP_FILE_PATHS`, `ENTITY_FILTER_SKIP_NUMERIC`
- 后处理过滤集成：`extract_with_relations()` 返回前调用过滤函数

### Fixed
- 修复无意义实体入库问题（"用户"、"代码"、"技术"、"中文"等不再入库）
- 修复格式错误提取问题（文件路径、纯数值不再作为实体）
- 修复类型判断错误问题（通过 Prompt 边界规则强化）

## [5.1.7] - 2026-04-04

### Added
- Session Summary 提取优化：只保存重要内容（偏好/约束、发现/决策、明确约束）
- 自动去重：避免重复存储相似内容
- 存储格式优化：从几千字压缩到几百字

### Changed
- OpenCode 插件版本：1.7.9 → 1.8.0
- 新增 `summary-extractor.ts` 提取重要内容
- 修改 `compaction.ts` 使用新提取逻辑

## [5.1.6] - 2026-04-04

### Added
- 项目隔离：自动为每个项目生成独立的 container_tag
- keyId 配置：插件配置改用 `keyId`，自动生成 `userTag` 和 `projectTag`
- 后端验证增强：`verify_container_ownership` 支持前缀匹配

### Changed
- OpenCode 插件版本：1.7.8 → 1.7.9
- CLI 使用 `keyId` 配置
- 自动生成项目隔离的 container_tag

### Fixed
- 后端 Session Summary 过滤：`context_inject_service.py` 自动过滤

## [5.1.5] - 2026-04-03

### Breaking Changes

#### 废弃 Migration 机制
- **删除** `migrations/` 目录
- **使用** `schema.sql` + `init_db.py` 初始化新环境
- 新环境部署：`python init_db.py`

#### 数据库结构更新
- **api_keys**: 添加 `user_name` 字段
- **memories**: 保留版本控制字段（`version`, `root_memory_id`, `source_count`, `is_inference`）
- **memory_profiles**: 保留 `entity_context` 字段
- **documents**: 重构为元数据表（添加 `title`, `url`, `source`, `doc_type`, `token_count`, `word_count`, `chunk_count`）
- **chunks**: 新增表，存储文档分块和嵌入

### Removed
- `migrations/` 目录（26个迁移文件已废弃）
- `container_registry` 表（不再需要）

### Added
- `schema.sql`：完整的数据库结构定义
- `chunks` 表：文档内容分块存储

## [5.1.4] - 2026-04-03

### Bug Fixes

#### 数据库迁移修复
- 修复 `002_add_indexes.sql` 中错误的列名（`entity_type` → `type`, `relationship` → `relation_type`）
- 修复 `002_add_indexes.sql` 迁移顺序问题（移除 `memories` 表索引，表在迁移 007 才创建）
- 在 `003_add_embedding.sql` 中添加 `CREATE EXTENSION IF NOT EXISTS vector;`

#### Docker 部署优化
- 添加 `docker-entrypoint-initdb.d/00_install_extensions.sql` 自动安装 pgvector 扩展
- 更新 `docker-compose.yml` 挂载初始化脚本目录

#### 文档更新
- README 添加 Docker 部署说明
- 添加服务地址和 pgAdmin 登录信息

## [5.1.3] - 2026-04-02

### Code Cleanup

删除废弃的图谱服务和冗余代码，保持代码库整洁。

#### 删除的服务（~3,973 行代码）
- `graph_recall_service.py` (1053行) - 已标记 DEPRECATED，无 API 调用
- `graph_builder_service.py` (775行) - 无 API 端点调用
- `enhanced_entity_extractor.py` (466行) - 仅被废弃服务调用
- `llm_recall_service.py` (324行) - 功能已迁移到 `context_inject_service`
- `entity_dictionary_service.py` (292行) - 实体表已替代内存词典
- `confirmation_service.py` (297行) - 完全未使用的死代码

#### 删除的测试文件
- `test_confirmation_service.py`
- `test_dict_update.py`
- `test_enhanced_entity_extraction.py`

#### 功能迁移
这些服务的功能已统一到：
- `context_inject_service.py` - 双图谱召回
- `memory_store.py` - 三层召回方法
- `llm_entity_extraction.py` - LLM 实体提取

#### 影响
- 删除代码：~3,973 行
- 不影响现有功能（这些服务已无调用）

## [5.1.2] - 2026-04-02

### Code Cleanup

删除废弃的 lossless 架构服务，保持代码库整洁。

#### 删除的服务
- `raw_message_store.py` - 查询已删除的 `raw_messages` 表
- `summary_store.py` - 查询已删除的 `summaries` 表
- `context_store.py` - 使用旧架构
- `compaction_engine.py` - 功能已合并到其他服务
- `dag_expand_service.py` - 功能已合并到 `relation_service`
- `memory_service.py` - 功能已合并到 `memory_store`
- `lossless.py` - 废弃的数据模型

#### 影响
- 删除代码：~1,970 行
- 不影响现有功能（这些服务已无调用）
- 清理 `services/core/__init__.py` 废弃导出

### Related
- OpenSpec change: `codebase-cleanup-and-review`

## [5.1.1] - 2026-04-02

### Bug Fixes

#### 实体去重策略优化
- 修复 `graph_builder_service._upsert_entity()` 字段名错误（`entity_type` → `type`）
- 修复 `memory_store._store_entity_graph()` 去重逻辑
- 调整 UNIQUE 约束：`(name, type, container_tag)` 支持同名不同类型实体
- 新增 `normalize_entity_name()` 归一化函数（大小写 + 空格处理）
- 新增归一化索引：`idx_entities_normalized_name`

#### 前端插件修复
- 修复 `context.ts` 后端 API 参数名映射错误：
  - `enable_graph_recall` → `enable_memory_graph`
  - `graph_max_depth` → `memory_graph_depth`
  - `graph_max_nodes` → `memory_graph_nodes`
- 新增 Entity Graph 参数：`enable_entity_graph`, `entity_graph_depth`, `entity_graph_nodes`

### Database Changes
- Migration 030: Entity Dedup Enhancement
  - 删除旧约束 `uq_entities_name_container`
  - 添加新约束 `uq_entities_name_type_container`
  - 创建归一化索引 `idx_entities_normalized_name`

### Code Changes
- `graph_tools.py`: 新增 `normalize_entity_name()` 函数
- `graph_builder_service.py`: 修复字段名 + 归一化查询
- `memory_store.py`: 修复去重逻辑 + 导入归一化函数
- `context.ts`: 修复后端 API 参数映射

## [5.1.0] - 2026-04-02

### Major Changes

#### Entity Graph 架构
- 新增 `entities` 表：存储提取的实体（人物、地点、组织等）
- 新增 `entity_relations` 表：存储实体间关系
- 新增 `memory_entities` 关联表：连接记忆与实体
- 支持 12 种预定义关系类型（friend/colleague/works_at/lives_at 等）

#### 双图谱召回系统
- **Memory Graph**：遍历记忆演进关系（updates/extends/derives）
- **Entity Graph**：遍历实体关系网络
- **三层召回**：Vector Search + Memory Graph + Entity Graph
- 配置参数：`enable_memory_graph`, `enable_entity_graph`, `*_depth`, `*_nodes`

#### Entity Graph 遍历服务
- `traverse_entity_relations()` - 双向遍历实体关系
- `get_entities_for_memories()` - 获取记忆关联实体
- `find_memories_by_entities()` - 通过实体查找记忆

#### Context Injection 增强
- 集成双图谱召回到上下文注入流程
- 新增 API 配置参数支持图谱召回控制
- 前端 `ContextInjectConfig` 接口更新

#### 数据迁移工具
- `run_027_migrate_entities.py` - 从 metadata 迁移实体到新表
- `run_028_reextract_relations.py` - 使用 LLM 重提取关系
- `run_029_check_consistency.py` - 数据一致性检查

### Database Changes
- Migration 026: Create Entity Graph tables
- 新增索引：`idx_entities_name`, `idx_entity_relations_from/to`, `idx_memory_entities_*`
- UNIQUE 约束：实体去重、关系去重

### API Changes
- `POST /context-inject` 新增参数：
  - `enable_memory_graph: bool` - 启用 Memory Graph 召回
  - `enable_entity_graph: bool` - 启用 Entity Graph 召回
  - `memory_graph_depth: int` - Memory Graph 遍历深度
  - `memory_graph_nodes: int` - Memory Graph 最大节点数
  - `entity_graph_depth: int` - Entity Graph 遍历深度
  - `entity_graph_nodes: int` - Entity Graph 最大节点数
  - `memory_similarity_threshold: float` - 记忆相似度阈值

### Code Reuse
- 复用 `graph_tools.RELATION_TYPES` 和 `ENTITY_TYPES`
- 复用 `graph_builder_service._upsert_entity/relation()` 去重逻辑
- 复用 `relation_service.get_related_memories()` 遍历逻辑

### Tests
- 新增 12 个 Entity Graph 遍历单元测试
- 新增 4 个 Context Injection 集成测试
- 修复 `TestTraverseMemoryRelations` mock 配置

## [5.0.0] - 2026-03-29

### Major Changes

#### Universal Agent Memory Service
- Transformed from OpenClaw ContextEngine plugin to standalone REST API service
- Added API Key authentication with `rk_live_xxx` and `rk_test_xxx` formats
- Implemented permission levels: read, write, delete, admin

#### New REST API v1 Endpoints
- `POST /v1/memories` - Create memory with behavior/lifespan
- `GET /v1/memories` - List memories with pagination
- `GET /v1/memories/{id}` - Get single memory
- `PATCH /v1/memories/{id}` - Update memory metadata
- `DELETE /v1/memories/{id}` - Delete memory
- `POST /v1/memories/{id}/forget` - Mark as forgotten
- `POST /v1/recall` - Smart recall with RRF fusion
- `GET /v1/profile` - Get user profile (~50ms target)
- `POST /v1/profile/refresh` - Force profile rebuild
- `POST /v1/containers` - Create container
- `GET /v1/containers` - List containers
- `GET /v1/memories/{id}/relations` - Get memory relations
- `GET /v1/memories/{id}/history` - Get version chain
- `GET /v1/notifications` - List notifications

#### Memory Evolution Services
- **UserProfileService** - Aggregates static facts, dynamic facts, and preferences
- **TemporalService** - Time-aware lifecycle management with configurable lifespans
- **ForgettingService** - Auto-expiration with notifications
- **ChunkingService** - Long document splitting (sentence/semantic/fixed strategies)
- **FactExtractionService** - Entity-centric fact extraction from content
- **ImportanceService** - Multi-factor importance scoring
- **FusionService** - Memory deduplication and merging

#### Memory Behaviors (NEW)
- `fact` - Persistent until updated, no decay
- `preference` - Strengthens with repetition
- `episode` - Decays unless significant

#### Memory Lifespans
- `temporary` - 1 day
- `short_term` - 30 days
- `long_term` - 365 days
- `permanent` - 100 years

#### Background Tasks
- Profile rebuild task (every 5 minutes)
- Expiration check task (daily)
- Cleanup task (daily)

### Database Changes

#### New Tables (Migration 017)
- `api_keys` - API key management
- `memory_relations` - Memory relationships
- `user_profiles` - Aggregated user profiles
- `facts` - Entity-centric facts
- `notifications` - System notifications
- `content_chunks` - Long document chunks

#### New Columns in raw_messages
- `event_date` - When event occurred
- `document_date` - When recorded
- `expiration_date` - Auto-forget timestamp
- `memory_lifespan` - Retention policy
- `is_latest` - Version control flag
- `is_expired` - Soft delete flag
- `container_id` - Grouping identifier
- `access_count` - Recall frequency
- `last_accessed_at` - Last access time
- `importance_score` - Calculated importance
- `memory_behavior` - fact/preference/episode
- `chunk_count` - Number of chunks

### Improvements

#### Recall Enhancements
- Reciprocal Rank Fusion (RRF) for result merging
- Time decay scoring (30-day half-life)
- Importance weighting
- Memory behavior weighting
- Profile-first recall option
- Chunk injection for long documents

#### Performance
- Target: ~50ms for profile retrieval
- Optimized database queries with proper indexing

### Breaking Changes
- Removed `src/openclaw_plugin/` directory
- Renamed `services/lossless/` to `services/core/`
- Renamed `MemoryRecallEngine` to `MemoryService`
- Removed legacy `memory_service.py`, `recall_service.py`

### Migration Guide

1. Run migration 017:
```bash
python migrations/run_single_migration.py migrations/017_clean_and_evolve.sql
```

2. Update imports:
```python
# Old
from src.services.lossless.memory_recall_engine import memory_recall_engine

# New
from src.services.core.memory_service import memory_service
```

3. Generate API keys:
```bash
POST /v1/auth/api-keys
{
    "name": "My API Key",
    "permissions": ["read", "write"]
}
```

## [3.0.0] - Previous Release
- DAG compression architecture
- Hybrid recall (vector + keyword + graph)
- Entity extraction
- Knowledge graph integration
