<div align="center">
  <h1>🧠 Memory Recall</h1>
  <p><strong>AI 的长期记忆系统 — 持久化、可搜索、可推理</strong></p>
  <p>
    <a href="https://github.com/TZHR-invest/memory_recall/blob/main/LICENSE">
      <img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="License">
    </a>
    <a href="https://www.python.org/downloads/">
      <img src="https://img.shields.io/badge/python-3.10+-blue.svg" alt="Python">
    </a>
    <a href="https://github.com/TZHR-invest/memory_recall/issues">
      <img src="https://img.shields.io/badge/PRs-welcome-brightgreen.svg" alt="PRs Welcome">
    </a>
    <a href="https://github.com/TZHR-invest/memory_recall">
      <img src="https://img.shields.io/github/stars/TZHR-invest/memory_recall?style=social" alt="Stars">
    </a>
  </p>
  <p>
    <a href="README_EN.md">English</a> · 
    <a href="https://github.com/TZHR-invest/memory_recall/issues">报告 Bug</a> · 
    <a href="https://github.com/TZHR-invest/memory_recall/issues">请求功能</a>
  </p>
</div>

---

**Memory Recall** 是一个为 AI 助手提供跨会话持久化记忆的开源系统。它结合了**向量检索**、**知识图谱**和**语义关系**，让 AI 能真正"记住"用户。

### ✨ 核心特性

| 特性 | 说明 |
|------|------|
| 🔍 **三层召回** | 向量搜索 + 记忆图谱 + 实体图谱，召回延迟 < 50ms |
| 🧩 **统一 API** | 单一入口管理记忆、画像、文档、图谱 |
| 🔐 **完整认证** | API Key + 容器隔离 + 速率限制 |
| 🧠 **知识图谱** | 实体提取、关系推理、可视化查询 |
| 🌐 **多平台插件** | OpenCode / DeepSeek TUI / Hermes Agent |
| 📄 **文档记忆** | 自动导入 README、设计文档、支持全文搜索 |
| 🐳 **一键部署** | Docker Compose 启动，30 秒跑起来 |

---

## 🚀 快速开始（30 秒）

```bash
git clone https://github.com/TZHR-invest/memory_recall.git
cd memory_recall/apps/api

# 启动（PostgreSQL + API + Adminer）
docker compose up -d

# 验证
curl http://localhost:8000/health
```

> 需要配置 LLM API Key？参考 `.env.example` 文件。

### 📦 一键试用

```bash
# 创建一条记忆
curl -X POST http://localhost:8000/memories \
  -H "Content-Type: application/json" \
  -d '{"content":"用户喜欢喝美式咖啡","container_tag":"demo","is_static":true}'

# 搜索
curl -X POST http://localhost:8000/search \
  -H "Content-Type: application/json" \
  -d '{"query":"咖啡喜好","container_tag":"demo"}'
```

---

## 🏗 架构总览

```
用户输入 → 向量搜索(50%) → 记忆图谱(30%) → 实体图谱(20%) → 去重合并 → 上下文注入
↓                                                                        ↓
embedding 模型 ← PostgreSQL + pgvector                              Token 优化输出
```

**数据流**：`API → 认证 → 提取实体 → 检测关系 → 向量化 → 存储 → 图谱构建 → 召回`

<details>
<summary><b>📁 项目结构</b></summary>

```
memory_recall/
├── apps/api/              # 核心后端（FastAPI + PostgreSQL + pgvector）
│   ├── src/
│   │   ├── api/           # API 端点（memories, auth, graph）
│   │   ├── services/
│   │   │   ├── core/      # 核心服务（存储、关系、画像、实体提取、文档处理）
│   │   │   └── ...
│   │   ├── plugins/       # OpenCode / Hermes / DeepSeek TUI 插件源码
│   │   └── llm/           # LLM 客户端（火山引擎 / OpenAI 兼容）
│   ├── schema.sql         # 完整数据库结构
│   └── tests/
```
</details>

---

## 📋 API 速览

| 端点 | 说明 |
|------|------|
| `POST /memories` | 创建记忆 |
| `POST /search` | 语义搜索（支持图谱扩展） |
| `GET /profile` | 获取用户画像（~50ms） |
| `GET /graph` | 知识图谱可视化 |
| `POST /memories/{id}/forget` | 遗忘记忆（软删除） |
| `POST /memories/{id}/update` | 版本化更新 |
| `POST /context-inject` | 统一上下文注入 |

> 启动后访问 `/docs` 查看 Swagger UI。

---

## 🔌 插件生态

| 平台 | 安装方式 | 说明 |
|------|---------|------|
| **OpenCode** | `bunx memory-recall-opencode install` | TypeScript 插件，自动项目隔离 |
| **DeepSeek TUI** | `./install.sh` | MCP 协议，15 个工具 |
| **Hermes Agent** | `python server.py` | MCP 协议，15 个工具 |


---

## 🐳 Docker 部署

```bash
cd apps/api
docker compose up -d
# API: http://localhost:8000
# Swagger: http://localhost:8000/docs
# Adminer: http://localhost:8888
```

---

## 🧪 技术栈

| 组件 | 选型 |
|------|------|
| 后端框架 | **FastAPI** (Python) |
| 数据库 | **PostgreSQL 14+** + **pgvector** |
| 向量维度 | 1024 维（doubao-embedding） |
| LLM | 火山引擎 doubao-seed / OpenAI 兼容 |


---

## 🤝 贡献

欢迎 PR！见 [CONTRIBUTING.md](CONTRIBUTING.md) 和 [SECURITY.md](SECURITY.md)。

## 📄 许可证

[MIT License](LICENSE)

---

*创建时间：2026-03-19 · 最后更新：2026-06-03*
