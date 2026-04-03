-- 删除摘要相关字段
-- 创建时间: 2026-03-20
-- 注意：此迁移已废弃，memories 表在迁移 007 才创建
--       这些字段在迁移 004 添加（如果表存在），最终不在架构中

-- ============================================================================
-- 检查 memories 表是否存在，不存在则跳过
-- ============================================================================

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'memories' AND table_schema = 'public') THEN
        RAISE NOTICE 'memories table does not exist yet (created in migration 007), skipping migration 006';
    ELSE
        -- 删除字段
        ALTER TABLE memories DROP COLUMN IF EXISTS summary;
        ALTER TABLE memories DROP COLUMN IF EXISTS summary_embedding;
        
        -- 删除索引
        DROP INDEX IF EXISTS idx_memories_summary;
        DROP INDEX IF EXISTS idx_memories_summary_embedding;
        
        RAISE NOTICE 'Migration 006 completed: removed summary fields from memories table';
    END IF;
END $$;

-- 完成
SELECT 'Migration 006 completed successfully!' AS status;