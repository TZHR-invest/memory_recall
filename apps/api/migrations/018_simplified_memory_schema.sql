-- Migration 018: Simplified Memory Schema
-- Version: 018
-- Purpose: Create simplified 3-table architecture for memory system
-- Design: memories, relations, profiles (with optional documents)

-- ============================================================================
-- PART 1: CREATE CORE TABLES
-- ============================================================================

-- Core Table 1: memories - Unified memory storage
CREATE TABLE IF NOT EXISTS memories (
    id VARCHAR(24) PRIMARY KEY DEFAULT 'mem_' || replace(gen_random_uuid()::text, '-', ''),
    container_tag VARCHAR(100) NOT NULL,  -- Isolation identifier (user_id/project_id)
    content TEXT NOT NULL,                 -- Memory content
    embedding vector(1024),                -- Vector embedding
    
    -- Temporal semantics
    is_static BOOLEAN DEFAULT FALSE,       -- Permanent trait (name, profession, preference)
    is_latest BOOLEAN DEFAULT TRUE,        -- Is this the latest version
    valid_from TIMESTAMP WITH TIME ZONE,   -- When information became effective
    valid_until TIMESTAMP WITH TIME ZONE,  -- When information became obsolete
    
    -- Metadata
    metadata JSONB DEFAULT '{}',           -- Entities, tags, source info
    confidence FLOAT DEFAULT 0.8,          -- Confidence score
    
    -- System fields
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    is_forgotten BOOLEAN DEFAULT FALSE     -- Soft delete
);

-- Core Table 2: relations - Memory relationships
CREATE TABLE IF NOT EXISTS memory_relations_new (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    from_memory_id VARCHAR(24) NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
    to_memory_id VARCHAR(24) NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
    relation_type VARCHAR(20) NOT NULL CHECK (relation_type IN ('updates', 'extends', 'derives')),
    confidence FLOAT DEFAULT 0.8,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Core Table 3: profiles - Cached user profile
CREATE TABLE IF NOT EXISTS memory_profiles (
    container_tag VARCHAR(100) PRIMARY KEY,
    static_memories JSONB DEFAULT '[]',    -- List of static memories
    dynamic_memories JSONB DEFAULT '[]',   -- List of dynamic memories
    last_updated TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Optional Table: documents - Original document storage
CREATE TABLE IF NOT EXISTS documents_new (
    id VARCHAR(24) PRIMARY KEY DEFAULT 'doc_' || replace(gen_random_uuid()::text, '-', ''),
    container_tag VARCHAR(100) NOT NULL,
    content TEXT NOT NULL,
    metadata JSONB DEFAULT '{}',
    status VARCHAR(20) DEFAULT 'done' CHECK (status IN ('queued', 'processing', 'done')),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- ============================================================================
-- PART 2: CREATE INDEXES
-- ============================================================================

-- Vector index on memories.embedding (HNSW)
CREATE INDEX IF NOT EXISTS idx_memories_embedding ON memories 
    USING hnsw (embedding vector_cosine_ops);

-- B-tree indexes for common queries
CREATE INDEX IF NOT EXISTS idx_memories_container ON memories(container_tag);
CREATE INDEX IF NOT EXISTS idx_memories_latest ON memories(container_tag, is_latest) WHERE is_latest = TRUE;
CREATE INDEX IF NOT EXISTS idx_memories_static ON memories(container_tag, is_static) WHERE is_static = TRUE;
CREATE INDEX IF NOT EXISTS idx_memories_forgotten ON memories(container_tag, is_forgotten) WHERE is_forgotten = FALSE;
CREATE INDEX IF NOT EXISTS idx_memories_created ON memories(created_at DESC);

-- Relation indexes
CREATE INDEX IF NOT EXISTS idx_memory_relations_from ON memory_relations_new(from_memory_id);
CREATE INDEX IF NOT EXISTS idx_memory_relations_to ON memory_relations_new(to_memory_id);
CREATE INDEX IF NOT EXISTS idx_memory_relations_type ON memory_relations_new(relation_type);

-- Document indexes
CREATE INDEX IF NOT EXISTS idx_documents_container ON documents_new(container_tag);

-- ============================================================================
-- PART 3: CREATE HELPER FUNCTIONS
-- ============================================================================

-- Function to generate memory ID
CREATE OR REPLACE FUNCTION generate_memory_id() RETURNS VARCHAR(24) AS $$
BEGIN
    RETURN 'mem_' || substr(replace(gen_random_uuid()::text, '-', ''), 1, 20);
END;
$$ LANGUAGE plpgsql;

-- Function to generate document ID
CREATE OR REPLACE FUNCTION generate_document_id() RETURNS VARCHAR(24) AS $$
BEGIN
    RETURN 'doc_' || substr(replace(gen_random_uuid()::text, '-', ''), 1, 20);
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- PART 4: MIGRATE DATA FROM RAW_MESSAGES (if exists)
-- ============================================================================

-- Migrate existing raw_messages to memories
INSERT INTO memories (id, container_tag, content, embedding, is_static, is_latest, metadata, confidence, created_at, is_forgotten)
SELECT 
    CASE 
        WHEN id LIKE 'raw_%' THEN 'mem_' || substr(id, 5)
        ELSE 'mem_' || substr(id, 1, 20)
    END,
    COALESCE(user_id, 'default'),
    content,
    embedding,
    FALSE,  -- is_static
    TRUE,   -- is_latest
    jsonb_build_object(
        'original_id', id,
        'memory_type', memory_type,
        'agent_id', agent_id,
        'session_id', session_id,
        'tags', COALESCE(tags, '[]'::jsonb)
    ),
    0.8,
    COALESCE(created_at, NOW()),
    FALSE
FROM raw_messages
WHERE NOT EXISTS (SELECT 1 FROM memories WHERE memories.content = raw_messages.content);

-- ============================================================================
-- PART 5: GRANT PERMISSIONS
-- ============================================================================

-- Grant permissions to application user
GRANT ALL PRIVILEGES ON TABLE memories TO postgres;
GRANT ALL PRIVILEGES ON TABLE memory_relations_new TO postgres;
GRANT ALL PRIVILEGES ON TABLE memory_profiles TO postgres;
GRANT ALL PRIVILEGES ON TABLE documents_new TO postgres;

-- ============================================================================
-- COMPLETE
-- ============================================================================

SELECT 'Migration 018 completed successfully - Simplified memory schema created' AS status;
