# MR-017: 注入 cap 硬编码 6/6/4 + 插件 maxProjectMemories 静默丢弃

> 状态: OPEN · 严重度: P2 · 创建: 2026-08-13

## 问题

两件事同源：注入 cap 的参数化缺失 + 一个真实存在的静默契约 bug。

### 1. 注入 cap 硬编码（A6 遗留，87baa09 记录"需后端加字段"）

`context_inject_service.py` `_apply_injection_caps`（L912-925）硬编码：
- projectMemory `[:6]`、userMemory `[:6]`、chunk `[:4]`、profile 不裁剪。

参数来历（git 历史）：a1818b6（121 trace 实测注入量 mean 17.3/max 37 定 memory 合并 cap 12、
chunk 4）→ a86c647 review 发现合并 cap 会被 project 挤占 user，改 project 6 + user 6 分开。
是数据驱动 + review 修正的工程折中，非推导最优。

### 2. 插件 maxProjectMemories 被后端静默丢弃（bug）

链路（Oracle 验证 + 复核）：
- 插件 `opencode/src/index.ts` L201/L220 传 `maxProjectMemories`（默认 10）
- 后端 `ContextInjectConfig`（context_inject.py L25-26）**只有 `max_memories`/`max_chunks`**
  （且这俩是 SQL fetch limit，不是 cap），无 `max_project_memories` 字段
- Pydantic 默认静默忽略未知字段 → 用户以为配了 10，实际 cap 恒为硬编码 6，无任何报错

与项目反复踩过的"Pydantic 静默丢弃未知字段"是同一 bug 类。

## 实证数据（2026-08-13，14 天 317 trace）

- cap 生效后（容器 8-12 16:13 UTC 重启）6 trace 全部 mem ≤ 12，0 超限 → cap 无 bug
- projectMemory 触顶 6 条：150/313（48%），kept>6 被截 106 次（max 19）
- userMemory 触顶：74（24%），截 55 次；chunk 触顶：42（13%），截 16 次
- 平均 final：pm 4.6 + um 2.8 + ch 1.4 + profile 10.5
- 被截断记忆是相似度最低档（0.44-0.47），内容仍相关（进化/cron 修复类）
- hermes 容器触顶最严重（"进化 修复 cron"类 query 每次召回 13-19 条相关 projectMemory），
  根因是进化循环每次迭代存一条新记录 → 记忆库"主题相关但内容不同"的累积冗余
  （semantic_dedup 0.85 只去近似重复，不去这类）

## 结论（2026-08-13 Oracle 评估）

1. **6/6/4 值不改**：触顶率高 ≠ 损失大（被砍的永远是相似度最低档，边际增益递减）；
   token 经济学不支持提 cap（hermes final 已 22.8 条）；48% 触顶是"召回过量供给、cap 裁剪"
   的健康信号。
2. **参数化值得做（低优先级）**：核心理由是修静默契约 bug（让已存在的插件字段生效），
   不是给普通用户加旋钮。默认值必须 = 6/6/4 保证零行为变更。
3. **更本质问题**：hermes 记忆库增量累积冗余是"写时未合并"，不是"读时 cap 太小"——
   需改 hermes 插件侧写时逻辑（合并/降权），属 Large，另行处理。

## 建议方案（若实施，Short / 1-4h）

1. `ContextInjectConfig` 加 3 字段，默认值 = 6/6/4（零行为变更）
2. 命名用 `*_cap` 后缀避开歧义（现有 `max_memories`/`max_chunks` 是 fetch limit；
   注意 chunk 现有三个数：插件 maxChunks=5、后端 fetch 3、cap 4）
3. `_apply_injection_caps(items, caps)` 改签名收参，`inject`/`inject_with_tags` 从 config 传入
4. opencode 插件映射表补 `max_project_memories_cap: config.maxProjectMemories`
5. deepseek-tui/hermes 靠默认值兜底，不铺开
6. 加测试 + `recall_regression.py` 确认默认值下注入量无退化

## 解决记录

（修复后填写 commit / 版本）
