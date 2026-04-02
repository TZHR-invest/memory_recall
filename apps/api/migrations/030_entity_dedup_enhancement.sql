-- Migration 030: Entity Dedup Enhancement
-- 实体去重策略优化：调整 UNIQUE 约束，支持同名不同类型实体
-- References: 实体去重策略讨论

-- =============================================================================
-- 1. 调整 UNIQUE 约束
-- =============================================================================

-- 删除旧约束（仅基于 name + container_tag）
ALTER TABLE entities DROP CONSTRAINT IF EXISTS uq_entities_name_container;

-- 添加新约束（包含 type，允许同名不同类型）
ALTER TABLE entities ADD CONSTRAINT uq_entities_name_type_container 
    UNIQUE (name, type, container_tag);

-- =============================================================================
-- 2. 添加归一化名称索引（用于快速去重查询）
-- =============================================================================

-- 为归一化查询创建函数索引
CREATE INDEX IF NOT EXISTS idx_entities_normalized_name 
    ON entities (LOWER(TRIM(name)), container_tag);

-- =============================================================================
-- 3. 数据清理：归一化现有实体名称
-- =============================================================================

-- 注意：这里只更新名称的前后空格，不改变大小写
-- 大小写归一化在代码层处理，避免破坏原始数据
UPDATE entities 
SET name = TRIM(name)
WHERE name != TRIM(name);

-- =============================================================================
-- 4. Comments
-- =============================================================================

COMMENT ON CONSTRAINT uq_entities_name_type_container ON entities IS 
    '实体唯一性约束：允许同名不同类型的实体存在（如 Alice 可以是人名、地点名）';

COMMENT ON INDEX idx_entities_normalized_name IS 
    '归一化名称索引：支持快速查询忽略大小写和空格的实体';
