# Memory Recall - AI Agent 开发指南

## 项目概述

Memory Recall 是一个简化的记忆召回系统，支持：
- **简化架构**（3 核心表：memories, relations, profiles）
- **时序语义关系**（updates/extends/derives）
- **用户画像分离**（static/dynamic）
- **OpenClaw/OpenCode 插件集成**

**当前版本**: v5.0.0  
**工作目录**: `apps/api/`

---

## 构建、测试、运行命令

### 环境设置

```bash
cd apps/api
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

创建 `.env` 文件：
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

### 数据库迁移

```bash
# 运行所有迁移
python migrations/run_migrations.py

# 运行简化架构迁移
python migrations/run_single_migration.py migrations/018_simplified_memory_schema.sql
```

### 测试

```bash
# 运行所有测试
pytest tests/ -v

# 运行 v2 架构测试
pytest tests/test_v2/ -v

# 运行单个测试文件
pytest tests/test_v2/test_memory_store.py -v
```

### 启动服务

```bash
# 开发模式
uvicorn main:app --host 0.0.0.0 --port 8000 --reload

# 或直接运行
python main.py
```

### API 文档

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

---

## 代码风格指南

### 项目结构

```
apps/api/src/
├── config.py           # 配置管理（pydantic-settings）
├── database.py         # 数据库连接（asyncpg）
├── client.py           # 统一客户端接口
├── services/
│   └── core/           # 核心服务
│       ├── memory_store.py      # 记忆存储
│       ├── relation_service.py  # 关系管理
│       ├── profile_service.py   # 用户画像
│       └── entity_extraction.py # 实体提取
├── api/
│   ├── auth.py                  # 认证系统
│   ├── auth_endpoints.py        # API Key 管理
│   ├── memories.py              # 记忆 API
│   └── graph.py                 # 知识图谱 API
├── background/
│   └── scheduler.py    # 后台任务调度
├── plugins/
│   ├── openclaw/       # OpenClaw 插件
│   └── opencode/       # OpenCode 插件
├── llm/                # LLM 客户端
└── embedding/          # 向量嵌入
```

### 导入规范

```python
# 标准库
from typing import Dict, Any, List, Optional
from datetime import datetime
from dataclasses import dataclass

# 第三方库
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

# 本地导入 - 使用绝对导入
from src.database import db
from src.config import settings
from src.services.core.memory_store import memory_store
from src.services.core.relation_service import relation_service
from src.services.core.profile_service import profile_service
```

### 类型注解

```python
# 函数参数和返回值必须有类型注解
async def create(
    content: str,
    container_tag: str,
    is_static: bool = False,
) -> Memory:
    ...

# 使用 Optional 表示可空
def get_by_id(self, memory_id: str) -> Optional[Memory]:
    ...

# 使用 List, Dict, Any
async def search(
    self,
    query: str,
    container_tag: str,
    limit: int = 10,
) -> List[Dict[str, Any]]:
    ...
```

### 异步编程

```python
# 所有数据库操作使用 async/await
async def get_by_id(self, memory_id: str) -> Optional[Memory]:
    row = await db.fetchrow("SELECT * FROM memories WHERE id = $1", memory_id)
    ...

# 使用 asyncio.gather 并行执行
results = await asyncio.gather(
    memory_store.search(...),
    profile_service.get_profile(...),
)
```

### 数据库操作

```python
# 使用参数化查询（防 SQL 注入）
await db.execute(
    "INSERT INTO memories (container_tag, content) VALUES ($1, $2)",
    container_tag, content
)

# 向量嵌入使用字符串格式
embedding_str = "[" + ",".join(map(str, embedding)) + "]"
```

### 命名约定

```python
# 类名：PascalCase
class MemoryStore:
class RelationService:

# 函数/方法：snake_case
async def get_by_id(self, memory_id: str):
async def detect_contradiction(new_content: str, existing_content: str):

# 常量：UPPER_SNAKE_CASE
CONTRADICTION_PATTERNS = [...]
TOPIC_KEYWORDS = {...}

# 私有方法：_前缀
async def _mark_not_latest(self, memory_id: str):
def _row_to_memory(self, row: Dict) -> Memory:

# 单例实例：模块级变量
memory_store = MemoryStore()
relation_service = RelationService()
profile_service = ProfileService()
```

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

### 核心服务

```python
# MemoryStore - 记忆存储
from src.services.core.memory_store import memory_store

# 创建记忆（自动提取实体、自动创建关系）
memory = await memory_store.create(
    content="我是素食主义者",
    container_tag="user_001",
    is_static=True,
)

# 搜索记忆
results = await memory_store.search(
    query="饮食偏好",
    container_tag="user_001",
    limit=10,
)

# RelationService - 关系管理
from src.services.core.relation_service import relation_service

# 自动检测矛盾并创建关系
relations = await relation_service.auto_create_relations(
    new_memory_id=memory.id,
    new_content="我现在在 Supermemory 工作",
    container_tag="user_001",
)

# 获取版本历史
history = await relation_service.get_version_history(memory_id)

# ProfileService - 用户画像
from src.services.core.profile_service import profile_service

# 获取画像（static + dynamic）
profile = await profile_service.get_profile(
    container_tag="user_001",
    query="饮食偏好",  # 可选，触发搜索
)
```

### 数据库表

| 表名 | 说明 | 核心字段 |
|-----|------|---------|
| `memories` | 记忆表 | id, container_tag, content, embedding, is_static, is_latest, metadata |
| `memory_relations` | 关系表 | from_memory_id, to_memory_id, relation_type, confidence |
| `memory_profiles` | 画像缓存 | container_tag, static_memories, dynamic_memories |

---

## 时序语义关系

### updates 关系

当新记忆与旧记忆存在矛盾时，自动创建 `updates` 关系：

```python
# 旧记忆："我在 Google 工作"
# 新记忆："我现在在 Supermemory 工作"
# 自动创建：new_memory -[updates]-> old_memory
# 自动标记：old_memory.is_latest = FALSE
```

### extends 关系

当新记忆与旧记忆属于同一主题时，自动创建 `extends` 关系：

```python
# 旧记忆："我喜欢喝咖啡"
# 新记忆："我每天早上都要喝一杯美式咖啡"
# 自动创建：new_memory -[extends]-> old_memory
```

### derives 关系

推断关系（暂未自动创建，可手动创建）：

```python
# 从多条记忆推断新知识
await relation_service.create(
    from_memory_id=inferred_memory.id,
    to_memory_id=source_memory.id,
    relation_type="derives",
    confidence=0.7,
)
```

---

## 用户画像系统

### static vs dynamic

- **static**: `is_static = TRUE`，永久特征（姓名、职业、偏好）
- **dynamic**: `is_static = FALSE`，最近活动（项目、兴趣）

### 画像缓存

```python
# 获取画像（从缓存或重新构建）
profile = await profile_service.get_profile(container_tag="user_001")

# 返回结构
{
    "profile": {
        "static": ["John Doe", "高级工程师", "喜欢暗黑模式"],
        "dynamic": ["正在做认证迁移", "调试速率限制"]
    },
    "searchResults": [...]  # 如果提供了 query
}
```

### 后台任务

- **profile_rebuild**: 每 5 分钟重建有更新的用户画像
- **cache_cleanup**: 每 10 分钟清理过期缓存

---

## 实体提取

使用 jieba 和正则表达式提取实体：

```python
from src.services.core.entity_extraction import entity_extractor

# 提取实体
entities = entity_extractor.extract("我在北京工作，喜欢喝咖啡")

# 返回结构
[
    Entity(text="北京", type="location", ...),
    Entity(text="工作", type="activity", ...),
]

# 提取到 metadata 格式
metadata = entity_extractor.extract_to_metadata(content)
# {"location": ["北京"], "preference": ["喜欢喝咖啡"]}
```

支持的实体类型：
- `location`: 地点
- `organization`: 组织
- `person`: 人物
- `time`: 时间
- `preference`: 偏好
- `contact`: 联系方式

---

## API 端点

### 统一 API（v5.0）

所有端点需要 `X-API-Key` header 认证。

| 端点 | 说明 |
|-----|------|
| `POST /memories` | 创建记忆 |
| `GET /memories` | 列出记忆 |
| `GET /memories/{id}` | 获取记忆 |
| `POST /memories/{id}/forget` | 遗忘记忆 |
| `POST /memories/{id}/restore` | 恢复记忆 |
| `POST /memories/{id}/update` | 创建新版本 |
| `GET /memories/{id}/history` | 版本历史 |
| `GET /profile` | 获取用户画像 |
| `POST /search` | 搜索记忆 |
| `POST /documents` | 上传文档 |
| `GET /documents` | 列出文档 |
| `GET /graph` | 知识图谱 |
| `POST /auth/keys` | 创建 API Key |

### 认证

- **API Key 格式**: `rk_live_xxx` 或 `rk_test_xxx`
- **权限级别**: read, write, delete, admin
- **速率限制**: 100 请求/60秒
- **容器所有权**: `container_tag` 必须以 `user_id` 开头

---

## 插件集成

### OpenClaw 插件

路径：`src/plugins/openclaw/`

- `plugin.json`: 插件清单
- `client.py`: 客户端封装
- `hooks.py`: 钩子实现（before_agent_start, agent_end）
- `tools.py`: 工具实现（memory_store, memory_search, memory_profile, memory_forget）

### OpenCode 插件

路径：`src/plugins/opencode/`

- `tool.py`: 统一 supermemory 工具
- `context.py`: 上下文注入
- `client.py`: 客户端封装

---

## 测试规范

### 测试文件结构

```python
import pytest
from pathlib import Path
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.services.core.memory_store import memory_store
from src.database import db


@pytest.mark.asyncio
async def test_create_memory():
    await db.connect()
    try:
        memory = await memory_store.create(
            content="测试内容",
            container_tag="test_user_001",
            is_static=True,
        )
        assert memory.id.startswith("mem_")
    finally:
        await db.disconnect()
```

### 测试用户 ID

使用描述性前缀：`test_<feature>_<purpose>`
- `test_user_store` - 存储测试
- `test_user_recall` - 召回测试

---

## 注意事项

1. **向量嵌入**：使用字符串格式 `"[0.1,0.2,...]"` 存储
2. **container_tag**：用户隔离标识（替代原来的 Schema 隔离）
3. **is_latest**：标记记忆是否为最新版本
4. **自动关系创建**：创建记忆时自动检测并创建关系
5. **实体提取**：使用 jieba + 正则，提取到 metadata JSONB
