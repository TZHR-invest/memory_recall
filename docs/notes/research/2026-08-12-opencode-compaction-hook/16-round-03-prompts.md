# Round 3 提示词（去留评估 + R3-1/R3-2）

> 类型: 调研（提示词）
> 调研: 2026-08-12-opencode-compaction-hook
> 说明: Q3-Q8 去留判断 + 最终两题

## 第三轮：Q3-Q8 去留评估与提示词（2026-08-13）

### 去留判断

| 原问题 | 结论 | 理由 |
|--------|------|------|
| Q3 原生压缩配置/阈值 | **可选保留**（仅 Claude，窄化） | 默认值/公式已由源码验证；唯一剩余价值是社区调参经验，用于 README/部署建议，不阻塞实现 |
| Q4 agent/todos 历史演进 | **删除** | 当前版本保留语义已由源码证实，ADR-0008 决策已定；历史不影响实施 |
| Q5 summarize 与 hook 异同 | **删除** | 源码已回答：同一条管线、hook 必触发、summarize 不支持自定义 prompt |
| Q6 压缩相关事件 | **删除** | 删除捕获/恢复后插件无需监听压缩完成；未来需要时再调研 |
| Q7 锚定摘要语义 | **删除** | 决策已定（不替换 prompt），原生锚定自动生效 |
| Q8 注入记忆最佳实践/坑 | **保留并重写** | 多插件共存是真实信息差（谁写 prompt 会覆盖谁）；与 R2-4 的 fail-open 组合成最终实现约束 |

### R3-1（Q8 共存/最佳实践；Grok + ChatGPT，doubao 可选）

> 在 opencode 生态中，有哪些已知的压缩相关插件/项目（例如 Oh-My-OpenCode、compaction 增强类插件）
> 会注册 `experimental.session.compacting` 或 `experimental.compaction.autocontinue`？
> 它们倾向于只 push `output.context`，还是会设置 `output.prompt`？
> 如果我的插件只 push context，与它们共存有哪些已知冲突或最佳实践？
> 请给出项目名、链接与具体行为（设置 prompt 会覆盖我的 context）。

### R3-2（Q3 调参经验，可选；Claude）

> opencode 原生自动压缩默认 `reserved = min(20000, maxOutputTokens)`，
> 触发条件为最近一条 assistant 消息 token 总量 >= `context - reserved`。
> 社区通常如何调 `compaction.reserved` / `tail_turns` / `preserve_recent_tokens`？
> 有没有推荐值或反模式（例如 reserved 设太大导致过早压缩、太小导致快满才压）？请给出来源。


