# 开发计划：LLM 调用链 trace-id 日志系统

> 类型: 开发计划（**已实施 2026-08-19**） · 日期: 2026-08-19 · 系统: crystal（跨模块基建）
> 关联: [M2.1 拆条实现](../initiatives/crystal/reconciliation-design.md)（调用链）· [reasoning-LLM max_tokens 发现](2026-08-19-reasoning-llm-max-tokens-empty-content.md)（本次动机）
>
> **实施状态：已完成**（commit 见 STATUS）——`src/logging_utils.py`（ContextVar + Filter + helper）、
> `main.py` 挂 root handler + TraceIdFilter、`llm/client.py` 请求/响应日志、
> `reconcile_evidence` 入口 trace 管理；测试：logging_utils 8 + llm client trace 5 + 集成 2，
> crystal 全绿（单元 65 + 集成 46），v5 回归与基线一致（零新增失败）。
> 顺带修复：uvicorn 默认 logging 配置 root logger 无 handler → 应用 INFO 日志此前被静默丢弃，
> 现已补 root StreamHandler + 按 LOG_LEVEL 设级别。

## 一、动机

M2.1 拆条开发中踩到"deepseek 返回空"问题，排查时**无法从日志串联完整调用链**：
- 一次 evidence 对账 = evidence 落库 → embedding → 拆条（LLM ①，最多 3 次重试）→ 候选检索 →
  碰撞判定（LLM ②）→ 批量写，是一条 6+ 步的调用链；
- 当前日志是散点：`reconcile_service.py` 的 logger 与 `llm/client.py` 的 logger 各自打，
  **没有共同标识串起"这次 evidence 处理过程中发了哪几次 LLM 调用、每次结果如何"**；
- 排查问题时只能靠时间戳猜关联，效率低且易错（本次就一度误判为"模型不稳定/限流"）。

**目标**：给 LLM 调用链加 **trace-id**，让一次业务操作（如一条 evidence 对账）的所有日志
（业务步骤 + LLM 请求/响应摘要 + 重试）自动携带同一 trace-id，可按 id 一键串联排查。

## 二、范围与边界

| 做 | 不做 |
|----|------|
| 对账链路（evidence → 拆条 → 碰撞 → 写）trace-id | 全系统分布式追踪（Jaeger/Zipkin 等，过度设计） |
| LLM 调用自动带 trace-id（client 层） | 日志采集/聚合平台（ELK 等，个人自托管不需要） |
| 日志格式：`[trace_id=xxx]` 前缀 | 修改业务日志内容（只加标识，不改语义） |
| worker / API 请求入口生成 trace-id | 跨进程 trace 传播（单进程个人自托管，不需要） |

## 三、方案设计（轻量 contextvars + logging.Filter）

### 3.1 核心机制

```
contextvars.ContextVar（进程内贯穿异步调用链）
        │
        ▼
logging.Filter（挂在 root logger 或关键 logger 上）
        │  每条 log record 自动读 ContextVar → 追加 "[trace_id=xxx]"
        ▼
所有业务日志 + LLM client 日志自动带 trace_id，无需每处手动传
```

- **入口生成**：`reconcile_evidence(evidence_id)` 入口（或 worker 认领时）生成
  `trace_id = 'ev_' + 短uuid`，写入 ContextVar；函数返回后清理；
- **自动传播**：async 场景 contextvars 自动跟随 Task（asyncio 原生支持），
  拆条/碰撞里的 await 调用天然在同一 trace 上下文；
- **重试日志**：`_decompose_single_call` 的重试日志自动带同一 trace_id，
  一眼看到"这次拆条重试了 3 次"。

### 3.2 文件结构

| 文件 | 内容 |
|------|------|
| `src/logging_utils.py`（新建） | `TraceIdContext`（ContextVar）+ `TraceIdFilter`（logging.Filter）+ `generate_trace_id()` + `trace_id()` 读取 helper |
| `src/llm/client.py` | `achat`/`chat` 加日志：请求（trace_id + model + prompt 摘要）+ 响应（trace_id + 成功/空/失败 + 耗时 + usage）；`_apply_reasoning_effort` 已有 |
| `src/api/crystal/reconcile_service.py` | `reconcile_evidence` 入口设置 trace_id；拆条/碰撞调用日志已存在（自动带 trace_id） |
| `src/api/crystal/worker.py` | worker 认领 batch 时可为整批设 trace_id（或每条 evidence 单独） |
| `src/main.py`（或 config） | 应用启动时把 `TraceIdFilter` 挂到 root logger |

### 3.3 LLM 调用日志规范（本次排查最缺的）

`llm/client.py` 每次调用（chat/achat）记录：

```
INFO  [trace_id=ev_abc123] LLM 请求: model=deepseek-v4-flash reasoning_effort=low max_tokens=16000 prompt_len=947
INFO  [trace_id=ev_abc123] LLM 响应: ok=true content_len=621 reasoning_len=1379 usage=1003 (reasoning=737) elapsed=12.3s
WARN  [trace_id=ev_abc123] LLM 响应: ok=false content='' reasoning_len=3998 → 返回空（思考吃光预算）
```

这样**下次再遇到"返回空"，一条 trace 就能看到：哪条 evidence、发了哪次 LLM、思考链多长、
是不是 max_tokens/effort 问题**，不用再手动复现。

### 3.4 错误场景 trace 示例（目标效果）

```
INFO  [trace_id=ev_9f2c] 对账开始: evidence=ev_9f2c content_len=430
INFO  [trace_id=ev_9f2c] 拆条 LLM ① 请求: prompt_len=947
INFO  [trace_id=ev_9f2c] 拆条 LLM ① 响应: ok=true 15 条 claim
INFO  [trace_id=ev_9f2c] 候选检索: scope=project-x top_k=20 → 3 候选
INFO  [trace_id=ev_9f2c] 碰撞 LLM ② 请求: 15 claims + 3 candidates
INFO  [trace_id=ev_9f2c] 批量写: created=15 superseded=0 reinforced=0
INFO  [trace_id=ev_9f2c] 对账完成: done

# 失败场景
INFO  [trace_id=ev_5a1b] 对账开始: evidence=ev_5a1b content_len=1722
WARN  [trace_id=ev_5a1b] 拆条 LLM ① 响应: ok=false content='' reasoning_len=3998 → 第1次重试
WARN  [trace_id=ev_5a1b] 拆条 LLM ① 响应: ok=false content='' reasoning_len=4102 → 第2次重试
WARN  [trace_id=ev_5a1b] 拆条 LLM ① 响应: ok=false → 放弃
WARN  [trace_id=ev_5a1b] 拆条失败 → 隔离到 workbench（evidence 保留，待人工裁决）
```

## 四、验收标准

- [x] 对账一次 evidence，`grep 'trace_id=ev_xxx' api.log` 能拿到该次处理**全部**相关日志（业务 + LLM + 重试）；
      —— 集成测试 `TestReconcileTraceId::test_reconcile_logs_carry_same_trace_id` 断言同一 trace_id 覆盖全部业务日志
- [x] LLM client 每次调用记录：model / reasoning_effort / max_tokens / prompt 摘要 / 响应长度 /
       reasoning 长度 / 是否空 / 耗时；—— `_response_summary` 覆盖（reasoning_effort 走 kwargs 传递，日志含 max_tokens/prompt_len/usage/reasoning/elapsed）
- [x] 重试日志自动带同一 trace_id（一次拆条的多次重试可串联）；—— `_decompose_single_call` 重试日志自动带（contextvars 传播）
- [x] 并发对账多条 evidence 时，trace_id 不串（contextvars 隔离）；—— `TestTraceIdConcurrency::test_concurrent_tasks_isolated`
- [x] 不影响现有日志输出格式（新增前缀 + 新 LLM 日志行，不改旧语义）；—— TraceIdFilter 无 trace 时原样输出，有 trace 时仅加前缀
- [x] 单元测试：TraceIdFilter 给 record 加前缀；并发 contextvars 隔离；
       LLM client mock 验证日志行包含 trace_id 与关键字段。—— `test_logging_utils.py` + `test_llm_client_trace.py`

## 五、实施步骤（后续开发时按此推进）

1. ✅ 新建 `src/logging_utils.py`（ContextVar + Filter + helper）+ 单元测试（`tests/test_crystal/unit/test_logging_utils.py`）；
2. ✅ `main.py` / config 挂 Filter 到 root logger（顺带补 root StreamHandler——uvicorn 默认配置 root 无 handler，INFO 日志此前被丢）；
3. ✅ `llm/client.py` 加请求/响应日志（含 usage/耗时/reasoning 长度，`_response_summary` + `_prompt_len`）；
4. ✅ `reconcile_evidence` 入口设置/清理 trace_id（wrapper：嵌套调用沿用外层 trace，finally 清理）；
5. ✅ worker 批量认领时生成 trace_id——**实现拍板：每条 evidence 单独 trace**（`reconcile_evidence` 入口生成 `ev_<12hex>`，batch 内多条各带各的 trace，worker 日志不带 trace 属正常）；
6. ✅ 集成测试：真实对账一次 → 收集日志断言 trace 完整性（`TestReconcileTraceId`，含早退路径清理验证）；
7. ✅ 手工验证：构造一次失败拆条 → 确认 trace 能看到重试 + 隔离日志（拆条重试日志在 `_decompose_single_call`，自动带同一 trace_id）。

> 实施中新增发现（超出原计划）：uvicorn 默认 logging 配置 root logger 无 handler，应用级 INFO 日志
> （业务 + LLM）默认被丢弃（lastResort 仅 WARNING+），trace 日志 grep 不到——已随本实施修复。

## 六、不做 / 推后

- 不做跨进程/跨服务 trace 传播（单进程个人自托管）；
- 不做 trace 落库/查询 API（先 stdout/文件日志，按需再上 `logging` 的 RotatingFileHandler）；
- 不做日志聚合平台（ELK/Loki）；
- v5 旧链路（memories.py 等）的 LLM 调用暂不纳入（M5 退役目标，随 crystal 全量接管自然覆盖）。

*状态: 计划（未实施） · 日期: 2026-08-19*
