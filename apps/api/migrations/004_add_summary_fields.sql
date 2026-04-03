-- 记忆网络构建系统 - 数据库迁移
-- 版本：004
-- 创建时间：2026-03-20
-- 说明：添加记忆摘要和关键事件字段
-- 注意：此迁移已废弃，memories 表在迁移 007 才创建
--       这些字段在迁移 006 被移除，且不在最终架构中

-- ============================================================================
-- 检查 memories 表是否存在，不存在则跳过
-- ============================================================================

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'memories' AND table_schema = 'public') THEN
        RAISE NOTICE 'memories table does not exist yet (created in migration 007), skipping migration 004';
    ELSE
        -- 添加摘要字段
        ALTER TABLE memories ADD COLUMN IF NOT EXISTS summary TEXT;
        
        -- 添加关键事件字段（JSON 数组）
        ALTER TABLE memories ADD COLUMN IF NOT EXISTS key_events JSONB;
        
        -- 添加摘要向量（用于摘要搜索）
        ALTER TABLE memories ADD COLUMN IF NOT EXISTS summary_embedding VECTOR(1024);
        
        -- 创建摘要全文搜索索引
        CREATE INDEX IF NOT EXISTS idx_memories_summary ON memories 
        USING gin(to_tsvector('simple', summary));
        
        -- 创建摘要向量索引（用于相似摘要搜索）
        CREATE INDEX IF NOT EXISTS idx_memories_summary_embedding ON memories 
        USING ivfflat (summary_embedding vector_cosine_ops) WITH (lists = 100);
        
        -- 创建关键事件索引（用于事件查询）
        CREATE INDEX IF NOT EXISTS idx_memories_key_events ON memories USING gin(key_events);
        
        -- 添加字段注释
        COMMENT ON COLUMN memories.summary IS '记忆摘要：简洁的内容概括（自动生成或手动提供）';
        COMMENT ON COLUMN memories.key_events IS '关键事件：从记忆中提取的关键事件列表（JSON 数组）';
        COMMENT ON COLUMN memories.summary_embedding IS '摘要向量：用于摘要相似度搜索';
        
        RAISE NOTICE 'Migration 004 completed: added summary fields to memories table';
    END IF;
END $$;

-- 完成
SELECT 'Migration 004 completed successfully!' AS status;