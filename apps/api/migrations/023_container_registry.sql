-- Container Registry: Bind container_tag to API key
-- When a container is first used, it is automatically bound to the API key that created it.
-- Subsequent access requires verification of the binding relationship.

CREATE TABLE IF NOT EXISTS container_registry (
    container_tag VARCHAR(100) PRIMARY KEY,
    api_key_id UUID NOT NULL REFERENCES api_keys(id) ON DELETE CASCADE,
    user_id VARCHAR(100) NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_container_registry_api_key ON container_registry(api_key_id);
CREATE INDEX IF NOT EXISTS idx_container_registry_user ON container_registry(user_id);

-- Add comment
COMMENT ON TABLE container_registry IS 'Records container_tag ownership. First-use auto-registration binds container to API key.';
COMMENT ON COLUMN container_registry.container_tag IS 'Unique container identifier';
COMMENT ON COLUMN container_registry.api_key_id IS 'API key that first created/used this container';
COMMENT ON COLUMN container_registry.user_id IS 'User ID (redundant, for quick lookups)';
