-- ============================================================================
-- Memory Recall - Complete Database Schema
-- Version: 5.1.5
-- Purpose: New environment initialization (replaces migrations)
-- ============================================================================

-- Install pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- ============================================================================
-- 1. API Keys Table (Authentication)
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

-- API Keys indexes
CREATE INDEX IF NOT EXISTS idx_api_keys_user ON api_keys(user_id);
CREATE INDEX IF NOT EXISTS idx_api_keys_prefix ON api_keys(key_prefix);
CREATE INDEX IF NOT EXISTS idx_api_keys_active ON api_keys(is_active) WHERE is_active = TRUE;

COMMENT ON TABLE api_keys IS 'API authentication keys with permissions and usage tracking';
COMMENT ON COLUMN api_keys.key_hash IS 'SHA-256 hash of the full API key';
COMMENT ON COLUMN api_keys.key_prefix IS 'First 12 characters of the key for identification';

-- ============================================================================
-- 2. Container Registry Table (Container Ownership)
-- ============================================================================
CREATE TABLE IF NOT EXISTS container_registry (
    container_tag VARCHAR(100) PRIMARY KEY,
    api_key_id UUID NOT NULL REFERENCES api_keys(id) ON DELETE CASCADE,
    user_id VARCHAR(100) NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_container_registry_api_key ON container_registry(api_key_id);
CREATE INDEX IF NOT EXISTS idx_container_registry_user ON container_registry(user_id);

COMMENT ON TABLE container_registry IS 'Records container_tag ownership. First-use auto-registration binds container to API key.';

-- ============================================================================
-- 3. Memories Table (Core Memory Storage)
-- ============================================================================
CREATE TABLE IF NOT EXISTS memories (
    id VARCHAR(24) PRIMARY KEY DEFAULT 'mem_' || replace(gen_random_uuid()::text, '-', ''),
    container_tag VARCHAR(100) NOT NULL,
    content TEXT NOT NULL,
    embedding vector(1024),
    
    -- Temporal semantics
    is_static BOOLEAN DEFAULT FALSE,
    is_latest BOOLEAN DEFAULT TRUE,
    valid_from TIMESTAMP WITH TIME ZONE,
    valid_until TIMESTAMP WITH TIME ZONE,
    
    -- Metadata
    metadata JSONB DEFAULT '{}',
    confidence FLOAT DEFAULT 0.8,
    
    -- System fields
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    is_forgotten BOOLEAN DEFAULT FALSE
);

-- Memories indexes
CREATE INDEX IF NOT EXISTS idx_memories_embedding ON memories USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS idx_memories_container ON memories(container_tag);
CREATE INDEX IF NOT EXISTS idx_memories_latest ON memories(container_tag, is_latest) WHERE is_latest = TRUE;
CREATE INDEX IF NOT EXISTS idx_memories_static ON memories(container_tag, is_static) WHERE is_static = TRUE;
CREATE INDEX IF NOT EXISTS idx_memories_forgotten ON memories(container_tag, is_forgotten) WHERE is_forgotten = FALSE;
CREATE INDEX IF NOT EXISTS idx_memories_created ON memories(created_at DESC);

-- Memories update trigger
CREATE OR REPLACE FUNCTION update_memories_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_memories_updated_at ON memories;
CREATE TRIGGER trigger_memories_updated_at
    BEFORE UPDATE ON memories
    FOR EACH ROW
    EXECUTE FUNCTION update_memories_updated_at();

-- ============================================================================
-- 4. Memory Relations Table
-- ============================================================================
CREATE TABLE IF NOT EXISTS memory_relations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    from_memory_id VARCHAR(24) NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
    to_memory_id VARCHAR(24) NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
    relation_type VARCHAR(20) NOT NULL CHECK (relation_type IN ('updates', 'extends', 'derives')),
    confidence FLOAT DEFAULT 0.8,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Memory relations indexes
CREATE INDEX IF NOT EXISTS idx_memory_relations_from ON memory_relations(from_memory_id);
CREATE INDEX IF NOT EXISTS idx_memory_relations_to ON memory_relations(to_memory_id);
CREATE INDEX IF NOT EXISTS idx_memory_relations_type ON memory_relations(relation_type);

-- ============================================================================
-- 5. Memory Profiles Table (User Profile Cache)
-- ============================================================================
CREATE TABLE IF NOT EXISTS memory_profiles (
    container_tag VARCHAR(100) PRIMARY KEY,
    static_memories JSONB DEFAULT '[]',
    dynamic_memories JSONB DEFAULT '[]',
    entity_context TEXT,
    last_updated TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

COMMENT ON TABLE memory_profiles IS 'Cached user profiles for fast recall';
COMMENT ON COLUMN memory_profiles.entity_context IS 'Custom instructions for entity extraction';

-- ============================================================================
-- 6. Documents Table
-- ============================================================================
CREATE TABLE IF NOT EXISTS documents (
    id VARCHAR(24) PRIMARY KEY DEFAULT 'doc_' || replace(gen_random_uuid()::text, '-', ''),
    container_tag VARCHAR(100) NOT NULL,
    content TEXT NOT NULL,
    content_hash VARCHAR(64),
    metadata JSONB DEFAULT '{}',
    status VARCHAR(20) DEFAULT 'done' CHECK (status IN ('queued', 'processing', 'done')),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_documents_container ON documents(container_tag);
CREATE INDEX IF NOT EXISTS idx_documents_hash ON documents(content_hash);

-- ============================================================================
-- 7. Entities Table (Knowledge Graph Nodes)
-- ============================================================================
CREATE TABLE IF NOT EXISTS entities (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    type VARCHAR(50) NOT NULL,
    container_tag VARCHAR(100) NOT NULL,
    normalized_name VARCHAR(255),
    mention_count INT DEFAULT 1,
    confidence FLOAT DEFAULT 0.8,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Entity indexes
CREATE INDEX idx_entities_name ON entities(name);
CREATE INDEX idx_entities_container ON entities(container_tag);
CREATE INDEX idx_entities_type ON entities(type);
CREATE INDEX idx_entities_normalized_name ON entities (LOWER(TRIM(name)), container_tag);

-- Entity unique constraint (name + type + container_tag)
ALTER TABLE entities ADD CONSTRAINT uq_entities_name_type_container UNIQUE (name, type, container_tag);

COMMENT ON TABLE entities IS 'Entity nodes for knowledge graph';
COMMENT ON COLUMN entities.type IS 'Entity type: person/location/organization/event/topic/emotion/time/task/decision/concept/solution/problem';

-- Entity update trigger
DROP TRIGGER IF EXISTS update_entities_updated_at ON entities;
CREATE TRIGGER update_entities_updated_at
    BEFORE UPDATE ON entities
    FOR EACH ROW
    EXECUTE FUNCTION update_memories_updated_at();

-- ============================================================================
-- 8. Entity Relations Table (Knowledge Graph Edges)
-- ============================================================================
CREATE TABLE IF NOT EXISTS entity_relations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    from_entity_id UUID NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    to_entity_id UUID NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    relation_type VARCHAR(50) NOT NULL,
    weight FLOAT DEFAULT 0.5,
    confidence FLOAT DEFAULT 0.8,
    container_tag VARCHAR(100) NOT NULL,
    source_memory_id VARCHAR(24),
    created_at TIMESTAMP DEFAULT NOW()
);

-- Entity relations indexes
CREATE INDEX idx_entity_relations_from ON entity_relations(from_entity_id);
CREATE INDEX idx_entity_relations_to ON entity_relations(to_entity_id);
CREATE INDEX idx_entity_relations_type ON entity_relations(relation_type);
CREATE INDEX idx_entity_relations_container ON entity_relations(container_tag);

-- Entity relations unique constraint
ALTER TABLE entity_relations ADD CONSTRAINT uq_entity_relations UNIQUE (from_entity_id, to_entity_id, relation_type, container_tag);

COMMENT ON TABLE entity_relations IS 'Relationships between entities in the knowledge graph';
COMMENT ON COLUMN entity_relations.relation_type IS 'Relation type: friend/colleague/works_at/lives_at/met_at/located_in/same_as/is_a etc.';

-- ============================================================================
-- 9. Memory-Entities Junction Table
-- ============================================================================
CREATE TABLE IF NOT EXISTS memory_entities (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    memory_id VARCHAR(24) NOT NULL,
    entity_id UUID NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    entity_type VARCHAR(50),
    mention_context TEXT,
    confidence FLOAT DEFAULT 0.8,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Memory-entities indexes
CREATE INDEX idx_memory_entities_memory ON memory_entities(memory_id);
CREATE INDEX idx_memory_entities_entity ON memory_entities(entity_id);
CREATE INDEX idx_memory_entities_type ON memory_entities(entity_type);

-- Memory-entities unique constraint
ALTER TABLE memory_entities ADD CONSTRAINT uq_memory_entities UNIQUE (memory_id, entity_id);

COMMENT ON TABLE memory_entities IS 'Junction table linking memories to their extracted entities';

-- ============================================================================
-- 10. Helper Functions
-- ============================================================================

-- Generate memory ID
CREATE OR REPLACE FUNCTION generate_memory_id() RETURNS VARCHAR(24) AS $$
BEGIN
    RETURN 'mem_' || substr(replace(gen_random_uuid()::text, '-', ''), 1, 20);
END;
$$ LANGUAGE plpgsql;

-- Generate document ID
CREATE OR REPLACE FUNCTION generate_document_id() RETURNS VARCHAR(24) AS $$
BEGIN
    RETURN 'doc_' || substr(replace(gen_random_uuid()::text, '-', ''), 1, 20);
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- 11. Grants
-- ============================================================================
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO postgres;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO postgres;

-- ============================================================================
-- Complete
-- ============================================================================
SELECT 'Schema initialized successfully!' AS status;