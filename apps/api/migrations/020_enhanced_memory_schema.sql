-- Migration 020: Enhanced Memory Schema
-- Version: 020
-- Purpose: Add version control, root_memory_id, and embedded memoryRelations

-- Add new columns to memories table
ALTER TABLE memories ADD COLUMN IF NOT EXISTS version INTEGER DEFAULT 1;
ALTER TABLE memories ADD COLUMN IF NOT EXISTS root_memory_id VARCHAR(24);
ALTER TABLE memories ADD COLUMN IF NOT EXISTS source_count INTEGER DEFAULT 1;
ALTER TABLE memories ADD COLUMN IF NOT EXISTS is_inference BOOLEAN DEFAULT FALSE;

-- Add index on root_memory_id for version chain queries
CREATE INDEX IF NOT EXISTS idx_memories_root ON memories(root_memory_id) WHERE root_memory_id IS NOT NULL;

-- Add index on version for version tracking
CREATE INDEX IF NOT EXISTS idx_memories_version ON memories(id, version) WHERE is_latest = TRUE;

-- Update metadata structure to support embedded relations
-- metadata JSONB now includes:
-- {
--   "entities": {"location": [...], "preference": [...]},
--   "relations": {"updates": ["mem_xxx"], "extends": ["mem_yyy"]}
-- }

-- Add comment documenting the metadata structure
COMMENT ON COLUMN memories.metadata IS 'JSONB containing: entities (extracted entities), relations (embedded memory relations as Record<relationType, targetIds[]>)';

-- Add constraint for version >= 1
ALTER TABLE memories ADD CONSTRAINT chk_version_positive CHECK (version >= 1);

-- Update existing memories to have version 1 if NULL
UPDATE memories SET version = 1 WHERE version IS NULL;

-- Select complete
SELECT 'Migration 020 completed successfully - Enhanced memory schema with version control' AS status;
