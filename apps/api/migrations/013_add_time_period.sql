-- 添加时间段字段
-- 用于支持"昨天晚上"、"今天早上"等时间段查询

-- 添加 time_period 字段到 memories 表
ALTER TABLE memories ADD COLUMN IF NOT EXISTS time_period VARCHAR(20);

-- 添加注释
COMMENT ON COLUMN memories.time_period IS '时间段: morning, afternoon, evening, night';

-- 创建索引（可选，如果需要按时间段查询）
-- CREATE INDEX IF NOT EXISTS idx_memories_time_period ON memories(time_period);
