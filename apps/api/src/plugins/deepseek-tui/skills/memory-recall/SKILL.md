---
name: memory-recall
description: Persistent memory across sessions via Memory Recall MCP tools. Always check memory before exploring code.
metadata:
  short-description: Cross-session persistent memory via MCP
---

# Memory Recall Skill

你已接入 Memory Recall 记忆系统，可通过 MCP 工具 `mcp_memory-recall_*` 管理跨会话记忆。

## 🚨 强制行为规则

**收集上下文时，memory-recall 是第一选择。**

### 优先级顺序（从高到低）

1. **检查已注入上下文**（用户消息中的信息）
2. **调用 memory-recall**（`context-inject` / `profile` + `search`，< 1 秒）
3. **最后才使用**：读文件、grep、探索（30-60 秒）

### 必须先调用 memory-recall 的场景

- 了解用户偏好、约束、习惯
- 查找之前讨论过的功能或决策
- 回顾项目架构、技术栈、设计决策
- 执行操作前（部署、清理、变更）：检查记忆中是否有现成脚本或注意事项
- 用户问"记得之前…"、"之前讨论过"等

### 任务完成后必须存储

- 重要决策 → `mcp_memory-recall_add` with `type: "architecture"`
- 错误解决方案 → `mcp_memory-recall_add` with `type: "error-solution"`
- 用户偏好 → `mcp_memory-recall_add` with `type: "preference"`, `scope: "user"`
- 经验教训 → `mcp_memory-recall_add` with `type: "learned-pattern"`

## 全部工具（15 个）

| 场景 | 工具 | 说明 |
|------|------|------|
| 存储记忆 | `mcp_memory-recall_add` | 默认异步，秒回 |
| 语义搜索 | `mcp_memory-recall_search` | 向量相似度检索 |
| 查用户画像 | `mcp_memory-recall_profile` | static + dynamic 记忆 |
| 软删除 | `mcp_memory-recall_forget` | 可恢复 |
| 列出记忆 | `mcp_memory-recall_list` | 按 scope 列出 |
| 更新记忆 | `mcp_memory-recall_update` | 修改内容 |
| 恢复记忆 | `mcp_memory-recall_restore` | 取消软删除 |
| 混合搜索 | `mcp_memory-recall_hybrid-search` | 记忆+文档混合 |
| 提取记忆 | `mcp_memory-recall_extract-memory` | 从摘要中提取 |
| 完整召回 | `mcp_memory-recall_context-inject` | 画像+记忆+文档+图谱 |
| 状态检查 | `mcp_memory-recall_status` | API 连通性与版本 |

## 初始化项目记忆（首次使用）

在新项目中手动执行：

```
mcp_memory-recall_add  content="<技术栈和核心架构>"  type="project-config"
mcp_memory-recall_add  content="<构建、测试、部署方式>"  type="learned-pattern"
```

## 配置文件

MCP 连接配置位于 `~/.deepseek/plugins/memory-recall/config.jsonc`。

## 核心原则

**先问记忆，再找代码。记忆里没有，才去探索。**
