-- Simplify container ownership: one API key = one container
-- Remove container_registry table (no longer needed)
-- Add user_name field to api_keys for human-readable identification

DROP TABLE IF EXISTS container_registry;

ALTER TABLE api_keys ADD COLUMN IF NOT EXISTS user_name VARCHAR(100);

CREATE INDEX IF NOT EXISTS idx_api_keys_user_name ON api_keys(user_name);

COMMENT ON COLUMN api_keys.user_name IS 'Human-readable name specified by user during installation';
