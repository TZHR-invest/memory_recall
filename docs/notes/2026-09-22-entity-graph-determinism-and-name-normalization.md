# 图谱通道的抽签问题 + 同名实体归一（P0+P1，读路径）

> 状态: DONE · 日期: 2026-09-22 · 效果: 召回内容**可复现**（trace 除耗时外逐字段相等）；`tailscale` 一组 **+15 条记忆 / +15 条边**重新可达

## 症状（review 实体合并提案时发现的，不是新报障）

1. **两处没有 `ORDER BY`**：
   - `context_inject_service` 取种子写的是 `entities[:5]`，而 `get_entities_for_memories` 的 SQL 是
     `SELECT DISTINCT e.*`——**无排序**；
   - `traverse_entity_relations` 的出边/入边查询**也无排序**，且 `max_nodes=3` **含起点自身**
     ⇒ 每种子实际只跟 ~2 条边（全库平均每实体 2.02 条边、每记忆 6.2 个实体链接）。
   - 一次召回通常产生 30~50 个候选实体 ⇒ **只有"物理顺序靠前"的 5 个被扩展**。
2. **实测旧行为**（同一 query、同一召回集，连跑 5 次）：种子顺序稳定，但**与相关性无关**——
   5 个种子来自不同记忆（命中 2/5、1/5、1/5…），即按链接表物理顺序取。
   ⇒ 不是"每次都不一样"，而是**未定义顺序**（计划/统计信息/物理顺序一变就变），**无法归因**。
3. **同名实体被类型拆散**：`entities` 唯一键是 `(name, type, container_tag)`，而 `type` 由 LLM 抽取、
   同一实体换个 run 就可能变 ⇒ 库内 **424 组**同名不同型（856 行）：

| 项 | 实测 |
|---|---|
| 分裂组 / 行数 | 424 组（417×2 行、6×3、1×4）= 856 行；其中 8 组是纯大小写/空格变体 |
| 链接 | 3,733 总 / 主行 3,128 / **次要行 605（16.2%）** |
| 次要行身上的关系边 | 384 出 + 367 入 = **751 条** |
| 同组两行之间的边 | **0 条**（互为孤岛，合并不产生自环） |
| 受影响记忆 | **466 条**（全库 8,974 的 5.2%）/ 585 个「记忆↔实体组」链接在主行上查不到 |
| 复发速度 | 近 7 天新增 47 组、近 24h 16 组（≈7 组/天） |
| 典型 | `tailscale thing(70)+organization(21)`、`dsh thing(93)+organization(1)`、`A股 thing(170)+organization(5)+event(1)+location(1)`、`devbox thing(69)+location(1)` |

## 为什么选「读路径归一」而不是数据合并

1. 同组两行之间 **0 条边** ⇒ 合并对遍历的净增益只剩"次行那 751 条边并入主行"，而遍历每种子
   只肯跟 ~2 个邻居 ⇒ **先确定化，合并的收益才谈得上**；
2. 记忆可达性收益用「按名字展开」**等价拿到**，零数据变更、可 `git revert`；
3. **合并不止血**：身份含 `type` ⇒ 一次性合并约 40 天后回到原点（≈7 组/天）。真止血要同时改
   唯一约束 + `_store_entity_graph` 的 get-or-create + `document_store.py:850` 的 `ON CONFLICT`；
4. 合并脚本复杂度实测：20 处 `memory_entities` 重指向撞 `uq_memory_entities`、68 处边撞
   `uq_entity_relations`、49 条 `chunk_entities`、FK 是 `ON DELETE CASCADE`（须先重指后删）、
   面板实体数会掉 432。

## 改动（全部读路径，不动数据）

| # | 位置 | 改动 |
|---|---|---|
| P0 | `memory_store.get_entities_for_memories` | `GROUP BY e.id ORDER BY co_occur_count DESC, e.mention_count DESC, e.id`（种子 = **当前结果集的枢纽**） |
| P0 | `memory_store.traverse_entity_relations` | 出/入边查询加 `ORDER BY confidence DESC, id` |
| P1 | `memory_store.resolve_entity_families` / `expand_entity_ids_by_name`（新增） | 同容器内 `lower(btrim(name))` 相同即一族；代表 = 链接最多者（平局取 id 最小）⇒ 确定性；**跨容器绝不归并** |
| P1 | `traverse_entity_relations` | 一个家族只占 **1 个节点预算**，但家族所有行的边**并起来查**（次行的边不再走不到） |
| P1 | `find_memories_by_entities` | 先展开家族；命中计数改 `COUNT(DISTINCT lower(btrim(e.name)))`（否则一个实体拆 3 行会被算 3 次） |
| P1 | `context_inject_service` | 种子按 `(container_tag, lower(trim(name)))` 去重（同一实体不再占掉 2 个种子位） |
| 开关 | `settings.ENTITY_FAMILY_EXPANSION`（默认 True） | 置 False = 旧行为（种子不排序 + 单行语义；边仍保持确定性排序），改后需重启 API ⇒ 供 A/B 与一键回滚 |

**安全性论据**：同名 + 同型 + 同容器**今天已被 unique 约束强制成一行**，`_store_entity_graph` 也按
`LOWER(TRIM(name)) + type` 匹配 ⇒ 系统本来就按"同名即同实体"处理；跨 type 展开不是新增一类混淆，
只是把因类型漂移分裂的异常补回去。

## 验证（活库，只读）

| 项 | 结果 |
|---|---|
| **端到端可复现** | 同 query 两次：注入记忆**集合与顺序一致**；`trace` 除 `elapsed_ms/total_ms` 外**逐字段相等**（`channels`/`dedup`/`final` 全等）。真实 HTTP 链路（`POST /context-inject` + `X-API-Key`）复验同样一致 |
| 家族归并 | 从主行、从次行进入都得到同一代表；异容器解析返回空（租户边界有效） |
| **覆盖增量** | `tailscale`（70 + 21）：记忆 **41 → 56（+15、0 丢失）**；出边邻居 **28 → 43（+15）** |
| 遍历可复现 | 3 次调用结果完全一致 |
| 通道产出 | 10 个 query：`entity_ids` 11.9 / `memories` 4.9 / `new` 3.3（历史基线 entity_graph 候选 3.7/次；`find_memories_by_entities` 受 `limit=max_memories`=5 封顶 ⇒ 增量体现在候选**选择**而非数量） |
| **活 A/B**（真改 `.env` + 重启，不是仿真） | `tailscale 打洞速度很慢怎么排查`：开关 ON 与 OFF **各注入 6 条、两种配置各自可复现**，但 6 条里**换掉 1 条**——ON 多出「办公室/家庭到 Tailscale 官方 STUN 端点 IPv4 回包率极低、IPv6 正常」（**直击排障线索**），OFF 多出「siderouter OpenClash 被一次人为 LuCI 更新打开」（相关但偏外围配置史）|
| 开关双向 | flag=True 记忆 56 / flag=False 41；`.env` 恢复默认后线上结果与 ON 完全一致（回滚路径有效） |
| 单测 | 新增 13 条 `tests/test_v2/test_entity_family_expansion.py` 全绿；快速单元循环 FAILED 集合与改前**逐项一致**（487 passed = 改前 474 + 新增 13） |

## 未验证 / 边界（诚实清单）

- **质量没做盲判 A/B**：本次只证明"确定性 + 覆盖"，**没证明注入质量变好**。要下结论得跑
  [召回通道消融](2026-09-22-recall-channel-ablation.md) 的 harness（开关就是为它准备的）。
- 误合并上限 = 466 条记忆（5.2%）进候选池，且仍要过下游排序；真正同名不同指的实体在同型时
  本来就已被合并，故边际风险有限。
- **数据本身没清**：面板实体行数仍是 27,598 口径；P2（合并 + 身份改造）随时可做，代价见上。

## 相关

- 实体抽取广度修复（更上游的同类问题）：[entity-extraction-breadth-fix](2026-09-22-entity-extraction-breadth-fix.md)
- 通道消融（本次改动的下游影响评估工具）：[recall-channel-ablation](2026-09-22-recall-channel-ablation.md)
- thing 重分类负结果（为什么不做类型重标）：[thing-reclassify-negative-result](2026-09-22-thing-reclassify-negative-result.md)
