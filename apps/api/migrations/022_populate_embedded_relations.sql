-- Migration 022: Populate Embedded Relations
-- Version: 022
-- Purpose: Populate embedded relations for existing memories from memory_relations_new table

-- Update memories metadata to include relations from memory_relations_new table
UPDATE memories m
SET metadata = jsonb_set(
    COALESCE(m.metadata, '{}'::jsonb),
    '{relations}',
    (
        SELECT jsonb_build_object(
            'updates', COALESCE(
                jsonb_agg(to_memory_id) FILTER (WHERE relation_type = 'updates'),
                '[]'::jsonb
            ),
            'extends', COALESCE(
                jsonb_agg(to_memory_id) FILTER (WHERE relation_type = 'extends'),
                '[]'::jsonb
            ),
            'derives', COALESCE(
                jsonb_agg(to_memory_id) FILTER (WHERE relation_type = 'derives'),
                '[]'::jsonb
            )
        )
        FROM memory_relations_new
        WHERE from_memory_id = m.id
    )
)
WHERE EXISTS (
    SELECT 1 FROM memory_relations_new
    WHERE from_memory_id = m.id
);

-- Select complete
SELECT 'Migration 022 completed successfully - Embedded relations populated for existing memories' AS status;
