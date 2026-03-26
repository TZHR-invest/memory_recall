-- Phase 1: 统一 DAG 记忆架构迁移
-- 版本：016
-- 说明：扩展 raw_messages 表以支持传统 memories 功能

-- ============================================================================
-- 1. 扩展 raw_messages 表字段
-- ============================================================================

-- 添加缺失字段
ALTER TABLE raw_messages ADD COLUMN IF NOT EXISTS location_address TEXT;
ALTER TABLE raw_messages ADD COLUMN IF NOT EXISTS location_latitude FLOAT;
ALTER TABLE raw_messages ADD COLUMN IF NOT EXISTS location_longitude FLOAT;
ALTER TABLE raw_messages ADD COLUMN IF NOT EXISTS people JSONB DEFAULT '[]'::jsonb;
ALTER TABLE raw_messages ADD COLUMN IF NOT EXISTS emotion JSONB;
ALTER TABLE raw_messages ADD COLUMN IF NOT EXISTS source_type VARCHAR(20) DEFAULT 'manual'
    CHECK (source_type IN ('manual', 'agent', 'migrated', 'file'));

-- 添加 input_type 字段（与 memories 表一致）
ALTER TABLE raw_messages ADD COLUMN IF NOT EXISTS input_type VARCHAR(10) DEFAULT 'text'
    CHECK (input_type IN ('text', 'image', 'audio', 'file', 'segment'));

-- 添加 importance_score 字段
ALTER TABLE raw_messages ADD COLUMN IF NOT EXISTS importance_score FLOAT DEFAULT 0.5;

-- 添加访问计数字段
ALTER TABLE raw_messages ADD COLUMN IF NOT EXISTS access_count INTEGER DEFAULT 0;
ALTER TABLE raw_messages ADD COLUMN IF NOT EXISTS last_accessed_at TIMESTAMP WITH TIME ZONE;

-- ============================================================================
-- 2. 创建索引
-- ============================================================================

CREATE INDEX IF NOT EXISTS idx_raw_messages_source_type ON raw_messages(source_type);
CREATE INDEX IF NOT EXISTS idx_raw_messages_input_type ON raw_messages(input_type);

-- ============================================================================
-- 3. 创建兼容视图（向后兼容）
-- ============================================================================

CREATE OR REPLACE VIEW memories_compatible AS
SELECT 
    id,
    content,
    input_type,
    user_id,
    agent_id,
    memory_type,
    session_id,
    document_id,
    role,
    token_count,
    time_value,
    time_source,
    location_name,
    location_address,
    location_latitude,
    location_longitude,
    people,
    emotion,
    tags,
    metadata,
    source_type,
    importance_score,
    access_count,
    last_accessed_at,
    created_at,
    is_archived
FROM raw_messages;

COMMENT ON VIEW memories_compatible IS '兼容视图：映射 raw_messages 到传统 memories 结构';

-- ============================================================================
-- 4. 更新表注释
-- ============================================================================

COMMENT ON COLUMN raw_messages.source_type IS '来源类型：manual(用户手动)/agent(Agent对话)/migrated(迁移数据)/file(文件导入)';
COMMENT ON COLUMN raw_messages.input_type IS '输入类型：text/image/audio/file/segment';
COMMENT ON COLUMN raw_messages.people IS '人物信息（JSON数组）';
COMMENT ON COLUMN raw_messages.emotion IS '情绪信息（JSON对象）';

-- ============================================================================
-- 5. 为用户 Schema 创建相同的扩展
-- ============================================================================

-- 注意：用户 Schema 的 raw_messages 扩展需要在 init_user 时自动执行
-- 这里仅创建公共 Schema 的扩展

-- 完成
-- ============================================================================
