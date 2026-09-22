# 异步处理完成信号（`metadata._status` 终态）

> 状态: DONE · 日期: 2026-09-22 · 影响面: 所有 `async_process=true` 的写入（dsh/codex/hermes/deepseek-tui 插件默认走这条）+ stats/dashboard 可观测性

## 背景：信号存在但不可区分、也没有时间

原实现（2026-09-22 之前）的 `_status` 终态并不统一：

| 场景 | 旧终态 |
|---|---|
| 异步写入成功 | **pop 掉（无该键）** |
| 异步写入失败 | `failed` |
| 捕获/重复记忆被合并 | pop 掉（注释：防 dashboard 误报"处理中"） |
| 捕获去重被物理丢弃 | 整行 DELETE |
| 显式修订 update | `processing` → `completed`（**唯一一个已落终态的分支，且有测试**） |
| 同步写入 | 从来没有该键 |

后果两条：
1. **"没有 `_status`" 同时意味着"异步已完成"和"本来就是同步写的"** —— 库里不可区分，
   `GET /memories/{id}` 虽然返回 metadata，但读到的信息是二义的；
2. **没有处理时间戳**，dashboard 的"处理中 N"分不清"在跑"和"卡死"，也没有后台耗时的度量。

## 改动（本次）

1. **成功收尾写终态**：`process_memory_async` 结尾把 pop 改为
   `_status=completed` + `_processed_at`（ISO）。选 `completed` 而不是 `done`：它是 update 分支
   已在用、且**已有测试断言**的词，换成 `done` 只会徒增改动面（docstring 里的 `done` 是笔误，已修）。
2. **失败分支**同样补 `_processed_at`（"失败过"与"还卡着"要能分开）。
3. **合并分支**（捕获/重复记忆被并入既有记忆）由 pop 改为 `completed` + `_processed_at`：
   它同样是终态，本行不会再做提取。
4. **卡死判定上线**：新增 `config.STUCK_PROCESSING_MINUTES`（默认 10 分钟），
   `stats/overview` 的 `anomalies` 增加 **`processing_stuck`** = `_status=processing` 且
   `created_at` 过期。dashboard"处理异常"卡片改为按 `failed + processing_stuck` 标红，
   "处理中"本身不再算异常（在跑是正常态）。
5. **顺手修掉一个既有 bug（实测发现）**：收尾写回的 `fresh_meta` 来自**重新读库的行**，
   而 `_pending_*` 只在函数开头从内存副本 pop —— 旧写法只"不新增"、**从未删除**，
   实测近 3 天 **340/340** 条已完成记忆仍残留 `_pending_extract_entities` 等键（而注释声称
   "移除 pending 标记"）。现在收尾时显式过滤 `_pending_*`。

## 存量清理（2026-09-22 同日执行）

把范围从"近 3 天"放宽到全库后，实际残留比最初看到的大一个量级：

| 项 | 数 |
|---|---|
| 带顶层 `_pending_*` 的行 | **6590**（6587 行无 `_status`＝已处理完，3 行 `completed`） |
| 残留键总数 | **32,945**（5 类键 × 行数） |
| 其中处于 `processing`（在飞） | **0** |

**判据核查**（防误伤）：`_pending_*` 的唯一读取者是 `process_memory_async` 开头（把键当后台任务入参）；
插件侧零引用；`document_store` 用的是另一套同名前缀键、不同表。⇒ 对"已处理完"的行，这些键是纯惰性残留。

**决定：清理**。理由不是"占空间"，而是**它会误导排查**：审计"这条记忆为什么没实体"时看到
`_pending_extract_entities: true` 会误以为提取还没做（我自己在写测试时就被它带偏过一次）。

**执行**：
1. 备份（可回滚）：`apps/api/backups/pending-keys-rollback-20260922.json`（5.5 MB，6590 行的 id+完整
   旧 metadata；该目录已在 `.gitignore` 里，含敏感数据不入库）；
2. `UPDATE` 用 `jsonb_object_agg(...) FILTER (WHERE left(key,9) <> '_pending_')` 重写 metadata，
   **带在飞保护**（`_status='processing'` 的行不动 —— 它们的 `_pending_*` 是正在跑的任务入参）；
   **不动 `updated_at`**（少一个副作用面）；
3. 结果：`pending_keys 32,945 → 0`，记忆总数 8948 不变，抽样行 `type`/`entities`/`profile_worthy` 均在。

**顺带堵住"再长出来"的源头**：`create()` 里加了剥离——调用方（尤其 `create_update_version`
整份复制旧版本 metadata）带进来的 `_pending_*` 一律先删掉，再由 async 分支写入本次任务真正需要的键。
那 3 行 `completed` 就是这么来的（同步/更新路径不覆盖这些键，于是永久继承）。新增回归测试
`test_create_strips_inherited_pending_markers`。

## 验证

**单元**：`tests/test_v2/test_memory_store.py` 新增 3 个用例（成功写 completed+processed_at 且
pending 清空 / 失败写 failed+processed_at / 合并写 completed+processed_at）。
全套快跑档 `6 failed, 477 passed, 15 skipped, 38 errors` —— 失败与错误数与改动前**逐项一致**
（既有基线：crystal schema 未建 + 测试耦合），通过的 474 → **477** 即新增的 3 个。

**线上实测（重启 api 后走真实 HTTP）**：

```
1) POST /memories(async) → status=processing
2) 刚写完 GET /memories/{id} → _status='processing'，pending 5 个键在（在飞）
3) +14.1s → _status='completed'  _processed_at='2026-09-22T04:19:50.734268+00:00'
4) pending 残留=[]（已清）| entities={'person': ['张三'], 'thing': [...]}
5) GET /stats/overview → anomalies={'processing':0,'processing_stuck':0,'failed':0}
6) 同步写入回归：status='done'（未变）
```

**卡死阈值实测**：人造一行 `_status=processing` 且 `created_at = now() - 30min`
→ `{'processing': 1, 'processing_stuck': 1}`；再插一行 `created_at = now()`
→ `{'processing': 2, 'processing_stuck': 1}` —— 只有超时那条被算作卡住。

测试数据（`project-statusverify-*`：3 条记忆 + 2 条人造探针 + 关联实体/embedding 日志）**已全部清理**，残留复查为 0。

## 影响与兼容（逐条核过）

- `processing` 的**全部**比较点 = dsh/hermes/codex 三个客户端对**创建时**响应的判断
  （`status === "processing"`）、update 分支的 `== "processing"`、以及 stats 计数 ——
  多写一个 `completed` 一个都不影响。
- `GET /memories/{id}` 早已返回 `metadata`，**无需新端点**；`POST /memories` 的 `status`
  是创建时的值，仍恒为 `processing`。
- `update_metadata` 是整份覆盖，收尾写状态沿用"重读 → 合并 → 写回"，不会抹掉并发写入的 `relations`。
- `_status` 不会进 prompt（注入服务只读 `metadata.relations`）。
- 契约已写进 [ARCHITECTURE.md](../ARCHITECTURE.md#异步处理的终态契约metadata_status勿改回成功后-pop-掉)，
  避免以后又被"优化"回 pop。
