-- Migration 026: Create Entity Graph tables
-- Creates entities, entity_relations, and memory_entities tables for Entity Graph functionality
-- References: design.md Decision 2, REFERENCE_FUNCTION_CALLING.md

-- =============================================================================
-- 1. Entities Table
-- Stores extracted entities (persons, locations, organizations, events, etc.)
-- =============================================================================

CREATE TABLE IF NOT EXISTS entities (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    type VARCHAR(50) NOT NULL,  -- person/location/organization/event/topic/emotion/time/task/decision/concept/solution/problem
    container_tag VARCHAR(100) NOT NULL,
    normalized_name VARCHAR(255),  -- For entity merging (e.g., "张三" → normalized form)
    mention_count INT DEFAULT 1,
    confidence FLOAT DEFAULT 0.8,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Indexes for fast lookups
CREATE INDEX idx_entities_name ON entities(name);
CREATE INDEX idx_entities_container ON entities(container_tag);
CREATE INDEX idx_entities_type ON entities(type);

-- Unique constraint for deduplication
ALTER TABLE entities ADD CONSTRAINT uq_entities_name_container UNIQUE (name, container_tag);

-- =============================================================================
-- 2. Entity Relations Table
-- Stores relationships between entities (friend, works_at, lives_at, etc.)
-- =============================================================================

CREATE TABLE IF NOT EXISTS entity_relations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    from_entity_id UUID NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    to_entity_id UUID NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    relation_type VARCHAR(50) NOT NULL,  -- friend/colleague/works_at/lives_at/met_at/same_as/is_a etc.
    weight FLOAT DEFAULT 0.5,  -- Relation strength (increases with multiple mentions)
    confidence FLOAT DEFAULT 0.8,
    container_tag VARCHAR(100) NOT NULL,
    source_memory_id VARCHAR(24),  -- Memory ID where this relation was extracted from
    created_at TIMESTAMP DEFAULT NOW()
);

-- Indexes for bidirectional traversal
CREATE INDEX idx_entity_relations_from ON entity_relations(from_entity_id);
CREATE INDEX idx_entity_relations_to ON entity_relations(to_entity_id);
CREATE INDEX idx_entity_relations_type ON entity_relations(relation_type);
CREATE INDEX idx_entity_relations_container ON entity_relations(container_tag);

-- Unique constraint for deduplication
ALTER TABLE entity_relations ADD CONSTRAINT uq_entity_relations UNIQUE (from_entity_id, to_entity_id, relation_type, container_tag);

-- =============================================================================
-- 3. Memory-Entities Junction Table
-- Links memories to their extracted entities
-- =============================================================================

CREATE TABLE IF NOT EXISTS memory_entities (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    memory_id VARCHAR(24) NOT NULL,
    entity_id UUID NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    entity_type VARCHAR(50),  -- Denormalized for fast queries
    mention_context TEXT,  -- Context where entity was mentioned
    confidence FLOAT DEFAULT 0.8,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Indexes for bidirectional lookups
CREATE INDEX idx_memory_entities_memory ON memory_entities(memory_id);
CREATE INDEX idx_memory_entities_entity ON memory_entities(entity_id);
CREATE INDEX idx_memory_entities_type ON memory_entities(entity_type);

-- Unique constraint to prevent duplicate links
ALTER TABLE memory_entities ADD CONSTRAINT uq_memory_entities UNIQUE (memory_id, entity_id);

-- =============================================================================
-- 4. Comments
-- =============================================================================

COMMENT ON TABLE entities IS 'Entity nodes for knowledge graph - extracted from memory content';
COMMENT ON TABLE entity_relations IS 'Relationships between entities in the knowledge graph';
COMMENT ON TABLE memory_entities IS 'Junction table linking memories to their extracted entities';

COMMENT ON COLUMN entities.name IS 'Entity name (e.g., "张三", "北京", "字节跳动")';
COMMENT ON COLUMN entities.type IS 'Entity type: person/location/organization/event/topic/emotion/time/task/decision/concept/solution/problem';
COMMENT ON COLUMN entities.container_tag IS 'Container identifier for multi-tenant isolation';
COMMENT ON COLUMN entities.normalized_name IS 'Normalized form for entity merging';
COMMENT ON COLUMN entities.mention_count IS 'Number of times this entity has been mentioned';

COMMENT ON COLUMN entity_relations.relation_type IS 'Relation type: friend/colleague/works_at/lives_at/met_at/located_in/same_as/is_a etc.';
COMMENT ON COLUMN entity_relations.weight IS 'Relation strength (0.0-1.0), increases with multiple mentions';
COMMENT ON COLUMN entity_relations.source_memory_id IS 'Memory ID where this relation was extracted from';

COMMENT ON COLUMN memory_entities.mention_context IS 'Surrounding text where entity was mentioned';
