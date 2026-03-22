-- 创建 create_user_schema 函数（如果不存在）

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
        -- 用户已存在，直接返回
        RETURN;
    END IF;

    -- 创建 schema
    EXECUTE format('CREATE SCHEMA IF NOT EXISTS %I', v_schema_name);

    -- 在 schema 下创建 memories 表
    EXECUTE format('
        CREATE TABLE IF NOT EXISTS %I.memories (
            id VARCHAR(24) PRIMARY KEY,
            content TEXT NOT NULL,
            input_type VARCHAR(10) NOT NULL CHECK (input_type IN (''text'', ''image'', ''audio'', ''file'')),

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
            CONSTRAINT unique_relation UNIQUE (from_entity_id, to_entity_id, relation_type)
        )
    ', v_schema_name);

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
            CONSTRAINT fk_memory FOREIGN KEY (memory_id) REFERENCES %I.memories(id) ON DELETE CASCADE,
            CONSTRAINT fk_entity FOREIGN KEY (entity_id) REFERENCES %I.entities(id) ON DELETE CASCADE
        )
    ', v_schema_name, v_schema_name, v_schema_name);

    -- 创建索引
    EXECUTE format('CREATE INDEX IF NOT EXISTS idx_memories_created_at ON %I.memories(created_at DESC)', v_schema_name);
    EXECUTE format('CREATE INDEX IF NOT EXISTS idx_memories_time_value ON %I.memories(time_value)', v_schema_name);
    EXECUTE format('CREATE INDEX IF NOT EXISTS idx_memories_status ON %I.memories(status)', v_schema_name);
    EXECUTE format('CREATE INDEX IF NOT EXISTS idx_memories_content_fts ON %I.memories USING gin(to_tsvector(''simple'', content))', v_schema_name);
    EXECUTE format('CREATE INDEX IF NOT EXISTS idx_memories_embedding ON %I.memories USING hnsw (embedding vector_cosine_ops)', v_schema_name);

    -- 插入用户记录
    INSERT INTO public.users (id, schema_name) VALUES (p_user_id, v_schema_name)
    ON CONFLICT (id) DO NOTHING;

    RAISE NOTICE 'Created schema for user: %', p_user_id;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION create_user_schema IS '创建用户 schema：为指定用户创建独立的 schema 和所有相关表';
