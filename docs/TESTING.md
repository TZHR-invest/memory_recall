# Memory Recall 测试指南

> 状态: ACTIVE · 版本: v1.1 · 最后更新: 2026-08-20

`pytest.ini`: `asyncio_mode = auto`、`testpaths = tests`。**没有 `conftest.py`** —— fixture 内联在各文件
（照抄 `test_v2/test_context_inject_api.py` 或 `test_v2/test_chunks_search.py` 的模式）。

## 三层分级

1. **单元（mock，任意环境可跑）** — 大部分 `tests/test_v2/`、全部 `tests/test_opencode/`、`tests/test_api/`、
   `tests/test_crystal/unit/`。
2. **集成（需要运行中的 Postgres + pgvector + schema）** — `tests/test_v2/test_integration.py`、
   `tests/test_v2/test_performance.py`、`tests/test_document_deduplication.py`、`tests/test_source_deduplication.py`、
   `tests/test_crystal/integration/`、`tests/test_stats_tz_integration.py`。
3. **火山引擎实跑脚本（带真实 LLM/embedding 调用，属于集成/验收测试而非单元测试）** —
   `tests/test_llm_service.py`、`tests/test_embedding.py`、`tests/test_function_calling.py`。
   pytest 会收集它们（无 `VOLC_API_KEY` 即失败），**必须始终 `--ignore`**。

> 结论：**带 LLM 真实调用的不算单元测试，属于集成/验收测试**，不应进 CI 的常规单元回归；
> CI 需要的是 mock LLM/embedding 的隔离测试（如 `tests/test_crystal/` 用 `mock_llm`/`mock_embedding`
> fixture 替身）。真实 LLM 链路验证放本地手动跑（`venv/bin/python tests/test_llm_service.py`）。

## 环境注意点

- **没有 `TEST_DATABASE_URL`**：`src/database.py` 只通过 `DATABASE_HOST/PORT/NAME/USER/PASSWORD` 连库
  （`DATABASE_URL` 在 config 里声明但从不解析）。指向临时库用覆盖这些变量，如 `DATABASE_NAME=memory_recall_test`。
- **无 `VOLC_API_KEY` 时 app 必须能 import**：`RelationService`/`MemoryStore`/`DocumentStore` 的
  embedding client 已惰性初始化（与 `DocumentProcessor`/`LLMEntityExtractor` 同模式）——无 key 时
  `embedding_client=None`，调用侧优雅降级。不要再把 `get_embedding_client()` 放回 `__init__` 顶层。
- `test_document_deduplication.py` / `test_source_deduplication.py` **不能一起跑**（会互相
  失败 18/26）：根因是全局 `db` 单例 asyncpg 连接跨 pytest-asyncio module loop 冲突
  （"attached to a different loop"）。不是顺序问题——装 `pytest-order` 无法解决，
  改 `asyncio_default_test_loop_scope=session` 也会变成 "Event loop is closed"。
  正确做法：**两个文件分开单独跑**（各自全绿）。彻底修复需重构测试连接管理（每文件
  独立连接或 session fixture 统一管理），属测试基建改造，未排期。
- 同源 loop 冲突也发生在 `tests/test_crystal/integration/` 与 `tests/test_stats_tz_integration.py`
  一起跑时：crystal 套件先在模块 loop 上建全局池，tz 测试在另一模块 loop 复用会报
  "attached to a different loop"。tz 测试已改为先 `db.disconnect()` 再 `db.connect()` 规避。
- 集成测试不清理自己的测试数据（容器如 `test_integration_*`、`test_perf_*`）。
- **`pytest.ini` 的 `asyncio_default_test_loop_scope = module` 不能删**：pytest-asyncio 1.x 默认测试函数用
  函数级 loop，而异步 fixture/db 用模块级 loop，asyncpg 连接会报 "attached to a different loop"。
  删掉后整个集成套件挂掉（0/7）。

## 常用命令

```bash
cd apps/api
# 快速单元循环（无 DB、无 API key）——默认迭代用
venv/bin/python -m pytest tests -q -x \
  --ignore=tests/test_llm_service.py --ignore=tests/test_embedding.py \
  --ignore=tests/test_function_calling.py --ignore=tests/test_document_deduplication.py \
  --ignore=tests/test_source_deduplication.py --ignore=tests/test_v2/test_integration.py \
  --ignore=tests/test_v2/test_performance.py

# 单测 / 单文件
venv/bin/python -m pytest tests/test_v2/test_integration.py -k test_full_memory_lifecycle -x -v
venv/bin/python -m pytest tests/test_v2/test_memory_store.py -x -v
```

*状态: ACTIVE · 版本: v1.0 · 最后更新: 2026-08-13*
