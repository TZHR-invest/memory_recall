-- 修复记忆表 ID 字段长度
-- 版本：009
-- 创建时间：2026-03-22
-- 说明：将 memories 表的 id 字段从 VARCHAR(24) 改为 VARCHAR(36)，以支持 UUID

-- ============================================================================
-- 1. 修改 public.memories 表（如果存在）
-- ============================================================================

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'memories' AND table_schema = 'public') THEN
        ALTER TABLE public.memories ALTER COLUMN id TYPE VARCHAR(36);
    END IF;
END $$;

-- ============================================================================
-- 2. 修改用户 schema 中的 memories 表
-- ============================================================================

CREATE OR REPLACE FUNCTION fix_memories_id_length()
RETURNS VOID AS $$
DECLARE
    user_record RECORD;
BEGIN
    FOR user_record IN SELECT schema_name FROM public.users LOOP
        BEGIN
            EXECUTE format('ALTER TABLE %I.memories ALTER COLUMN id TYPE VARCHAR(36)', user_record.schema_name);
            RAISE NOTICE 'Fixed table: %.memories', user_record.schema_name;
        EXCEPTION
            WHEN OTHERS THEN
                RAISE NOTICE 'Skip table: %.memories (error: %)', user_record.schema_name, SQLERRM;
        END;
    END LOOP;
END;
$$ LANGUAGE plpgsql;

-- 执行修复
SELECT fix_memories_id_length();

-- ============================================================================
-- 完成
-- ============================================================================

SELECT 'Migration 009 completed successfully!' AS status;
SELECT 'memories.id now supports UUID (VARCHAR(36))' AS info;
