# 2026-08-12: 召回质量优化（trace 数据驱动 Phase 0-3）

> 类型: 调研 + 实现
> 日期: 2026-08-12
> 关联: commits f483f4b / 72b7953 / 66a09d6 / 50adc9b / 955bc0a

## 背景

用户目标：召回尽量多相关有价值记忆（不遗漏），同时尽量少召回无关记忆（减噪音）。
基于 235 条 trace 实证数据分析召回链路，产出并执行优化方案。方案经 Oracle 架构审查修正。

## 数据发现（trace 实证）

- final 注入构成：**profile 68%**（1244/1836）——固定 23 条与 query 无关；
- 0.40-0.45 边缘命中占 vector 候选 35%，抽样约 50% 噪音，通过阈值后 93% 留存（145/156 进 final）；
- 34 条 `[CONTEXT]>500` 子代理 prompt 平均注入 29.6 条（profile 16.6）——纯浪费；
- entity_graph 高候选低注入（69/85 次 memories=0，28 paths 仅注入 2）；
- HTML 噪音 chunk（`<div align=center>`）命中 37 次；
- 去重效率低（dropped 1.2 vs final 21.4）。

## 执行内容

### Phase 0（f483f4b）
- **O8**：memory_store.search / document_store.search_chunks 阈值 SQL `>` → `>=`，
  与 trace passed 计算语义统一（边界值 0.400000 不再被 SQL 排除）；`_check_similar_memory` 已是
  `>=`；relation_service 合并检测 `>` 保留（0.95 边界无实际影响，非召回路径）。
- **O10**：清理 19 条 HTML 噪音 chunk（6d9d1b8 修复前导入的 `failed_but_chunks_ready` 存量，
  复用 `_strip_html_preserving_code` 清洗 + 重建 embedding）；`_get_chunks` 加 HTML 开头 chunk
  防御性丢弃。

### Phase 2（72b7953）
- **O1**：`TRACE_FULL_CANDIDATE_RATE` 配置（默认 0 关闭）。采样命中时 SQL limit×3 + threshold 0.30，
  记录被生产阈值挡掉的 0.30-0.40 候选，`record_vector` 加 `full_candidate` 标记——漏召回分析能力。

### Phase 3（66a09d6 → 955bc0a，两次迭代）
- 第一版（66a09d6）：0.40-0.45 边缘命中标 `low_confidence`，DedupItem priority -1，cap 自然截断。
- **误伤修正**（955bc0a）：批量验证暴露纯相似度降级会误伤长内容相关记忆（"最近的热点研究"
  5 条候选被截 4 条，中际旭创/玻璃基板等完全相关）。改为**关键词二段验证**：jieba 关键词交集
  （query vs content 统一小写）判定——有交集保留（不降级），无交集才降级。

## 关键教训

1. **验证必须看 final 构成而非聚合留存率**："4/5 被截"是 verify 脚本聚合口径误读——
   实际 3 条进 final，另 2 条被 cap 6 条名额截断（非 O3 误伤）。聚合统计掩盖 cap 竞争。
2. **jieba 0.42.1 实际已装 venv**（不在 requirements.txt，relation_service try/except fallback
   掩盖）。Oracle 因"新依赖成本"否定的关键词方案零成本可用——依赖可用性需实测而非推断。
3. **纯相似度降级会误伤长内容相关记忆**（热点研究长内容 embedding 相似度天然偏低），
   需关键词辅助区分相关/噪音。
4. O3 修正版确认：高分（≥0.45）留存 100%，相关边缘关键词命中保留，噪音边缘（cron/运营回顾
   无交集）降级截断。

## 结论

Phase 0-3 完成：345 全绿，回归无退化（28.4 vs 28.1）。效果经对比实验验证（高分 100% 留存、
相关边缘保留、噪音降级）。已推送并重启 api 生效。

## 下一步

- **O2 子代理 profile 降级**（记录待做）：34 条系统消息 trace 平均注入 29.6 条是剩余最大浪费点。
  方案：插件 `chat.message` hook 传 `is_subagent` 标志，后端据此降级 profile。不依赖
  `_is_subagent_query` 字符串启发式（已证实误伤用户真实消息）。
- **Phase 4**：cap 6/6/4 提为 Pydantic 字段（可维护性改进，优先级低）。
- 采样工具 `TRACE_FULL_CANDIDATE_RATE` 留作需要时手动用，不默认开启（避免持续 3x 负载）。

## 未决问题

- 真实使用环境下 O3 关键词二段验证的长期效果（需采样窗口积累数据确认，当前为对比实验验证）。
- jieba 是否应进 requirements.txt：当前跟随项目既有模式（可选依赖 + fallback），保持轻依赖。
