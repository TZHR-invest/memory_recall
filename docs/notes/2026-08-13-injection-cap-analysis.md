# 2026-08-13: 注入 cap 6/6/4 是否需要优化（trace 数据驱动 + Oracle 评估）

> 类型: 调研
> 日期: 2026-08-13
> 关联: MR-017（cap 参数化 + maxProjectMemories 静默丢弃）；commits a1818b6 / a86c647 / 87baa09（A6 遗留）
> 结论: 值不改；参数化可做（低优先级）；hermes 记忆冗余是真问题（记档不动码）

## 背景

用户问"召回很多条最终只注入 15 条"是否正常，进而追问 cap 参数怎么定的、是否需优化。
数据驱动分析 + Oracle 咨询，产出"改/不改"结论。

## 参数来历（git 历史）

- **a1818b6**（8-12）：121 trace 实测注入量 mean 17.3/max 37、53% 超 10 条 → memory 合并 cap 12、
  chunk cap 4、profile 不裁剪（23 条画像有意全量）。
- **a86c647**（同日 review）：合并 12 会被 project 记忆量大的容器完全挤占 user 偏好
  （模拟 12 project + 4 user → user 注入 0）→ 改 project 6 + user 6 分开，user 保底 6。
- 数据驱动 + review 修正的工程折中，非推导最优；有测试锁定（test_cap_project_user_balanced）。

## 截取逻辑（当前实现）

两层：
1. **dedup 排序**：`sorted(items, key=-priority)`，SOURCE_PRIORITY =
   profile(4) > projectMemory(3) > userMemory(2) > chunk(1)；同 source 内保持 search 返回顺序
   （`ORDER BY similarity DESC`）→ cap 切片实际保留同 source 内**相似度最高**的前 N 条。
2. **`_apply_injection_caps`**（L912-925）：projectMemory `[:6]`、userMemory `[:6]`、chunk `[:4]`、
   profile 不裁剪。

## 实证数据（14 天 317 trace）

- **cap 生效边界**：容器 8-12 16:13 UTC 重启后才跑 cap 代码。生效后 6 trace 全部 mem ≤ 12，
  0 超限 → **cap 无 bug**。49 条 mem>12 的 trace 全在重启前（旧代码）。
- **触顶率**（kept 层）：projectMemory 150/313（48%）、userMemory 74（24%）、chunk 42（13%）。
- **被截断质量**：vector 命中 20 条全 passed（0.44-0.63 全相关），cap 只放行 12 条；
  被砍的是 0.44-0.47 最低档，内容仍相关（进化/cron 修复类）。
- **容器差异**：hermes 平均 final 22.8（顶 cap 严重），main 平均 6.7（不触顶）。
- **重复 query**：hermes "进化 修复 cron 错误" 9 次、平均 final 32.3——进化循环定期自检类。

## Oracle 结论（2026-08-13）

1. **6/6/4 值不改**：触顶率高 ≠ 损失大（被砍的永远是相似度最低档，边际增益递减）；
   token 经济学不支持提 cap（hermes final 已 22.8 条，提 12→18 推 final 到 ~30 条换最弱档）；
   48% 触顶是"召回过量供给、cap 裁剪"的健康信号（永不触顶才是召回不足）。
2. **参数化值得做（低优先级）**：核心理由是修**静默契约 bug**——插件 index.ts L201/L220 传
   `maxProjectMemories`（默认 10），后端 ContextInjectConfig 只有 `max_memories`/`max_chunks`
   （且是 fetch limit 非 cap），Pydantic 静默丢弃未知字段 → 用户以为配 10 实际恒为 6。
   与"Pydantic 静默丢弃未知字段" bug 类一致。默认值必须 = 6/6/4 零行为变更。
3. **更本质问题**：hermes 每次召回 13-19 条相关 projectMemory，根因是进化循环每次迭代存一条
   新记录 → 记忆库"主题相关但内容不同"的累积冗余（semantic_dedup 0.85 只去近似重复）。
   cap 正确约束症状；病根是写时未合并/降权。需改 hermes 插件侧写时逻辑，属 Large。

## 结论

- **本次不动代码**：cap 工作正常，参数化是债务清理（MR-017）而非 bug 修复，等下次触碰 recall
  代码时顺手做。
- 记录: MR-017（P2，含建议方案 Short/1-4h）。

## 下一步

- MR-017 排期：参数化 3 字段（默认 6/6/4）+ opencode 映射补 `max_project_memories_cap` +
  回归验证。命名用 `*_cap` 后缀避开与 fetch limit 的歧义（chunk 现有三个数：插件 5 / fetch 3 / cap 4）。
- hermes 记忆冗余（写时合并/降权）单独评估，属插件侧 Large 改动。

## 未决问题

- hermes 类容器的 cap 是否应高于默认（参数化后可自行调，无需改全局默认）。
