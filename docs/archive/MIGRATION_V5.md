# Migration Guide: v1/v2 → v5.0 Unified API

This guide helps you migrate from the legacy v1/v2 API to the new unified v5.0 API.

## Summary of Changes

| Change | v1/v2 | v5.0 |
|--------|-------|------|
| API Version Prefix | `/v1/*`, `/v2/*` | `/*` (root) |
| Authentication | Optional | Required (API Key) |
| Endpoints | 30+ | 14 (streamlined) |

## Breaking Changes

### 1. API Paths

All endpoints now use root paths without version prefix:

```
# Before (v1)
POST /v1/memories
GET /v1/profile

# Before (v2)
POST /v2/memories
GET /v2/profile

# After (v5.0)
POST /memories
GET /profile
```

### 2. Authentication Required

All endpoints now require `X-API-Key` header:

```bash
# Before (v1/v2)
curl http://localhost:8000/memories

# After (v5.0)
curl -H "X-API-Key: rk_live_xxx" http://localhost:8000/memories
```

### 3. Container Tag Ownership

`container_tag` must now start with your `user_id`:

```bash
# Valid
container_tag="user_123_default"
container_tag="user_123_project_alpha"

# Invalid (will return 403)
container_tag="other_user_data"
```

## Migration Steps

### Step 1: Create API Key

```bash
curl -X POST http://localhost:8000/auth/keys \
  -H "Content-Type: application/json" \
  -d '{
    "name": "My App",
    "permissions": ["read", "write"],
    "is_test": false
  }'
```

### Step 2: Update Base URL

Remove version prefix from your base URL:

```python
# Before
client = MemoryRecallClient(base_url="http://localhost:8000/v2")

# After
client = MemoryRecallClient(base_url="http://localhost:8000")
```

### Step 3: Add API Key to Requests

```python
# Before
headers = {"Content-Type": "application/json"}

# After
headers = {
    "Content-Type": "application/json",
    "X-API-Key": "rk_live_xxx"
}
```

### Step 4: Update Container Tags

Ensure your container tags follow the ownership pattern:

```python
# Before
container_tag = "my_project"

# After
container_tag = f"{user_id}_my_project"
```

## Endpoint Mapping

| v1 Endpoint | v5.0 Endpoint |
|-------------|---------------|
| `POST /v1/memories` | `POST /memories` |
| `GET /v1/memories` | `GET /memories` |
| `GET /v1/memories/{id}` | `GET /memories/{id}` |
| `DELETE /v1/memories/{id}` | `POST /memories/{id}/forget` |
| `GET /v1/profile` | `GET /profile` |
| `POST /v1/search` | `POST /search` |
| `GET /v1/graph` | `GET /graph` |

| v2 Endpoint | v5.0 Endpoint |
|-------------|---------------|
| `POST /v2/memories` | `POST /memories` |
| `GET /v2/memories` | `GET /memories` |
| `GET /v2/profile` | `GET /profile` |
| `POST /v2/search` | `POST /search` |
| `POST /v2/memories/{id}/forget` | `POST /memories/{id}/forget` |
| `POST /v2/memories/{id}/restore` | `POST /memories/{id}/restore` |
| `POST /v2/memories/{id}/update` | `POST /memories/{id}/update` |

## New Features

### API Key Management

```bash
# Create API Key
POST /auth/keys

# Response
{
  "key": "rk_live_xxx",
  "name": "My App",
  "permissions": ["read", "write"],
  "created_at": "2026-03-29T10:00:00Z"
}
```

### Permission Levels

| Permission | Access |
|------------|--------|
| `read` | GET endpoints |
| `write` | POST, PUT endpoints |
| `delete` | DELETE, forget endpoints |
| `admin` | All endpoints + auth management |

### Rate Limiting

- Default: 100 requests per 60 seconds
- Exceeded: Returns `429 Too Many Requests`

## Removed Endpoints

The following v1 endpoints have been removed:

- `/v1/containers/*` - Use `container_tag` parameter instead
- `/v1/relations/*` - Relations are now automatic
- `/v1/notifications/*` - Feature deprecated
- `/v1/recall/*` - Use `/search` instead

## Troubleshooting

### 401 Unauthorized

```
Error: "Missing or invalid API key"
Solution: Add X-API-Key header to all requests
```

### 403 Forbidden

```
Error: "Container ownership mismatch"
Solution: Ensure container_tag starts with your user_id
```

### 429 Too Many Requests

```
Error: "Rate limit exceeded"
Solution: Wait 60 seconds or reduce request frequency
```
