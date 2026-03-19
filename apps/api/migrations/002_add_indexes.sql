-- 数据库查询优化索引
-- 执行时间: 2026-03-20

-- ==================== 实体和关系表索引 ====================

-- 实体表索引
CREATE INDEX IF NOT EXISTS idx_entities_user_name ON entities(user_id, name);
CREATE INDEX IF NOT EXISTS idx_entities_user_type ON entities(user_id, entity_type);
CREATE INDEX IF NOT EXISTS idx_entities_name ON entities(name);

-- 关系表索引
CREATE INDEX IF NOT EXISTS idx_relations_user_from ON relations(user_id, from_entity_id);
CREATE INDEX IF NOT EXISTS idx_relations_user_to ON relations(user_id, to_entity_id);
CREATE INDEX IF NOT EXISTS idx_relations_type ON relations(relationship);

-- 记忆-实体关联表索引
CREATE INDEX IF NOT EXISTS idx_memory_entities_memory ON memory_entities(memory_id);
CREATE INDEX IF NOT EXISTS idx_memory_entities_entity ON memory_entities(entity_id);

-- ==================== 记忆表优化 ====================

-- 用户+创建时间复合索引（常用查询）
CREATE INDEX IF NOT EXISTS idx_memories_user_created ON memories(user_id, created_at DESC);

-- 状态索引
CREATE INDEX IF NOT EXISTS idx_memories_status ON memories(status);

-- 向量索引（pgvector 自动创建，但可以优化参数）
-- 注意：向量索引会在插入大量数据后自动创建
-- CREATE INDEX IF NOT EXISTS idx_memories_embedding ON memories USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- ==================== 待确认表索引 ====================

CREATE INDEX IF NOT EXISTS idx_pending_confirmations_user ON pending_confirmations(user_id);
CREATE INDEX IF NOT EXISTS idx_pending_confirmations_status ON pending_confirmations(status);

-- ==================== 分析查询 ====================

-- 查看索引使用情况
SELECT
    schemaname,
    tablename,
    indexname,
    idx_scan as index_scans,
    idx_tup_read as tuples_read,
    idx_tup_fetch as tuples_fetched
FROM pg_stat_user_indexes
WHERE schemaname = 'public'
ORDER BY idx_scan DESC;

-- 查看表大小
SELECT
    relname as table_name,
    pg_size_pretty(pg_total_relation_size(relid)) as total_size,
    pg_size_pretty(pg_relation_size(relid)) as table_size,
    pg_size_pretty(pg_total_relation_size(relid) - pg_relation_size(relid)) as index_size
FROM pg_catalog.pg_statio_user_tables
ORDER BY pg_total_relation_size(relid) DESC;

-- 查看缺失索引
SELECT
    schemaname,
    tablename,
    attname,
    n_distinct,
    correlation
FROM pg_stats
WHERE schemaname = 'public'
  AND n_distinct > 100
  AND correlation < 0.5
ORDER BY n_distinct DESC;
