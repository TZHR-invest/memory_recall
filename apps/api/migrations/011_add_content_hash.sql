-- 添加记忆去重支持
-- 版本：011
-- 创建时间：2026-03-23
-- 说明：为 memories 表添加 content_hash 字段，支持基于内容哈希的去重

-- ============================================================================
-- 1. 为现有用户 schema 添加 content_hash 字段
-- ============================================================================

-- 创建动态添加字段的函数
CREATE OR REPLACE FUNCTION add_content_hash_to_user_schema(p_user_id VARCHAR(100))
RETURNS VOID AS $$
DECLARE
    v_schema_name VARCHAR(100);
BEGIN
    -- 获取用户的 schema 名称
    SELECT schema_name INTO v_schema_name
    FROM public.users
    WHERE id = p_user_id;
    
    IF NOT FOUND THEN
        RAISE EXCEPTION 'User not found: %', p_user_id;
    END IF;
    
    -- 添加 content_hash 字段
    EXECUTE format('
        ALTER TABLE %I.memories 
        ADD COLUMN IF NOT EXISTS content_hash VARCHAR(64)
    ', v_schema_name);
    
    -- 创建索引（注意：这里不使用唯一索引，因为同一个哈希可能在不同的时间/地点出现）
    EXECUTE format('
        CREATE INDEX IF NOT EXISTS idx_memories_content_hash 
        ON %I.memories(content_hash)
    ', v_schema_name);
    
    -- 创建组合索引（user_id + content_hash），用于快速查重
    -- 注意：在多用户 schema 模式下，每个 schema 只有一个用户的数据
    -- 所以这个索引主要用于该用户内的去重检查
    
    RAISE NOTICE 'Added content_hash to user: %', p_user_id;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- 2. 更新 create_user_schema 函数，包含 content_hash 字段
-- ============================================================================

-- 先删除旧函数
DROP FUNCTION IF EXISTS create_user_schema(VARCHAR);

-- 创建新函数（包含 content_hash 字段）
CREATE OR REPLACE FUNCTION create_user_schema(p_user_id VARCHAR(100))
RETURNS VOID AS $$
DECLARE
    v_schema_name VARCHAR(100);
BEGIN
    -- 验证用户 ID 格式
    IF p_user_id !~ '^[a-z0-9_]+$' THEN
        RAISE EXCEPTION 'Invalid user_id format: %. Only lowercase letters, numbers, and underscores are allowed.', p_user_id;
    END IF;
    
    v_schema_name := 'user_' || p_user_id;
    
    -- 检查用户是否已存在
    IF EXISTS (SELECT 1 FROM public.users WHERE id = p_user_id) THEN
        RAISE EXCEPTION 'User already exists: %', p_user_id;
    END IF;
    
    -- 创建 schema
    EXECUTE format('CREATE SCHEMA IF NOT EXISTS %I', v_schema_name);
    
    -- 在 schema 下创建 memories 表（包含 content_hash 字段）
    EXECUTE format('
        CREATE TABLE IF NOT EXISTS %I.memories (
            id VARCHAR(24) PRIMARY KEY,
            content TEXT NOT NULL,
            input_type VARCHAR(10) NOT NULL CHECK (input_type IN (''text'', ''image'', ''audio'', ''file'', ''segment'')),
            
            -- 内容哈希（用于去重）
            content_hash VARCHAR(64),
            
            -- 时间字段
            time_value TIMESTAMP WITH TIME ZONE,
            time_source VARCHAR(10) CHECK (time_source IN (''extracted'', ''inferred'', ''metadata'')),
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
            people JSONB DEFAULT ''[]''::jsonb,
            
            -- 关键事件
            key_events JSONB DEFAULT ''[]''::jsonb,
            
            -- 分段存储
            segment_ids JSONB DEFAULT ''[]''::jsonb,
            segment_count INTEGER DEFAULT 0,
            file_name TEXT,
            file_size BIGINT,
            
            -- 可选字段
            emotion JSONB,
            tags JSONB DEFAULT ''[]''::jsonb,
            duration JSONB,
            topic JSONB,
            
            -- 附件
            attachments JSONB DEFAULT ''[]''::jsonb,
            
            -- 向量（1024 维，对应 doubao-embedding-vision）
            embedding vector(1024),
            
            -- 系统字段
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            access_count INTEGER DEFAULT 0,
            last_accessed_at TIMESTAMP WITH TIME ZONE,
            importance_score FLOAT DEFAULT 0.5,
            status VARCHAR(10) DEFAULT ''active'' CHECK (status IN (''active'', ''archived'', ''deleted''))
        )
    ', v_schema_name);
    
    -- 创建 entities 表
    EXECUTE format('
        CREATE TABLE IF NOT EXISTS %I.entities (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name VARCHAR(200) NOT NULL,
            type VARCHAR(20) NOT NULL,
            confidence FLOAT DEFAULT 0.8,
            mention_count INT DEFAULT 1,
            last_mentioned_at TIMESTAMP WITH TIME ZONE,
            user_id VARCHAR(100) NOT NULL,
            agent_id VARCHAR(100),
            run_id VARCHAR(100),
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            CONSTRAINT unique_entity UNIQUE (name, type, user_id)
        )
    ', v_schema_name);
    
    -- 创建 relations 表
    EXECUTE format('
        CREATE TABLE IF NOT EXISTS %I.relations (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            from_entity_id UUID,
            to_entity_id UUID NOT NULL,
            relation_type VARCHAR(50) NOT NULL,
            weight FLOAT DEFAULT 1.0,
            confidence FLOAT DEFAULT 0.8,
            user_id VARCHAR(100) NOT NULL,
            agent_id VARCHAR(100),
            run_id VARCHAR(100),
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            CONSTRAINT unique_relation UNIQUE (from_entity_id, to_entity_id, relation_type),
            CONSTRAINT fk_from_entity FOREIGN KEY (from_entity_id) REFERENCES %I.entities(id) ON DELETE CASCADE,
            CONSTRAINT fk_to_entity FOREIGN KEY (to_entity_id) REFERENCES %I.entities(id) ON DELETE CASCADE
        )
    ', v_schema_name, v_schema_name, v_schema_name);
    
    -- 创建 memory_entities 表
    EXECUTE format('
        CREATE TABLE IF NOT EXISTS %I.memory_entities (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            memory_id UUID NOT NULL,
            entity_id UUID NOT NULL,
            mention_context TEXT,
            mention_position INT,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            CONSTRAINT unique_memory_entity UNIQUE (memory_id, entity_id),
            CONSTRAINT fk_entity FOREIGN KEY (entity_id) REFERENCES %I.entities(id) ON DELETE CASCADE
        )
    ', v_schema_name, v_schema_name);
    
    -- 创建索引
    -- memories 表索引
    EXECUTE format('CREATE INDEX IF NOT EXISTS idx_memories_created_at ON %I.memories(created_at DESC)', v_schema_name);
    EXECUTE format('CREATE INDEX IF NOT EXISTS idx_memories_time_value ON %I.memories(time_value)', v_schema_name);
    EXECUTE format('CREATE INDEX IF NOT EXISTS idx_memories_status ON %I.memories(status)', v_schema_name);
    EXECUTE format('CREATE INDEX IF NOT EXISTS idx_memories_content_fts ON %I.memories USING gin(to_tsvector(''simple'', content))', v_schema_name);
    EXECUTE format('CREATE INDEX IF NOT EXISTS idx_memories_embedding ON %I.memories USING hnsw (embedding vector_cosine_ops)', v_schema_name);
    EXECUTE format('CREATE INDEX IF NOT EXISTS idx_memories_content_hash ON %I.memories(content_hash)', v_schema_name);
    
    -- entities 表索引
    EXECUTE format('CREATE INDEX IF NOT EXISTS idx_entities_user ON %I.entities(user_id)', v_schema_name);
    EXECUTE format('CREATE INDEX IF NOT EXISTS idx_entities_type ON %I.entities(type)', v_schema_name);
    
    -- relations 表索引
    EXECUTE format('CREATE INDEX IF NOT EXISTS idx_relations_user ON %I.relations(user_id)', v_schema_name);
    EXECUTE format('CREATE INDEX IF NOT EXISTS idx_relations_from ON %I.relations(from_entity_id)', v_schema_name);
    EXECUTE format('CREATE INDEX IF NOT EXISTS idx_relations_to ON %I.relations(to_entity_id)', v_schema_name);
    
    -- memory_entities 表索引
    EXECUTE format('CREATE INDEX IF NOT EXISTS idx_memory_entities_memory ON %I.memory_entities(memory_id)', v_schema_name);
    EXECUTE format('CREATE INDEX IF NOT EXISTS idx_memory_entities_entity ON %I.memory_entities(entity_id)', v_schema_name);
    
    -- 创建更新时间触发器
    EXECUTE format('
        CREATE OR REPLACE FUNCTION %I.update_updated_at()
        RETURNS TRIGGER AS $func$
        BEGIN
            NEW.updated_at = NOW();
            RETURN NEW;
        END;
        $func$ LANGUAGE plpgsql
    ', v_schema_name);
    
    EXECUTE format('
        DROP TRIGGER IF EXISTS trigger_memories_updated_at ON %I.memories;
        CREATE TRIGGER trigger_memories_updated_at
            BEFORE UPDATE ON %I.memories
            FOR EACH ROW
            EXECUTE FUNCTION %I.update_updated_at()
    ', v_schema_name, v_schema_name, v_schema_name);
    
    EXECUTE format('
        DROP TRIGGER IF EXISTS trigger_entities_updated_at ON %I.entities;
        CREATE TRIGGER trigger_entities_updated_at
            BEFORE UPDATE ON %I.entities
            FOR EACH ROW
            EXECUTE FUNCTION %I.update_updated_at()
    ', v_schema_name, v_schema_name, v_schema_name);
    
    -- 插入用户记录
    INSERT INTO public.users (id, schema_name) VALUES (p_user_id, v_schema_name);
    
    RAISE NOTICE 'Created schema for user: %', p_user_id;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION create_user_schema IS '创建用户 schema：为指定用户创建独立的 schema 和所有相关表（包含 content_hash 字段）';

-- ============================================================================
-- 3. 为现有用户添加 content_hash 字段
-- ============================================================================

-- 获取所有现有用户并添加字段
DO $$
DECLARE
    user_record RECORD;
BEGIN
    FOR user_record IN SELECT id FROM public.users LOOP
        PERFORM add_content_hash_to_user_schema(user_record.id);
    END LOOP;
END $$;

-- ============================================================================
-- 完成
-- ============================================================================

SELECT 'Migration 011 completed successfully!' AS status;
SELECT 'Added content_hash field to all existing users' AS info;
