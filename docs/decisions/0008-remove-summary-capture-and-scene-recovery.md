# ADR-0008: 删除摘要捕获与现场恢复

> 状态: Accepted
> 日期: 2026-08-12
> 系统: v5
> 关联: ADR-0006、ADR-0007

## 背景

压缩维护模块里有两组"冗余/历史兼容"代码：

- **摘要捕获**：`waitForSummaryMessage`（SDK 轮询 10×500ms）+ `extractSummaryContent`
  （读 `~/.opencode/parts` 兜底）+ 5 分钟内存缓存，用于向下一次压缩注入"上一版摘要"。
  但官方 `buildPrompt` 已自动传递 `previousSummary` 做锚定更新，插件缓存是重复功能；
  且会话摘要已决策不写入记忆库（ADR-0006），缓存的唯一用途被官方覆盖；
- **现场恢复**：`captureAgentConfig/recoverAgentConfig/captureTodos/restoreTodos`，
  为旧版本"压缩后丢 agent/todos"写的兼容层。官方源码证明：agent/model 由用户消息字段保留、
  todos 存独立表，压缩不删改；`autocontinue` 只控制合成 continue 消息，不承担恢复职责。

## 选项

- A: 全部保留；
- B: 仅删现场恢复，保留摘要捕获；
- C: 全部删除。

## 决策

选择 **C**：

- 删除摘要捕获整套：轮询、文件兜底、`latestSummaries` / `summarizedSessions` /
  `savedSummarySessions` 相关状态与触发逻辑；
- 删除现场恢复：`captureAgentConfig` / `recoverAgentConfig` / `captureTodos` /
  `restoreTodos` 及 `session.compacted` 事件里的恢复处理；
- 删除 README 中"与 Oh-My-OpenCode 共存需禁用其恢复"的章节（冲突正来自恢复逻辑）。

## 理由

- 冗余：官方锚定已覆盖"上一版摘要"，官方存储已覆盖 agent/todos；
- 风险：文件兜底保留了只读私有格式依赖，与"减少对 `~/.opencode` 私有格式依赖"目标冲突；
- 简化：这些模块的竞态处理（轮询窗口、事件字段差异）不再需要维护。

## 后果

- 正面：压缩模块只剩官方 hook 的 context 注入；无竞态状态机；
- 负面：无跨压缩摘要缓存；
- 跟进：若未来需要感知压缩完成，使用官方 `session.compacted` / `session.next.compaction.ended`
  事件 + SDK 查询，不再读私有文件。

*状态: Accepted · 日期: 2026-08-12*
