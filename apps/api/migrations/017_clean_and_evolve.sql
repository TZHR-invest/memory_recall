-- Migration 017: Clean and Evolve Schema
-- Version: 017
-- Purpose: Remove legacy tables, add evolution tables

-- ============================================================================
-- PART 1: DROP UNUSED OBJECTS
-- ============================================================================

-- Drop memories_compatible view (no longer needed)
DROP VIEW IF EXISTS memories_compatible;

-- Drop pending_confirmations table (unused)
DROP TABLE IF EXISTS pending_confirmations;

-- ============================================================================
-- PART 2: REMOVE REDUNDANT COLUMNS FROM ENTITIES
-- ============================================================================

ALTER TABLE entities DROP COLUMN IF EXISTS run_id;
ALTER TABLE entities DROP COLUMN IF EXISTS agent_id;

-- ============================================================================
-- PART 3: REMOVE REDUNDANT COLUMNS FROM RELATIONS
-- ============================================================================

ALTER TABLE relations DROP COLUMN IF EXISTS run_id;
ALTER TABLE relations DROP COLUMN IF EXISTS agent_id;
ALTER TABLE relations DROP COLUMN IF EXISTS weight;

-- ============================================================================
-- PART 4: REMOVE REDUNDANT COLUMNS FROM SUMMARIES
-- ============================================================================

ALTER TABLE summaries DROP COLUMN IF EXISTS agent_id;

-- ============================================================================
-- PART 5: ADD NEW COLUMNS TO RAW_MESSAGES
-- ============================================================================

ALTER TABLE raw_messages ADD COLUMN IF NOT EXISTS event_date TIMESTAMP WITH TIME ZONE;
ALTER TABLE raw_messages ADD COLUMN IF NOT EXISTS document_date TIMESTAMP WITH TIME ZONE;
ALTER TABLE raw_messages ADD COLUMN IF NOT EXISTS expiration_date TIMESTAMP WITH TIME ZONE;
ALTER TABLE raw_messages ADD COLUMN IF NOT EXISTS memory_lifespan VARCHAR(20) DEFAULT 'long_term' 
    CHECK (memory_lifespan IN ('temporary', 'short_term', 'long_term', 'permanent'));
ALTER TABLE raw_messages ADD COLUMN IF NOT EXISTS is_latest BOOLEAN DEFAULT TRUE;
ALTER TABLE raw_messages ADD COLUMN IF NOT EXISTS is_expired BOOLEAN DEFAULT FALSE;
ALTER TABLE raw_messages ADD COLUMN IF NOT EXISTS container_id VARCHAR(100);
ALTER TABLE raw_messages ADD COLUMN IF NOT EXISTS access_count INTEGER DEFAULT 0;
ALTER TABLE raw_messages ADD COLUMN IF NOT EXISTS last_accessed_at TIMESTAMP WITH TIME ZONE;
ALTER TABLE raw_messages ADD COLUMN IF NOT EXISTS importance_score FLOAT DEFAULT 0.5;
ALTER TABLE raw_messages ADD COLUMN IF NOT EXISTS memory_behavior VARCHAR(20) DEFAULT 'episode' 
    CHECK (memory_behavior IN ('fact', 'preference', 'episode'));
ALTER TABLE raw_messages ADD COLUMN IF NOT EXISTS chunk_count INTEGER DEFAULT 0;

-- Index on container_id
CREATE INDEX IF NOT EXISTS idx_raw_messages_container ON raw_messages(container_id);

-- ============================================================================
-- PART 6: ADD NEW COLUMNS TO SUMMARIES
-- ============================================================================

ALTER TABLE summaries ADD COLUMN IF NOT EXISTS expiration_date TIMESTAMP WITH TIME ZONE;
ALTER TABLE summaries ADD COLUMN IF NOT EXISTS is_expired BOOLEAN DEFAULT FALSE;

-- ============================================================================
-- PART 7: CREATE API_KEYS TABLE
-- ============================================================================

CREATE TABLE IF NOT EXISTS api_keys (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id VARCHAR(100) NOT NULL,
    key_hash VARCHAR(64) NOT NULL,
    key_prefix VARCHAR(12) NOT NULL,
    name VARCHAR(100),
    permissions JSONB DEFAULT '["read"]'::jsonb,
    is_active BOOLEAN DEFAULT TRUE,
    is_test BOOLEAN DEFAULT FALSE,
    last_used_at TIMESTAMP WITH TIME ZONE,
    usage_count INTEGER DEFAULT 0,
    expires_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    revoked_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX IF NOT EXISTS idx_api_keys_user ON api_keys(user_id);
CREATE INDEX IF NOT EXISTS idx_api_keys_prefix ON api_keys(key_prefix);
CREATE INDEX IF NOT EXISTS idx_api_keys_active ON api_keys(user_id, is_active) WHERE is_active = TRUE;

COMMENT ON TABLE api_keys IS 'API Key 管理表：支持 rk_live_xxx 和 rk_test_xxx 格式';

-- ============================================================================
-- PART 8: CREATE MEMORY_RELATIONS TABLE
-- ============================================================================

CREATE TABLE IF NOT EXISTS memory_relations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id VARCHAR(100) NOT NULL,
    source_memory_id VARCHAR(24) NOT NULL,
    target_memory_id VARCHAR(24) NOT NULL,
    relation_type VARCHAR(20) NOT NULL 
        CHECK (relation_type IN ('updates', 'extends', 'derives', 'supersedes', 'related_to')),
    confidence FLOAT DEFAULT 0.8,
    detected_by VARCHAR(20) DEFAULT 'manual',
    status VARCHAR(20) DEFAULT 'active',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_memory_relations_source ON memory_relations(source_memory_id);
CREATE INDEX IF NOT EXISTS idx_memory_relations_target ON memory_relations(target_memory_id);
CREATE INDEX IF NOT EXISTS idx_memory_relations_user ON memory_relations(user_id);

COMMENT ON TABLE memory_relations IS '记忆关系表：存储记忆之间的演化关系';

-- ============================================================================
-- PART 9: CREATE USER_PROFILES TABLE
-- ============================================================================

CREATE TABLE IF NOT EXISTS user_profiles (
    user_id VARCHAR(100) PRIMARY KEY,
    static_facts JSONB DEFAULT '{}'::jsonb,
    dynamic_facts JSONB DEFAULT '{}'::jsonb,
    preferences JSONB DEFAULT '{}'::jsonb,
    is_dirty BOOLEAN DEFAULT FALSE,
    last_rebuilt_at TIMESTAMP WITH TIME ZONE,
    source_memory_count INTEGER DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

COMMENT ON TABLE user_profiles IS '用户画像表：聚合静态事实、动态事实和偏好';

-- ============================================================================
-- PART 10: CREATE FACTS TABLE
-- ============================================================================

CREATE TABLE IF NOT EXISTS facts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id VARCHAR(100) NOT NULL,
    memory_id VARCHAR(24),
    entity_name VARCHAR(200),
    entity_type VARCHAR(50),
    attribute VARCHAR(100),
    value TEXT,
    confidence FLOAT DEFAULT 0.8,
    is_static BOOLEAN DEFAULT FALSE,
    valid_from TIMESTAMP WITH TIME ZONE,
    valid_until TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_facts_user ON facts(user_id);
CREATE INDEX IF NOT EXISTS idx_facts_entity ON facts(entity_name);
CREATE INDEX IF NOT EXISTS idx_facts_memory ON facts(memory_id);

COMMENT ON TABLE facts IS '实体中心化事实表：存储从记忆中提取的结构化事实';

-- ============================================================================
-- PART 11: CREATE NOTIFICATIONS TABLE
-- ============================================================================

CREATE TABLE IF NOT EXISTS notifications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id VARCHAR(100) NOT NULL,
    notification_type VARCHAR(50) NOT NULL,
    memory_id VARCHAR(24),
    message TEXT,
    is_read BOOLEAN DEFAULT FALSE,
    read_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_notifications_user ON notifications(user_id);
CREATE INDEX IF NOT EXISTS idx_notifications_unread ON notifications(user_id, is_read) WHERE is_read = FALSE;

COMMENT ON TABLE notifications IS '通知表：存储过期警告等系统通知';

-- ============================================================================
-- PART 12: CREATE CONTENT_CHUNKS TABLE
-- ============================================================================

CREATE TABLE IF NOT EXISTS content_chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    memory_id VARCHAR(24) NOT NULL,
    user_id VARCHAR(100) NOT NULL,
    chunk_index INTEGER NOT NULL,
    chunk_text TEXT NOT NULL,
    start_offset INTEGER,
    end_offset INTEGER,
    embedding vector(1024),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_content_chunks_memory ON content_chunks(memory_id);
CREATE INDEX IF NOT EXISTS idx_content_chunks_user ON content_chunks(user_id);

COMMENT ON TABLE content_chunks IS '内容分块表：存储长文档的分块内容';

-- ============================================================================
-- PART 13: BACKFILL DEFAULT VALUES
-- ============================================================================

-- Set default values for new columns
UPDATE raw_messages SET 
    memory_lifespan = 'long_term',
    is_latest = TRUE,
    is_expired = FALSE,
    access_count = 0,
    importance_score = 0.5,
    memory_behavior = 'episode',
    chunk_count = 0
WHERE memory_lifespan IS NULL;

UPDATE summaries SET 
    is_expired = FALSE
WHERE is_expired IS NULL;

-- ============================================================================
-- COMPLETE
-- ============================================================================

-- Migration complete
SELECT 'Migration 017 completed successfully' AS status;
