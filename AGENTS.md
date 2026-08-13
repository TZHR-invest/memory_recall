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

- `opencode/` — TypeScript/Bun plugin (`memory-recall-opencode`, main entry `dist/index.js`). Build with `bun run build` (NOT tsc — tsconfig has `noEmit: true`); install via `bunx memory-recall-opencode install`. Config written to `~/.config/opencode/memory-recall.jsonc`. **Dependency contract**: runtime imports are `@opencode-ai/plugin` (tool registration + `tool.schema.*` for args — never import `zod` directly, it causes dual-instance crashes) and `@opencode-ai/sdk` (type-only); build externalizes both (`--external`) per opencode official docs — do not bundle them or `zod`. `install --dev` (symlink mode) is deprecated and prints a notice only. npm 插件缓存：opencode 自 v1.4.3 起用 `@npmcli/arborist` 安装到 `~/.cache/opencode/packages/<pkg>@latest/`（官方文档 "node_modules/" 表述滞后，描述 v1.4.3 前旧机制，以源码为准；详见 README → 依赖架构）。See `apps/api/src/plugins/opencode/README.md` → 依赖架构.
- `deepseek-tui/`, `hermes/` — standalone Python MCP stdio servers (`python server.py`), configured via `MEMORY_RECALL_*` env vars. `deepseek-tui`'s documented `install.sh` is gitignored/missing — only manual setup works.
- Tag convention: `userTag = keyId` (cross-project), `projectTag = {keyId}_project-<dirName>`. Backend contract: `X-API-Key` header, `GET /auth/verify` → keyId, unified recall via `POST /context-inject` with `user_tag` + `project_tag`.

## 文档沉淀规范（Docs-as-Records，强制）

**所有工作信息必须落成文档，禁止只存在于对话里。** 完整规范见
[`docs/DOCUMENTATION_GUIDE.md`](docs/DOCUMENTATION_GUIDE.md)，下面是要点：

- 目录分工：
  - `docs/` 根目录 — 当前为真的知识（PROJECT_PLAN / ENTITY_DESIGN / ISSUES / DEPLOYMENT / MEMORY_FLOW）；
  - `docs/STATUS.md` — 实时任务状态（活跃工作/下一步/等待项），每次任务收尾必须更新，历史进 notes；
  - `docs/decisions/` — 决策记录 ADR：**只记已明确的取舍**，无 Proposed/Rejected；
    讨论过程在 notes，结论明确后落 ADR；编号递增，Accepted 后决策正文冻结，
    只能新 ADR 取代；新 ADR 写 `Supersedes: 00XX`，旧 ADR 同步标 `Superseded by: 00XX`；
    被否决但值得记录的方案写 Accepted 的"不采用 X" ADR，否则留在 notes；
  - `docs/notes/` — 讨论/调研/方向探讨：大型主题用 `YYYY-MM-DD-短slug.md` 独立文件，
    细碎信息按日汇总到 `YYYY-MM-DD-note.md`（骨架：背景/要点/结论/下一步/未决）；
  - `docs/designs/` — 产品设计（版本化，同主题只能有一个生效版本）；
  - `docs/ISSUES.md` — 问题索引；详情在 `docs/issues/MR-xxx.md`（每问题一文件）；
    修复后从 open 表移入已解决表并记录版本，**详情文件保留并标已解决**（不删除问题史）；
  - `docs/archive/` — 过时内容（git mv 归档并登记原因，不直接删除）。
- 文档头部必须有：状态（ACTIVE/ACCEPTED/SUPERSEDED/ARCHIVED）、版本、最后更新日期。
- 每个任务按此 checklist 收尾：新讨论→notes；新决策→ADR；新设计/变更→designs 或更新生效文档；
  新问题→ISSUES.md；更新 `docs/STATUS.md`（下一步不该只存在于对话里）；修改后更新 `docs/README.md` 索引；
  commit 时文档与代码一起提交（`docs:` 前缀）。
- 注意：opencode 插件默认只导入 `docs/*.md` 根目录一层作为知识；decisions/notes/designs/archive
  不进注入上下文，需要时通过搜索 API 获取。这是有意的边界，不要靠改插件绕过。
- 相关既有问题：`docs/ISSUES.md`（MR-xxx）；任务开始前先查它，避免重复劳动。

## 外部调研（Human-in-the-Loop Research）

当官方源码/文档难以覆盖、需要社区与平台信息差、或需要多模型交叉验证时，使用"外部调研"工作流：
核心原则：**问得少、问得准、按回答反馈式追问**，不预设长清单全平台轰炸。

### 三阶段漏斗

1. **定向轮**：按"问题分类 + 平台画像"分配，每平台只给 1-3 题，并按平台打包
   （每个平台一个可整体复制的文本块）；
2. **交叉/追问轮**：只对回答冲突或证据不足的问题追问，且只发给相关平台（通常 1-4 条）；
3. **收敛轮**：分歧点回项目内源码/官方文档验证，不再增加平台。

### 文件结构（一个调研一个文件夹）

新建 `docs/notes/research/YYYY-MM-DD-<slug>/`：

- `README.md` — 调研卡（目标/状态/结论入口/文件索引）；
- `01-goals.md` — 背景与已知源码事实；
- `NN-round-NN-prompts.md` — 每轮提示词（含平台分配，按平台打包）；
- `NN-round-NN-answers-<platform>.md` — 每平台回答原文（一次粘贴一个文件）；
- `NN-round-NN-conclusions.md` — 每轮统一理解；
- `99-final-conclusions.md` — 最终统一理解与实施映射。

平台名小写：`chatgpt/claude/gemini/grok/doubao`。

### 问题分类（入清单前先回答"这个答案会改变决策吗？"）

- **S（源码可验证）**：字段、默认值、触发条件等 → 1 个平台 sanity check 即可，不铺开；
- **C（信息差/社区）**：生态共存、历史 issue、最佳实践等 → 2-3 个不同数据源平台；
- **D（决策无关）**：不改变决策 → 直接砍掉。

### 平台画像（2026-08 观察，按需更新）

| 平台 | 特点 | 适用 |
|------|------|------|
| ChatGPT | 源码级结论可靠，web/issue 检索强 | 源码核对、社区历史 |
| Grok | 源码级结论可靠，X/社区信号强 | 生态共存、社区实践 |
| Claude | 诚实、会明确说"不知道"，但可能漏检新 API | 源码/公式推理、追问轮 |
| Gemini | 高层结论可参考，具体字段容易编造 | 仅作广谱参考，字段细节一律源码复核 |
| doubao | 同 Gemini，另有中文社区视角 | 中文生态补充，字段细节一律源码复核 |

### 批量打包（执行格式）

- 提示词文件按平台分节，每节一个整体可复制的文本块（含分配给该平台的所有题目）；
- 人类每平台**粘贴一次、回填一次**（写入对应 `answers-<platform>.md`）；
- Agent 负责拆解回答并按题归档；
- 原始回答保留，不二次概括。

### 提问纪律

- 每条提示词要求回答者**区分"源码事实 / 推断 / 不知道"**，不确定就明确说不知道；
- 涉及字段、行号、默认值，必须给源码路径或链接，并注明版本/分支；
- 若与官方文档不一致，说明依据。

### 统一理解与停止条件

- 读全部回答：一致 → 共同结论；冲突 → 标出冲突 + 证据倾向；缺失 → 标待补；
- **停止条件**：关键事实达到"源码 + ≥2 平台一致"即收敛；冲突项只在追问轮处理，不无限加平台；
- 可多轮：每轮只追加下一轮提示词，直到收敛。

### 纪律

- 外部回答是素材不是事实；进入 ADR / `docs/` 根目录文档前，必须以项目内源码、
  官方文档或可执行验证确认；
- 原始回答与链接保留在调研文档中，不删除；
- 该流程的产出仍是 `docs/notes/` 过程记录，方向性取舍按文档规范另落 ADR。
