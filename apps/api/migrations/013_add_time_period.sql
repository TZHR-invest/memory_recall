-- 添加时间段字段
-- 用于支持"昨天晚上"、"今天早上"等时间段查询
-- 注意：public.memories 表在迁移 018 才创建，这里检查表是否存在

-- ============================================================================
-- 检查 memories 表是否存在
-- ============================================================================

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'memories' AND table_schema = 'public') THEN
        RAISE NOTICE 'public.memories table does not exist yet (created in migration 018), skipping migration 013';
    ELSE
        -- 添加 time_period 字段到 memories 表
        ALTER TABLE memories ADD COLUMN IF NOT EXISTS time_period VARCHAR(20);
        
        -- 添加注释
        COMMENT ON COLUMN memories.time_period IS '时间段: morning, afternoon, evening, night';
        
        -- 创建索引（可选，如果需要按时间段查询）
        -- CREATE INDEX IF NOT EXISTS idx_memories_time_period ON memories(time_period);
        
        RAISE NOTICE 'Migration 013 completed: added time_period field to memories table';
    END IF;
END $$;

-- 完成
SELECT 'Migration 013 completed successfully!' AS status;