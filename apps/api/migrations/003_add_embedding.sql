-- 记忆网络构建系统 - 数据库迁移
-- 版本：003
-- 创建时间：2026-03-20
-- 说明：添加图谱增强召回功能

-- ============================================================================
-- 0. 安装 pgvector 扩展（必须先安装）
-- ============================================================================
CREATE EXTENSION IF NOT EXISTS vector;

-- ============================================================================
-- 1. 为 entities 表添加 embedding 字段
-- ============================================================================

-- 添加 embedding 字段（1024 维向量，匹配 doubao-embedding-vision-251215）
ALTER TABLE entities ADD COLUMN IF NOT EXISTS embedding VECTOR(1024);

-- 创建向量索引（使用 IVFFlat）
CREATE INDEX IF NOT EXISTS idx_entities_embedding ON entities 
USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

COMMENT ON COLUMN entities.embedding IS '实体向量：用于向量相似度搜索';

-- ============================================================================
-- 2. 为 relations 表添加关系强度索引
-- ============================================================================

CREATE INDEX IF NOT EXISTS idx_relations_weight ON relations(weight DESC);

-- ============================================================================
-- 3. 添加记忆-实体关联的上下文索引
-- ============================================================================

CREATE INDEX IF NOT EXISTS idx_memory_entities_context ON memory_entities 
USING gin(to_tsvector('simple', mention_context));

-- ============================================================================
-- 4. 说明
-- ============================================================================

-- 向量索引说明：
-- - IVFFlat 适用于中小规模数据（< 100 万条）
-- - lists = 100 表示聚类中心数量
-- - vector_cosine_ops 使用余弦距离

-- 使用方法：
-- 1. 生成实体 embedding：
--    UPDATE entities SET embedding = <embedding_vector> WHERE id = <entity_id>;
--
-- 2. 向量搜索实体：
--    SELECT name, 1 - (embedding <=> <query_vector>) AS similarity
--    FROM entities
--    WHERE user_id = <user_id>
--    ORDER BY embedding <=> <query_vector>
--    LIMIT 10;
