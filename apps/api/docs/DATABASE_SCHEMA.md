# Database Schema v4.0.0

## Overview

Memory Recall uses PostgreSQL with pgvector extension for vector similarity search. Each user has their own schema for multi-tenant isolation.

## Core Tables

### raw_messages
Primary storage for user memories.

| Column | Type | Description |
|--------|------|-------------|
| id | VARCHAR(40) | Primary key (raw_xxx format) |
| user_id | VARCHAR(100) | User identifier |
| content | TEXT | Memory content |
| memory_type | VARCHAR(20) | preference/note/dialogue |
| memory_behavior | VARCHAR(20) | fact/preference/episode |
| memory_lifespan | VARCHAR(20) | temporary/short_term/long_term/permanent |
| embedding | vector(1024) | Content embedding |
| event_date | TIMESTAMPTZ | When event occurred |
| expiration_date | TIMESTAMPTZ | Auto-forget timestamp |
| container_id | VARCHAR(100) | Grouping identifier |
| importance_score | FLOAT | 0.0-1.0 |
| access_count | INTEGER | Recall frequency |
| chunk_count | INTEGER | Number of content chunks |
| created_at | TIMESTAMPTZ | Creation timestamp |

### summaries
DAG compression summaries.

| Column | Type | Description |
|--------|------|-------------|
| summary_id | VARCHAR(40) | Primary key |
| content | TEXT | Summary content |
| depth | INTEGER | DAG depth level |
| token_count | INTEGER | Estimated tokens |

## Evolution Tables

### api_keys
API key management.

| Column | Type | Description |
|--------|------|-------------|
| id | UUID | Primary key |
| user_id | VARCHAR(100) | Owner |
| key_hash | VARCHAR(64) | SHA256 hash |
| key_prefix | VARCHAR(12) | rk_live_ or rk_test_ |
| permissions | JSONB | Permission array |

### memory_relations
Memory relationships.

| Column | Type | Description |
|--------|------|-------------|
| source_memory_id | VARCHAR(40) | Source memory |
| target_memory_id | VARCHAR(40) | Target memory |
| relation_type | VARCHAR(20) | updates/extends/derives/supersedes/related_to |

### user_profiles
Aggregated user profiles.

| Column | Type | Description |
|--------|------|-------------|
| user_id | VARCHAR(100) | Primary key |
| static_facts | JSONB | Permanent facts |
| dynamic_facts | JSONB | Event-based facts |
| preferences | JSONB | User preferences |

### facts
Entity-centric facts.

| Column | Type | Description |
|--------|------|-------------|
| entity_name | VARCHAR(200) | Entity name |
| entity_type | VARCHAR(50) | Entity type |
| attribute | VARCHAR(100) | Fact attribute |
| value | TEXT | Fact value |
| is_static | BOOLEAN | Static vs dynamic |

### notifications
System notifications.

| Column | Type | Description |
|--------|------|-------------|
| notification_type | VARCHAR(50) | Type of notification |
| memory_id | VARCHAR(40) | Related memory |
| is_read | BOOLEAN | Read status |

### content_chunks
Long document chunks.

| Column | Type | Description |
|--------|------|-------------|
| memory_id | VARCHAR(40) | Parent memory |
| chunk_index | INTEGER | Chunk position |
| chunk_text | TEXT | Chunk content |
| embedding | vector(1024) | Chunk embedding |