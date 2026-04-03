-- 数据库查询优化索引
-- 执行时间: 2026-03-20
-- 注意：memories 表的索引在后续迁移（007, 018）中创建

-- ==================== 实体和关系表索引 ====================

-- 实体表索引
CREATE INDEX IF NOT EXISTS idx_entities_user_name ON entities(user_id, name);
CREATE INDEX IF NOT EXISTS idx_entities_user_type ON entities(user_id, type);
CREATE INDEX IF NOT EXISTS idx_entities_name ON entities(name);

-- 关系表索引
CREATE INDEX IF NOT EXISTS idx_relations_user_from ON relations(user_id, from_entity_id);
CREATE INDEX IF NOT EXISTS idx_relations_user_to ON relations(user_id, to_entity_id);
CREATE INDEX IF NOT EXISTS idx_relations_type ON relations(relation_type);

-- 记忆-实体关联表索引
CREATE INDEX IF NOT EXISTS idx_memory_entities_memory ON memory_entities(memory_id);
CREATE INDEX IF NOT EXISTS idx_memory_entities_entity ON memory_entities(entity_id);

-- ==================== 待确认表索引 ====================

CREATE INDEX IF NOT EXISTS idx_pending_confirmations_user ON pending_confirmations(user_id);
CREATE INDEX IF NOT EXISTS idx_pending_confirmations_status ON pending_confirmations(status);

-- ==================== 注意事项 ====================
-- memories 表的索引在以下迁移中创建：
-- - 007_multi_user_schema.sql: idx_memories_created_at, idx_memories_status, idx_memories_embedding
-- - 018_simplified_memory_schema.sql: idx_memories_container, idx_memories_static, idx_memories_created
