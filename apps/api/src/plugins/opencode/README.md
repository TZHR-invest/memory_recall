# Memory Recall OpenCode Plugin

为 OpenCode 提供持久化记忆能力，支持跨会话上下文召回。

## 安装

```bash
# 1. 解压
tar -xzf memory-recall-opencode-1.2.0.tar.gz

# 2. 进入目录并运行安装
cd memory-recall-opencode
node dist/cli.js install
```

## 命令

```bash
node dist/cli.js install    # 安装插件
node dist/cli.js uninstall  # 卸载插件
node dist/cli.js reinstall  # 重新安装
node dist/cli.js status     # 查看状态
```

## 配置方式

安装时选择：

1. **使用已有 API Key** - 输入你现有的 API Key
2. **注册新用户** - 开发环境首次使用，自动创建 API Key

## 安装后

1. 确保 Memory Recall API 服务正在运行 (`http://localhost:8000`)
2. 重启 OpenCode
3. 使用 `/memory-init` 初始化项目记忆

## 工具

安装后可用 `memory-recall` 工具：

| 模式 | 说明 |
|------|------|
| `add` | 添加记忆 |
| `search` | 搜索记忆 |
| `profile` | 获取用户画像 |
| `list` | 列出记忆 |
| `forget` | 删除记忆 |

## 配置文件

`~/.config/opencode/memory-recall.jsonc`

## 许可证

MIT
