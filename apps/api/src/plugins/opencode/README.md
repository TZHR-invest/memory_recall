# Memory Recall OpenCode Plugin

为 OpenCode 提供持久化记忆能力，支持跨会话上下文召回。

## 安装

### 前置要求

- Bun 运行时环境
- Memory Recall API 服务

### 安装 Bun

```bash
curl -fsSL https://bun.sh/install | bash
```

### 安装插件

**Step 1: 获取打包文件**

从项目获取 `memory-recall-opencode-1.1.0.tar.gz` 文件。

**Step 2: 解压并安装**

```bash
# 解压
mkdir -p memory-recall-opencode
tar -xzvf memory-recall-opencode-1.1.0.tar.gz -C memory-recall-opencode

# 进入目录
cd memory-recall-opencode

# 运行安装脚本
bun run dist/install.js
```

**Step 3: 按提示完成配置**

安装脚本会引导您：

1. **选择用户类型**
   - 使用已有 API Key：输入您现有的 Key
   - 注册新用户：开发环境可直接注册（无需管理员 Key）
   - 创建新 API Key：使用管理员 Key 创建新 Key

2. **输入 API 服务地址**（默认 `http://localhost:8000`）

3. **确认并保存配置**

### 卸载

```bash
bun run dist/install.js uninstall
```

### 重新安装

```bash
bun run dist/install.js reinstall
```

### 查看帮助

```bash
bun run dist/install.js --help
```

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

### 什么是管理员 API Key？

首次通过"首次注册"选项创建的 API Key 具有**管理员权限**，可以：

1. 读写删除记忆数据
2. **创建新的 API Key**

权限级别：

| 权限 | 能力 |
|------|------|
| `read` | 只读 |
| `write` | 读取 + 写入 |
| `delete` | 读取 + 写入 + 删除 |
| `admin` | 全部权限 + 创建新 API Key |

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
2. 重新运行安装脚本更新配置
3. 确认 API Key 未过期

### 配置文件位置

- Linux/macOS: `~/.config/opencode/memory-recall.jsonc`
- Windows: `%APPDATA%\opencode\memory-recall.jsonc`

### 如何获取 API Key

**场景 1：服务器没有任何 API Key（首次使用）**

运行安装脚本，选择"首次注册"选项。创建的 Key 将具有管理员权限。

**场景 2：服务器已有 API Key**

- **选项 1**：使用已有的 API Key（如果您知道它）
- **选项 2**：使用首次注册时获得的管理员 Key 创建新 Key

**手动创建（命令行）：**

```bash
# 首次注册（无认证）
curl -X POST http://localhost:8000/auth/initialize \
  -H "Content-Type: application/json" \
  -d '{"user_name": "your-name", "plugin_name": "opencode-plugin"}'

# 使用管理员 Key 创建新 Key
curl -X POST http://localhost:8000/auth/api-keys \
  -H "Content-Type: application/json" \
  -H "X-API-Key: rk_live_your_admin_key" \
  -d '{"name": "my-plugin", "permissions": ["read", "write", "delete", "admin"]}'
```

## 许可证

MIT License
