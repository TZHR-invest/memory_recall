-- 记忆网络构建系统 - 数据库迁移
-- 版本：004
-- 创建时间：2026-03-20
-- 说明：添加记忆摘要和关键事件字段

-- ============================================================================
-- 1. 为 memories 表添加摘要和关键事件字段
-- ============================================================================

-- 添加摘要字段
ALTER TABLE memories ADD COLUMN IF NOT EXISTS summary TEXT;

-- 添加关键事件字段（JSON 数组）
ALTER TABLE memories ADD COLUMN IF NOT EXISTS key_events JSONB;

-- 添加摘要向量（用于摘要搜索）
ALTER TABLE memories ADD COLUMN IF NOT EXISTS summary_embedding VECTOR(1024);

-- ============================================================================
-- 2. 创建索引
-- ============================================================================

-- 创建摘要全文搜索索引
CREATE INDEX IF NOT EXISTS idx_memories_summary ON memories 
USING gin(to_tsvector('simple', summary));

-- 创建摘要向量索引（用于相似摘要搜索）
CREATE INDEX IF NOT EXISTS idx_memories_summary_embedding ON memories 
USING ivfflat (summary_embedding vector_cosine_ops) WITH (lists = 100);

-- 创建关键事件索引（用于事件查询）
CREATE INDEX IF NOT EXISTS idx_memories_key_events ON memories USING gin(key_events);

-- ============================================================================
-- 3. 添加字段注释
-- ============================================================================

COMMENT ON COLUMN memories.summary IS '记忆摘要：简洁的内容概括（自动生成或手动提供）';
COMMENT ON COLUMN memories.key_events IS '关键事件：从记忆中提取的关键事件列表（JSON 数组）';
COMMENT ON COLUMN memories.summary_embedding IS '摘要向量：用于摘要相似度搜索';

-- ============================================================================
-- 4. 使用示例
-- ============================================================================

-- 示例 1：插入带摘要的记忆
-- INSERT INTO memories (id, content, summary, key_events, summary_embedding, ...)
-- VALUES (..., '完整内容', '这是摘要', '["事件1", "事件2"]'::jsonb, embedding_vector, ...);

-- 示例 2：搜索相似摘要
-- SELECT id, content, summary, 
--        1 - (summary_embedding <=> <query_vector>) AS similarity
-- FROM memories
-- WHERE summary IS NOT NULL
-- ORDER BY summary_embedding <=> <query_vector>
-- LIMIT 10;

-- 示例 3：全文搜索摘要
-- SELECT id, content, summary
-- FROM memories
-- WHERE to_tsvector('simple', summary) @@ to_tsquery('simple', '关键词')
-- ORDER BY created_at DESC;

-- ============================================================================
-- 5. 数据迁移（可选）
-- ============================================================================

-- 如果需要为现有记忆生成摘要，可以运行以下脚本：
-- 注意：这需要 Python 代码执行，不能在 SQL 中直接完成

-- UPDATE memories 
-- SET summary = <generated_summary>,
--     summary_embedding = <generated_embedding>
-- WHERE content_length > 500 AND summary IS NULL;

-- 完成
SELECT 'Migration 004 completed successfully!' AS status;
