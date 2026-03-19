-- 记忆网络构建系统 - 数据库迁移
-- 版本：001
-- 创建时间：2026-03-19
-- 说明：创建图谱相关表（entities, relations, memory_entities, pending_confirmations）

-- ============================================================================
-- 1. 实体表（entities）
-- ============================================================================
CREATE TABLE IF NOT EXISTS entities (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(200) NOT NULL,
    type VARCHAR(20) NOT NULL,  -- person/location/event/topic/emotion
    confidence FLOAT DEFAULT 0.8,
    
    -- 统计字段
    mention_count INT DEFAULT 1,
    last_mentioned_at TIMESTAMP,
    
    -- 多租户
    user_id VARCHAR(100) NOT NULL,
    agent_id VARCHAR(100),
    run_id VARCHAR(100),
    
    -- 元数据
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    
    -- 唯一约束
    CONSTRAINT unique_entity UNIQUE (name, type, user_id)
);

-- 实体表索引
CREATE INDEX IF NOT EXISTS idx_entities_user ON entities(user_id);
CREATE INDEX IF NOT EXISTS idx_entities_type ON entities(type);
CREATE INDEX IF NOT EXISTS idx_entities_name ON entities USING gin(to_tsvector('simple', name));
CREATE INDEX IF NOT EXISTS idx_entities_created ON entities(created_at);

COMMENT ON TABLE entities IS '实体表：存储从记忆中提取的实体（人物、地点、事件等）';
COMMENT ON COLUMN entities.type IS '实体类型：person（人物）, location（地点）, event（事件）, topic（主题）, emotion（情感）';
COMMENT ON COLUMN entities.confidence IS '置信度：0-1 之间，表示提取的可靠程度';
COMMENT ON COLUMN entities.mention_count IS '提及次数：该实体在记忆中被提及的次数';

-- ============================================================================
-- 2. 关系表（relations）
-- ============================================================================
CREATE TABLE IF NOT EXISTS relations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    from_entity_id UUID NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    to_entity_id UUID NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    relation_type VARCHAR(50) NOT NULL,
    weight FLOAT DEFAULT 1.0,
    confidence FLOAT DEFAULT 0.8,
    
    -- 多租户
    user_id VARCHAR(100) NOT NULL,
    agent_id VARCHAR(100),
    run_id VARCHAR(100),
    
    -- 元数据
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    
    -- 唯一约束
    CONSTRAINT unique_relation UNIQUE (from_entity_id, to_entity_id, relation_type)
);

-- 关系表索引
CREATE INDEX IF NOT EXISTS idx_relations_from ON relations(from_entity_id);
CREATE INDEX IF NOT EXISTS idx_relations_to ON relations(to_entity_id);
CREATE INDEX IF NOT EXISTS idx_relations_type ON relations(relation_type);
CREATE INDEX IF NOT EXISTS idx_relations_user ON relations(user_id);

COMMENT ON TABLE relations IS '关系表：存储实体之间的关系';
COMMENT ON COLUMN relations.relation_type IS '关系类型：如 friend, met_at, at, discussed 等';
COMMENT ON COLUMN relations.weight IS '关系权重：0-1 之间，表示关系的强度';
COMMENT ON COLUMN relations.confidence IS '置信度：0-1 之间，表示关系推理的可靠程度';

-- ============================================================================
-- 3. 记忆-实体关联表（memory_entities）
-- ============================================================================
CREATE TABLE IF NOT EXISTS memory_entities (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    memory_id UUID NOT NULL,
    entity_id UUID NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    
    -- 关联信息
    mention_context TEXT,  -- 提及该实体的上下文
    mention_position INT,  -- 在记忆中的位置
    
    -- 元数据
    created_at TIMESTAMP DEFAULT NOW(),
    
    -- 唯一约束
    CONSTRAINT unique_memory_entity UNIQUE (memory_id, entity_id)
);

-- 记忆-实体关联表索引
CREATE INDEX IF NOT EXISTS idx_memory_entities_memory ON memory_entities(memory_id);
CREATE INDEX IF NOT EXISTS idx_memory_entities_entity ON memory_entities(entity_id);

COMMENT ON TABLE memory_entities IS '记忆-实体关联表：记录每条记忆中包含的实体';

-- ============================================================================
-- 4. 待确认队列表（pending_confirmations）
-- ============================================================================
CREATE TABLE IF NOT EXISTS pending_confirmations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id VARCHAR(100) NOT NULL,
    
    -- 确认类型
    confirmation_type VARCHAR(50) NOT NULL,  -- new_entity, low_confidence, relation_conflict
    
    -- 确认内容
    entity_data JSONB,  -- 实体数据
    relation_data JSONB,  -- 关系数据
    question TEXT NOT NULL,  -- 询问用户的问题
    options JSONB,  -- 选项列表
    
    -- 状态
    status VARCHAR(20) DEFAULT 'pending',  -- pending, confirmed, rejected, modified
    user_response JSONB,  -- 用户的回复
    
    -- 元数据
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    responded_at TIMESTAMP  -- 用户回复时间
);

-- 待确认队列表索引
CREATE INDEX IF NOT EXISTS idx_pending_confirmations_user ON pending_confirmations(user_id);
CREATE INDEX IF NOT EXISTS idx_pending_confirmations_status ON pending_confirmations(status);
CREATE INDEX IF NOT EXISTS idx_pending_confirmations_created ON pending_confirmations(created_at);

COMMENT ON TABLE pending_confirmations IS '待确认队列：存储需要用户确认的实体和关系';
COMMENT ON COLUMN pending_confirmations.confirmation_type IS '确认类型：new_entity（新实体）, low_confidence（低置信度）, relation_conflict（关系冲突）';
COMMENT ON COLUMN pending_confirmations.status IS '状态：pending（待处理）, confirmed（已确认）, rejected（已拒绝）, modified（已修改）';

-- ============================================================================
-- 5. 触发器：自动更新 updated_at 字段
-- ============================================================================
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- entities 表触发器
DROP TRIGGER IF EXISTS update_entities_updated_at ON entities;
CREATE TRIGGER update_entities_updated_at
    BEFORE UPDATE ON entities
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- relations 表触发器
DROP TRIGGER IF EXISTS update_relations_updated_at ON relations;
CREATE TRIGGER update_relations_updated_at
    BEFORE UPDATE ON relations
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- pending_confirmations 表触发器
DROP TRIGGER IF EXISTS update_pending_confirmations_updated_at ON pending_confirmations;
CREATE TRIGGER update_pending_confirmations_updated_at
    BEFORE UPDATE ON pending_confirmations
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- ============================================================================
-- 6. 初始数据（可选）
-- ============================================================================
-- 这里可以插入一些初始的关系类型或实体类型定义

-- 完成
SELECT 'Migration 001 completed successfully!' AS status;
