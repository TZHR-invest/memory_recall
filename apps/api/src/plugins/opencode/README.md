# Memory Recall OpenCode Plugin

为 OpenCode 提供持久化记忆能力，支持跨会话上下文召回。

## 安装

```bash
# 1. 解压
tar -xzf memory-recall-opencode-1.3.1.tar.gz

# 2. 进入目录并运行安装
cd memory-recall-opencode
node dist/cli.js install

# 3. 重启 OpenCode（依赖会自动安装）
```

## 目录结构

```
~/.config/opencode/
├── opencode.json              # 插件注册
├── package.json               # 依赖声明
├── plugins/
│   └── memory-recall-opencode/  # 本插件
│       ├── dist/
│       └── package.json
├── command/
│   └── memory-init.md
└── memory-recall.jsonc        # 插件配置
```

## 安装流程

1. 插件文件 → `~/.config/opencode/plugins/memory-recall-opencode/`
2. 依赖声明 → `~/.config/opencode/package.json`
3. 插件注册 → `~/.config/opencode/opencode.json`（使用 `./plugins/memory-recall-opencode`）
4. 重启 OpenCode → 自动安装依赖

## 开发模式

```bash
cd apps/api/src/plugins/opencode
bun run build
node dist/cli.js install --dev
```

## 命令

```bash
node dist/cli.js install           # 安装插件
node dist/cli.js install --dev     # 开发模式
node dist/cli.js uninstall         # 卸载插件（交互式）
node dist/cli.js uninstall --force # 卸载插件（无需确认）
node dist/cli.js status            # 查看状态
```

## 系统要求

- Node.js 18+ 或 Bun

## 工具

| 模式 | 说明 |
|------|------|
| `add` | 添加记忆 |
| `search` | 搜索记忆 |
| `profile` | 获取用户画像 |
| `list` | 列出记忆 |
| `forget` | 删除记忆 |
| `import-docs` | 导入项目文档 |
| `status` | 查询异步任务状态 |
| `retry` | 重试失败任务 |

## 初始化项目记忆

安装插件后，在 OpenCode 中运行以下命令初始化项目记忆：

```
/memory-init
```

这将：
1. 导入项目文档（README.md、docs/*.md 等）
2. 分析代码库结构和技术栈
3. 保存项目知识到记忆系统

## 重新导入文档

如果需要更新已导入的文档（例如分块参数变更后），使用强制重新导入：

```
memory-recall(mode: "import-docs", force: true)
```

这将重新扫描并导入所有匹配的文档文件，覆盖已有的分块数据。

## 配置文件

`~/.config/opencode/memory-recall.jsonc`

### 语义去重配置

插件支持基于 embedding 相似度的语义去重，避免上下文中出现语义相似但表述不同的重复内容。

```json
{
  "semanticDedup": {
    "enabled": true,
    "threshold": 0.85,
    "maxBatchSize": 50
  }
}
```

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `enabled` | `true` | 是否启用语义去重 |
| `threshold` | `0.85` | 相似度阈值（0.0-1.0），高于此值视为重复 |
| `maxBatchSize` | `50` | 批量 embedding 计算的最大数量 |

#### 阈值选择建议

- **严格模式 (0.90)**：仅去除高度相似的重复，适合精确匹配场景
- **平衡模式 (0.85)**：默认值，平衡去重效果和保留率
- **宽松模式 (0.75)**：更激进去重，可能误删相关但不完全相同的内容

#### 去重优先级

当检测到语义重复时，按以下优先级保留内容：

1. **profile** (最高) - 用户画像永久特征
2. **projectMemories** - 项目记忆
3. **userMemories** - 用户记忆
4. **chunks** (最低) - 文档片段

#### 分层去重策略

1. **第一层**：哈希去重（精确匹配，O(1) 时间复杂度）
2. **第二层**：语义去重（embedding 相似度，仅处理第一层未过滤的内容）

#### 性能影响

语义去重会增加约 50-200ms 的注入延迟，但可通过以下方式优化：
- 批量 embedding 计算
- LRU 缓存（1000 条，避免重复计算）
- 失败时自动降级到哈希去重

## 故障排除

### 上下文注入变慢

**症状**：每条消息处理时间增加 100-300ms

**可能原因**：
1. 语义去重启用，增加了 embedding 计算时间
2. 后端 embedding API 响应慢

**解决方案**：
```json
{
  "semanticDedup": {
    "enabled": false
  }
}
```

### 仍然出现重复内容

**症状**：上下文中有语义相似但表述不同的内容

**可能原因**：
1. 阈值设置过高（0.90+）
2. 语义相似但 embedding 差异较大

**解决方案**：
```json
{
  "semanticDedup": {
    "threshold": 0.80
  }
}
```

### 预期内容被误删

**症状**：某些内容应该出现但没有

**可能原因**：
1. 阈值设置过低，误判为重复
2. 优先级顺序导致被过滤

**解决方案**：
1. 提高阈值到 0.90
2. 检查内容是否属于更高优先级的来源

### Embedding API 失败

**症状**：日志中出现 "Semantic deduplication failed, falling back to hash-only"

**可能原因**：
1. 后端 API 未启动
2. API Key 无效
3. 网络超时

**解决方案**：
1. 确认后端服务运行：`curl http://localhost:8000/health`
2. 检查 API Key 配置
 3. 系统会自动降级到哈希去重，不影响正常使用

## 异步写入队列

### 概述

v5.2 新增异步写入队列功能，将写入操作（添加记忆、导入文档）放入后台队列执行，显著降低工具响应时间：

**优势**：
- 工具响应时间：200-500ms → < 10ms
- 自动重试：失败任务自动重试，确保数据不丢失
- 可观测性：随时查询任务状态和错误信息

### 配置

```json
{
  "asyncQueue": {
    "enabled": true,
    "maxConcurrency": 3,
    "maxSize": 100,
    "taskTimeoutMs": 120000,
    "retryPolicy": {
      "maxRetries": 3,
      "initialDelay": 1000,
      "maxDelay": 10000,
      "backoffMultiplier": 2
    }
  }
}
```

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `asyncQueue.enabled` | `false` | 启用异步队列 |
| `asyncQueue.maxConcurrency` | `3` | 最大并发任务数 |
| `asyncQueue.maxSize` | `100` | 队列最大大小 |
| `asyncQueue.taskTimeoutMs` | `120000` | 任务执行超时（毫秒），适合 LLM 调用场景 |
| `asyncQueue.retryPolicy.maxRetries` | `3` | 最大重试次数 |
| `asyncQueue.retryPolicy.initialDelay` | `1000` | 初始重试延迟（毫秒） |
| `asyncQueue.retryPolicy.maxDelay` | `10000` | 最大重试延迟（毫秒） |
| `asyncQueue.retryPolicy.backoffMultiplier` | `2` | 退避乘数 |

### 使用方法

启用异步队列后，`add` 和 `import-docs` 模式会立即返回任务 ID：

```json
// 添加记忆
memory-recall(mode: "add", content: "我是素食主义者")

// 返回
{
  "success": true,
  "message": "Memory queued for async processing",
  "taskId": "task_abc123",
  "scope": "project"
}
```

### 查询任务状态

使用 `status` 模式查询任务状态：

```json
// 查询单个任务
memory-recall(mode: "status", taskId: "task_abc123")

// 返回
{
  "success": true,
  "task": {
    "id": "task_abc123",
    "type": "add",
    "status": "success",
    "retryCount": 0,
    "maxRetries": 3,
    "createdAt": 1712345678000,
    "completedAt": 1712345678500
  }
}

// 查询所有任务
memory-recall(mode: "status")

// 返回
{
  "success": true,
  "count": 5,
  "pending": 2,
  "running": 1,
  "successCount": 1,
  "failed": 1,
  "tasks": [...]
}
```

### 重试失败任务

使用 `retry` 模式重试失败的任务：

```json
memory-recall(mode: "retry", taskId: "task_abc123")

// 返回
{
  "success": true,
  "message": "Task requeued for execution",
  "taskId": "task_abc123"
}
```

### 任务状态说明

| 状态 | 说明 |
|------|------|
| `pending` | 等待执行 |
| `running` | 正在执行 |
| `success` | 执行成功 |
| `failed` | 执行失败（达到最大重试次数） |

### 重试延迟计算

使用指数退避算法计算重试延迟：

```
第 1 次重试: 1s
第 2 次重试: 2s
第 3 次重试: 4s
第 4 次重试: 8s
第 5 次重试: 10s (达到 maxDelay 上限)
```

### 注意事项

1. **v1 版本限制**：当前版本为纯内存队列，进程退出时未完成任务会丢失。后续版本将添加持久化支持。

2. **向后兼容**：默认关闭异步队列，需要显式配置 `asyncQueue.enabled: true` 启用。

3. **队列满时**：当队列中的任务数达到 `maxSize` 时，新任务会被拒绝，返回错误 `"Queue is full"`。

## 后端语义去重

### 概述

v5.1 新增后端语义去重功能，通过 `/context-inject` API 统一处理上下文注入：

**优势**：
- 减少 API 调用次数：4 次 → 1-2 次
- 复用数据库 embedding，无需前端计算
- 降低延迟：300-500ms → 150-250ms

### 配置

```json
{
  "useBackendDedup": true,
  "semanticDedup": {
    "enabled": true,
    "threshold": 0.85
  }
}
```

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `useBackendDedup` | `true` | 使用后端 API 进行去重 |
| `semanticDedup.enabled` | `true` | 启用语义去重 |
| `semanticDedup.threshold` | `0.85` | 去重阈值 |

### 工作流程

1. 前端调用 `/context-inject` API
2. 后端获取用户画像、记忆、文档片段
3. 从数据库读取已有 embedding
4. 基于优先级进行语义去重
5. 返回格式化的上下文

### 回退机制

当后端 API 失败时，自动切换到前端去重逻辑：
- 使用前端 `semantic-dedup.ts` 进行去重
- 调用 `/embed` API 计算 embedding
- 保证系统可靠性

## 许可证

MIT
