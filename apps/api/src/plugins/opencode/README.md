# Memory Recall OpenCode Plugin

为 OpenCode 提供持久化记忆能力，支持跨会话上下文召回和项目隔离。

## 安装

```bash
# 1. 解压
tar -xzf memory-recall-opencode-1.8.2.tar.gz

# 2. 进入目录并运行安装
cd memory-recall-opencode
node dist/cli.js install

# 3. 重启 OpenCode（依赖会自动安装）
```

安装时会自动：
1. 连接后端 API 验证 API Key
2. 获取 `keyId` 并写入配置
3. 自动生成项目隔离的 container_tag

## 压缩兼容性说明

本插件在压缩时只向 `output.context` 追加 AI guidance 与项目记忆，不设置 `output.prompt`、
不注册 autocontinue。若同时启用任何设置 `output.prompt` 的压缩插件/开关
（如 Oh-My-OpenCode 的 customCompactionPrompt），本插件的压缩注入会失效。

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

**推荐：在 opencode 配置中直接指向源码，无需构建、无需安装。**

opencode 的插件加载器（Bun 运行时）原生支持直接加载 TypeScript 源码文件，因此开发时可以绕过构建和安装，改 `src/*.ts` 保存后重启 opencode 即生效：

```jsonc
// ~/.config/opencode/opencode.jsonc（全局）或项目 .opencode/opencode.jsonc（项目级）
"plugin": [
  "file:///Users/wusisu/repo/memory_recall/apps/api/src/plugins/opencode/src/index.ts"
]
```

- 路径必须是**绝对路径**（`file://` URL 或绝对路径均可），opencode 会将其解析为插件入口
- 源码中的相对 import（`./config`、`./client` 等）由 Bun 直接处理，无需构建
- 不需要 `dist/`、不需要 node_modules 解析链、不需要软链
- 同时启用多个项目时，可分别指向各自仓库的源码文件

> **为什么不推荐 `install --dev`（软链模式）**：旧版脚本用软链把插件目录连到 `~/.config/opencode/node_modules` 并依赖那里的 `@opencode-ai/plugin`（版本陈旧）。opencode 加载插件前会 `realpathSync` 解析软链，再从真实路径（仓库内）向上查找依赖——软链路径侧的 node_modules 根本不会被命中，导致 `Cannot find module '@opencode-ai/plugin'`。源码直连没有这个问题，且省去构建步骤。

## 发布 / 安装到用户环境

发布或安装给其他用户时，构建并复制到 opencode 插件目录：

```bash
cd apps/api/src/plugins/opencode
bun run build
node dist/cli.js install        # 生产模式：复制 dist + package.json 到 ~/.config/opencode/plugins/
```

- `dist/index.js` 外部引用 `@opencode-ai/plugin` / `@opencode-ai/sdk`（与 host opencode 版本天然对齐），安装时会自动在插件目录执行 `bun install`（或 `npm install`）安装运行时依赖
- 同时会把依赖声明到 `~/.config/opencode/package.json` 作为兜底（OpenCode 启动时自动安装）
- 若依赖安装失败，安装向导会给出提示，插件仍会注册，重启 OpenCode 后由兜底机制补齐

> `node dist/cli.js install --dev` 是遗留的软链安装方式，**已废弃不再执行**，仅打印提示。开发请使用上面的「开发模式」章节。

## 后续计划：发布到 npm

**本次迭代仍以 `node dist/cli.js install` 方式分发**（已确认，不改动）。将 `memory-recall-opencode` 发布到 npm 是后续计划，落地后用户安装方式简化为 opencode 配置直接引用：

```jsonc
// ~/.config/opencode/opencode.jsonc
"plugin": ["memory-recall-opencode"]
```

opencode 启动时自动从 npm 安装插件到 `~/.cache/opencode/packages/`（arborist），用户无需下载 tar 包、无需运行 cli install。

**版本管理约定**：

- 语义化版本：`package.json` `version` 随功能变更递增（当前 1.8.2）
- `prepublishOnly` 已配置（`bun run build`），发布前自动构建
- `files` 字段已限定发布内容：`dist/`、`dist/i18n`、`README.md`
- 发布命令（插件目录下执行）：`npm publish`（或 `bun publish`）

**发布后需同步更新**：本文档「安装」章节改为用户配置方式；AGENTS.md 安装说明同步为 npm 安装。

**依赖契约不变**：仍 `--external @opencode-ai/plugin @opencode-ai/sdk`，运行时依赖由宿主 opencode 安装（见下节）。

## 依赖架构

本插件的依赖策略遵循 opencode 官方推荐（[opencode.ai/docs/plugins](https://opencode.ai/docs/plugins/) 与 v2 文档 "include every runtime import in `dependencies`"）及生态主流做法：

**源码只直接依赖 2 个包**（`package.json` `dependencies`）：

| 包 | 使用位置 | 方式 |
|---|---|---|
| `@opencode-ai/plugin` | `src/tool.ts` | 运行时：`tool()` 注册工具 + `tool.schema.*` 定义参数 schema |
| `@opencode-ai/sdk` | （无源码引用） | 声明依赖，供宿主对齐版本 |

**关键约定**：

1. **参数 schema 一律用 `tool.schema.*`，不要直接 `import { z } from "zod"`**。`tool.schema` 是官方暴露的 zod 命名空间（`typeof z`），它随 `@opencode-ai/plugin` 使用 zod v4，与宿主 opencode 同实例。直接依赖 zod（尤其低版本）会产生双 zod 实例，导致 schema 校验崩溃（社区真实踩坑：oh-my-opencode-slim commit `e5e1f9b`，`TypeError: n._zod.def is not an object`）。
2. **构建时 `--external @opencode-ai/plugin --external @opencode-ai/sdk`，不打包**。opencode 加载 npm 插件时会自动安装插件及其生产依赖（`@npmcli/arborist`，缓存于 `~/.cache/opencode/packages/`），运行时从插件自身 node_modules 解析，与宿主版本天然对齐。打包会引入 ~1MB 的 effect/zod 副本与双实例风险，且任何知名插件都不这么做。

> **缓存目录说明（2026-08 定稿）**：官方文档（opencode.ai/docs/plugins）仍写 "npm 插件由 Bun 启动时自动安装，缓存于 `~/.cache/opencode/node_modules/`"——该表述描述的是 **v1.4.3 之前的旧机制**（`bun add --cwd ~/.cache/opencode` 扁平安装，版本写进缓存目录顶层 package.json）。源码自 commit `c9326fc19`（2026-04-01，首个含此机制的 release v1.4.3）起一律用 `@npmcli/arborist` 按包安装到 `~/.cache/opencode/packages/<pkg>/`（每包独立 node_modules + package-lock.json），dev 分支（2026-08-12）与此一致，**以源码为准**。本机 `~/.cache/opencode/node_modules/`（bun.lock 4月17日）即旧机制遗留产物，当前版本不会再写入。
3. **zod/effect 不直接声明**：它们是 `@opencode-ai/plugin` 的传递依赖，由宿主安装。

## 命令

```bash
node dist/cli.js install           # 安装插件
node dist/cli.js install --dev     # 已废弃，不再执行（仅打印提示）
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
| `search` | 搜索记忆和文档（默认启用 Memory Graph） |
| `profile` | 获取用户画像 |
| `list` | 列出记忆 |
| `forget` | 删除记忆 |
| `import-docs` | 导入项目文档 |
| `status` | 查询异步任务状态 |
| `retry` | 重试失败任务 |

## Search 图谱召回增强

### 概述

`search` 模式支持图谱召回增强，可在向量搜索基础上启用 **Memory Graph**（记忆演进关系）和 **Entity Graph**（实体关系网络）召回。

### 双图谱召回架构

```
┌─────────────────────────────────────────────────────────────┐
│                    三层召回系统                               │
├─────────────────────────────────────────────────────────────┤
│  第1层: Vector Search (50%)                                 │
│  └─ 语义相似度匹配（embedding 余弦相似度）                    │
│                                                             │
│  第2层: Memory Graph (30%)  ← enableMemoryGraph             │
│  └─ 遍历记忆演进关系                                         │
│     ├─ updates: 信息更新链                                   │
│     ├─ extends: 信息补充                                     │
│     └─ derives: 信息推断                                     │
│                                                             │
│  第3层: Entity Graph (20%)  ← enableEntityGraph             │
│  └─ 遍历实体关系网络                                         │
│     ├─ friend/colleague: 人物关系                           │
│     ├─ works_at/lives_at: 工作/居住                         │
│     └─ prefers/uses: 偏好/使用                              │
└─────────────────────────────────────────────────────────────┘
```

### 参数说明

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `enableMemoryGraph` | `true` | 启用 Memory Graph 召回（信息演进链） |
| `enableEntityGraph` | `false` | 启用 Entity Graph 召回（实体关系网络） |
| `graphDepth` | `2` | 图遍历深度（最大 5） |
| `graphNodes` | `5` | 每层最大节点数（最大 20） |

### 使用示例

**默认搜索（向量 + Memory Graph + 文档）**：
```json
memory-recall(mode: "search", query: "项目架构")
```

**禁用图谱（仅向量搜索）**：
```json
memory-recall(
  mode: "search", 
  query: "用户偏好",
  enableMemoryGraph: false
)
```

**完整三层召回**：
```json
memory-recall(
  mode: "search",
  query: "张三的朋友",
  enableMemoryGraph: true,
  enableEntityGraph: true,
  graphDepth: 2
)
```

### 返回结果

**默认返回（记忆 + 文档）**：
```json
{
  "success": true,
  "query": "项目架构",
  "count": 9,
  "results": [
    { "id": "mem_abc123", "content": "...", "type": "memory", "scope": "project" },
    { "id": "chk_xyz789", "content": "...", "type": "document", "scope": "project" }
  ],
  "breakdown": {
    "memories": 4,
    "documents": 5
  },
  "graphRecall": {
    "enabled": true,
    "memoryGraph": true,
    "entityGraph": false,
    "depth": 2,
    "nodes": 5
  },
  "stats": {
    "totalItems": 14,
    "afterDedup": 12,
    "dedupedCount": 2
  }
}
```

### 性能对比

| 模式 | 延迟 | 召回层 | 适用场景 |
|------|------|--------|---------|
| 默认（Memory Graph） | ~150ms | 向量 + 记忆演进 + 文档 | 通用搜索 |
| 禁用图谱 | ~50ms | 仅向量搜索 | 精确匹配 |
| Entity Graph | ~200ms | 向量 + 实体关联 | 需要关系推理 |
| 完整召回 | ~250ms | 三层召回 | 复杂查询 |

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

### 基础配置

```json
{
  "apiKey": "rk_live_xxx",
  "baseUrl": "http://localhost:8000",
  "userName": "YourName",
  "keyId": "<your-key-id>",
  
  "similarityThreshold": 0.4,
  "maxMemories": 5,
  "maxProjectMemories": 10,
  "injectionStrategy": "smart"
}
```

### 项目隔离（v1.7.9 新增）

插件使用 `keyId` 自动生成项目隔离的 container_tag：

| 类型 | container_tag 格式 | 说明 |
|------|-------------------|------|
| 用户画像 | `{keyId}` | 跨项目共享 |
| 用户记忆 | `{keyId}` | 跨项目共享 |
| 用户文档 | `{keyId}` | 跨项目共享（v5.2 新增） |
| 项目记忆 | `{keyId}_project-{项目名}` | 按项目隔离 |
| 项目文档 | `{keyId}_project-{项目名}` | 按项目隔离 |

**示例**：
```
keyId: <your-key-id>

memory_recall 项目:
  user_tag: <your-key-id>
  project_tag: <your-key-id>_project-memory_recall

shuihu_card_game 项目:
  user_tag: <your-key-id>
  project_tag: <your-key-id>_project-shuihu_card_game
```


### 语义去重配置

插件支持基于 embedding 相似度的语义去重，避免上下文中出现语义相似但表述不同的重复内容。

```json
{
  "semanticDedup": {
    "enabled": true,
    "threshold": 0.85
  }
}
```

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `enabled` | `true` | 是否启用后端语义去重 |
| `threshold` | `0.85` | 相似度阈值（0.0-1.0），高于此值视为重复 |

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
| `asyncQueue.enabled` | `true` | 启用异步队列（v5.2.2 默认启用） |
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
- 减少 API 调用次数：4 次 → 1 次（v5.2 优化）
- 复用数据库 embedding，无需前端计算
- 降低延迟：300-500ms → 100-200ms
- 支持用户文档和项目文档

### v5.2 优化：一次 API 调用

v5.2 进一步优化，支持一次 API 调用完成所有召回：

```json
POST /context-inject
{
  "user_tag": "{keyId}",
  "project_tag": "{keyId}_project-{项目名}",
  "query": "用户输入",
  "config": {
    "inject_profile": true,
    "max_memories": 5,
    "max_chunks": 3
  }
}
```

**返回**：
```json
{
  "context": "格式化后的上下文",
  "sources": {
    "profile": ["用户画像"],
    "user_memories": [{"id": "...", "content": "..."}],
    "memories": [{"id": "...", "content": "..."}],
    "user_chunks": [{"id": "...", "content": "..."}],
    "chunks": [{"id": "...", "content": "..."}]
  },
  "stats": {
    "profile_count": 5,
    "user_memories_count": 3,
    "project_memories_count": 10,
    "chunks_count": 3
  }
}
```

### 配置

```json
{
  "semanticDedup": {
    "enabled": true,
    "threshold": 0.85
  }
}
```

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `semanticDedup.enabled` | `true` | 启用后端语义去重 |
| `semanticDedup.threshold` | `0.85` | 去重阈值 |

### 工作流程

1. 前端调用 `/context-inject` API，传入 `user_tag` 和 `project_tag`
2. 后端从 user_tag 获取：用户画像、用户记忆、用户文档
3. 后端从 project_tag 获取：项目记忆、项目文档
4. 从数据库读取已有 embedding
5. 基于优先级进行语义去重
6. 返回格式化的上下文

### 单通道失败优雅降级

`/context-inject` 单通道（profile / memories / chunks）失败时返回成功通道的部分结果，
并在 `failed_channels` 中标记失败通道；仅当全部通道失败或请求级错误时才返回 500。

## 许可证

MIT
