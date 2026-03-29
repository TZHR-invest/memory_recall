-- Migration 021: Add Entity Context to Profiles
-- Version: 021
-- Purpose: Add entity_context field for container-level extraction guidance

-- Add entity_context column to memory_profiles table
ALTER TABLE memory_profiles ADD COLUMN IF NOT EXISTS entity_context TEXT;

-- Add constraint for max length (1500 characters per Supermemory design)
ALTER TABLE memory_profiles ADD CONSTRAINT chk_entity_context_length 
    CHECK (char_length(entity_context) <= 1500 OR entity_context IS NULL);

-- Add comment documenting the entity_context purpose
COMMENT ON COLUMN memory_profiles.entity_context IS 'Per-container context to guide entity extraction (max 1500 chars). Combined with org-level filter_prompt in LLM calls.';

-- Select complete
SELECT 'Migration 021 completed successfully - Entity context field added to memory_profiles' AS status;
