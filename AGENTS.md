# AGENTS.md

Memory Recall (v5.2.1) — personal memory & recall system. FastAPI backend (`apps/api/`). Storage: PostgreSQL + pgvector. LLM/embedding: 火山引擎 doubao (Volcengine Ark, OpenAI-compatible). Client plugins live under `apps/api/src/plugins/`. Repo comments/commits are mostly Chinese — match the language of the file you touch.

## Setup & run (everything from `apps/api/`)

```bash
cd apps/api
python3 -m venv venv && venv/bin/pip install -r requirements.txt
cp .env.example .env        # fill DATABASE_* and VOLC_API_KEY
venv/bin/python setup_database.py        # create DB + pgvector ext + schema.sql tables
venv/bin/python -m uvicorn main:app --reload --port 8000
```

- Imports are absolute `src.*` — the server MUST be launched from `apps/api/` (`uvicorn main:app`), never from repo root.
- No venv is committed; macOS system python 3.9 is too old for the pinned deps (`fastapi==0.135.1`) — create one.
- **No migration framework.** `apps/api/schema.sql` is the single source of truth. After editing it, re-init: `setup_database.py` (full) or `init_db.py` (tables only). `docker-compose.yml` boots postgres (`pgvector/pgvector:pg16`) + adminer on :8888; schema auto-applies from `docker-entrypoint-initdb.d/` on first boot.
- **`VOLC_API_KEY` is required** for LLM + embedding calls; without it, memory creation (embedding step), entity extraction, and relation detection fail.

## Architecture

- `apps/api/main.py` — FastAPI wiring. Registers routers from `src.api` (`memories`, `graph`, `auth_endpoints`, `embed`, `context_inject`) and `src.routes` (`health`). New routers must be added to this `include_router` block.
- `src/api/` — current v5 endpoint layer: thin APIRouter per domain (`memories.py` also holds `/profile`, `/search`, `/documents*`, `/extract-memory`). `auth.py` — auth dependency layer (key management, permission checks, rate limit, `verify_container_ownership`), NOT a router itself. `src/routes/` — legacy, only `health.py` (incl. stale `/api/stats*`).
- `src/services/core/` — all business logic:
  - `context_inject_service.py` — **ALL recall/injection logic** (semantic search → memory-graph → entity-graph → chunks → dedup → markdown formatting)
  - `memory_store.py` — memory CRUD / versioning / vector search / entity-graph writes
  - `document_store.py` — documents + chunks storage, dedup, chunk search
  - `relation_service.py`, `profile_service.py`, `entity_extraction.py`, `llm_entity_extraction.py`, `semantic_dedup_service.py`
- `src/llm/client.py`, `src/embedding/client.py` — Volcengine clients, lazy singletons `get_llm_client()` / `get_embedding_client()`.
- Services are module-level singletons (`memory_store`, `db`, `settings`, `context_inject_service`, …) constructed at import time.

## Gotchas

- **Circular imports**: `profile_service` imports `memory_store` at module top, so `memory_store` must import `profile_service` only inside functions (see `process_memory_async`). Same pattern for `memory_store` inside `relation_service` (lazy in `create_derived_memory`). Don't "fix" these to top-level imports — startup breaks.
- **Dead code — don't mine these for features**: `src/models/`, `src/services/{prompts,embedding_cache}.py`. (`query_parser`/`keyword_extractor`/`image`/`openclaw` 已删除.)
- **Auth**: every endpoint requires `X-API-Key` (`rk_live_...` / `rk_test_...`). `verify_container_ownership` allows exact match or `{key_id}_*` prefix (project isolation). Keys via `POST /auth/api-keys` (admin key) or `install.py`.
- `apps/api/scripts/` holds one-off maintenance scripts (db optimize, entity cleanup, backups) — not part of the app.
- **两种"取代"语义并存（勿混淆/勿"修复"）**: ① 自动关系检测（`relation_service.auto_create_relations`, 检测到 contradiction/updates 时 `_mark_not_latest`）把旧记忆降级 `is_latest=FALSE` 但**不建版本链** —— N:1 取代语义（一条新记忆可同时取代多条旧记忆），被 `test_temporal_relations` 锁定。② 显式 `POST /memories/{id}/update`（`create_update_version`）建完整版本链（version+1, root_memory_id 链接）—— 1:1 修订语义。被降级的旧记忆仍可通过 updates 边被 `get_version_history` 追溯、被记忆图谱召回（`get_by_id` 不过滤 is_latest）。由此 `memories` 表会积累大量 `is_latest=FALSE, version=1, root_memory_id=NULL` 的"孤儿旧版本"（主容器实测 937 行）—— 这是设计产物不是数据损坏，stats 的 `old_versions` 计数含它们。`memory_store.get_version_chain` 是零调用死代码；真实历史走 `relation_service.get_version_history`（updates 边遍历）。

## Testing

`pytest.ini`: `asyncio_mode = auto`, `testpaths = tests`. **No `conftest.py`** — fixtures are inline per file (copy patterns from `test_v2/test_context_inject_api.py` or `test_v2/test_chunks_search.py`). Three tiers:

1. **Unit (mocked, safe anywhere)** — most of `tests/test_v2/`, all `tests/test_opencode/`, `tests/test_api/`.
2. **Integration (needs running Postgres + pgvector + schema)** — `tests/test_v2/test_integration.py`, `tests/test_v2/test_performance.py`, `tests/test_document_deduplication.py`, `tests/test_source_deduplication.py`.
3. **Live volcengine scripts** — `tests/test_llm_service.py`, `tests/test_embedding.py`, `tests/test_function_calling.py`. pytest collects these (they fail without `VOLC_API_KEY`); always `--ignore` them.

- **Env**: there is NO `TEST_DATABASE_URL`. `src/database.py` connects via `DATABASE_HOST/PORT/NAME/USER/PASSWORD` only (`DATABASE_URL` is declared in config but never parsed). Point tests at a scratch DB by overriding those vars, e.g. `DATABASE_NAME=memory_recall_test`.
- `test_document_deduplication.py` / `test_source_deduplication.py` use `@pytest.mark.order`, but `pytest-order` is NOT in `requirements.txt` — install it if ordering matters.
- Integration tests don't clean up their test data (containers like `test_integration_*`, `test_perf_*`).
- **pytest.ini keeps `asyncio_default_test_loop_scope = module`** — pytest-asyncio 1.x defaults test functions to a per-function loop, but async fixtures/db use the module loop, so asyncpg connections die with "attached to a different loop". Don't remove it; without it the whole integration suite fails (0/7).

```bash
cd apps/api
# fast unit loop (no DB, no API key) — default for iteration
venv/bin/python -m pytest tests -q -x \
  --ignore=tests/test_llm_service.py --ignore=tests/test_embedding.py \
  --ignore=tests/test_function_calling.py --ignore=tests/test_document_deduplication.py \
  --ignore=tests/test_source_deduplication.py --ignore=tests/test_v2/test_integration.py \
  --ignore=tests/test_v2/test_performance.py

# single test / file
venv/bin/python -m pytest tests/test_v2/test_integration.py -k test_full_memory_lifecycle -x -v
venv/bin/python -m pytest tests/test_v2/test_memory_store.py -x -v
```

## Plugins (`apps/api/src/plugins/`)

Three independent sub-projects. Build artifacts are gitignored (`dist/`, `*.tgz`, `*.sh`):

- `opencode/` — TypeScript/Bun plugin (`memory-recall-opencode`, main entry `dist/index.js`). Build with `bun run build` (NOT tsc — tsconfig has `noEmit: true`); install via `bunx memory-recall-opencode install`. Config written to `~/.config/opencode/memory-recall.jsonc`.
- `deepseek-tui/`, `hermes/` — standalone Python MCP stdio servers (`python server.py`), configured via `MEMORY_RECALL_*` env vars. `deepseek-tui`'s documented `install.sh` is gitignored/missing — only manual setup works.
- Tag convention: `userTag = keyId` (cross-project), `projectTag = {keyId}_project-<dirName>`. Backend contract: `X-API-Key` header, `GET /auth/verify` → keyId, unified recall via `POST /context-inject` with `user_tag` + `project_tag`.
