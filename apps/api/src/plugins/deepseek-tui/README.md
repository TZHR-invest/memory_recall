# Memory Recall DeepSeek TUI Plugin

为 DeepSeek TUI 提供跨会话持久化记忆能力，集成 Memory Recall 后端 API。

## 目录结构

```
deepseek-tui/
├── PLUGIN.md              # 插件说明（DeepSeek TUI 格式）
├── README.md              # 本文件
├── install.sh             # 安装脚本
├── server.py              # MCP Server（Python）
├── config.jsonc.example   # 配置文件模板
├── requirements.txt       # Python 依赖
└── skill.md               # DeepSeek TUI skill 定义
```

## 安装

```bash
cd apps/api/src/plugins/deepseek-tui
chmod +x install.sh
./install.sh
```

安装后重启 DeepSeek TUI 即可使用 15 个 MCP 工具。

## 架构

```
DeepSeek TUI  ←→  MCP (stdio)  ←→  server.py  ←→  Memory Recall HTTP API
                    ↓
        ~/.deepseek/plugins/memory-recall/
            ├── config.jsonc
            ├── .venv/
            └── scripts/run-mcp.sh
```

## 与 OpenClaw / OpenCode 插件的关系

| 插件 | 目标平台 | 实现语言 | 协议 |
|------|---------|---------|------|
| openclaw | OpenClaw Agent | Python | Plugin SDK |
| opencode | OpenCode | TypeScript | OpenCode SDK |
| hermes | Hermes Agent | Python | MCP |
| **deepseek-tui** | **DeepSeek TUI** | **Python** | **MCP** |

## Scope 机制

- `user`: 跨项目共享（个人偏好、姓名等）
- `project`: 当前项目隔离（项目文档、技术决策）
