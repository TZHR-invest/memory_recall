# Memory Recall - 简化记忆系统

**版本**：v4.0.0  
**状态**：重构完成  
**最后更新**：2026-03-29

---

## 项目定位

**核心目标**：
1. 简化架构，提升性能（召回延迟从 1.5-4 秒降到 ~50ms）
2. 实现时间语义（理解信息何时生效、何时失效）
3. 用户画像分离（static/dynamic 区分，精准上下文注入）
4. OpenClaw/OpenCode 插件集成

**核心特性**：
- ✅ 简化数据模型（3 核心表：memories, relations, profiles）
- ✅ 时间语义关系（updates/extends/derives）
- ✅ 用户画像分离（static/dynamic）
- ✅ OpenClaw 插件（Tools + Hooks）
- ✅ OpenCode 插件（统一 Tool + Context Injection）
- ✅ 统一客户端接口
- ✅ 轻量级实体提取

---

## 技术栈

| 组件 | 技术选择 | 说明 |
|------|---------|------|
| 数据库 | PostgreSQL 14+ | 关系型数据库 |
| 向量扩展 | pgvector | 向量相似度搜索 |
| LLM | 火山引擎 doubao-seed-2-0-mini | 文本处理 |
| Embedding | doubao-embedding-vision | 文本向量化 |
| 后端框架 | FastAPI | 异步 API 框架 |

---

## 核心架构

### 简化记忆架构（v4.0）

```
┌─────────────────────────────────────────────────────────────┐
│                    简化记忆架构                              │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  memories (核心表)                                          │
│  ├─ is_static: TRUE  → 永久特征（姓名、职业、偏好）         │
│  └─ is_static: FALSE → 最近活动（项目、兴趣）               │
│           │                                                 │
│           ↓ 三种关系                                        │
│           │                                                 │
│  memory_relations                                           │
│  ├─ updates: 信息更新（"我在 Google" → "我在 Supermemory"）  │
│  ├─ extends: 信息丰富（添加更多上下文）                      │
│  └─ derives: 信息推断（从模式推断新知识）                    │
│           │                                                 │
│           ↓ 缓存                                            │
│           │                                                 │
│  memory_profiles                                            │
│  └─ static + dynamic 缓存（~50ms 获取）                     │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Profile API (~50ms)

```python
profile = await client.get_profile(container_tag="user_123")

# 返回：
{
    "profile": {
        "static": ["John Doe", "高级工程师", "喜欢暗黑模式"],
        "dynamic": ["正在做认证迁移", "调试速率限制"]
    },
    "searchResults": [...]  # 可选
}
```

---

## 快速开始

### 环境要求

- Python 3.10+
- PostgreSQL 14+ (with pgvector)

### 安装依赖

```bash
cd apps/api
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 配置环境变量

创建 `apps/api/.env` 文件：

```env
DATABASE_HOST=localhost
DATABASE_PORT=5432
DATABASE_NAME=memory_recall
DATABASE_USER=postgres
DATABASE_PASSWORD=postgres
VOLC_API_KEY=your_api_key
VOLC_API_BASE=https://ark.cn-beijing.volces.com/api/v3
VOLC_LLM_MODEL=doubao-seed-2-0-mini-260215
VOLC_EMBEDDING_MODEL=doubao-embedding-vision-251215
```

### 运行数据库迁移

```bash
cd apps/api
python migrations/run_migrations.py
```

### 启动 API 服务

```bash
cd apps/api
source venv/bin/activate
uvicorn main:app --host 0.0.0.0 --port 8000
```

---

## API 接口

### 创建记忆

```bash
POST /v1/memories
Content-Type: application/json

{
    "content": "我是素食主义者，不喜欢吃肉",
    "container_tag": "user_001",
    "is_static": true
}
```

### 获取用户画像

```bash
GET /v1/profile?container_tag=user_001&query=饮食偏好
```

### 搜索记忆

```bash
POST /v1/search
Content-Type: application/json

{
    "query": "饮食偏好",
    "container_tag": "user_001",
    "limit": 10,
    "threshold": 0.6
}
```

### 遗忘记忆

```bash
POST /v1/memories/{memory_id}/forget
```

### 恢复记忆

```bash
POST /v1/memories/{memory_id}/restore
```

### 更新记忆版本

```bash
POST /v1/memories/{memory_id}/update
Content-Type: application/json

{
    "content": "我现在在 Supermemory 工作"
}
```

---

## OpenClaw 插件

### 安装

```bash
openclaw plugins install memory-recall
```

### 配置

```json
{
    "apiKey": "your-api-key",
    "baseUrl": "http://localhost:8000",
    "containerTag": "openclaw_default",
    "autoRecall": true,
    "autoCapture": true,
    "maxRecallResults": 10
}
```

### 可用 Tools

| Tool | 说明 |
|------|------|
| `memory_store` | 存储记忆 |
| `memory_search` | 搜索记忆 |
| `memory_profile` | 获取用户画像 |
| `memory_forget` | 删除记忆 |

---

## OpenCode 插件

### 安装

```bash
bunx memory-recall-opencode install
```

### 配置

```json
{
    "apiKey": "your-api-key",
    "baseUrl": "http://localhost:8000",
    "containerTagPrefix": "opencode"
}
```

### 统一 Tool

```json
{
    "name": "supermemory",
    "modes": ["add", "search", "profile", "list", "forget"],
    "scopes": ["user", "project"]
}
```

---

## 客户端使用

### 异步客户端

```python
from src.client import MemoryRecallClient

async with MemoryRecallClient(base_url="http://localhost:8000") as client:
    # 添加记忆
    result = await client.add_memory(
        content="用户喜欢暗黑模式",
        container_tag="user_123",
        is_static=True,
    )
    
    # 获取画像
    profile = await client.get_profile(container_tag="user_123")
    
    # 搜索
    results = await client.search(
        query="编程偏好",
        container_tag="user_123",
    )
```

### 同步客户端

```python
from src.client import SyncMemoryRecallClient

client = SyncMemoryRecallClient(base_url="http://localhost:8000")
result = client.add_memory(
    content="用户喜欢暗黑模式",
    container_tag="user_123",
    is_static=True,
)
client.close()
```

---

## 数据模型

### 记忆表（memories）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | VARCHAR(24) | 主键（mem_xxx） |
| container_tag | VARCHAR(100) | 隔离标识 |
| content | TEXT | 记忆内容 |
| embedding | VECTOR(1024) | 向量嵌入 |
| is_static | BOOLEAN | 是否永久特征 |
| is_latest | BOOLEAN | 是否最新版本 |
| valid_from | TIMESTAMP | 生效时间 |
| valid_until | TIMESTAMP | 失效时间 |
| metadata | JSONB | 元数据 |
| is_forgotten | BOOLEAN | 软删除标记 |

### 关系表（memory_relations）

| 字段 | 类型 | 说明 |
|------|------|------|
| from_memory_id | VARCHAR(24) | 源记忆 |
| to_memory_id | VARCHAR(24) | 目标记忆 |
| relation_type | VARCHAR(20) | updates/extends/derives |

### 画像表（memory_profiles）

| 字段 | 类型 | 说明 |
|------|------|------|
| container_tag | VARCHAR(100) | 主键 |
| static_memories | JSONB | 静态记忆列表 |
| dynamic_memories | JSONB | 动态记忆列表 |

---

## 关键变更（v4.0）

### 新增功能

- 时间语义关系（updates/extends/derives）
- 用户画像分离（static/dynamic）
- OpenClaw 插件
- OpenCode 插件
- 统一客户端接口

### 删除功能

- DAG 压缩机制
- 图谱召回
- Function Calling 实体提取
- Schema 隔离（改为 container_tag）

### 性能提升

- 召回延迟：1.5-4 秒 → ~50ms
- 数据模型：6+ 表 → 3 核心表
- 代码量：72 文件 → ~40 文件

---

## 许可证

MIT License

---

*创建者：颓弟*  
*创建时间：2026-03-19*  
*最后更新：2026-03-29*
