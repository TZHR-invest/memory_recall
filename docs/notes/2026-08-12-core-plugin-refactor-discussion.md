# 2026-08-12: 核心服务 + OpenCode 插件精简讨论记录

> 类型: 讨论
> 日期: 2026-08-12
> 关联: [2026-08-11_refactor_core_and_plugin.md](../archive/2026-08-11_refactor_core_and_plugin.md)（已归档讨论稿，内容不可信任）、
> docs/notes/2026-08-12-opencode-compaction-hook.md

## 背景

对 `docs/archive/2026-08-11_refactor_core_and_plugin.md`（原 `docs/` 下）逐点做代码核查后，
与用户确认了删留与文档落点。
原讨论稿中的数字（如 config 17 个字段）、结论（如 autocontinue 原生化恢复）均以代码/官方源码为准重新核实。

## 讨论要点与已收敛结论

1. **预压缩完全废弃**：删除 `checkAndTriggerCompaction`、`injectHookMessage`、预压缩专用 prompt 路径；
   只保留官方 `experimental.session.compacting` hook。摘要捕获保留（SDK 轮询 + 只读文件兜底）。
2. **现场恢复可删除**：压缩不丢 agent/todos；`autocontinue` 仅控制合成 continue 消息。
   删除 `captureAgentConfig/recoverAgentConfig/captureTodos/restoreTodos` 及 README 中与
   Oh-My-OpenCode 的冲突章节。
3. **container_tag 旧模式移除**：仅指 `/context-inject` 旧 `container_tag` 路径 +
   插件 `userContainerTag/projectContainerTag` 配置 + `useBackendDedup` 开关；
   存储层与其他端点的 container_tag 不动。
4. **优雅降级**：`/context-inject` 单通道失败不拖垮整体请求，返回已成功通道结果，
   失败记录 trace/stats；仅全失败或请求级错误才 500。
5. **失败提示策略**：log + toast，每会话最多 3 次，第 3 次告知后续不再显示、详情见日志；不污染对话上下文。
6. **会话摘要不进记忆库**（代码已实现），删除 `src/summary.ts` 死代码。
7. **项目阶段需记录**：开发早期、用户个位数、自托管、允许破坏性变更——写入 PROJECT_PLAN，
   供 agent 做决策。

## 未决 / 待确认

- 摘要捕获的只读文件兜底是否保留（建议保留，见压缩 hook 调研笔记）；
- `docs/CONTEXT_INJECT.md` 范围是否按"add + inject 全业务流程"写（倾向：是）；
- 正式文档（PROJECT_PLAN 节、ADR-0003~0006、CONTEXT_INJECT.md、README 索引、原稿归档）待确认后落地。

## 下一步

确认上述未决项后，按文档规范落 ADR / 根目录 ACTIVE 文档并更新索引；再输出实施计划（删代码 + 测试改造）。

## 未决问题

暂无其他未决。

---

**更新（2026-08-12 当日）**：用户已确认——文档命名为 `docs/MEMORY_FLOW.md`（add + inject 全流程）、
摘要捕获整套删除、压缩不替换 prompt。最终决策见 ADR-0003~0008，实施计划见
[2026-08-12-core-plugin-refactor-plan.md](2026-08-12-core-plugin-refactor-plan.md)。
