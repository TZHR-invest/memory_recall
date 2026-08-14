# Memory Recall 已知问题清单（索引）

> 状态: ACTIVE · 版本: v1.4 · 最后更新: 2026-08-14
>
> 本文件是问题清单**索引**（进知识库，Agent 一眼看到当前有哪些坑）；
> 每个问题的详情在 `docs/issues/MR-xxx-短slug.md`。
> 规则见 [DOCUMENTATION_GUIDE.md](DOCUMENTATION_GUIDE.md#6-问题清单issuesmd-索引--docsissues-详情)。

## 严重度说明

- **P0**：影响产品根基，建议尽快决策；
- **P1**：会造成数据错误/丢失或明显体验缺陷；
- **P2**：一致性、维护性与可观测性问题。

## Open 问题

| ID | 标题 | 严重度 | 详情 |
|----|------|--------|------|
| MR-004 | 异步队列纯内存，进程退出丢任务 | P2 | [详情](issues/MR-004-inmemory-queue.md) |
| MR-006 | 无统一"知识对象/单一事实源"，最新语义多路径不一致 | P0 | [详情](issues/MR-006-knowledge-object.md) |
| MR-008 | 画像缓存一致性靠补丁 | P1 | [详情](issues/MR-008-profile-cache.md) |
| MR-009 | 实体合并靠字符串唯一约束 | P2 | [详情](issues/MR-009-entity-merging.md) |
| MR-010 | 产品定位漂移：文档与代码讲了三套故事 | P0 | [详情](issues/MR-010-positioning-drift.md) |
| MR-011 | 缺少知识浏览/纠错闭环 | P0 | [详情](issues/MR-011-knowledge-ui.md) |
| MR-012 | 性能与召回数字失真 | P2 | [详情](issues/MR-012-performance-claims.md) |
| MR-013 | 无迁移框架，schema 双源 | P1 | [详情](issues/MR-013-migration-framework.md) |
| MR-014 | 版本号漂移 | P2 | [详情](issues/MR-014-version-drift.md) |
| MR-015 | 死代码与设计残留 | P2 | [详情](issues/MR-015-dead-code.md) |
| MR-016 | DATABASE_URL 配置误导 | P2 | [详情](issues/MR-016-database-url.md) |
| MR-017 | 注入 cap 硬编码 6/6/4 + 插件 maxProjectMemories 静默丢弃 | P2 | [详情](issues/MR-017-injection-caps.md) |
| MR-018 | profile 写入路径无 embedding，semantic_dedup 对画像失效 | P2 | [详情](issues/MR-018-profile-dedup.md) |
| MR-019 | 文档 → 记忆蒸馏是否值得做（ADR-0010 遗留） | P2 | [详情](issues/MR-019-document-to-memory-distillation.md) |
| MR-020 | /history 端点对显式版本链返回空（版本历史双路径不一致） | P2 | [详情](issues/MR-020-version-history-gap.md) |

## 已关闭（决策导致不再适用）

| ID | 标题 | 关闭原因 |
|----|------|---------|
| MR-001 | 文档删除链路断裂：源文件删除后知识残留 | [ADR-0010](decisions/0010-remove-document-rag.md)：文档 RAG 移出核心 |
| MR-002 | URL 去重跳过内容更新 | 同上 |
| MR-003 | 文档无版本/变更历史，更新即销毁旧知识 | 同上 |
| MR-005 | 文档处理失败静默 | 同上 |
| MR-007 | 文档知识只有向量路，实体图谱关联浅 | 同上 |

## 已解决

（修复后从 Open 表移入，记录版本/commit；**详情文件不删除**，
只把 docs/issues/MR-xxx.md 的状态改为"已解决"——问题史是资产，
未来回归或相似问题可直接参考。已解决表超过 20 条时，
把旧记录对应的详情文件移入 docs/archive/issues/，索引只保留近 20 条。）

| ID | 标题 | 解决版本/commit |
|----|------|----------------|
| MR-021 | codex 插件项目容器探测启动竞态（VSCode 扩展模式偶发 403，容器回退 codex-default 被冻结） | 见 [MR-021 详情](issues/MR-021-codex-mcp-container-race.md)（2026-08-14 修复，config.py 惰性重探测） |
| MR-022 | memory-recall-dsh 缺 dsh.client.platform + exports["./client"]，dsh web 启动即崩溃（3080 无监听） | 见 [MR-022 详情](issues/MR-022-dsh-client-platform-missing.md)（2026-08-14 修复，package.json 补元数据 + install.sh --restart） |

## 优先行动建议

1. **先实施 ADR-0010**：移除文档 RAG（表/代码/路由/插件/测试），减少 MR-006 需统一的召回路径数量。
2. **再定知识对象**（MR-006/008）：统一"当前事实"的存储与语义，这是架构层关键决策，越晚越难改。
3. **同时做产品面最小闭环**（MR-011）：让用户看到并纠正系统记住了什么，这是信任与留存的基础。
4. **清理工程债**（MR-013 迁移框架 / MR-015 死代码 / MR-017 cap 配置化 / MR-018 画像去重 / MR-020 版本历史读取）。

*状态: ACTIVE · 版本: v1.4 · 最后更新: 2026-08-13*
