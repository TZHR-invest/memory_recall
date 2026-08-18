-- ============================================================================
-- Memory Recall - Complete Database Schema
-- Version: 5.1.5
-- Purpose: New environment initialization (replaces migrations)
-- Updated: 2026-04-03 - Synced with codebase actual usage
-- ============================================================================

-- Install pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- ============================================================================
-- 1. API Keys Table (Authentication)
-- ============================================================================
CREATE TABLE IF NOT EXISTS api_keys (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id VARCHAR(100) NOT NULL,
    user_name VARCHAR(100),
    key_hash VARCHAR(64) NOT NULL,
    key_prefix VARCHAR(20) NOT NULL,
    name VARCHAR(100),
    permissions TEXT[] DEFAULT ARRAY['read']::TEXT[],
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
CREATE INDEX IF NOT EXISTS idx_api_keys_active ON api_keys(user_id, is_active) WHERE is_active = TRUE;
CREATE INDEX IF NOT EXISTS idx_api_keys_hash ON api_keys(key_hash);
CREATE INDEX IF NOT EXISTS idx_api_keys_user_name ON api_keys(user_name);

-- API Keys constraints
ALTER TABLE api_keys ADD CONSTRAINT api_keys_key_hash_key UNIQUE (key_hash);

COMMENT ON TABLE api_keys IS 'API authentication keys with permissions and usage tracking';
COMMENT ON COLUMN api_keys.key_hash IS 'SHA-256 hash of the full API key';
COMMENT ON COLUMN api_keys.key_prefix IS 'First 20 characters of the key for identification';
COMMENT ON COLUMN api_keys.user_name IS 'Display name for the user';

-- ============================================================================
-- 2. Memories Table (Core Memory Storage)
-- ============================================================================
CREATE TABLE IF NOT EXISTS memories (
    id VARCHAR(24) PRIMARY KEY DEFAULT 'mem_' || substr(replace(gen_random_uuid()::text, '-', ''), 1, 20),
    container_tag VARCHAR(100) NOT NULL,
    content TEXT NOT NULL,
    embedding vector(1024),
    embedding_model VARCHAR(100),
    
    -- Temporal semantics
    is_static BOOLEAN DEFAULT FALSE,
    is_latest BOOLEAN DEFAULT TRUE,
    valid_from TIMESTAMP WITH TIME ZONE,
    valid_until TIMESTAMP WITH TIME ZONE,
    
    -- Version control
    version INTEGER DEFAULT 1,
    root_memory_id VARCHAR(24),
    source_count INTEGER DEFAULT 1,
    is_inference BOOLEAN DEFAULT FALSE,
    
    -- Metadata
    metadata JSONB DEFAULT '{}',
    confidence FLOAT DEFAULT 0.8,
    
    -- System fields
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    is_forgotten BOOLEAN DEFAULT FALSE,
    forget_after TIMESTAMP WITH TIME ZONE,
    forget_reason VARCHAR(500),
    
    -- Constraints
    CONSTRAINT chk_version_positive CHECK (version >= 1)
);

-- Memories indexes
CREATE INDEX IF NOT EXISTS idx_memories_embedding ON memories USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS idx_memories_container ON memories(container_tag);
CREATE INDEX IF NOT EXISTS idx_memories_latest ON memories(container_tag, is_latest) WHERE is_latest = TRUE;
CREATE INDEX IF NOT EXISTS idx_memories_static ON memories(container_tag, is_static) WHERE is_static = TRUE;
CREATE INDEX IF NOT EXISTS idx_memories_forgotten ON memories(container_tag, is_forgotten) WHERE is_forgotten = FALSE;
CREATE INDEX IF NOT EXISTS idx_memories_created ON memories(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_memories_root ON memories(root_memory_id) WHERE root_memory_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_memories_version ON memories(id, version) WHERE is_latest = TRUE;

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

COMMENT ON COLUMN memories.embedding_model IS 'Embedding model used for vectorization (e.g., doubao-embedding-vision-251215)';
COMMENT ON COLUMN memories.version IS 'Version number for memory evolution tracking';
COMMENT ON COLUMN memories.root_memory_id IS 'Reference to the original memory in version chain';
COMMENT ON COLUMN memories.source_count IS 'Number of sources contributing to this memory';
COMMENT ON COLUMN memories.is_inference IS 'Whether this memory was inferred from patterns';
COMMENT ON COLUMN memories.metadata IS 'JSONB containing: entities (extracted entities), relations (embedded memory relations as Record<relationType, targetIds[]>)';

-- ============================================================================
-- 3. Memory Relations Table
-- ============================================================================
CREATE TABLE IF NOT EXISTS memory_relations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    from_memory_id VARCHAR(24) NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
    to_memory_id VARCHAR(24) NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
    relation_type VARCHAR(20) NOT NULL CHECK (relation_type IN ('updates', 'extends', 'derives')),
    confidence FLOAT DEFAULT 0.8,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    CONSTRAINT uq_memory_relations_src_dst_type UNIQUE (from_memory_id, to_memory_id, relation_type)
);

-- Memory relations indexes
CREATE INDEX IF NOT EXISTS idx_memory_relations_from ON memory_relations(from_memory_id);
CREATE INDEX IF NOT EXISTS idx_memory_relations_to ON memory_relations(to_memory_id);
CREATE INDEX IF NOT EXISTS idx_memory_relations_type ON memory_relations(relation_type);

-- ============================================================================
-- 4. Memory Profiles Table (User Profile Cache)
-- ============================================================================
CREATE TABLE IF NOT EXISTS memory_profiles (
    container_tag VARCHAR(100) PRIMARY KEY,
    static_memories JSONB DEFAULT '[]',
    dynamic_memories JSONB DEFAULT '[]',
    entity_context TEXT,
    last_updated TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    -- Constraints
    CONSTRAINT chk_entity_context_length CHECK (char_length(entity_context) <= 1500 OR entity_context IS NULL)
);

COMMENT ON TABLE memory_profiles IS 'Cached user profiles for fast recall';
COMMENT ON COLUMN memory_profiles.entity_context IS 'Per-container context to guide entity extraction (max 1500 chars). Combined with org-level filter_prompt in LLM calls.';

-- ============================================================================
-- 5. Documents Table (Document Metadata)
-- ============================================================================
CREATE TABLE IF NOT EXISTS documents (
    id VARCHAR(24) PRIMARY KEY DEFAULT 'doc_' || substr(replace(gen_random_uuid()::text, '-', ''), 1, 20),
    container_tag VARCHAR(100) NOT NULL,
    title VARCHAR(500),
    url TEXT,
    source VARCHAR(200),
    doc_type VARCHAR(50) DEFAULT 'text',
    token_count INTEGER DEFAULT 0,
    word_count INTEGER DEFAULT 0,
    chunk_count INTEGER DEFAULT 0,
    content_hash VARCHAR(64),
    status VARCHAR(20) DEFAULT 'queued' CHECK (status IN ('queued', 'extracting', 'chunking', 'embedding', 'indexing', 'done', 'failed')),
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_documents_container ON documents(container_tag);
CREATE INDEX IF NOT EXISTS idx_documents_created ON documents(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_documents_status ON documents(status);
CREATE INDEX IF NOT EXISTS idx_documents_content_hash ON documents(container_tag, content_hash);
CREATE INDEX IF NOT EXISTS idx_documents_url ON documents(container_tag, url);

COMMENT ON TABLE documents IS 'Document metadata storage. Actual content stored in chunks table.';
COMMENT ON COLUMN documents.doc_type IS 'Document type: text, markdown, pdf, etc.';
COMMENT ON COLUMN documents.token_count IS 'Estimated token count';
COMMENT ON COLUMN documents.word_count IS 'Word count';
COMMENT ON COLUMN documents.chunk_count IS 'Number of chunks';
COMMENT ON COLUMN documents.content_hash IS 'SHA-256 hash of document content for deduplication';

-- ============================================================================
-- 6. Chunks Table (Document Content Chunks)
-- ============================================================================
CREATE TABLE IF NOT EXISTS chunks (
    id VARCHAR(24) PRIMARY KEY DEFAULT 'chk_' || substr(replace(gen_random_uuid()::text, '-', ''), 1, 20),
    document_id VARCHAR(24) NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    content TEXT NOT NULL,
    embedded_content TEXT,
    position INTEGER NOT NULL,
    chunk_type VARCHAR(20) DEFAULT 'text',
    content_hash VARCHAR(64),
    embedding vector(1024),
    embedding_model VARCHAR(100),
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_chunks_document ON chunks(document_id);
CREATE INDEX IF NOT EXISTS idx_chunks_embedding ON chunks USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS idx_chunks_position ON chunks(document_id, position);
CREATE INDEX IF NOT EXISTS idx_chunks_content_hash ON chunks(document_id, content_hash);

COMMENT ON COLUMN chunks.content_hash IS 'SHA-256 hash of chunk content for incremental updates';

COMMENT ON TABLE chunks IS 'Document content chunks with embeddings.';
COMMENT ON COLUMN chunks.embedded_content IS 'Contextualized content for embedding (with surrounding context)';
COMMENT ON COLUMN chunks.position IS 'Position of this chunk in the original document';

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
CREATE INDEX IF NOT EXISTS idx_entities_name ON entities(name);
CREATE INDEX IF NOT EXISTS idx_entities_container ON entities(container_tag);
CREATE INDEX IF NOT EXISTS idx_entities_type ON entities(type);
CREATE INDEX IF NOT EXISTS idx_entities_normalized_name ON entities (LOWER(TRIM(name)), container_tag);

-- Entity unique constraint (name + type + container_tag)
ALTER TABLE entities DROP CONSTRAINT IF EXISTS uq_entities_name_container;
ALTER TABLE entities ADD CONSTRAINT uq_entities_name_type_container UNIQUE (name, type, container_tag);

COMMENT ON TABLE entities IS 'Entity nodes for knowledge graph';
COMMENT ON COLUMN entities.type IS 'Entity type: person/location/organization/event/topic/emotion/time/task/decision/concept/solution/problem';
COMMENT ON COLUMN entities.normalized_name IS 'Normalized form for entity merging';

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
CREATE INDEX IF NOT EXISTS idx_entity_relations_from ON entity_relations(from_entity_id);
CREATE INDEX IF NOT EXISTS idx_entity_relations_to ON entity_relations(to_entity_id);
CREATE INDEX IF NOT EXISTS idx_entity_relations_type ON entity_relations(relation_type);
CREATE INDEX IF NOT EXISTS idx_entity_relations_container ON entity_relations(container_tag);

-- Entity relations unique constraint
ALTER TABLE entity_relations ADD CONSTRAINT uq_entity_relations UNIQUE (from_entity_id, to_entity_id, relation_type, container_tag);

COMMENT ON TABLE entity_relations IS 'Relationships between entities in the knowledge graph';
COMMENT ON COLUMN entity_relations.relation_type IS 'Relation type: friend/colleague/works_at/lives_at/met_at/located_in/same_as/is_a etc.';
COMMENT ON COLUMN entity_relations.weight IS 'Relation strength (0.0-1.0), increases with multiple mentions';
COMMENT ON COLUMN entity_relations.source_memory_id IS 'Memory ID where this relation was extracted from';

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
CREATE INDEX IF NOT EXISTS idx_memory_entities_memory ON memory_entities(memory_id);
CREATE INDEX IF NOT EXISTS idx_memory_entities_entity ON memory_entities(entity_id);
CREATE INDEX IF NOT EXISTS idx_memory_entities_type ON memory_entities(entity_type);

-- Memory-entities unique constraint
ALTER TABLE memory_entities ADD CONSTRAINT uq_memory_entities UNIQUE (memory_id, entity_id);

COMMENT ON TABLE memory_entities IS 'Junction table linking memories to their extracted entities';
COMMENT ON COLUMN memory_entities.mention_context IS 'Surrounding text where entity was mentioned';

-- ============================================================================
-- 9.5. Chunk-Entities Junction Table (v5.2.1)
-- ============================================================================
CREATE TABLE IF NOT EXISTS chunk_entities (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    chunk_id VARCHAR(24) NOT NULL REFERENCES chunks(id) ON DELETE CASCADE,
    entity_id UUID NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    entity_type VARCHAR(50),
    mention_context TEXT,
    confidence FLOAT DEFAULT 0.8,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Chunk-entities indexes
CREATE INDEX IF NOT EXISTS idx_chunk_entities_chunk ON chunk_entities(chunk_id);
CREATE INDEX IF NOT EXISTS idx_chunk_entities_entity ON chunk_entities(entity_id);
CREATE INDEX IF NOT EXISTS idx_chunk_entities_type ON chunk_entities(entity_type);

-- Chunk-entities unique constraint
ALTER TABLE chunk_entities DROP CONSTRAINT IF EXISTS uq_chunk_entities;
ALTER TABLE chunk_entities ADD CONSTRAINT uq_chunk_entities UNIQUE (chunk_id, entity_id);

COMMENT ON TABLE chunk_entities IS 'Junction table linking document chunks to entities extracted from document summary';
COMMENT ON COLUMN chunk_entities.mention_context IS 'Surrounding text where entity was mentioned in the chunk';
COMMENT ON COLUMN chunk_entities.confidence IS 'Confidence score for this entity association';

-- ============================================================================
-- 9.8. Recall Traces Table (Debug Observability, v5.3)
-- ============================================================================
CREATE TABLE IF NOT EXISTS recall_traces (
    id VARCHAR(24) PRIMARY KEY DEFAULT 'trace_' || substr(replace(gen_random_uuid()::text, '-', ''), 1, 18),
    container_tag VARCHAR(100) NOT NULL,
    mode VARCHAR(20) NOT NULL DEFAULT 'single',
    user_tag VARCHAR(100),
    project_tag VARCHAR(100),
    query TEXT,
    config JSONB DEFAULT '{}',
    channels JSONB DEFAULT '{}',
    dedup JSONB DEFAULT '{}',
    final JSONB DEFAULT '[]',
    elapsed_ms JSONB DEFAULT '{}',
    total_ms FLOAT DEFAULT 0,
    summary JSONB DEFAULT '{}',
    error TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_recall_traces_container ON recall_traces(container_tag, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_recall_traces_created ON recall_traces(created_at);

COMMENT ON TABLE recall_traces IS 'Per-request recall pipeline traces for debugging (channel-level visibility)';
COMMENT ON COLUMN recall_traces.channels IS 'Per-channel recall details: profile/vector/memory_graph/entity_graph/chunks';
COMMENT ON COLUMN recall_traces.dedup IS 'Dedup details: kept and dropped (with duplicate_of reference)';
COMMENT ON COLUMN recall_traces.final IS 'Final injection order after dedup';
COMMENT ON COLUMN recall_traces.summary IS 'Channel counts for list view (avoids reading large JSONB columns)';

-- ============================================================================
-- 9.9. Embedding Call Logs (Debug Observability, v5.3)
-- 每次 embedding API 调用（成功/失败/缓存命中）的结构化日志，用于排查 LLM/embedding 故障
-- ============================================================================
CREATE TABLE IF NOT EXISTS recall_embedding_logs (
    id VARCHAR(24) PRIMARY KEY DEFAULT 'embed_' || substr(replace(gen_random_uuid()::text, '-', ''), 1, 18),
    container_tag VARCHAR(100) NOT NULL DEFAULT '',
    kind VARCHAR(32) NOT NULL DEFAULT 'memory',
    model VARCHAR(64),
    text_preview VARCHAR(500),
    text_len INT DEFAULT 0,
    ok BOOLEAN NOT NULL DEFAULT FALSE,
    cache_hit BOOLEAN NOT NULL DEFAULT FALSE,
    error VARCHAR(500),
    elapsed_ms FLOAT DEFAULT 0,
    output_dim INT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_recall_embedding_logs_container ON recall_embedding_logs(container_tag, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_recall_embedding_logs_created ON recall_embedding_logs(created_at DESC);

COMMENT ON TABLE recall_embedding_logs IS 'Structured log of every embedding API call (memory create, context query, etc.)';

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
-- 12. crystal schema（目标模型迭代，Stage A / M1，2026-08-18 草稿）
-- 命名空间隔离：crystal.* 与 public.*（v5）物理并存；回退 = DROP SCHEMA crystal CASCADE
-- 表字段依据 docs/initiatives/crystal/entity-attributes.md（v1 已定稿）
-- 只跑 init_db.py（幂等建表）；绝不跑 setup_database.py（全量清库）
-- ============================================================================
CREATE SCHEMA IF NOT EXISTS crystal;

-- ----------------------------------------------------------------------------
-- 12.1 crystal.evidence（不可再生核心，append-only）
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS crystal.evidence (
    id TEXT PRIMARY KEY DEFAULT 'ev_' || substr(replace(gen_random_uuid()::text, '-', ''), 1, 22),
    observed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    source_kind TEXT NOT NULL CHECK (source_kind IN ('agent_add', 'outcome_trace', 'document', 'user_correction')),
    content TEXT NOT NULL,
    scope TEXT,
    owner_type TEXT NOT NULL CHECK (owner_type IN ('personal', 'team')),
    owner_id TEXT NOT NULL,
    source_ref JSONB,
    extraction_type TEXT CHECK (extraction_type IN ('verbatim', 'paraphrase', 'inference')),
    embedding vector(1024),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_crystal_evidence_owner ON crystal.evidence(owner_type, owner_id);
CREATE INDEX IF NOT EXISTS idx_crystal_evidence_scope ON crystal.evidence(owner_type, scope);
CREATE INDEX IF NOT EXISTS idx_crystal_evidence_source_kind ON crystal.evidence(source_kind);
CREATE INDEX IF NOT EXISTS idx_crystal_evidence_observed ON crystal.evidence(observed_at DESC);
CREATE INDEX IF NOT EXISTS idx_crystal_evidence_embedding ON crystal.evidence USING hnsw (embedding vector_cosine_ops);

COMMENT ON TABLE crystal.evidence IS 'crystal: 不可再生原始观察（append-only，语义字段不可变）';
COMMENT ON COLUMN crystal.evidence.observed_at IS '事件时间（语义核心，可显式覆盖补录）';
COMMENT ON COLUMN crystal.evidence.extraction_type IS '提炼方式 verbatim/paraphrase/inference（B5 定案：inference 降档）';
COMMENT ON COLUMN crystal.evidence.source_ref IS '出处 {session_id, message_id, plugin, file, ...}';

-- ----------------------------------------------------------------------------
-- 12.2 crystal.evidence_processing（1:1 伴随状态机）
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS crystal.evidence_processing (
    evidence_id TEXT PRIMARY KEY REFERENCES crystal.evidence(id) ON DELETE CASCADE,
    processing_state TEXT NOT NULL DEFAULT 'pending' CHECK (processing_state IN ('pending', 'processing', 'done', 'failed')),
    current_step TEXT,
    last_error JSONB,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_crystal_evidence_processing_state ON crystal.evidence_processing(processing_state);

COMMENT ON TABLE crystal.evidence_processing IS 'crystal: evidence 处理状态机（步骤名是数据不是列）';
COMMENT ON COLUMN crystal.evidence_processing.last_error IS '{step, message, attempts, last_attempt_at}';

-- ----------------------------------------------------------------------------
-- 12.3 crystal.claim（派生层，可版本化；status 为派生物化缓存）
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS crystal.claim (
    id TEXT PRIMARY KEY DEFAULT 'cl_' || substr(replace(gen_random_uuid()::text, '-', ''), 1, 22),
    statement TEXT NOT NULL,
    claim_kind TEXT NOT NULL CHECK (claim_kind IN ('fact', 'preference', 'constraint', 'learned-pattern')),
    content_confidence FLOAT,
    scope TEXT,
    owner_type TEXT NOT NULL CHECK (owner_type IN ('personal', 'team')),
    owner_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'superseded', 'disputed', 'retracted')),
    embedding vector(1024),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_crystal_claim_owner ON crystal.claim(owner_type, owner_id);
CREATE INDEX IF NOT EXISTS idx_crystal_claim_scope ON crystal.claim(owner_type, scope);
CREATE INDEX IF NOT EXISTS idx_crystal_claim_kind ON crystal.claim(claim_kind);
CREATE INDEX IF NOT EXISTS idx_crystal_claim_status ON crystal.claim(status);
CREATE INDEX IF NOT EXISTS idx_crystal_claim_embedding_active ON crystal.claim USING hnsw (embedding vector_cosine_ops) WHERE status = 'active';

COMMENT ON TABLE crystal.claim IS 'crystal: 派生主张（对账产物，可重算；status 写边事务内同步维护）';
COMMENT ON COLUMN crystal.claim.content_confidence IS '单轴内容置信度（Beta 期望），NULL=UNKNOWN';
COMMENT ON COLUMN crystal.claim.status IS '派生物化缓存：active/superseded/disputed/retracted';

-- ----------------------------------------------------------------------------
-- 12.4 crystal.lineage_edge（谱系边，推理在边；无触发证据字段，审计走 claim_activity）
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS crystal.lineage_edge (
    id TEXT PRIMARY KEY DEFAULT 'le_' || substr(replace(gen_random_uuid()::text, '-', ''), 1, 22),
    from_claim_id TEXT NOT NULL REFERENCES crystal.claim(id) ON DELETE CASCADE,
    to_claim_id TEXT REFERENCES crystal.claim(id) ON DELETE CASCADE,
    edge_type TEXT NOT NULL CHECK (edge_type IN ('supersedes', 'generalizes', 'contradicts', 'retract')),
    reason TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_lineage_not_self CHECK (from_claim_id <> to_claim_id)
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_crystal_lineage_permanent ON crystal.lineage_edge(from_claim_id, to_claim_id, edge_type) WHERE edge_type IN ('supersedes', 'generalizes', 'retract');
CREATE INDEX IF NOT EXISTS idx_crystal_lineage_from ON crystal.lineage_edge(from_claim_id, edge_type);
CREATE INDEX IF NOT EXISTS idx_crystal_lineage_to ON crystal.lineage_edge(to_claim_id);

COMMENT ON TABLE crystal.lineage_edge IS 'crystal: claim 演变谱系（supersedes/generalizes 永久；contradicts 临时；retract 单端 to=NULL）';

-- ----------------------------------------------------------------------------
-- 12.4b crystal.claim_activity（变更审计日志，非核心模型，2026-08-18 新增）
-- 承接原 lineage_edge.triggered_by_evidence 职责：谁/哪条证据/什么动作导致变更
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS crystal.claim_activity (
    id TEXT PRIMARY KEY DEFAULT 'ca_' || substr(replace(gen_random_uuid()::text, '-', ''), 1, 22),
    claim_id TEXT NOT NULL REFERENCES crystal.claim(id) ON DELETE CASCADE,
    action TEXT NOT NULL CHECK (action IN ('superseded_by', 'generalized_to', 'confirmed', 'retracted', 'promoted_scope', 'poison_warning')),
    actor_type TEXT NOT NULL CHECK (actor_type IN ('system', 'user', 'admin')),
    actor_id TEXT,
    triggered_by_evidence_id TEXT REFERENCES crystal.evidence(id),
    detail JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_crystal_activity_claim ON crystal.claim_activity(claim_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_crystal_activity_trigger ON crystal.claim_activity(triggered_by_evidence_id);
CREATE INDEX IF NOT EXISTS idx_crystal_activity_action ON crystal.claim_activity(action);

COMMENT ON TABLE crystal.claim_activity IS 'crystal: 变更审计日志（append-only；记录谁/哪条证据/什么动作导致状态变更）';
COMMENT ON COLUMN crystal.claim_activity.detail IS '补充：目标 claim_id / reason / 旧值快照等';

-- ----------------------------------------------------------------------------
-- 12.5 crystal.claim_evidence（Claim↔Evidence 支持关系，派生物化）
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS crystal.claim_evidence (
    claim_id TEXT NOT NULL REFERENCES crystal.claim(id) ON DELETE CASCADE,
    evidence_id TEXT NOT NULL REFERENCES crystal.evidence(id) ON DELETE CASCADE,
    role TEXT NOT NULL DEFAULT 'support' CHECK (role IN ('support')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (claim_id, evidence_id)
);

CREATE INDEX IF NOT EXISTS idx_crystal_claim_evidence_ev ON crystal.claim_evidence(evidence_id);

COMMENT ON TABLE crystal.claim_evidence IS 'crystal: 结论引用证据（1..N，不变量①）；role 预留支持/反证分离';

-- ----------------------------------------------------------------------------
-- 12.6 crystal.claim_usage（复用/outcome 离散价值信号，P1 遥测激活）
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS crystal.claim_usage (
    claim_id TEXT PRIMARY KEY REFERENCES crystal.claim(id) ON DELETE CASCADE,
    reuse_count INTEGER NOT NULL DEFAULT 0,
    outcome_good INTEGER NOT NULL DEFAULT 0,
    outcome_bad INTEGER NOT NULL DEFAULT 0,
    last_used_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_crystal_claim_usage_reuse ON crystal.claim_usage(reuse_count DESC);

COMMENT ON TABLE crystal.claim_usage IS 'crystal: 复用频率/outcome 离散统计（一期不写入，P1 遥测激活）';

-- ============================================================================
-- Complete
-- ============================================================================
SELECT 'Schema initialized successfully!' AS status;