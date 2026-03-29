-- Migration 019: Drop old tables from previous architecture
-- These tables are no longer needed after the simplified architecture refactor

-- Drop old DAG architecture tables
DROP TABLE IF EXISTS summaries CASCADE;
DROP TABLE IF EXISTS summary_messages CASCADE;
DROP TABLE IF EXISTS summary_parents CASCADE;
DROP TABLE IF EXISTS summary_entities CASCADE;
DROP TABLE IF EXISTS context_items CASCADE;

-- Drop old entities table (replaced by metadata JSONB)
DROP TABLE IF EXISTS entities CASCADE;

-- Drop old relations table (renamed to memory_relations_new -> memory_relations)
DROP TABLE IF EXISTS relations CASCADE;

-- Drop old raw_messages table (replaced by memories)
DROP TABLE IF EXISTS raw_messages CASCADE;

-- Drop old content_chunks table
DROP TABLE IF EXISTS content_chunks CASCADE;

-- Drop old notifications table (not used in simplified architecture)
DROP TABLE IF EXISTS notifications CASCADE;

-- Drop old user_profiles table (replaced by memory_profiles)
DROP TABLE IF EXISTS user_profiles CASCADE;

-- Rename memory_relations_new to memory_relations if not already done
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'memory_relations_new') THEN
        DROP TABLE IF EXISTS memory_relations CASCADE;
        ALTER TABLE memory_relations_new RENAME TO memory_relations;
    END IF;
END $$;

-- Create indexes on memory_relations if not exists
CREATE INDEX IF NOT EXISTS idx_memory_relations_from ON memory_relations(from_memory_id);
CREATE INDEX IF NOT EXISTS idx_memory_relations_to ON memory_relations(to_memory_id);
CREATE INDEX IF NOT EXISTS idx_memory_relations_type ON memory_relations(relation_type);

-- Drop old function calling tools table if exists
DROP TABLE IF EXISTS function_calling_tools CASCADE;

-- Clean up old evolution services tables
DROP TABLE IF EXISTS evolution_facts CASCADE;
DROP TABLE IF EXISTS evolution_importance CASCADE;
DROP TABLE IF EXISTS evolution_temporal CASCADE;

-- Note: This migration is irreversible. Backup data before running.
