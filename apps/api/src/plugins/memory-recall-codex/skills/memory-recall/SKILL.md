---
name: memory-recall
description: 跨会话持久记忆。通过 Memory Recall MCP 工具在任务开始前召回相关记忆、任务结束后沉淀关键信息。当用户询问"之前讨论过/记得吗"、需要项目历史与个人偏好，或开始新任务需要已有上下文时使用。
---

# Memory Recall Skill

你已接入 Memory Recall 记忆系统，可通过 MCP 工具管理跨会话记忆。

工具前缀：`mcp__memory_recall__`（如 `mcp__memory_recall__add`）。

## 🚨 强制行为规则

**收集上下文时，memory-recall 是第一选择。**

### 优先级顺序（从高到低）
1. **检查已注入上下文**（用户消息中的信息）
2. **调用 memory-recall**（`mcp__memory_recall__context_inject` / `mcp__memory_recall__search`，< 1 秒）
3. **最后才使用**：读文件、grep、探索（30-60 秒）

### 必须先调用 memory-recall 的场景
- 了解用户偏好、约束、习惯
- 查找之前讨论过的功能或决策
- 回顾项目架构、技术栈、设计决策
- 执行操作前（部署、清理、变更）：检查记忆中是否有现成脚本或注意事项
- 用户问"记得之前..."、"之前讨论过"等
- 新任务开始时：先 `mcp__memory_recall__context_inject` 召回相关记忆再动手

### 用户画像注入（新会话必做）

**每个新会话的首次 `mcp__memory_recall__context_inject` 调用必须传 `injectProfile: true`**
（同时建议 `maxMemories: 8`），一次性获取用户画像（static 永久特征 + dynamic 近期活动）。
同一会话后续调用保持 `injectProfile: false`（默认），避免重复注入浪费上下文。
若用户提到新偏好/特征，任务结束时用 `add` 存到 user 范围，画像会自动更新。

### 任务完成后必须存储
- 重要决策 → `mcp__memory_recall__add` with `type: "architecture"`
- 错误解决方案 → `mcp__memory_recall__add` with `type: "error-solution"`
- 用户偏好 → `mcp__memory_recall__add` with `type: "preference"`, `scope: "user"`
- 经验教训 → `mcp__memory_recall__add` with `type: "learned-pattern"`
- 项目配置/技术栈 → `mcp__memory_recall__add` with `type: "project-config"`

### scope 语义（user / project）

- `user`：跨项目共享（用户偏好、全局事实），存时用 `scope: "user"`
- `project`：项目范围（当前 Codex 插件所有项目共用一个 project 池，因为 MCP server 无法感知工作目录；需要隔离时在内容里标注项目名，如 `【项目X】...`）

### 记忆维护

- 已有记忆过时/需要修正 → `mcp__memory_recall__update`（版本化：旧版本自动标记，可追溯历史）
- **结论/行为变更后主动维护**：任务改变了某个结论、配置或行为规则时，收尾前用
  `search` 检索相关主题，若旧记忆与新结论冲突或过时，立即 `update` 修正（不要只
  新增一条新的，旧结论会继续误导后续召回）。注入上下文里带「记录于 N 天前」标注的
  记忆尤其要核对是否仍成立（ADR-0009）。
- 记忆错误/不再需要 → `mcp__memory_recall__forget`（软删除，可恢复）
- 会话较长时 → 用 `mcp__memory_recall__extract_memory` 从关键对话摘要提取值得保存的记忆，再 `add` 入库：
  `extract_memory summary="<本次会话的关键结论、决策、用户偏好摘要>"`（返回建议保存列表，逐条 `add`）
- 存储前先 `search` 查重：同一事实已存在时用 `update` 补充而不是重复 `add`（避免记忆冗余）

## 工具对照

| 场景 | 工具 | 说明 |
|------|------|------|
| 完整召回 | `mcp__memory_recall__context_inject` | 画像+记忆+文档+双重图谱，任务开始首选 |
| 搜记忆 | `mcp__memory_recall__search` | 语义搜索 |
| 查画像 | `mcp__memory_recall__profile` | 用户 static + dynamic |
| 存储 | `mcp__memory_recall__add` | 默认异步，秒回 |
| 更新 | `mcp__memory_recall__update` | 版本化更新（建版本链） |
| 删除 | `mcp__memory_recall__forget` | 软删除，可恢复 |
| 文档搜索 | `mcp__memory_recall__hybrid_search` | 记忆+文档混合 |
| 导入文档 | `mcp__memory_recall__import_docs` | 项目文档入库分块 |
| 会话提取 | `mcp__memory_recall__extract_memory` | 从摘要提取值得保存的记忆 |
| 状态 | `mcp__memory_recall__status` | API 连通性与统计 |


## 初始化项目记忆（首次使用新项目）

手动执行以下流程初始化记忆：

```
mcp__memory_recall__import_docs  content="<粘贴 README.md 内容>"  title="README"
mcp__memory_recall__add  content="<项目技术栈和核心架构>"  type="project-config"
mcp__memory_recall__add  content="<构建、测试、部署方式>"  type="learned-pattern"
```

优先导入可自动分块检索的项目文档（`import_docs`，docType 可选 markdown/code）：
- README.md、AGENTS.md、CHANGELOG.md、docs/*.md —— 让 `context_inject` 的文档片段检索能覆盖项目知识

## 核心原则

**先问记忆，再找代码。记忆里没有，才去探索。**
