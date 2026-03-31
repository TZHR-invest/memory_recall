# 统一 DAG 记忆架构实施计划

## 概述

将传统记忆架构（`memories` 表 + 记忆点提取）统一到 DAG 架构（`raw_messages` + `summaries`），实现设计文档 v3.0 的统一记忆架构要求。

## 当前状态

| 组件 | 当前状态 | 目标状态 |
|-----|---------|---------|
| 用户手动输入 | `memories` 表 | `raw_messages` 表 |
| Agent 对话 | `raw_messages` 表 | `raw_messages` 表 |
| 记忆点提取 | LLM 提取多条记忆点 | 废弃，消息级别存储 |
| agent_id 区分 | 未实现 | NULL=手动，非NULL=Agent |
| 召回服务 | `memories` 表搜索 | `raw_messages` + `summaries` |

---

## Phase 1: 数据库迁移准备

### 1.1 扩展 raw_messages 表字段

**目标**: 添加传统 memories 表的字段到 raw_messages

**SQL 变更**:
```sql
-- 添加缺失字段
ALTER TABLE raw_messages ADD COLUMN IF NOT EXISTS location_name VARCHAR(255);
ALTER TABLE raw_messages ADD COLUMN IF NOT EXISTS location_address TEXT;
ALTER TABLE raw_messages ADD COLUMN IF NOT EXISTS people JSONB;
ALTER TABLE raw_messages ADD COLUMN IF NOT EXISTS tags JSONB;
ALTER TABLE raw_messages ADD COLUMN IF NOT EXISTS source_type VARCHAR(50) DEFAULT 'manual';
```

**验证**:
```bash
psql -d memory_recall -c "\d raw_messages"
```

### 1.2 创建迁移脚本

**文件**: `migrations/016_unify_memory_architecture.sql`

**内容**:
- 扩展 raw_messages 表
- 添加数据迁移逻辑
- 创建视图保持向后兼容

---

## Phase 2: 服务层重构

### 2.1 更新 RawMessageStore

**文件**: `src/services/lossless/raw_message_store.py`

**新增方法**:
```python
async def store_with_metadata(
    self,
    user_id: str,
    content: str,
    memory_type: str = "preference",
    agent_id: Optional[str] = None,
    session_id: Optional[str] = None,
    # 新增字段
    location_name: Optional[str] = None,
    location_address: Optional[str] = None,
    people: Optional[List[Dict]] = None,
    tags: Optional[List[str]] = None,
    source_type: str = "manual",
) -> str:
    """存储带元数据的消息"""
    ...
```

**验证**:
```bash
pytest tests/test_lossless/test_raw_message_store.py -v
```

### 2.2 创建 UnifiedMemoryService

**文件**: `src/services/unified_memory_service.py`

**职责**:
- 统一入口，处理用户手动输入和 Agent 对话
- 自动判断 agent_id 区分来源
- 处理长文本分段
- 可选压缩

**核心方法**:
```python
class UnifiedMemoryService:
    async def store(
        self,
        user_id: str,
        content: str,
        source: str = "manual",  # manual | agent
        agent_id: Optional[str] = None,
        session_id: Optional[str] = None,
        metadata: Optional[Dict] = None,
    ) -> Dict:
        """
        统一存储入口
        
        Returns:
            {
                "raw_message_id": "raw_xxx",
                "memory_type": "preference",
                "is_long_document": False,
                "chunk_count": 1,
            }
        """
        ...
    
    async def recall(
        self,
        query: str,
        user_id: str,
        scope: str = "all",  # all | manual_only | agent_only
        agent_id: Optional[str] = None,
        limit: int = 20,
    ) -> List[Dict]:
        """统一召回"""
        ...
```

**验证**:
```bash
pytest tests/test_unified_memory_service.py -v
```

### 2.3 废弃 MemoryService 的记忆点提取

**文件**: `src/services/memory_service.py`

**变更**:
- 标记 `create_memory_with_graph_v2` 为废弃
- 添加迁移提示日志

```python
import warnings

async def create_memory_with_graph_v2(...):
    warnings.warn(
        "create_memory_with_graph_v2 is deprecated. "
        "Use UnifiedMemoryService.store() instead.",
        DeprecationWarning,
    )
    # ... 保留旧逻辑用于兼容
```

---

## Phase 3: API 层重构

### 3.1 修改 /memories 端点

**文件**: `src/routes/memories.py`

**变更前**:
```python
@router.post("")
async def create_memory(memory: MemoryCreate, user_id: str):
    result = await memory_service.create_memory_with_graph_v2(...)
    ...
```

**变更后**:
```python
@router.post("")
async def create_memory(memory: MemoryCreate, user_id: str):
    # 使用统一服务
    from ..services.unified_memory_service import unified_memory_service
    
    result = await unified_memory_service.store(
        user_id=user_id,
        content=memory.content,
        source="manual",
        agent_id=None,
        metadata={
            "location_name": memory.location.name if memory.location else None,
            "tags": memory.tags,
            "people": [p.model_dump() for p in memory.people] if memory.people else None,
        },
    )
    
    return {
        "code": 200,
        "message": "success",
        "data": {
            "id": result["raw_message_id"],
            "content": memory.content,
            "memory_type": result["memory_type"],
        },
    }
```

### 3.2 更新召回端点

**文件**: `src/routes/memories.py`

**变更**:
```python
@router.post("/recall")
async def recall(request: RecallRequest):
    from ..services.unified_memory_service import unified_memory_service
    
    results = await unified_memory_service.recall(
        query=request.query,
        user_id=request.user_id,
        scope="manual_only" if not request.use_agent_context else "all",
        limit=request.limit,
    )
    
    # 生成 LLM 回答
    answer = await llm_recall_service.generate_recall_response(...)
    
    return {
        "answer": answer["answer"],
        "memories": results,
        "memory_count": len(results),
    }
```

### 3.3 新增 Agent 专用端点

**文件**: `src/routes/agent_context.py` (新建)

```python
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/agent/context", tags=["Agent Context"])

class AgentIngestRequest(BaseModel):
    user_id: str
    agent_id: str
    session_id: str
    message: dict  # {"role": "user/assistant", "content": "..."}

class AgentRecallRequest(BaseModel):
    query: str
    user_id: str
    agent_id: str
    session_id: Optional[str] = None
    limit: int = 20

@router.post("/ingest")
async def ingest(request: AgentIngestRequest):
    """Agent 存储消息"""
    ...

@router.post("/recall")
async def recall(request: AgentRecallRequest):
    """Agent 召回上下文"""
    ...

@router.post("/assemble")
async def assemble(request: AssembleRequest):
    """组装上下文给 LLM"""
    ...
```

---

## Phase 4: 召回服务统一

### 4.1 更新 LosslessRecallService

**文件**: `src/services/lossless/lossless_recall_service.py`

**变更**:
- 增加对传统 memories 表的兼容查询（过渡期）
- 优先搜索 raw_messages + summaries

```python
async def hybrid_recall(...):
    # 主搜索：raw_messages + summaries
    results = await self._search_unified(query, user_id, ...)
    
    # 过渡期：兼容旧 memories 表
    if len(results) < limit:
        legacy_results = await self._search_legacy_memories(query, user_id)
        results.extend(legacy_results)
    
    return results[:limit]
```

### 4.2 创建兼容视图

**文件**: `migrations/016_unify_memory_architecture.sql`

```sql
-- 创建视图保持向后兼容
CREATE OR REPLACE VIEW memories_view AS
SELECT 
    id,
    content,
    NULL as time_value,
    location_name,
    location_address,
    people,
    tags,
    created_at,
    user_id
FROM raw_messages
WHERE agent_id IS NULL;  -- 仅用户手动输入
```

---

## Phase 5: 数据迁移

### 5.1 迁移脚本

**文件**: `scripts/migrate_memories_to_raw_messages.py`

```python
"""
将 memories 表数据迁移到 raw_messages
"""
import asyncio
from src.database import db

async def migrate():
    await db.connect()
    
    # 获取所有用户的 memories
    memories = await db.fetch("""
        SELECT id, user_id, content, created_at, 
               location_name, location_address, people, tags
        FROM memories
        WHERE status = 'active'
    """)
    
    migrated = 0
    for mem in memories:
        async with db.user_context(mem["user_id"]):
            # 检查是否已迁移
            exists = await db.fetchval(
                "SELECT 1 FROM raw_messages WHERE id = $1",
                mem["id"]
            )
            if exists:
                continue
            
            # 插入到 raw_messages
            await db.execute("""
                INSERT INTO raw_messages (
                    id, user_id, content, memory_type, agent_id,
                    location_name, location_address, people, tags,
                    source_type, created_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
            """,
                mem["id"],
                mem["user_id"],
                mem["content"],
                "preference",  # 默认类型
                None,  # agent_id = NULL 表示用户手动
                mem["location_name"],
                mem["location_address"],
                mem["people"],
                mem["tags"],
                "migrated",
                mem["created_at"],
            )
            migrated += 1
    
    print(f"Migrated {migrated} memories to raw_messages")
    await db.disconnect()

if __name__ == "__main__":
    asyncio.run(migrate())
```

### 5.2 迁移验证

```bash
# 运行迁移
python scripts/migrate_memories_to_raw_messages.py

# 验证数据
psql -d memory_recall -c "
SELECT 
    (SELECT COUNT(*) FROM memories) as old_count,
    (SELECT COUNT(*) FROM raw_messages WHERE agent_id IS NULL) as new_count
"
```

---

## Phase 6: 测试与验证

### 6.1 单元测试

**新建文件**: `tests/test_unified_memory_service.py`

```python
import pytest

@pytest.mark.asyncio
async def test_store_manual_memory():
    """测试用户手动存储"""
    service = UnifiedMemoryService()
    
    result = await service.store(
        user_id="test_user",
        content="我是素食主义者",
        source="manual",
    )
    
    assert result["raw_message_id"].startswith("raw_")
    assert result["memory_type"] == "preference"

@pytest.mark.asyncio
async def test_store_agent_message():
    """测试 Agent 消息存储"""
    result = await service.store(
        user_id="test_user",
        content="今天天气不错",
        source="agent",
        agent_id="agent_001",
        session_id="session_001",
    )
    
    assert result["raw_message_id"].startswith("raw_")

@pytest.mark.asyncio
async def test_recall_unified():
    """测试统一召回"""
    # 存储手动记忆
    await service.store(user_id="test_user", content="我喜欢咖啡", source="manual")
    
    # 存储Agent消息
    await service.store(
        user_id="test_user", 
        content="用户问今天天气",
        source="agent",
        agent_id="agent_001",
    )
    
    # 召回
    results = await service.recall(
        query="咖啡",
        user_id="test_user",
        scope="manual_only",
    )
    
    assert len(results) >= 1
    assert results[0]["agent_id"] is None
```

### 6.2 集成测试

**新建文件**: `tests/test_unified_integration.py`

```python
"""统一架构集成测试"""

async def test_api_create_memory():
    """测试 API 创建记忆"""
    response = await client.post("/memories?user_id=test_user", json={
        "content": "我喜欢喝美式咖啡",
    })
    
    assert response.status_code == 200
    data = response.json()
    assert data["data"]["id"].startswith("raw_")

async def test_api_recall():
    """测试 API 召回"""
    # 创建记忆
    await client.post("/memories?user_id=test_user", json={
        "content": "我是素食主义者",
    })
    
    # 召回
    response = await client.post("/memories/recall", json={
        "query": "我有什么饮食偏好？",
        "user_id": "test_user",
    })
    
    assert response.status_code == 200
    data = response.json()
    assert "answer" in data
```

### 6.3 回归测试

```bash
# 运行所有测试
pytest tests/ -v

# 运行统一架构测试
pytest tests/test_unified*.py -v

# 运行集成测试
python tests/test_unified_integration.py
```

---

## Phase 7: 清理与文档

### 7.1 废弃旧代码

**标记废弃**:
- `MemoryService.create_memory_with_graph_v2()`
- `MemoryService.create_with_chunks()`
- `MemoryExtractionService`（记忆点提取）

### 7.2 更新文档

**更新文件**:
- `AGENTS.md` - 更新使用说明
- `docs/api-design.md` - 更新 API 文档
- `README.md` - 更新项目说明

### 7.3 删除废弃代码（可选，建议保留过渡期）

**过渡期后可删除**:
- `memories` 表（保留视图）
- 记忆点提取相关代码

---

## 时间估算

| Phase | 任务 | 预计时间 |
|-------|-----|---------|
| 1 | 数据库迁移准备 | 2 小时 |
| 2 | 服务层重构 | 4 小时 |
| 3 | API 层重构 | 3 小时 |
| 4 | 召回服务统一 | 2 小时 |
| 5 | 数据迁移 | 2 小时 |
| 6 | 测试与验证 | 3 小时 |
| 7 | 清理与文档 | 2 小时 |
| **总计** | | **18 小时** |

---

## 风险与缓解

| 风险 | 影响 | 缓解措施 |
|-----|-----|---------|
| 旧数据迁移失败 | 用户数据丢失 | 迁移前备份，保留原表 |
| API 行为变化 | 客户端兼容性 | 保持接口签名不变 |
| 性能下降 | 用户体验 | 添加索引，监控查询性能 |
| 召回结果不一致 | 召回质量下降 | 过渡期兼容旧表 |

---

## 验收标准

- [ ] `POST /memories` 使用 `raw_messages` 表存储
- [ ] `agent_id` 正确区分来源（NULL=手动，非NULL=Agent）
- [ ] 召回搜索 `raw_messages` + `summaries`
- [ ] DAG 压缩/展开功能正常
- [ ] 所有测试通过
- [ ] API 文档更新
- [ ] 旧数据成功迁移
