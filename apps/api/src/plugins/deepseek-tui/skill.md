---
name: memory-recall
description: Persistent memory across sessions via Memory Recall MCP tools.
---

# Memory Recall Skill

你已接入 Memory Recall 记忆系统，可通过 MCP 工具 `mcp_memory-recall_*` 管理跨会话记忆。

## 🚨 强制行为规则

**收集上下文时，memory-recall 是第一选择。**

### 优先级顺序（从高到低）
1. **检查已注入上下文**（用户消息中的信息）
2. **调用 memory-recall**（`profile` + `search` / `context-inject`，< 1 秒）
3. **最后才使用**：读文件、grep、探索（30-60 秒）

### 必须先调用 memory-recall 的场景
- 了解用户偏好、约束、习惯
- 查找之前讨论过的功能或决策
- 回顾项目架构、技术栈、设计决策
- 执行操作前（部署、清理、变更）：检查记忆中是否有现成脚本或注意事项
- 用户问"记得之前..."、"之前讨论过"等

### 任务完成后必须存储
- 重要决策 → `mcp_memory-recall_add` with `type: "architecture"`
- 错误解决方案 → `mcp_memory-recall_add` with `type: "error-solution"`
- 用户偏好 → `mcp_memory-recall_add` with `type: "preference"`, `scope: "user"`
- 经验教训 → `mcp_memory-recall_add` with `type: "learned-pattern"`

## 工具对照

| 场景 | 工具 | 说明 |
|------|------|------|
| 搜记忆 | `mcp_memory-recall_search` | 语义搜索 |
| 查画像 | `mcp_memory-recall_profile` | 用户 static + dynamic |
| 完整召回 | `mcp_memory-recall_context-inject` | 画像+记忆+文档+图谱 |
| 存储 | `mcp_memory-recall_add` | 默认异步，秒回 |
| 文档搜索 | `mcp_memory-recall_hybrid-search` | 记忆+文档混合 |
| 删除 | `mcp_memory-recall_forget` | 软删除，可恢复 |
| 状态 | `mcp_memory-recall_status` | API 连通性 |

## 初始化项目记忆（首次使用）

在一个新项目中，手动执行以下流程初始化记忆：

```
mcp_memory-recall_import-docs  content="<粘贴 README.md 内容>"  title="README"
mcp_memory-recall_add  content="<项目技术栈和核心架构>"  type="project-config"
mcp_memory-recall_add  content="<构建、测试、部署方式>"  type="learned-pattern"
```

每次完成重要任务后，用 `mcp_memory-recall_add` 保存关键决策和教训。

## 核心原则

**先问记忆，再找代码。记忆里没有，才去探索。**
