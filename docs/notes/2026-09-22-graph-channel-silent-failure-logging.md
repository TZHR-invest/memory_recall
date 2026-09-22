# 图谱通道不再静默失败（可观测性收口）

> 状态: DONE · 日期: 2026-09-22 · 效果: 4 处吞异常的 `except: pass` 改为留痕；顺带修掉一个**污染整个测试会话**的 mock 泄漏

## 为什么做

同日的"图谱通道没有 `ORDER BY`"只能靠人肉 review 才发现，根因之一是**通道级失败不留任何痕迹**：
`context_inject_service` 里有 4 处 `except Exception: pass`，其中两处正好包着记忆图 / 实体图。

## 实测的静默形态（改前）

| 位置 | 形态 | 后果 |
|---|---|---|
| 记忆图 expansion | `try` 在 `for mem in all_memories[:3]` **内**，且**没有任何外层 handler** | 整条通道可无声消失，每次召回最多吞 3×2 次 |
| 实体图 per-seed traverse | 外层**已有** `logger.error("entity_graph injection failed")`，但逐种子异常被内层吞掉 ⇒ **外层永不触发** | `traverse` 整体坏掉（例如 SQL 写错）时**零日志** |
| chunks 实体命中子通道 | 内层吞掉，外层 `chunks fetch failed` 覆盖不到 | 同上 |
| 全通道失败路径的 trace 落库 | 吞掉 | 排障时看不出 trace 有没有写成功 |
| `_chunk_similarity` | **有意**兜底 `return 0.0`（丢弃坏 embedding） | 加 **debug** 留痕——按 chunk 逐条调用，warning 会刷屏 |

## 改动

按本文件既有惯例 `logger.warning("<channel> failed for %s: %s", container_tag, e)` 补 4 处；`_chunk_similarity` 用 debug。
**刻意不动**：`_age_days` 的 `except (ValueError, TypeError): return None`（docstring 已说明是有意的解析兜底）。
**刻意不做**：把图谱通道塞进响应的 `failed_channels`——那会改 API 契约（模型只声明 profile/memories/chunks，
且插件侧未验证），本次只要"留痕"。

## 顺带修掉的既有测试 bug（重要）

`test_context_inject_api.py::test_context_inject_with_chunks` 原先直接
`context_inject_service._get_chunks = AsyncMock(...)` 且**从不还原** ⇒ 整个 pytest 会话里**后续所有模块**
的 chunks 通道都静默走那个 mock（永远返回 `chunk_001`）。

发现方式值得记一笔：新写的测试**单跑通过、全套失败**，探针显示"我 patch 的 document_store / embedding 工厂
调用次数都是 0，却拿到了 polluter 的 fixture 数据"⇒ 才定位到泄漏。已改为 `patch.object` 上下文。

## 验证

- 新增 4 条回归测试 `tests/test_v2/test_graph_channel_failure_logging.py`：故障留 WARNING、正常返回不受影响、坏 embedding 走 debug。
- 全套快速单元循环：**491 passed**（= 改前 487 + 4），**FAILED 集合与改前逐项一致**（6 个既有失败不变，其中 1 个真失败 + 5 个套件内互相污染）。
- 线上冒烟（重启后）：两次召回注入集合一致、`failed_channels=[]`、**新告警零误报**、图谱通道正常产出。

## 相关

- 图谱通道确定性 + 同名家族归一：[entity-graph-determinism-and-name-normalization](2026-09-22-entity-graph-determinism-and-name-normalization.md)
- 上游同类修法（抽取降级留痕）：[entity-extraction-breadth-fix](2026-09-22-entity-extraction-breadth-fix.md)
- 测试污染清单：[TESTING.md](../TESTING.md)
