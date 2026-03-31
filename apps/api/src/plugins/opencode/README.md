# Memory Recall OpenCode Plugin

为 OpenCode 提供持久化记忆能力，支持跨会话上下文召回。

## 快速开始

### 安装

```bash
bunx memory-recall-opencode install
```

安装脚本会引导您完成配置：

1. **现有用户**：输入 API Key 和用户信息
2. **新用户**：自动注册并获取 API Key

### 前置要求

- Memory Recall API 服务正在运行
- Bun 运行时环境

## 配置

配置文件位置：`~/.config/opencode/memory-recall.jsonc`

### 配置选项

| 选项 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `apiKey` | string | - | API 密钥（必需） |
| `baseUrl` | string | `http://localhost:8000` | API 服务地址 |
| `userName` | string | `User` | 用户名 |
| `userContainerTag` | string | null | 用户容器标签 |
| `projectContainerTag` | string | null | 项目容器标签 |
| `similarityThreshold` | number | `0.6` | 相似度阈值 |
| `maxMemories` | number | `5` | 最大召回记忆数 |
| `maxProjectMemories` | number | `10` | 最大项目记忆数 |
| `injectionStrategy` | string | `smart` | 注入策略：once/smart/always |
| `compactionThreshold` | number | `0.8` | 压缩阈值 |
| `enableGraphRecall` | boolean | `true` | 启用图谱召回 |
| `enableEntityRecall` | boolean | `true` | 启用实体召回 |

### 注入策略

| 策略 | 说明 |
|------|------|
| `once` | 仅在会话首条消息注入上下文 |
| `smart` | 首次注入 + 关键词触发召回（推荐） |
| `always` | 每条消息都注入上下文 |

### 配置示例

```jsonc
{
    "apiKey": "rk_live_xxx",
    "baseUrl": "http://localhost:8000",
    "userName": "Alice",
    
    // 容器标签配置
    "userContainerTag": "user-123",
    "projectContainerTag": "project-abc",
    
    // 检索配置
    "similarityThreshold": 0.6,
    "maxMemories": 5,
    "maxProjectMemories": 10,
    
    // 注入策略
    "injectionStrategy": "smart",
    "initialInjection": {
        "profile": true,
        "projectMemories": true,
        "chunks": true,
        "maxChunks": 3
    },
    "smartRecall": {
        "enabled": true,
        "keywords": ["记得", "之前", "recall", "remember"],
        "maxAdditionalMemories": 3,
        "maxAdditionalChunks": 2
    },
    
    // 文档追踪
    "enableDocumentTracking": true,
    "trackedDocPatterns": [
        "README*.md",
        "CHANGELOG*.md",
        "docs/*.md",
        "AGENTS.md"
    ]
}
```

## 使用

### 安装后

安装完成后，重启 OpenCode 即可使用记忆功能。

### 记忆工具

插件提供以下工具：

| 工具 | 说明 |
|------|------|
| `memory-recall` | 统一记忆工具 |

### 工具模式

`memory-recall` 工具支持以下模式：

| 模式 | 说明 |
|------|------|
| `add` | 添加记忆 |
| `search` | 搜索记忆 |
| `profile` | 获取用户画像 |
| `list` | 列出记忆 |
| `forget` | 删除记忆 |

### 智能召回关键词

当 `injectionStrategy` 设为 `smart` 时，以下关键词会触发额外召回：

- 中文：记得、之前、上次、以前、回忆、记忆
- 英文：recall、remember、previous、earlier

## 常见问题

### API 服务未运行

**问题**：安装脚本提示无法连接到服务器

**解决**：
1. 确认 Memory Recall API 服务正在运行
2. 检查 `baseUrl` 配置是否正确
3. 确认防火墙允许访问

### API Key 无效

**问题**：配置完成后无法使用记忆功能

**解决**：
1. 检查 API Key 是否正确
2. 重新运行 `bunx memory-recall-opencode install` 更新配置
3. 确认 API Key 未过期

### 配置文件位置

- Linux/macOS: `~/.config/opencode/memory-recall.jsonc`
- Windows: `%APPDATA%\opencode\memory-recall.jsonc`

### 如何获取 API Key

**方法 1：自动注册（推荐）**
```bash
bunx memory-recall-opencode install
# 选择 "新用户"
```

**方法 2：手动创建**
```bash
curl -X POST http://localhost:8000/auth/initialize \
  -H "Content-Type: application/json" \
  -d '{"user_name": "your-name", "plugin_name": "opencode-plugin"}'
```

## 开发

### 构建

```bash
cd apps/api/src/plugins/opencode
bun run build
```

### 本地测试

```bash
bun run src/install.ts
```

## 许可证

MIT License
