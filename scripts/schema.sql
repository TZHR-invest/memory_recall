-- Memory Recall - 数据库 Schema
-- PostgreSQL + pgvector

-- 启用 pgvector 扩展
CREATE EXTENSION IF NOT EXISTS vector;

-- ========== 记忆表 ==========
CREATE TABLE memories (
    id VARCHAR(24) PRIMARY KEY,
    content TEXT NOT NULL,
    input_type VARCHAR(10) NOT NULL CHECK (input_type IN ('text', 'image', 'audio')),
    
    -- 时间字段
    time_value TIMESTAMP WITH TIME ZONE,
    time_source VARCHAR(10) CHECK (time_source IN ('extracted', 'inferred', 'metadata')),
    time_confidence FLOAT,
    time_original_text TEXT,
    
    -- 位置字段
    location_name TEXT,
    location_address TEXT,
    location_latitude FLOAT,
    location_longitude FLOAT,
    location_need_confirm BOOLEAN DEFAULT false,
    location_original_text TEXT,
    
    -- 人物字段（JSON 数组）
    people JSONB DEFAULT '[]'::jsonb,
    
    -- 可选字段
    emotion JSONB,
    tags JSONB DEFAULT '[]'::jsonb,
    duration JSONB,
    topic JSONB,
    
    -- 附件
    attachments JSONB DEFAULT '[]'::jsonb,
    
    -- 向量（1024 维，对应 doubao-embedding-vision）
    embedding vector(1024),
    
    -- 系统字段
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    access_count INTEGER DEFAULT 0,
    last_accessed_at TIMESTAMP WITH TIME ZONE,
    importance_score FLOAT DEFAULT 0.5,
    status VARCHAR(10) DEFAULT 'active' CHECK (status IN ('active', 'archived', 'deleted'))
);

-- 创建索引
CREATE INDEX idx_memories_created_at ON memories(created_at DESC);
CREATE INDEX idx_memories_time_value ON memories(time_value);
CREATE INDEX idx_memories_location_name ON memories USING gin(to_tsvector('simple', location_name));
CREATE INDEX idx_memories_tags ON memories USING gin(tags);
CREATE INDEX idx_memories_people ON memories USING gin(people);
CREATE INDEX idx_memories_status ON memories(status);

-- 向量索引（使用 HNSW）
CREATE INDEX idx_memories_embedding ON memories USING hnsw (embedding vector_cosine_ops);

-- 全文搜索索引
CREATE INDEX idx_memories_content_fts ON memories USING gin(to_tsvector('simple', content));

-- 更新时间触发器
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_memories_updated_at
    BEFORE UPDATE ON memories
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at();

-- ========== 人物档案表 ==========
CREATE TABLE persons (
    id VARCHAR(24) PRIMARY KEY,
    name TEXT NOT NULL,
    aliases JSONB DEFAULT '[]'::jsonb,
    relationship VARCHAR(50),
    
    first_mentioned TIMESTAMP WITH TIME ZONE,
    last_mentioned TIMESTAMP WITH TIME ZONE,
    mention_count INTEGER DEFAULT 0,
    
    profile JSONB DEFAULT '{}'::jsonb,
    interactions JSONB DEFAULT '[]'::jsonb,
    notes TEXT,
    tags JSONB DEFAULT '[]'::jsonb,
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 索引
CREATE INDEX idx_persons_name ON persons USING gin(to_tsvector('simple', name));
CREATE INDEX idx_persons_aliases ON persons USING gin(aliases);
CREATE INDEX idx_persons_last_mentioned ON persons(last_mentioned DESC);

-- 更新时间触发器
CREATE TRIGGER trigger_persons_updated_at
    BEFORE UPDATE ON persons
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at();

-- ========== 人脸特征表 ==========
CREATE TABLE face_features (
    id VARCHAR(24) PRIMARY KEY,
    person_id VARCHAR(24) REFERENCES persons(id) ON DELETE SET NULL,
    image_path TEXT NOT NULL,
    
    -- 人脸框
    face_box JSONB,
    landmarks JSONB,
    
    -- 人脸特征向量（128 维，face_recognition 标准）
    embedding vector(128),
    
    -- 质量评分
    quality_score FLOAT,
    blur_score FLOAT,
    brightness FLOAT,
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    source_memory VARCHAR(24) REFERENCES memories(id) ON DELETE SET NULL
);

-- 向量索引
CREATE INDEX idx_face_features_embedding ON face_features USING hnsw (embedding vector_cosine_ops);
CREATE INDEX idx_face_features_person_id ON face_features(person_id);
CREATE INDEX idx_face_features_quality ON face_features(quality_score DESC);

-- ========== 索引缓存表 ==========
CREATE TABLE index_cache (
    id SERIAL PRIMARY KEY,
    index_type VARCHAR(20) NOT NULL,  -- time/location/people/tags
    key_value TEXT NOT NULL,           -- 索引键值
    memory_ids JSONB NOT NULL,         -- 记忆 ID 列表
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    UNIQUE(index_type, key_value)
);

CREATE INDEX idx_index_cache_type ON index_cache(index_type);

-- ========== 插入测试数据 ==========
INSERT INTO memories (id, content, input_type, time_value, time_source, tags, status) VALUES
('mem_test001', '这是一条测试记忆', 'text', NOW(), 'extracted', '["测试"]'::jsonb, 'active');

INSERT INTO persons (id, name, relationship, mention_count, tags) VALUES
('person_test001', '测试人物', '朋友', 1, '["测试"]'::jsonb);

-- 输出创建成功信息
SELECT 'Database schema created successfully!' as message;
