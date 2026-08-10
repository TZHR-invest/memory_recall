<div align="center">
  <h1>🧠 Memory Recall</h1>
  <p><strong>Long-term memory system for AI — Persistent, Searchable, Reasonable</strong></p>
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
    <a href="README.md">中文</a> ·
    <a href="https://github.com/TZHR-invest/memory_recall/issues">Report Bug</a> ·
    <a href="https://github.com/TZHR-invest/memory_recall/issues">Request Feature</a>
  </p>
</div>

---

**Memory Recall** is an open-source persistent memory system for AI assistants. It combines **vector search**, **knowledge graphs**, and **semantic relations** to give AI long-term cross-session memory.

### ✨ Features

| Feature | Description |
|---------|-------------|
| 🔍 **3-Layer Recall** | Vector search + Memory Graph + Entity Graph, < 50ms latency |
| 🧩 **Unified API** | Single endpoint for memories, profiles, documents, and graph |
| 🔐 **Auth & Isolation** | API Key authentication + container-level data isolation |
| 🧠 **Knowledge Graph** | Entity extraction, relation inference, visual queries |
| 🌐 **Multi-Platform** | Plugins for OpenCode, DeepSeek TUI, Hermes Agent |
| 📄 **Document Memory** | Auto-import README, design docs, full-text search |
| 🐳 **30s Setup** | Docker Compose one-command deployment |

---

## 🚀 Quick Start (30s)

```bash
git clone https://github.com/TZHR-invest/memory_recall.git
cd memory_recall/apps/api

# Start everything (PostgreSQL + API + Adminer)
docker compose up -d

# Verify
curl http://localhost:8000/health
```

> Need LLM API Key? See `.env.example` for configuration reference.

### 📦 Try It Now

```bash
# Create a memory
curl -X POST http://localhost:8000/memories \
  -H "Content-Type: application/json" \
  -d '{"content":"User prefers American coffee","container_tag":"demo","is_static":true}'

# Search
curl -X POST http://localhost:8000/search \
  -H "Content-Type: application/json" \
  -d '{"query":"coffee preference","container_tag":"demo"}'
```

---

## 🏗 Architecture

```
Input → Vector Search(50%) → Memory Graph(30%) → Entity Graph(20%) → Merge → Context Injection
↓                                                                         ↓
embedding model ← PostgreSQL + pgvector                              Optimized tokens
```

**Data Flow**: `API → Auth → Entity Extraction → Relation Detection → Embedding → Storage → Graph Building → Recall`

<details>
<summary><b>📁 Project Structure</b></summary>

```
memory_recall/
├── apps/api/              # Core API (FastAPI + PostgreSQL + pgvector)
│   ├── src/
│   │   ├── api/           # Endpoints (memories, auth, graph)
│   │   ├── services/
│   │   │   ├── core/      # Core services (store, relations, profiles, entities, documents)
│   │   │   └── ...
│   │   ├── plugins/       # OpenCode / Hermes / DeepSeek TUI plugin source
│   │   └── llm/           # LLM client (Volcengine / OpenAI compatible)
│   ├── schema.sql         # Full database schema
│   └── tests/
```
</details>

---

## 📋 API Overview

| Endpoint | Description |
|----------|-------------|
| `POST /memories` | Create a memory |
| `POST /search` | Semantic search (with graph expansion support) |
| `GET /profile` | Get user profile (~50ms) |
| `GET /graph` | Knowledge graph visualization |
| `POST /memories/{id}/forget` | Soft-delete a memory |
| `POST /memories/{id}/update` | Versioned update |
| `POST /context-inject` | Unified context injection |

> Visit `/docs` after starting the service for Swagger UI.

---

## 🔌 Plugin Ecosystem

| Platform | Install | Description |
|----------|---------|-------------|
| **OpenCode** | `bunx memory-recall-opencode install` | TypeScript plugin, auto project isolation |
| **DeepSeek TUI** | `./install.sh` | MCP protocol, 15 tools |
| **Hermes Agent** | `python server.py` | MCP protocol, 15 tools |


---

## 🐳 Docker Deployment

```bash
cd apps/api
docker compose up -d
# API: http://localhost:8000
# Swagger: http://localhost:8000/docs
# Adminer: http://localhost:8888
```

---

## 🧪 Tech Stack

| Component | Choice |
|-----------|--------|
| Backend | **FastAPI** (Python) |
| Database | **PostgreSQL 14+** + **pgvector** |
| Embedding | 1024-dim (doubao-embedding) |
| LLM | Volcengine doubao-seed / OpenAI compatible |


---

## 🤝 Contributing

PRs welcome! See [CONTRIBUTING.md](CONTRIBUTING.md) and [SECURITY.md](SECURITY.md).

## 📄 License

[MIT License](LICENSE)

---

*Created: 2026-03-19 · Last updated: 2026-06-03*
