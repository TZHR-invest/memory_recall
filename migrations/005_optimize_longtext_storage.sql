-- 优化长文本存储
-- 问题：主记忆存储完整内容导致数据冗余
-- 解决：主记忆只存储摘要和分段索引，分段内容存储在子记忆中

-- 1. 添加分段索引字段
ALTER TABLE memories ADD COLUMN IF NOT EXISTS segment_ids JSONB;

-- segment_ids 格式示例：["uuid1", "uuid2", "uuid3"]
-- 用于存储分段记忆的 ID 列表，支持按顺序重组完整内容

-- 2. 创建索引以提高查询性能
CREATE INDEX IF NOT EXISTS idx_memories_segment_ids ON memories USING GIN (segment_ids);

-- 3. 添加元数据字段（可选，用于存储文件信息）
ALTER TABLE memories ADD COLUMN IF NOT EXISTS file_name VARCHAR(500);
ALTER TABLE memories ADD COLUMN IF NOT EXISTS file_size INTEGER;
ALTER TABLE memories ADD COLUMN IF NOT EXISTS segment_count INTEGER;
