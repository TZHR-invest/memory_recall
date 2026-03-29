# Changelog

All notable changes to Memory Recall will be documented in this file.

## [4.0.0] - 2026-03-29

### Major Changes

#### Universal Agent Memory Service
- Transformed from OpenClaw ContextEngine plugin to standalone REST API service
- Added API Key authentication with `rk_live_xxx` and `rk_test_xxx` formats
- Implemented permission levels: read, write, delete, admin

#### New REST API v1 Endpoints
- `POST /v1/memories` - Create memory with behavior/lifespan
- `GET /v1/memories` - List memories with pagination
- `GET /v1/memories/{id}` - Get single memory
- `PATCH /v1/memories/{id}` - Update memory metadata
- `DELETE /v1/memories/{id}` - Delete memory
- `POST /v1/memories/{id}/forget` - Mark as forgotten
- `POST /v1/recall` - Smart recall with RRF fusion
- `GET /v1/profile` - Get user profile (~50ms target)
- `POST /v1/profile/refresh` - Force profile rebuild
- `POST /v1/containers` - Create container
- `GET /v1/containers` - List containers
- `GET /v1/memories/{id}/relations` - Get memory relations
- `GET /v1/memories/{id}/history` - Get version chain
- `GET /v1/notifications` - List notifications

#### Memory Evolution Services
- **UserProfileService** - Aggregates static facts, dynamic facts, and preferences
- **TemporalService** - Time-aware lifecycle management with configurable lifespans
- **ForgettingService** - Auto-expiration with notifications
- **ChunkingService** - Long document splitting (sentence/semantic/fixed strategies)
- **FactExtractionService** - Entity-centric fact extraction from content
- **ImportanceService** - Multi-factor importance scoring
- **FusionService** - Memory deduplication and merging

#### Memory Behaviors (NEW)
- `fact` - Persistent until updated, no decay
- `preference` - Strengthens with repetition
- `episode` - Decays unless significant

#### Memory Lifespans
- `temporary` - 1 day
- `short_term` - 30 days
- `long_term` - 365 days
- `permanent` - 100 years

#### Background Tasks
- Profile rebuild task (every 5 minutes)
- Expiration check task (daily)
- Cleanup task (daily)

### Database Changes

#### New Tables (Migration 017)
- `api_keys` - API key management
- `memory_relations` - Memory relationships
- `user_profiles` - Aggregated user profiles
- `facts` - Entity-centric facts
- `notifications` - System notifications
- `content_chunks` - Long document chunks

#### New Columns in raw_messages
- `event_date` - When event occurred
- `document_date` - When recorded
- `expiration_date` - Auto-forget timestamp
- `memory_lifespan` - Retention policy
- `is_latest` - Version control flag
- `is_expired` - Soft delete flag
- `container_id` - Grouping identifier
- `access_count` - Recall frequency
- `last_accessed_at` - Last access time
- `importance_score` - Calculated importance
- `memory_behavior` - fact/preference/episode
- `chunk_count` - Number of chunks

### Improvements

#### Recall Enhancements
- Reciprocal Rank Fusion (RRF) for result merging
- Time decay scoring (30-day half-life)
- Importance weighting
- Memory behavior weighting
- Profile-first recall option
- Chunk injection for long documents

#### Performance
- Target: ~50ms for profile retrieval
- Optimized database queries with proper indexing

### Breaking Changes
- Removed `src/openclaw_plugin/` directory
- Renamed `services/lossless/` to `services/core/`
- Renamed `MemoryRecallEngine` to `MemoryService`
- Removed legacy `memory_service.py`, `recall_service.py`

### Migration Guide

1. Run migration 017:
```bash
python migrations/run_single_migration.py migrations/017_clean_and_evolve.sql
```

2. Update imports:
```python
# Old
from src.services.lossless.memory_recall_engine import memory_recall_engine

# New
from src.services.core.memory_service import memory_service
```

3. Generate API keys:
```bash
POST /v1/auth/api-keys
{
    "name": "My API Key",
    "permissions": ["read", "write"]
}
```

## [3.0.0] - Previous Release
- DAG compression architecture
- Hybrid recall (vector + keyword + graph)
- Entity extraction
- Knowledge graph integration
