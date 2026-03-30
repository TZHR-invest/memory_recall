-- Migration 025: Add content_hash to documents and chunks
-- Version: 025
-- Purpose: Add content hash for document deduplication and incremental updates
-- Design: Add nullable content_hash column, backfill in batches

-- ============================================================================
-- PART 1: ADD content_hash TO documents
-- ============================================================================

ALTER TABLE documents ADD COLUMN IF NOT EXISTS content_hash VARCHAR(64);

COMMENT ON COLUMN documents.content_hash IS 'SHA-256 hash of document content for deduplication';

-- ============================================================================
-- PART 2: ADD INDEX ON documents.content_hash
-- ============================================================================

CREATE INDEX IF NOT EXISTS idx_documents_content_hash ON documents(container_tag, content_hash);

-- ============================================================================
-- PART 3: ADD content_hash TO chunks
-- ============================================================================

ALTER TABLE chunks ADD COLUMN IF NOT EXISTS content_hash VARCHAR(64);

COMMENT ON COLUMN chunks.content_hash IS 'SHA-256 hash of chunk content for incremental updates';

-- ============================================================================
-- PART 4: ADD INDEX ON chunks.content_hash
-- ============================================================================

CREATE INDEX IF NOT EXISTS idx_chunks_content_hash ON chunks(document_id, content_hash);

-- ============================================================================
-- PART 5: CREATE BACKFILL FUNCTION
-- ============================================================================

CREATE OR REPLACE FUNCTION backfill_document_content_hash(batch_size INTEGER DEFAULT 1000)
RETURNS INTEGER AS $$
DECLARE
    updated_count INTEGER := 0;
    batch_updated INTEGER;
BEGIN
    LOOP
        UPDATE documents
        SET content_hash = encode(sha256(content::bytea), 'hex')
        WHERE id IN (
            SELECT id FROM documents
            WHERE content_hash IS NULL
            LIMIT batch_size
        );
        
        GET DIAGNOSTICS batch_updated = ROW_COUNT;
        updated_count := updated_count + batch_updated;
        
        EXIT WHEN batch_updated = 0;
        
        RAISE NOTICE 'Backfilled % documents, total %', batch_updated, updated_count;
    END LOOP;
    
    RETURN updated_count;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION backfill_chunk_content_hash(batch_size INTEGER DEFAULT 1000)
RETURNS INTEGER AS $$
DECLARE
    updated_count INTEGER := 0;
    batch_updated INTEGER;
BEGIN
    LOOP
        UPDATE chunks
        SET content_hash = encode(sha256(content::bytea), 'hex')
        WHERE id IN (
            SELECT id FROM chunks
            WHERE content_hash IS NULL
            LIMIT batch_size
        );
        
        GET DIAGNOSTICS batch_updated = ROW_COUNT;
        updated_count := updated_count + batch_updated;
        
        EXIT WHEN batch_updated = 0;
        
        RAISE NOTICE 'Backfilled % chunks, total %', batch_updated, updated_count;
    END LOOP;
    
    RETURN updated_count;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- PART 6: RUN BACKFILL (Optional - comment out for large datasets)
-- ============================================================================

-- SELECT backfill_document_content_hash(1000);
-- SELECT backfill_chunk_content_hash(1000);

-- ============================================================================
-- COMPLETE
-- ============================================================================

SELECT 'Migration 025 completed successfully - content_hash added to documents and chunks' AS status;
