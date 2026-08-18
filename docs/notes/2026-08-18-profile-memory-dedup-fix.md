# 画像与向量记忆同内容重复注入修复（2026-08-18）

## 背景

用户通过 trace 发现注入记忆里存在画像与向量召回的同内容记忆未去重。

复现 trace：#trace_269dd48a3fc34ae788ff4b550c972dcd（query="test"）

证据：「用户关心实际影响而非追求100%测试通过率」在 final 中同时以
- final[8]  source=profile    id=None
- final[25] source=userMemory id=mem_c9ea80eccec24bccb616

出现两次，且 dedup.dropped 为空数组。

## 根因

1. _collect_items_with_tags（context_inject_service.py）为画像条目创建 DedupItem 时**不传 embedding**（profile 缓存 memory_profiles 只存 content 字符串）。
2. semantic_dedup_service.deduplicate 只对**带 embedding 的条目**做相似度比较，items_without_embedding 无条件保留（L96 kept.extend(items_without_embedding)）。
3. 结果：画像条目永远无法参与语义去重，与向量召回的同一条记忆以双身份重复注入。

## 修复（方案：内容精确匹配预去重）

_collect_items_with_tags 增加 seen_contents 集合：

- 画像 static/dynamic 条目加入 items 的同时，把 fact.strip() 登记进 seen_contents；
- 后续 projectMemory / userMemory 条目若 content.strip() 命中 seen_contents 则直接 continue（跳过），保留画像高优先级版本。

改动仅 context_inject_service.py 的 _collect_items_with_tags（约 18 行），
不动 schema / 缓存结构 / 语义去重服务。

## 验证

1. 新增回归测试 2 个（test_context_inject_api.py）：
   - test_profile_content_dedup_memory_skipped：画像与 user/project 记忆逐字相同 → 只保留画像版本
   - test_profile_content_dedup_keeps_different：内容不同不受影响
2. 相关测试全绿：test_context_inject_api 39 + test_semantic_dedup + test_recall_trace 48。
3. 服务重启（docker restart memory_recall-api-1）后用原 trace 同配置复现：
   - vector 仍命中 mem_c9ea80eccec24bccb616（user 0.4100）→ 证明是去重跳过而非未召回
   - final 中目标记忆仅出现 1 次（profile 版本）→ 重复 1→0 消除
   - stats: total_items=19（画像19 + 向量1 被跳过），after_dedup=19

## 已知局限

- 仅覆盖**逐字相同**的重复（含 strip 前后空白差异）。
- 带 [补充] 前缀、标点差异等"近似但非逐字"的重复仍会漏过 —— 需要语义 embedding 比较，
  而画像条目无 embedding（缓存仅存 content），做语义去重需额外查询记忆表或改缓存结构，
  成本较高，暂不实施。若未来出现大量近似重复，再考虑给画像条目补 embedding 方案。

## 相关记忆版本化更新（ADR-0009）

- mem_710336f679464d079b14 → mem_e3a2429f946449729f40（问题描述，标记已修复）
- mem_00a45143d6c44e76b6c7 → mem_8b6d2836e52b4ba3bfb5（方案建议，标记已实施）
- mem_b62e75dc2dfb44b5bf02 → mem_b1039014894a480b9857（影响评估，标记已修复）
- mem_d41eba0f02364441a12d → mem_7a62fac304b342658e2d（缓存约束，补充现状）
