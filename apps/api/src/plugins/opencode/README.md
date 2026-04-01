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

## 许可证

MIT
