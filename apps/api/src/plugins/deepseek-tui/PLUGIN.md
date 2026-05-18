---
name: memory-recall-deepseek-tui
description: Persistent memory plugin for DeepSeek TUI via MCP protocol. Provides 15 tools for memory storage, semantic search, user profiles, knowledge graph, and document management.
status: active
---

# Memory Recall Plugin for DeepSeek TUI

通过 MCP 协议在 DeepSeek TUI 中集成 Memory Recall 记忆系统。

## 功能

- **记忆存储**: 存储用户偏好、项目知识、经验教训
- **语义搜索**: 向量相似度检索
- **记忆管理**: 更新、删除、恢复、历史版本追踪
- **用户画像**: static（永久特征）+ dynamic（近期活动）
- **知识图谱**: 双重图谱（记忆演进 + 实体关系）
- **文档管理**: 导入、分块、搜索文档

## 15 个工具

add, search, profile, forget, list, update, restore,
import-docs, list-docs, read-doc, delete-doc, hybrid-search,
extract-memory, context-inject, status

## 激活方式

```bash
# 1. 运行安装脚本
cd apps/api/src/plugins/deepseek-tui
./install.sh

# 2. 重启 DeepSeek TUI
```

## 配置

编辑 `~/.deepseek/plugins/memory-recall/config.jsonc`

## 环境变量（优先级高于配置文件）

- `MEMORY_RECALL_BASE_URL`, `MEMORY_RECALL_API_KEY`
- `MEMORY_RECALL_USER_TAG`, `MEMORY_RECALL_PROJECT_TAG`
