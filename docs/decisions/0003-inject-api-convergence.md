# ADR-0003: 注入接口收敛为 /context-inject 单一路径

> 状态: Accepted
> 日期: 2026-08-12
> 关联: [PROJECT_PLAN.md](../PROJECT_PLAN.md#0-当前阶段与工程约束)、ADR-0004、ADR-0005

## 背景

插件存在两套注入实现：

- 后端路径 `injectContextFromBackend`：一次调用 `/context-inject`（默认）；
- 前端复合路径 `injectContext`：自己串 `/profile` + `/search` + `/documents/search` + `/graph`
  + `/embed`，并在客户端做图谱遍历与去重。

两者由 `useBackendDedup` 开关选择，去重/图谱逻辑两端重复实现，行为与 trace 能力不一致。
同时 `/context-inject` 保留旧 `container_tag` 单容器模式，与新版 `user_tag/project_tag` 双容器并存。

## 选项

- A: 保留双路径与 `useBackendDedup` 开关，继续兼容旧 `container_tag` 模式；
- B: 收敛为 `/context-inject` 新接口（`user_tag/project_tag`），删除前端复合路径与旧模式；
- C: 反向收敛为前端复合路径，删除后端聚合接口。

## 决策

选择 **B**：注入只走 `POST /context-inject`（`user_tag/project_tag`）。

删除范围：

- 插件前端复合注入路径（`injectContext` / `formatContext` / `traverseFromSeeds` /
  `deduplicateAcrossScopes` / `semantic-dedup.ts` / `embedding-cache.ts` / `client.embedBatch` 及相关测试）；
- 插件 `useBackendDedup` 开关与 `userContainerTag/projectContainerTag` 旧配置；
- `/context-inject` 旧 `container_tag` 模式（请求字段与 `inject()` 服务路径）。

**存储层与其他端点的 `container_tag` 不在此次删除范围。**

## 理由

- 后端聚合已是唯一带语义去重、cap 与 trace 的召回实现，前端路径是重复劳动且行为漂移；
- 项目处于开发早期、用户个位数、自托管，允许破坏性变更（见 [PROJECT_PLAN](../PROJECT_PLAN.md) §0）；
- 单端点故障对主流程的影响由插件外层 best-effort catch 兜底（ADR-0004 / ADR-0005）。

## 后果

- 正面：单一事实源；去重/图谱/cap/trace 只在后端维护；插件代码显著缩小；
- 负面：`/context-inject` 单端点故障时注入整体不可用（相比前端逐端点降级）；
- 跟进：同步改写 `tests/test_v2/test_context_inject_api.py` 旧 `container_tag` 用例；
  旧配置用户需迁移到 `user_tag/project_tag`。

*状态: Accepted · 日期: 2026-08-12*
