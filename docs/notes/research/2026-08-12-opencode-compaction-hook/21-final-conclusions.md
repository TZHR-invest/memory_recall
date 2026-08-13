# 最终统一理解（Round 3 结论）

> 类型: 调研（统一理解）
> 调研: 2026-08-12-opencode-compaction-hook
> 说明: 第三轮结论 + 调研收敛声明

### 第三轮统一结论（2026-08-13）

1. **Q8 生态结论**：共存风险集中在"会设置 `output.prompt` 的插件"（hashpress-opencode、
   opencode-plugin-compaction-prompt、OMO 的 customCompactionPrompt 开关）；主流状态保活类插件
   （OMO 默认、goal、swarm、smart-compaction）都只 push context，与我们策略天然可组合。
   → 保持 context-only，不注册 autocontinue。
2. **Q8 行动项**：
   - hook 开头检测 `output.prompt !== undefined`：若已被其他插件接管，记 warn 并跳过注入，
     避免"静默失效"；
   - README 声明兼容性：只追加 context；同时启用任何设置 prompt 的压缩插件/开关时
     本插件注入失效（尤其提示 OMO 用户勿开 customCompactionPrompt）；
   - 注入文案短、结构化、可去重（固定标题如 `## Persistent Memory`），避免 context 膨胀。
3. **Q3 调参结论（Claude R3-2 部分采信）**：
   - 默认值以 v1.18.16 源码为准：`reserved = min(20000, maxOutputTokens)`、
     `tail_turns = 2`、`preserve_recent_tokens` 默认钳制 `[2000, 8000]`；
     Claude 的 15_000 / "tail_turns 未设则不限" 与源码不符，不采信；
   - 确认风险：模型无 `limit.input` 时 `reserved` 被忽略（源码 else 分支 + issue #13980）；
   - 大窗口模型（如 1M context）默认 20k reserved 占比仅 ~2%，原生 auto 可能"快满才压"
     （issue #27706/#11314 佐证）——正是原预压缩想解决的痛点，实施后需观察；
     README 可给调参指引（如显式调大 `reserved`，注意模型限制），不阻塞实现。
4. **V1/V2 配置并存**：`reserved` vs `buffer`、`preserve_recent_tokens` vs `keep.tokens`
   字段名不同；本项目按当前运行时 v1.18.16 的 V1 字段为准，社区示例先确认版本。
5. **外部调研收敛**：所有决策支撑点已确认，与 ADR-0003~0008 无冲突，可以进入实施。
