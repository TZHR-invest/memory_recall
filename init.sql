-- 初始化 PostgreSQL 数据库
-- 启用 pgvector 扩展

CREATE EXTENSION IF NOT EXISTS vector;

-- 创建记忆表
CREATE TABLE IF NOT EXISTS memories (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    content TEXT NOT NULL,
    time_value TIMESTAMP,
    time_source VARCHAR(20),
    time_confidence FLOAT,
    location_name VARCHAR(255),
    location_need_confirm BOOLEAN DEFAULT FALSE,
    location_source VARCHAR(20),
    people JSONB,
    emotion_value VARCHAR(50),
    emotion_confidence FLOAT,
    tags JSONB,
    embedding VECTOR(768),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 创建向量索引
CREATE INDEX IF NOT EXISTS memories_embedding_idx ON memories USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- 创建时间索引
CREATE INDEX IF NOT EXISTS memories_time_idx ON memories (time_value);

-- 创建位置索引
CREATE INDEX IF NOT EXISTS memories_location_idx ON memories (location_name);

-- 创建标签索引
CREATE INDEX IF NOT EXISTS memories_tags_idx ON memories USING gin (tags);

-- 创建更新时间触发器
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER memories_updated_at
BEFORE UPDATE ON memories
FOR EACH ROW
EXECUTE FUNCTION update_updated_at();
