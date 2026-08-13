# Memory Recall 任务状态（实时工作台）

> 状态: ACTIVE · 最后更新: 2026-08-12
>
> 规则：本文件只放"当前活跃工作 + 下一步 + 等待项"；历史一律进 `docs/notes/`；
> 每次任务收尾必须更新；无活跃工作则写"空闲"。

## 活跃任务

| 任务 | 状态 | 入口 |
|------|------|------|
| OpenCode 压缩 hook 外部调研 | 已完成（三轮收敛，结论与 ADR-0003~0008 一致） | [调研目录](notes/research/2026-08-12-opencode-compaction-hook/README.md) |
| 核心服务 + 插件精简实施 | 未开始（下一步） | [实施计划](notes/2026-08-12-core-plugin-refactor-plan.md) |

## 下一步

1. 按[实施计划](notes/2026-08-12-core-plugin-refactor-plan.md)阶段 1 开始：
   后端 `/context-inject` 优雅降级 + 移除旧 `container_tag` 模式；
2. 阶段 2/3：插件注入收敛、压缩收敛（context-only + fail-open 防御层 + 共存检测）；
3. 阶段 4：toast 节流、版本对齐；
4. 阶段 5：残留检查、测试、手工验证（抛错 hook / 超时 / 共存检测实测）。

## 等待项 / 阻塞

- 暂无（外部调研已完成；等待开始实施）。

*状态: ACTIVE · 最后更新: 2026-08-12*
