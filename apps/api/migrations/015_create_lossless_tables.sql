-- Phase 1: 创建 Lossless DAG 相关表
-- 版本：015
-- 说明：创建 raw_messages, summaries, summary_messages, summary_parents, summary_entities, context_items 表

-- ============================================================================
-- 1. raw_messages 表（原始消息，替代 memories）
-- ============================================================================
CREATE TABLE IF NOT EXISTS raw_messages (
    id VARCHAR(24) PRIMARY KEY,
    user_id VARCHAR(100) NOT NULL,
    agent_id VARCHAR(100),              -- NULL=用户手动，非NULL=Agent对话
    
    -- 来源类型
    memory_type VARCHAR(20) NOT NULL DEFAULT 'preference'
        CHECK (memory_type IN ('preference', 'note', 'dialogue')),
    -- preference: 用户偏好
    -- note: 用户笔记/日记/长文档
    -- dialogue: Agent 对话消息
    
    -- 会话关联
    session_id VARCHAR(100),
    document_id VARCHAR(24),            -- 长文档分段共享此 ID
    
    -- 消息内容
    role VARCHAR(20) NOT NULL DEFAULT 'user'
        CHECK (role IN ('user', 'assistant', 'system')),
    content TEXT NOT NULL,
    token_count INTEGER DEFAULT 0,
    
    -- 向量嵌入
    embedding vector(1024),
    
    -- 时间信息
    time_value TIMESTAMP WITH TIME ZONE,
    time_source VARCHAR(10),
    
    -- 位置信息
    location_name TEXT,
    
    -- 元数据
    tags JSONB DEFAULT '[]'::jsonb,
    metadata JSONB DEFAULT '{}'::jsonb,
    
    -- 系统字段
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    is_archived BOOLEAN DEFAULT FALSE
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_raw_messages_user ON raw_messages(user_id);
CREATE INDEX IF NOT EXISTS idx_raw_messages_agent ON raw_messages(agent_id) 
    WHERE agent_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_raw_messages_no_agent ON raw_messages(agent_id) 
    WHERE agent_id IS NULL;
CREATE INDEX IF NOT EXISTS idx_raw_messages_session ON raw_messages(user_id, session_id);
CREATE INDEX IF NOT EXISTS idx_raw_messages_document ON raw_messages(document_id);
CREATE INDEX IF NOT EXISTS idx_raw_messages_time ON raw_messages(time_value);
CREATE INDEX IF NOT EXISTS idx_raw_messages_created ON raw_messages(created_at DESC);

-- 向量索引（如果数据量大，可以使用 ivfflat）
-- CREATE INDEX idx_raw_messages_embedding ON raw_messages 
--     USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

COMMENT ON TABLE raw_messages IS '原始消息表：统一存储用户手动输入和Agent对话';
COMMENT ON COLUMN raw_messages.agent_id IS 'Agent ID：NULL=用户手动输入，非NULL=Agent对话提取';
COMMENT ON COLUMN raw_messages.memory_type IS '记忆类型：preference(偏好)/note(笔记)/dialogue(对话)';
COMMENT ON COLUMN raw_messages.document_id IS '文档 ID：长文本分段共享此 ID';

-- ============================================================================
-- 2. summaries 表（摘要节点，DAG 结构）
-- ============================================================================
CREATE TABLE IF NOT EXISTS summaries (
    summary_id VARCHAR(24) PRIMARY KEY,
    user_id VARCHAR(100) NOT NULL,
    agent_id VARCHAR(100),              -- 与 raw_messages 一致
    
    -- 节点类型
    kind VARCHAR(20) NOT NULL CHECK (kind IN ('leaf', 'condensed')),
    depth INTEGER NOT NULL DEFAULT 0,
    
    -- 内容
    content TEXT NOT NULL,
    token_count INTEGER NOT NULL DEFAULT 0,
    
    -- 向量嵌入
    embedding vector(1024),
    
    -- 统计字段
    earliest_at TIMESTAMP WITH TIME ZONE,
    latest_at TIMESTAMP WITH TIME ZONE,
    descendant_count INTEGER NOT NULL DEFAULT 0,
    descendant_token_count INTEGER NOT NULL DEFAULT 0,
    source_message_token_count INTEGER NOT NULL DEFAULT 0,
    
    -- 文档关联
    document_id VARCHAR(24),
    
    -- 元数据
    model VARCHAR(100) DEFAULT 'unknown',
    compression_level VARCHAR(20) DEFAULT 'normal',  -- normal/aggressive/fallback
    
    -- 时间戳
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_summaries_user ON summaries(user_id);
CREATE INDEX IF NOT EXISTS idx_summaries_agent ON summaries(agent_id);
CREATE INDEX IF NOT EXISTS idx_summaries_kind_depth ON summaries(kind, depth);
CREATE INDEX IF NOT EXISTS idx_summaries_document ON summaries(document_id);
CREATE INDEX IF NOT EXISTS idx_summaries_created ON summaries(created_at DESC);

COMMENT ON TABLE summaries IS '摘要节点表：DAG 结构，leaf(叶级) 和 condensed(高层)';
COMMENT ON COLUMN summaries.kind IS '节点类型：leaf(叶级摘要)/condensed(高层摘要)';
COMMENT ON COLUMN summaries.depth IS 'DAG 深度：0=leaf, >0=condensed';

-- ============================================================================
-- 3. summary_messages 表（摘要-消息关系）
-- ============================================================================
CREATE TABLE IF NOT EXISTS summary_messages (
    summary_id VARCHAR(24) NOT NULL REFERENCES summaries(summary_id) ON DELETE CASCADE,
    message_id VARCHAR(24) NOT NULL REFERENCES raw_messages(id) ON DELETE RESTRICT,
    ordinal INTEGER NOT NULL,
    
    PRIMARY KEY (summary_id, message_id)
);

CREATE INDEX IF NOT EXISTS idx_summary_messages_summary ON summary_messages(summary_id, ordinal);
CREATE INDEX IF NOT EXISTS idx_summary_messages_message ON summary_messages(message_id);

COMMENT ON TABLE summary_messages IS '摘要-消息关系表：leaf 摘要引用的原始消息';
COMMENT ON COLUMN summary_messages.ordinal IS '消息在摘要中的顺序';

-- ============================================================================
-- 4. summary_parents 表（摘要-DAG 关系）
-- ============================================================================
CREATE TABLE IF NOT EXISTS summary_parents (
    summary_id VARCHAR(24) NOT NULL REFERENCES summaries(summary_id) ON DELETE CASCADE,
    parent_summary_id VARCHAR(24) NOT NULL REFERENCES summaries(summary_id) ON DELETE RESTRICT,
    ordinal INTEGER NOT NULL,
    
    PRIMARY KEY (summary_id, parent_summary_id)
);

CREATE INDEX IF NOT EXISTS idx_summary_parents_summary ON summary_parents(summary_id, ordinal);
CREATE INDEX IF NOT EXISTS idx_summary_parents_parent ON summary_parents(parent_summary_id);

COMMENT ON TABLE summary_parents IS '摘要-DAG 关系表：parent_summary_id 是被压缩的节点';
COMMENT ON COLUMN summary_parents.summary_id IS 'condensed 节点（压缩结果）';
COMMENT ON COLUMN summary_parents.parent_summary_id IS '被压缩的节点（展开时向上遍历）';

-- ============================================================================
-- 5. summary_entities 表（摘要-实体关系，用于图谱召回）
-- ============================================================================
CREATE TABLE IF NOT EXISTS summary_entities (
    summary_id VARCHAR(24) NOT NULL REFERENCES summaries(summary_id) ON DELETE CASCADE,
    entity_id UUID NOT NULL,  -- 暂不添加外键，因为 entities 表在用户 schema 中
    role VARCHAR(50) DEFAULT 'mentioned',
    confidence FLOAT DEFAULT 0.8,
    
    PRIMARY KEY (summary_id, entity_id)
);

CREATE INDEX IF NOT EXISTS idx_summary_entities_entity ON summary_entities(entity_id);

COMMENT ON TABLE summary_entities IS '摘要-实体关系表：用于图谱召回发现相关摘要';

-- ============================================================================
-- 6. context_items 表（有序上下文序列）
-- ============================================================================
CREATE TABLE IF NOT EXISTS context_items (
    user_id VARCHAR(100) NOT NULL,
    agent_id VARCHAR(100),
    session_id VARCHAR(100) NOT NULL,
    ordinal INTEGER NOT NULL,
    item_type VARCHAR(20) NOT NULL CHECK (item_type IN ('message', 'summary')),
    message_id VARCHAR(24) REFERENCES raw_messages(id) ON DELETE RESTRICT,
    summary_id VARCHAR(24) REFERENCES summaries(summary_id) ON DELETE RESTRICT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    PRIMARY KEY (user_id, session_id, ordinal),
    
    -- 约束：message 和 summary 只能有一个
    CHECK (
        (item_type = 'message' AND message_id IS NOT NULL AND summary_id IS NULL) OR
        (item_type = 'summary' AND summary_id IS NOT NULL AND message_id IS NULL)
    )
);

CREATE INDEX IF NOT EXISTS idx_context_items_session ON context_items(user_id, session_id, ordinal);
CREATE INDEX IF NOT EXISTS idx_context_items_message ON context_items(message_id) WHERE message_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_context_items_summary ON context_items(summary_id) WHERE summary_id IS NOT NULL;

COMMENT ON TABLE context_items IS '上下文序列表：维护有序的消息/摘要序列';
COMMENT ON COLUMN context_items.ordinal IS '顺序号：决定上下文组装顺序';
COMMENT ON COLUMN context_items.item_type IS '类型：message(原始消息)/summary(摘要)';

-- ============================================================================
-- 7. 辅助函数
-- ============================================================================

-- 获取 context_items 的下一个 ordinal
CREATE OR REPLACE FUNCTION get_next_ordinal(
    p_user_id VARCHAR(100),
    p_session_id VARCHAR(100)
) RETURNS INTEGER AS $$
DECLARE
    v_max_ordinal INTEGER;
BEGIN
    SELECT COALESCE(MAX(ordinal), -1) INTO v_max_ordinal
    FROM context_items
    WHERE user_id = p_user_id AND session_id = p_session_id;
    
    RETURN v_max_ordinal + 1;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION get_next_ordinal IS '获取 context_items 的下一个 ordinal';

-- 计算 context_items 的 token 总数
CREATE OR REPLACE FUNCTION get_context_token_count(
    p_user_id VARCHAR(100),
    p_session_id VARCHAR(100)
) RETURNS INTEGER AS $$
DECLARE
    v_total INTEGER;
BEGIN
    SELECT COALESCE(SUM(
        CASE 
            WHEN ci.item_type = 'message' THEN rm.token_count
            WHEN ci.item_type = 'summary' THEN s.token_count
            ELSE 0
        END
    ), 0) INTO v_total
    FROM context_items ci
    LEFT JOIN raw_messages rm ON ci.message_id = rm.id
    LEFT JOIN summaries s ON ci.summary_id = s.summary_id
    WHERE ci.user_id = p_user_id AND ci.session_id = p_session_id;
    
    RETURN v_total;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION get_context_token_count IS '计算 context_items 的 token 总数';

-- ============================================================================
-- 完成
-- ============================================================================
SELECT 'Migration 015 completed successfully!' AS status;
