# 2026-08-13: ADR-0010 实施计划（三阶段，用户已确认）

> 类型: 实施计划 · 日期: 2026-08-13 · 状态: 已确认，待开工
> 关联: [ADR-0010](../decisions/0010-remove-document-rag.md)、
> [实施优先级讨论](2026-08-13-adr0010-implementation-discussion.md)、
> [升级顺序讨论](2026-08-13-adr0010-upgrade-sequence-discussion.md)
> 前置: 讨论结论已落档；git 基线 main 与 origin/main 一致（无分叉）

## 已确认决策（用户拍板 2026-08-13）

1. **三阶段单向兼容**：插件先行发版 → 用户升级 → 后端一次删除；后端**不写**兼容代码；
2. **opencode 不发 npm 版**：打包分发（`bun run build` 产出 dist，install CLI 复制到
   ~/.config/opencode/ 插件目录），用户从仓库构建安装；
3. **存量文档数据直接删除、不导出**（[实施优先级讨论](2026-08-13-adr0010-implementation-discussion.md) 已确认）；
4. **部署库 DROP TABLE 最后一步单独执行**，可延后到用户确认无回滚需求。

---

## 阶段 1：插件移除文档功能（先行）

### 1.1 opencode（TS/Bun，版本 1.8.2 → 1.9.0）

| 文件 | 改动 |
|------|------|
| `src/document-tracker.ts`（463 行） | 整文件删除 |
| `src/index.ts` | 摘除 DocumentTracker / FileWatcher / 文档 taskQueue 接线 |
| `src/tool.ts` | 删除 import-docs 等文档 tool 定义与分支 |
| `src/config.ts` | 删除 `enableDocumentTracking` / `trackedDocPatterns` 配置项 |
| `src/client.ts` | 删除 `addDocument` 等文档 API 方法 |
| `src/file-watcher.ts` | 仅服务于文档导入，随文档功能删除 |
| `tests/test_document_tracker.py` 等 | 删除/改写对应测试 |
| `README.md` | 移除文档功能说明 |

验证：`bun run build` 通过；插件加载后 tools 列表无文档工具。
分发：不 npm 发版；用户从仓库 `bun install && bun run build` 后运行 install CLI。

### 1.2 hermes（Python MCP stdio）

`server.py`：删除文档工具（list/read/delete/add + inputSchema 定义 + `/documents*` 调用，
约 421-440、631、725、855-944 行区域）；status 命令删除文档计数。

### 1.3 deepseek-tui（Python MCP stdio）

`server.py`：删除文档工具（约 107-218 行区域：schema 定义 + POST/GET/DELETE /documents 调用）。

### 1.4 memory-recall-codex（Codex 插件）

`server.py`：删除文档工具（约 500-519 schema、716 导入、814-815 status 计数、953-1042 工具）；
README 工具数更新（15 → 去掉文档相关）。

### 1.5 发布协调

- 四端同一批 commit 完成，opencode 版本号 bump 至 1.9.0；
- 提交后通知 1-2 个在用用户升级（进入阶段 2）。

## 阶段 2：用户升级（沟通项，不做强制）

| 插件 | 升级方式 |
|------|---------|
| opencode | 拉仓库代码 → `bun install && bun run build` → `memory-recall-opencode install`（本地 dist） |
| codex | 拉仓库代码（skills + server.py），重启 |
| hermes / deepseek-tui | 同步 `server.py`，重启 |

确认点：用户侧不再调用任何 `/documents` API（后端访问日志核对）。

## 阶段 3：后端删除（ADR-0010 主体）

### 3.1 删除清单（已盘点）

1. **schema.sql**：删 `documents` / `chunks` / `chunk_entities` 三表 + 索引 + 注释
   （约 153-209、305-322 行区域）；
2. **服务**：删 `document_store.py`(952) / `document_processor.py`(483) /
   `document_chunker.py`(424) / `chunking/` 包 10 文件(~1840)；
3. **路由**：删 `/documents*` 五条路由；
4. **召回通道**：`context_inject_service.py` 摘除 chunks 通道；`memories.py` hybrid search 清理；
5. **引用清理**：`stats.py` / `debug.py` / `client.py` / `models/api.py` /
   `llm_entity_extraction.py` / `semantic_dedup_service.py` / `recall_trace_service.py` /
   `asmr_entity_types.py` 中 document/chunk 引用；
6. **测试**：删 `test_document_deduplication.py` / `test_v2/test_document_chunker.py` /
   `test_v2/test_chunks_search.py` / `test_chunking_performance.py`；
7. **根目录文档**（当前为真，必须同步改，否则知识库持续注入过时内容）：
   - `ENTITY_DESIGN.md`：删"文档与分块模型"§3、chunk 实体来源、注入通道中的 chunks；
   - `MEMORY_FLOW.md`：删文档知识表行、chunks 通道、注入顺序中的文档分区；
   - `ARCHITECTURE.md`：删 document_store 模块条目、chunks 通道描述；
   - `README.md`：修正 34/38 行"文档记忆/全文搜索"叙事（顺带完成 ADR-0001 剩余项）。

### 3.2 验证

- 单元 + 集成测试通过（按 TESTING.md 三层分级，忽略需 VOLC_API_KEY 的脚本）；
- 起服务实测：`/context-inject` 返回 channels 无 chunks、`/documents*` 返回 404、
  stats/debug 正常。

### 3.3 数据删除（最后一步，单独执行）

- 部署库手动 `DROP TABLE IF EXISTS documents, chunks, chunk_entities CASCADE;`；
- 执行时机：阶段 3 代码上线且用户确认无回滚/导出需求后。

## 收尾检查点

1. STATUS.md：ADR 实施跟踪表 ADR-0010 登记"已实现" + commit；活跃任务表更新；
2. ISSUES.md：确认 MR-001/002/003/005/007 关闭原因指向实施 commit（决策已关，实施后补记录）；
3. ADR-0009 检查点：服务可用后检索修正"文档知识闭环/文档支柱"类过时记忆；
4. MR-019 保持冻结；PROJECT_PLAN 已按 ADR-0010 改写（2026-08-13），无需再动。

## 未决问题

- 阶段 2 用户升级的确认方式（后端访问日志核对 / 用户口头确认），实施时定。
