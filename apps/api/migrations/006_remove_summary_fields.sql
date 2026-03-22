-- 删除摘要相关字段
-- 创建时间: 2026-03-20

-- 删除字段
ALTER TABLE memories DROP COLUMN IF EXISTS summary;
ALTER TABLE memories DROP COLUMN IF EXISTS summary_embedding;

-- 删除索引
DROP INDEX IF EXISTS idx_memories_summary;
DROP INDEX IF EXISTS idx_memories_summary_embedding;