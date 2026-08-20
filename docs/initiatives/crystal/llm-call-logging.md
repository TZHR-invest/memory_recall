# LLM 调用链存储（llm-call-log）开发设计 v1

> 状态: 草稿（待实现） · 系统: crystal · 版本: v1 · 最后更新: 2026-08-19
> 关联: [trace-id 日志计划](../../notes/2026-08-19-llm-trace-id-logging-plan.md)（已实现，调用链标识）·
> [对账技术设计](reconciliation-design.md)（写路径 LLM 调用）· [workbench](workbench.md)（查询面）·
> [api-contract](api-contract.md)（/api/v2 debug 桩）· [entity-attributes](entity-attributes.md)（schema 惯例）
> 定位: 本文定 **crystal 全生命周期 LLM 调用（输入/输出）的临时存储 + 定时清理 + workbench 查询**。
> 不做: v5 旧链路 LLM 调用的功能设计（同 client 层，顺带记录，见 §1.2 范围决策）。

## 0. 一句话

**LLM 调用链 trace-id 只解决"日志里能串联"，不解决"输入/输出原文可回看"——本设计新增一张
`llm_call_logs` 表，在 `llm/client.py` 统一记录每次 crystal 生命周期的 LLM 调用
（prompt 截断 5k / 输出截断 50k，用户拍板"不用抠门"），定时清理过期行（默认保留 7 天），
workbench 按 trace_id / evidence 查询调用链。**

## 1. 背景与动机

### 1.1 为什么做

- trace-id 日志系统（已实现）把一次对账的所有日志串成一条 `[trace_id=ev_xxx]`，但**日志里只有摘要**
  （`content_len=330 reasoning_len=569`），没有 prompt 原文、没有完整输出；
- 排查问题（如"拆条返回空""碰撞误判 CONFLICT""JSON 畸形"）时，**看不到 LLM 实际收到了什么、输出了什么**，
  只能靠复现 + 猜；LLM 调用有随机性，复现不一定重现；
- 用户需求：LLM 输入/输出**临时储存**（定时删除过期数据），且 **workbench 迟早要做这个查询**——本次一起设计。

### 1.2 范围决策（用户拍板）

| 做 | 不做 |
|----|------|
| crystal 全生命周期 LLM 调用**全覆盖**（不只对账：拆条/碰撞/claim_kind + 未来新增调用点） | v5 旧链路 LLM 调用的**功能设计**（实体提取/蒸馏等） |
| 输入/输出落库（prompt 截断 **5k** / response 截断 **50k**，用户拍板不抠门） | 长期大规模下的**采样存储**（用户明确：上线大量使用后再考虑，本文 §7 记录为演进方向） |
| 定时清理过期数据（对齐 `TRACE_RETENTION_DAYS` 惯例） | 永久存储 / 审计用途（临时排查定位，非不可再生资产） |
| workbench 查询调用链（debug 桩真实化 + workbench 详情联动） | 全系统分布式追踪 / 日志采集平台 |

**技术注记（实现时定）**：记录点统一放 `llm/client.py`（唯一 LLM 入口，未来 crystal 新增调用自动覆盖）。
v5 调用也走同一 client——默认**顺带记录**（成本≈0、排查受益；如用户要求严格隔离，
可加 `caller` 参数门控，v5 调用点不传 → 不落，文档给出开关）。**本次文档与查询面聚焦 crystal。**

## 2. crystal 全生命周期 LLM 调用点盘点（现状）

crystal 对象生命周期：**evidence 落库 → worker 对账（拆条 → 碰撞 → 写）→ 召回查询 → workbench 裁决 → 迁移/重建**。
LLM（对话式）调用点当前全部集中在对账阶段（`reconcile_service.py`，均走 `llm.aextract_json`）：

| # | 调用点 | 函数 | 阶段 | 输入特征 | 输出特征 |
|---|--------|------|------|----------|----------|
| 1 | 拆条 LLM ① | `_decompose_single_call_once` | 对账-拆条 | evidence 原文（≤1500 字双上限）+ 拆条规则 prompt | N 条原子 claim JSON（可大：长文本拆出 15 条） |
| 2 | 碰撞判定（单条，旧路径） | `_llm_collision_judge` | 对账-碰撞 | evidence + 候选 claims | relations JSON |
| 3 | 碰撞判定批处理 LLM ② | `_llm_collision_judge_batch` | 对账-碰撞 | N 条新 claim + 各自候选（可大） | judgments JSON |
| 4 | claim_kind 判定 + statement 提炼 | `_llm_claim_kind_and_statement` | 对账-冲突路径 | evidence 原文 | {claim_kind, statement} JSON |

**其他阶段确认不走 LLM**（调研结论）：
- evidence 落库（`evidence.py`）：仅 embedding（`reconcile_service._embed`），无对话式 LLM；
- 召回查询（`recall_service.py`）：仅 query embedding，无对话式 LLM；
- workbench 裁决（`workbench.py`）：correct 特权 supersede **明确跳过 LLM**（§3.1 特权路径）、confirm/forget 纯 SQL；
- promote-scope：纯 SQL；
- 迁移/重建脚本（`migrate_memories.py` / `rebuild_claims.py`）：落库后触发同一对账 worker，LLM 调用同上表。

**embedding 调用（向量）**：`recall_service`（query）+ `reconcile_service._embed`（evidence）。
**不在本设计记录范围**（文本→向量，回看价值低、体积大）；如需记录可在 §7 演进中加 `embedding_logs` 表。

**未来 crystal 可能新增的 LLM 调用点**（文档保证"全覆盖"的机制）：workbench 裁决辅助（promote 理由生成）、
评估集 ingest 适配、P1/P2 采集档（outcome_trace/document 摘要）。因记录点在 client 层统一，
**新增调用点自动落库，无需改本设计**。

## 3. 表设计（schema 增量）

### 3.1 建表（v5 段通用表，与 recall_traces 同层）

```sql
CREATE TABLE IF NOT EXISTS llm_call_logs (
    id                BIGSERIAL PRIMARY KEY,
    trace_id          TEXT,                          -- trace-id 日志系统（对账链路 ev_xxx）；无则 NULL
    caller            TEXT,                          -- 调用方标识：crystal:reconcile:decompose 等（见 §3.3）
    provider          TEXT NOT NULL,                 -- deepseek / volcengine
    model             TEXT NOT NULL,
    method            TEXT NOT NULL,                 -- aextract_json / achat / chat / achat_with_system ...
    temperature       DOUBLE PRECISION,
    max_tokens        INT,
    reasoning_effort  TEXT,                          -- deepseek 思考档位（low/medium/high，可 NULL）
    prompt_len        INT,                           -- 输入字符数（截断前）
    prompt            TEXT,                          -- 输入（截断到 LLM_LOG_PROMPT_MAX_CHARS，默认 5000）
    response_len      INT,                           -- 输出字符数（截断前）
    response          TEXT,                          -- 输出（截断到 LLM_LOG_RESPONSE_MAX_CHARS，默认 50000）
    reasoning_len     INT,                           -- 思考链字符数（deepseek 特有，排查"思考吃光预算"关键）
    usage_total       INT,                           -- 本次调用 token 总用量
    usage_reasoning   INT,                           -- 其中思考链 token
    ok                BOOLEAN,                       -- true=有内容 / false=空或异常
    elapsed_ms        INT,                           -- 耗时（毫秒）
    error             TEXT,                          -- 异常信息（ok=false 时）
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_llm_call_logs_trace   ON llm_call_logs (trace_id);
CREATE INDEX IF NOT EXISTS idx_llm_call_logs_created ON llm_call_logs (created_at);
```

### 3.2 截断策略（用户拍板：不抠门）

| 字段 | 上限 | 依据 |
|------|------|------|
| `prompt` | **5000 字符**（`LLM_LOG_PROMPT_MAX_CHARS`） | 输入含规则 prompt + evidence 原文，5k 足够定位"哪个调用、喂了什么" |
| `response` | **50000 字符**（`LLM_LOG_RESPONSE_MAX_CHARS`） | 输出是排查重点（JSON 结构/返回空/畸形），50k 容纳 15 条拆条的大输出；再大截断 |
| 截断标记 | 截断时尾部追加 `…[truncated]` | 查询时一眼看出不完整 |

> 用户明确：**"截断 5k 或者 50k 吧，不用那么小气"**——单行上限放宽，靠 §5 的定时清理控制总量，
> 而非靠小截断省空间。长期大量上线后演进为采样（§7）。

### 3.3 caller 标识规范（查询分组/过滤依据）

格式 `crystal:<阶段>:<子步骤>`，取值：

| caller | 对应调用点 |
|--------|-----------|
| `crystal:reconcile:decompose` | 拆条 LLM ① |
| `crystal:reconcile:collision` | 碰撞判定（单条旧路径） |
| `crystal:reconcile:collision_batch` | 碰撞判定批处理 LLM ② |
| `crystal:reconcile:claim_kind` | claim_kind 判定 + statement 提炼 |
| `crystal:migrate:*` / `crystal:rebuild:*` | 迁移/重建触发的对账（沿用上述 caller，trace_id 区分） |

未来新增：`crystal:workbench:*`（裁决辅助）、`crystal:eval:*`（评估 ingest）等，**按需扩展，格式不变**。

### 3.4 配置项（config.py 增量）

```python
LLM_LOG_ENABLED: bool = True          # 总开关（量大时可一键关）
LLM_LOG_PROMPT_MAX_CHARS: int = 5000
LLM_LOG_RESPONSE_MAX_CHARS: int = 50000
LLM_LOG_RETENTION_DAYS: int = 7       # 对齐 TRACE_RETENTION_DAYS
```

## 4. 记录点设计（llm/client.py 统一落库）

### 4.1 落库位置与方式

- **位置**：`llm/client.py` 的 `chat`/`achat`（`aextract_json`/`achat_with_system` 都汇聚到这里），
  在已有请求/响应日志（trace-id 已实现）处**顺手落库**；
- **方式**：**fire-and-forget**——`asyncio.create_task` 后台写，**失败仅 warning 日志，绝不影响主流程**
  （与 `cache_manager` 同层语义；LLM 调用是主链路，落库是旁路可观测）；
- **同步 `chat`**：同步路径用 `asyncio.get_event_loop().create_task` 或直接同步 `db.execute`（await 不可用时降级），
  实现时定（同步调用点较少，crystal 全走 `aextract_json` = 异步）。

### 4.2 记录的字段来源（复用 trace-id 已有的 `_response_summary` 素材）

- `trace_id`：`get_trace_id()`（无则 NULL）；
- `prompt_len`/`response_len`/`reasoning_len`/`usage_*`/`elapsed_ms`/`ok`：已有 `_response_summary` 的同源数据，落库复用；
- `prompt`/`response` 原文：截断后写入（§3.2）；
- `caller`：**通过 kwargs 传递**（crystal 调用点 `aextract_json(..., caller="crystal:reconcile:decompose")`），
  client 默认 `caller=None` → 顺带记录（v5 调用也落，无 caller 标识）。

### 4.3 开关与异常

- `LLM_LOG_ENABLED=False` 时不落库（client 层短路）；
- 落库异常：`logger.warning("llm call log 落库失败: ...")` 后继续——**LLM 调用结果不受影响**。

## 5. 定时清理（复用 scheduler）

- 新增 `llm_log_cleanup_task`（`src/background/scheduler.py`，仿 `trace_cleanup_task`）：
  ```python
  async def llm_log_cleanup_task() -> None:
      deleted = await db.execute(
          "DELETE FROM llm_call_logs WHERE created_at < NOW() - ($1::int || ' days')::interval",
          settings.LLM_LOG_RETENTION_DAYS,
      )
      print(f"LLM call log cleanup: deleted {deleted} records")
  ```
- 注册：`scheduler.register_task(name="llm_log_cleanup", interval_seconds=3600, task_func=llm_log_cleanup_task)`
  （每小时一次，与 trace_cleanup 同频）；
- 清理只按 `created_at`，**不按 trace 级联**（trace 可能跨多天，逐行过期即可）。

## 6. workbench 查询（用户要求一起做）

### 6.1 API（真实化一个 debug 桩）

`GET /api/v2/debug/llm-logs`（admin 校验，api-contract §2.5 debug 桩真实化）：

| 参数 | 说明 |
|------|------|
| `trace_id` | 按 trace 查整条调用链（对账一次 = 一次 trace = 若干 LLM 调用） |
| `evidence_id` | 按 evidence 查（反查 trace_id 再查日志，或 JOIN） |
| `caller` | 按调用点过滤（如只看拆条） |
| `limit`/`cursor` | 游标分页（对齐 G4 惯例） |

响应（统一信封，api-contract §3）：`{data: {items: [...], next_cursor}}`，每条含 §3.1 全字段（prompt/response 截断后）。

### 6.2 workbench 页面联动

- **对账详情/召回复盘**：展示该 evidence 的 LLM 调用链（trace_id → 各步 prompt 摘要 + response 可展开）；
- **裁决面**：correct 触发 supersede 后，可查该 evidence 的调用链核对（特权路径无 LLM，但 evidence 本身的拆条链可查）；
- 网络视图（G5）暂不联动（图是 claim×evidence，LLM 调用链属诊断面）。

### 6.3 权限

- `GET /api/v2/debug/llm-logs`：**admin only**（LLM 输入/输出含用户对话原文，属敏感诊断数据；
  api-contract §2.5 debug 段现有 admin 校验直接沿用）；
- workbench 页面内嵌时按同一 admin key 访问。

## 7. 演进方向（长期，本次不做）

- **采样存储**（用户明确：上线大量使用后考虑）——`LLM_LOG_SAMPLE_RATE`（0~1），
  命中率采样（对齐 `TRACE_SAMPLE_RATE` 惯例）；trace 级采样（整条 trace 记/不记）优先于单行采样；
- **embedding 调用日志**（`embedding_logs` 表）——文本→向量回看价值低，量大，默认不做；
- **存储分层**：prompt/response 大字段可迁外部对象存储（保留指针），表只留元数据；
- **LLM 日志查询 API 分页/筛选增强**（按时间范围/模型/耗时排序）。

## 8. 验收标准

- [ ] 一次 crystal 对账（含拆条/碰撞），`llm_call_logs` 落库该次全部 LLM 调用（≥2 行：拆条 + 碰撞批处理），
      `trace_id` 一致、`caller` 正确、prompt/response 截断合规（>5k/>50k 截断 + `[truncated]` 标记）；
- [ ] `GET /api/v2/debug/llm-logs?trace_id=ev_xxx`（admin）返回该 trace 完整调用链，字段齐全；
- [ ] workbench 页面可查 evidence 的 LLM 调用链（对账详情联动）；
- [ ] 定时清理生效：插入过期行（created_at 手动改旧）→ 跑 cleanup → 删除；
- [ ] 落库失败不影响主流程（mock db 异常 → 对账照常 done）；
- [ ] crystal 测试全绿 + v5 回归与基线一致（零新增失败）。

## 9. 实施步骤（按此推进）

1. `schema.sql` 加 `llm_call_logs` 表 + 索引（v5 段，与 recall_traces 同层）+ `init_db.py` 增量段
   （或 `init_crystal_db.py`，实现时按"已建库增量"惯例定）；
2. `config.py` 加 §3.4 四项配置；
3. `llm/client.py`：`chat`/`achat` 落库（fire-and-forget + 截断 + caller 透传，复用 trace-id 素材）；
4. crystal 4 个调用点传 `caller`（§3.3 表）；
5. `scheduler.py` 注册 `llm_log_cleanup`（§5）；
6. `debug` 桩真实化 `GET /api/v2/debug/llm-logs`（§6.1，admin + 游标分页）；
7. workbench 页面对账详情联动（§6.2）；
8. 测试（单元：截断/清理/落库短路；集成：对账落库 + API 查询 + 权限）+ 真实库 E2E；
9. 文档收尾（本设计状态 → 已实现，STATUS/CHANGELOG 更新）。

## 10. 不做 / 推后

- v5 旧链路 LLM 调用的功能设计（顺带记录，无 caller 标识；需要时 §1.2 开关门控）；
- embedding 调用日志（§7）；
- 采样存储（§7，等大量上线）；
- LLM 日志审计/永久留存（临时排查定位）。

*状态: 草稿（待实现） · 日期: 2026-08-19*
