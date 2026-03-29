# Memory Recall - AI Agent 开发指南

## 项目概述

Memory Recall 是一个通用记忆召回系统，支持：
- **统一 DAG 记忆架构**（raw_messages + summaries）
- **混合召回**（向量 + 关键词 + 图谱）
- **OpenClaw ContextEngine 插件集成**
- **多用户 Schema 隔离**

**当前版本**: v4.0.0  
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

# 运行单个迁移（DAG 架构表）
python migrations/run_single_migration.py migrations/015_create_lossless_tables.sql
python migrations/run_single_migration.py migrations/016_unify_memory_architecture.sql
```

### 测试

```bash
# 运行所有测试
pytest tests/ -v

# 运行 DAG 架构测试
pytest tests/test_lossless/ -v

# 运行单个测试文件
pytest tests/test_lossless/test_memory_recall_engine.py -v

# 运行单个测试函数
pytest tests/test_lossless/test_memory_recall_engine.py::test_ingest_user_memory -v

# 运行带详细输出的测试
pytest tests/test_lossless/ -v --tb=short

# 运行集成测试
python tests/test_lossless_integration.py
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
├── models/             # 数据模型（Pydantic, dataclass）
│   ├── memory.py       # 传统记忆模型
│   └── lossless.py     # DAG 架构模型
├── services/           # 核心业务逻辑
│   ├── lossless/       # DAG 架构服务（v3.0 核心）
│   │   ├── raw_message_store.py      # 原始消息存储
│   │   ├── summary_store.py          # 摘要节点管理
│   │   ├── context_store.py          # 上下文序列
│   │   ├── compaction_engine.py      # 三阶段压缩
│   │   ├── memory_recall_engine.py   # ContextEngine 接口
│   │   ├── lossless_recall_service.py # 混合召回
│   │   └── dag_expand_service.py     # DAG 展开
│   ├── evolution/      # 记忆进化服务（v4.0 新增）
│   │   ├── importance_service.py     # 重要性评估
│   │   ├── fact_extraction_service.py # 事实提取
│   │   ├── fusion_service.py          # 记忆融合
│   │   ├── user_profile_service.py    # 用户画像
│   │   ├── temporal_service.py        # 时间感知
│   │   ├── chunking_service.py        # 分段服务
│   │   └── forgetting_service.py      # 遗忘机制
│   ├── unified_memory_service.py     # 统一入口（v3.0）
│   ├── memory_service.py             # 传统记忆服务
│   ├── recall_service.py             # 召回服务
│   └── graph_recall_service.py       # 图谱召回
├── api/                # API v1 路由（v4.0 新增）
│   └── v1/
│       ├── memories.py       # 记忆 API
│       ├── recall.py         # 召回 API
│       ├── profile.py        # 用户画像 API
│       ├── relations.py      # 关系 API
│       ├── notifications.py  # 通知 API
│       ├── containers.py     # 容器 API
│       └── auth.py           # 认证 API
├── routes/             # FastAPI 路由（遗留）
│   ├── memories.py     # 记忆 CRUD（已迁移到 DAG）
│   ├── files.py        # 文件上传（已迁移到 DAG）
│   └── graph.py        # 图谱查询
├── background/         # 后台任务（v4.0 新增）
│   └── scheduler.py    # 任务调度器
├── llm/                # LLM 客户端
├── embedding/          # 向量嵌入
├── tools/              # Function Calling 工具
└── openclaw_plugin/    # OpenClaw 插件
    ├── openclaw.plugin.json  # 插件清单
    └── context_engine.py     # ContextEngine 实现
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
from src.models.lossless import RawMessage, Summary
from src.services.lossless.raw_message_store import RawMessageStore
```

### 类型注解

```python
# 函数参数和返回值必须有类型注解
async def store(
    user_id: str,
    content: str,
    memory_type: str = "preference",
    agent_id: Optional[str] = None,
) -> str:
    ...

# 使用 Optional 表示可空
def get_by_id(self, raw_id: str) -> Optional[RawMessage]:
    ...

# 使用 List, Dict, Any
async def recall(
    self,
    query: str,
    user_id: str,
    limit: int = 20,
) -> List[Dict[str, Any]]:
    ...
```

### 数据模型

```python
# 简单模型使用 dataclass
@dataclass
class ContextEngineInfo:
    id: str = "memory-recall"
    name: str = "Memory Recall Engine"
    version: str = "3.0.0"
    owns_compaction: bool = True

# API 请求/响应使用 Pydantic BaseModel
class SearchRequest(BaseModel):
    query: str = Field(..., description="搜索查询文本")
    user_id: str = Field(..., description="用户 ID")
    limit: int = Field(10, ge=1, le=100)
```

### 异步编程

```python
# 所有数据库操作使用 async/await
async def get_by_id(self, raw_id: str) -> Optional[RawMessage]:
    row = await db.fetchrow("SELECT * FROM raw_messages WHERE id = $1", raw_id)
    ...

# 使用 asyncio.gather 并行执行
results = await asyncio.gather(
    self._vector_recall(...),
    self._keyword_recall(...),
    self._graph_recall(...),
)
```

### 数据库操作

```python
# 使用参数化查询（防 SQL 注入）
await db.execute(
    "INSERT INTO raw_messages (id, content) VALUES ($1, $2)",
    raw_id, content
)

# 使用 user_context 切换 Schema
async with db.user_context(user_id):
    # 所有操作在用户 Schema 下执行
    await db.execute(...)

# 向量嵌入使用字符串格式
embedding_str = "[" + ",".join(map(str, embedding)) + "]"
```

### 错误处理

```python
# API 层使用 HTTPException
if not memory:
    raise HTTPException(status_code=404, detail="Memory not found")

# 服务层返回 Optional 或抛出异常
async def get_by_id(self, id: str) -> Optional[RawMessage]:
    row = await db.fetchrow(...)
    if not row:
        return None
    return self._row_to_model(row)
```

### 命名约定

```python
# 类名：PascalCase
class RawMessageStore:
class MemoryRecallEngine:

# 函数/方法：snake_case
async def get_by_id(self, id: str):
def estimate_tokens(text: str):

# 常量：UPPER_SNAKE_CASE
FALLBACK_MAX_CHARS = 512 * 4
DEFAULT_FRESH_TAIL_COUNT = 8

# 私有方法：_前缀
async def _summarize_with_escalation(self, source_text: str):
def _row_to_model(self, row: Dict) -> RawMessage:

# 单例实例：模块级变量
raw_message_store = RawMessageStore()
memory_recall_engine = MemoryRecallEngine()
```

---

## 核心架构

### DAG 记忆架构（v3.0）

```
┌─────────────────────────────────────────────────────────────┐
│                    DAG 记忆架构                              │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  raw_messages (Layer 1)                                     │
│  ├─ 用户手动输入 (agent_id = NULL)                          │
│  └─ Agent 对话 (agent_id = "agent_xxx")                     │
│           │                                                 │
│           ↓ DAG 压缩（三阶段：normal → aggressive → fallback)│
│           │                                                 │
│  summaries (Layer 2-3)                                      │
│  ├─ Leaf summaries（原始消息摘要）                           │
│  └─ Parent summaries（摘要的摘要）                           │
│           │                                                 │
│           ↓ 组装                                            │
│           │                                                 │
│  context_items (Layer 4)                                    │
│  └─ 有序上下文序列（fresh tail + summaries）                 │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### ContextEngine 接口

```python
class MemoryRecallEngine:
    async def bootstrap(params) -> Dict      # 初始化会话
    async def ingest(params) -> Dict         # 存储消息
    async def assemble(params) -> Dict       # 组装上下文
    async def compact(params) -> Dict        # DAG 压缩
    async def recall(query, user_id) -> List # 混合召回
    async def expand(summary_id) -> List     # DAG 展开
```

### 数据库表

| 表名 | 说明 | 核心字段 |
|-----|------|---------|
| `raw_messages` | 原始消息 | id, content, agent_id (NULL=手动), embedding |
| `summaries` | DAG 摘要节点 | id, content, level, token_count |
| `summary_messages` | 摘要-消息关联 | summary_id, raw_message_id |
| `summary_parents` | 摘要父子关系 | child_id, parent_id |
| `summary_entities` | 摘要-实体关联 | summary_id, entity_id |
| `context_items` | 有序上下文序列 | session_id, ordinal, item_type |
| `entities` / `relations` | 知识图谱 | name, type, relation_type |

---

## 统一 DAG 架构使用指南

### 统一记忆入口（UnifiedMemoryService）

```python
from src.services.unified_memory_service import unified_memory_service

# 用户手动存储偏好
result = await unified_memory_service.store(
    user_id="user_001",
    content="我是素食主义者，不喜欢吃肉",
    source="manual",  # manual 或 agent
    memory_type="preference",
    metadata={
        "tags": ["饮食", "偏好"],
        "location_name": "北京",
    },
)
# 返回: {"raw_message_id": "raw_xxx", "memory_type": "preference", ...}

# Agent 存储对话
result = await unified_memory_service.store(
    user_id="user_001",
    content="用户询问今天天气",
    source="agent",
    agent_id="agent_001",
    session_id="session_001",
)

# 统一召回
results = await unified_memory_service.recall(
    query="饮食偏好",
    user_id="user_001",
    scope="manual_only",  # all | manual_only | agent_only
    limit=10,
)
```

### API 端点

**创建记忆**（统一 DAG 架构）:
```bash
POST /memories?user_id=user_001
{
    "content": "我喜欢喝咖啡"
}
```

**智能召回**:
```bash
POST /memories/smart-recall
{
    "query": "我有什么饮食偏好？",
    "user_id": "user_001"
}
```

### 数据迁移

将旧 `memories` 表数据迁移到 `raw_messages`:
```bash
python scripts/migrate_memories_to_raw_messages.py
```

---

## Evolution Services（v4.0 新增）

Evolution Services 提供记忆进化机制，包括重要性评估、事实提取、记忆融合、用户画像、时间感知、分段和遗忘等功能。

### 服务列表

| 服务 | 文件 | 说明 |
|-----|------|------|
| ImportanceService | `importance_service.py` | 重要性评估 |
| FactExtractionService | `fact_extraction_service.py` | 事实提取 |
| FusionService | `fusion_service.py` | 记忆融合 |
| UserProfileService | `user_profile_service.py` | 用户画像 |
| TemporalService | `temporal_service.py` | 时间感知 |
| ChunkingService | `chunking_service.py` | 分段服务 |
| ForgettingService | `forgetting_service.py` | 遗忘机制 |

### 使用示例

```python
from src.services.evolution.importance_service import ImportanceService
from src.services.evolution.user_profile_service import UserProfileService

# 重要性评估
importance_service = ImportanceService()
score = await importance_service.evaluate(content, user_id)

# 用户画像
profile_service = UserProfileService()
profile = await profile_service.get_profile(user_id)
```

---

## API v1 Endpoints（v4.0 新增）

API v1 提供 RESTful API 接口，采用模块化设计。

### 端点列表

| 端点 | 文件 | 说明 |
|-----|------|------|
| Memories | `memories.py` | 记忆 CRUD |
| Recall | `recall.py` | 智能召回 |
| Profile | `profile.py` | 用户画像 |
| Relations | `relations.py` | 关系管理 |
| Notifications | `notifications.py` | 通知管理 |
| Containers | `containers.py` | 容器管理 |
| Auth | `auth.py` | 认证授权 |

### API 基础路径

```
/api/v1/
```

### 认证

API 使用 API Key 进行认证：
```bash
Authorization: Bearer rk_live_xxxxx
```

---

## Background Tasks（v4.0 新增）

Background Tasks 提供后台任务调度功能。

### 调度器

| 任务 | 说明 |
|-----|------|
| Scheduler | `scheduler.py` | 任务调度器 |

### 使用示例

```python
from src.background.scheduler import scheduler

# 启动调度器
await scheduler.start()

# 停止调度器
await scheduler.stop()
```

---

## 测试规范

### 测试文件结构

```python
import pytest
from pathlib import Path
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from dotenv import load_dotenv
env_path = Path(__file__).parent.parent.parent / ".env"
load_dotenv(env_path)

from src.services.lossless.raw_message_store import RawMessageStore
from src.database import db


@pytest.mark.asyncio
async def test_store_raw_message():
    store = RawMessageStore()
    user_id = "test_user_001"
    
    await db.connect()
    try:
        await db.init_user(user_id)
        async with db.user_context(user_id):
            # 测试逻辑
            raw_id = await store.store(user_id, "测试内容", "preference")
            assert raw_id.startswith("raw_")
    finally:
        await db.disconnect()
```

### 测试用户 ID

使用描述性前缀：`test_<feature>_<purpose>`
- `test_user_store` - 存储测试
- `test_user_recall` - 召回测试
- `test_user_compact` - 压缩测试

---

## OpenClaw 插件集成

### 插件清单

文件：`src/openclaw_plugin/openclaw.plugin.json`

```json
{
  "id": "memory-recall",
  "name": "Memory Recall Engine",
  "version": "4.0.0",
  "type": "context_engine",
  "capabilities": {
    "owns_compaction": true,
    "supports_dag": true,
    "supports_recall": true
  }
}
```

### ContextEngine 实现

```python
# src/openclaw_plugin/context_engine.py
from src.services.lossless.memory_recall_engine import memory_recall_engine

class MemoryRecallContextEngine:
    """OpenClaw ContextEngine 实现"""
    
    async def bootstrap(self, params: Dict) -> Dict:
        return await memory_recall_engine.bootstrap(params)
    
    async def ingest(self, params: Dict) -> Dict:
        return await memory_recall_engine.ingest(params)
    
    async def assemble(self, params: Dict) -> Dict:
        return await memory_recall_engine.assemble(params)
    
    async def compact(self, params: Dict) -> Dict:
        return await memory_recall_engine.compact(params)
```

---

## 实施进度

### ✅ 已完成（Phase 1-4）

| 模块 | 状态 | 文件 |
|-----|------|-----|
| 数据库表（6个） | ✅ | `migrations/015_create_lossless_tables.sql` |
| RawMessageStore | ✅ | `src/services/lossless/raw_message_store.py` |
| SummaryStore | ✅ | `src/services/lossless/summary_store.py` |
| ContextStore | ✅ | `src/services/lossless/context_store.py` |
| CompactionEngine | ✅ | `src/services/lossless/compaction_engine.py` |
| MemoryRecallEngine | ✅ | `src/services/lossless/memory_recall_engine.py` |
| LosslessRecallService | ✅ | `src/services/lossless/lossless_recall_service.py` |
| DAGExpandService | ✅ | `src/services/lossless/dag_expand_service.py` |
| UnifiedMemoryService | ✅ | `src/services/unified_memory_service.py` |
| OpenClaw 插件清单 | ✅ | `src/openclaw_plugin/openclaw.plugin.json` |
| API: POST /memories | ✅ | `src/routes/memories.py`（使用 raw_messages） |
| API: POST /files/upload | ✅ | `src/routes/files.py`（使用 raw_messages） |

### 🚧 待完成（Phase 5-6）

| 功能 | 优先级 | 影响范围 |
|-----|--------|---------|
| 实体提取集成 | P0 | 图谱召回失效 |
| 召回返回片段 | P0 | 长文本召回不可用 |
| 暴露 expand API | P1 | 摘要无法展开 |
| 暴露 assemble API | P1 | Agent 无法组装上下文 |
| 暴露 compact API | P1 | 无法手动触发压缩 |
| message_entities 关联 | P2 | 图谱召回精度下降 |
| 长文档自动压缩 | P2 | 长文档无摘要 |

---

## 注意事项

1. **向量嵌入**：使用字符串格式 `"[0.1,0.2,...]"` 存储
2. **Schema 隔离**：每个用户独立 Schema
3. **Fresh Tail 保护**：压缩时保护最近 8 条消息
4. **三阶段压缩**：normal → aggressive → fallback
5. **测试隔离**：每个测试使用唯一 user_id
6. **agent_id 区分**：NULL = 用户手动，非 NULL = Agent 对话
