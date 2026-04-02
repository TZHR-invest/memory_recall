# Changelog

All notable changes to Memory Recall will be documented in this file.

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
