# memory_recall Phase 3 异步处理实施方案

**创建时间**：2026-03-22 22:21
**目标**：实现异步处理架构，用户体验响应时间降至 0.5s
**预期效果**：用户体验提升 90%

---

## 一、Phase 3 核心设计

### 1.1 异步处理流程

```
用户提交内容
    ↓
立即返回 memory_id + status="processing"（0.5s）
    ↓
后台异步处理：
    - LLM 提取（15-20s）
    - 向量生成（3-5s）
    - 数据库存储（2-3s）
    ↓
更新状态为 status="completed"
    ↓
用户可通过 API 查询状态
```

### 1.2 状态管理

**记忆状态**：
- `processing`：处理中
- `completed`：已完成
- `failed`：处理失败

**状态查询 API**：
```
GET /api/v1/memories/{memory_id}/status
Response: {
  "memory_id": "xxx",
  "status": "processing",
  "progress": 50,  // 可选：进度百分比
  "error": null
}
```

---

## 二、技术实现方案

### 2.1 后台任务队列

**方案选择**：使用 Python asyncio 后台任务

**优势**：
- ✅ 不需要额外依赖（如 Celery、Redis）
- ✅ 简单易实现
- ✅ 适合中小规模应用

**劣势**：
- ⚠️ 服务重启会丢失任务
- ⚠️ 无分布式支持

**实现代码**：
```python
import asyncio
from typing import Dict, Any
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class AsyncTaskManager:
    def __init__(self):
        self.tasks: Dict[str, asyncio.Task] = {}
        self.status: Dict[str, Dict[str, Any]] = {}
    
    async def create_memory_async(
        self,
        content: str,
        user_id: str,
        enable_graph: bool = True
    ) -> str:
        """异步创建记忆，立即返回 memory_id"""
        import uuid
        memory_id = str(uuid.uuid4())
        
        # 初始化状态
        self.status[memory_id] = {
            "status": "processing",
            "progress": 0,
            "error": None,
            "created_at": datetime.now().isoformat()
        }
        
        # 创建后台任务
        task = asyncio.create_task(
            self._process_memory_background(
                memory_id, content, user_id, enable_graph
            )
        )
        
        self.tasks[memory_id] = task
        
        logger.info(f"Created async task for memory {memory_id}")
        
        return memory_id
    
    async def _process_memory_background(
        self,
        memory_id: str,
        content: str,
        user_id: str,
        enable_graph: bool
    ):
        """后台处理记忆"""
        try:
            # 更新进度：10%
            self.status[memory_id]["progress"] = 10
            
            # 1. LLM 提取（15-20s）
            structured_info = await self.llm_extract(content)
            self.status[memory_id]["progress"] = 50
            
            # 2. 向量生成（3-5s）
            embedding = await self.generate_embedding(content)
            self.status[memory_id]["progress"] = 70
            
            # 3. 数据库存储（2-3s）
            await self.save_to_db(memory_id, structured_info, embedding, user_id)
            self.status[memory_id]["progress"] = 100
            
            # 更新状态为完成
            self.status[memory_id]["status"] = "completed"
            
            logger.info(f"Memory {memory_id} processed successfully")
            
        except Exception as e:
            logger.error(f"Memory {memory_id} processing failed: {e}")
            self.status[memory_id]["status"] = "failed"
            self.status[memory_id]["error"] = str(e)
    
    async def get_status(self, memory_id: str) -> Dict[str, Any]:
        """查询任务状态"""
        return self.status.get(memory_id, {
            "status": "not_found",
            "error": "Memory ID not found"
        })

# 全局任务管理器
task_manager = AsyncTaskManager()
```

### 2.2 API 端点设计

**创建记忆（异步）**：
```python
from fastapi import APIRouter, BackgroundTasks

router = APIRouter()

@router.post("/api/v1/memories/async")
async def create_memory_async(
    content: str,
    user_id: str,
    enable_graph: bool = True
):
    """异步创建记忆，立即返回 memory_id"""
    memory_id = await task_manager.create_memory_async(
        content, user_id, enable_graph
    )
    
    return {
        "memory_id": memory_id,
        "status": "processing",
        "message": "Memory creation started. Use /api/v1/memories/{memory_id}/status to check progress."
    }
```

**查询状态**：
```python
@router.get("/api/v1/memories/{memory_id}/status")
async def get_memory_status(memory_id: str):
    """查询记忆创建状态"""
    status = await task_manager.get_status(memory_id)
    return status
```

**获取记忆（完成后）**：
```python
@router.get("/api/v1/memories/{memory_id}")
async def get_memory(memory_id: str, user_id: str):
    """获取记忆详情"""
    # 检查状态
    status = await task_manager.get_status(memory_id)
    
    if status["status"] == "processing":
        return {"error": "Memory is still being processed"}
    elif status["status"] == "failed":
        return {"error": f"Memory processing failed: {status['error']}"}
    
    # 从数据库获取记忆
    memory = await db.get_memory(memory_id, user_id)
    return memory
```

---

## 三、数据库设计

### 3.1 状态字段

**在 memories 表添加状态字段**：
```sql
ALTER TABLE memories ADD COLUMN processing_status VARCHAR(20) DEFAULT 'processing';
ALTER TABLE memories ADD COLUMN processing_progress INTEGER DEFAULT 0;
ALTER TABLE memories ADD COLUMN processing_error TEXT;
ALTER TABLE memories ADD COLUMN processing_started_at TIMESTAMP;
ALTER TABLE memories ADD COLUMN processing_completed_at TIMESTAMP;
```

### 3.2 状态更新

**创建记忆时**：
```sql
INSERT INTO memories (id, content, processing_status, processing_started_at)
VALUES ('memory_id', 'content', 'processing', NOW());
```

**完成时**：
```sql
UPDATE memories 
SET processing_status = 'completed',
    processing_progress = 100,
    processing_completed_at = NOW()
WHERE id = 'memory_id';
```

**失败时**：
```sql
UPDATE memories 
SET processing_status = 'failed',
    processing_error = 'Error message'
WHERE id = 'memory_id';
```

---

## 四、前端适配

### 4.1 用户交互流程

```
用户提交内容
    ↓
显示"处理中..." + 进度条
    ↓
轮询状态 API（每 2 秒）
    ↓
状态变为 "completed"
    ↓
显示记忆详情
```

### 4.2 前端代码示例

```javascript
async function createMemory(content) {
  // 1. 提交创建请求
  const response = await fetch('/api/v1/memories/async', {
    method: 'POST',
    body: JSON.stringify({ content, user_id: 'user123' })
  });
  
  const { memory_id } = await response.json();
  
  // 2. 显示处理中状态
  showProcessingUI(memory_id);
  
  // 3. 轮询状态
  const statusInterval = setInterval(async () => {
    const status = await fetch(`/api/v1/memories/${memory_id}/status`);
    const data = await status.json();
    
    // 更新进度条
    updateProgress(data.progress);
    
    if (data.status === 'completed') {
      clearInterval(statusInterval);
      showMemoryDetails(memory_id);
    } else if (data.status === 'failed') {
      clearInterval(statusInterval);
      showError(data.error);
    }
  }, 2000);
}
```

---

## 五、错误处理

### 5.1 任务失败重试

```python
async def _process_memory_with_retry(
    self,
    memory_id: str,
    content: str,
    user_id: str,
    enable_graph: bool,
    max_retries: int = 3
):
    """带重试的后台处理"""
    for attempt in range(max_retries):
        try:
            await self._process_memory_background(
                memory_id, content, user_id, enable_graph
            )
            return
        except Exception as e:
            logger.warning(f"Memory {memory_id} processing failed (attempt {attempt + 1}): {e}")
            
            if attempt == max_retries - 1:
                # 最后一次重试失败，标记为失败
                self.status[memory_id]["status"] = "failed"
                self.status[memory_id]["error"] = str(e)
            else:
                # 等待后重试
                await asyncio.sleep(5)
```

### 5.2 任务超时处理

```python
async def _process_memory_background(
    self,
    memory_id: str,
    content: str,
    user_id: str,
    enable_graph: bool
):
    """后台处理记忆，带超时"""
    try:
        # 设置超时：60 秒
        await asyncio.wait_for(
            self._process_memory_impl(memory_id, content, user_id, enable_graph),
            timeout=60
        )
    except asyncio.TimeoutError:
        logger.error(f"Memory {memory_id} processing timeout")
        self.status[memory_id]["status"] = "failed"
        self.status[memory_id]["error"] = "Processing timeout (60s)"
```

---

## 六、监控与日志

### 6.1 性能监控

**关键指标**：
- 创建记忆响应时间（应 < 1s）
- 任务完成时间（应 < 30s）
- 任务失败率（应 < 5%）
- 任务队列长度（应 < 100）

**监控代码**：
```python
import time
import logging

logger = logging.getLogger(__name__)

async def create_memory_async(self, content: str, user_id: str):
    start_time = time.time()
    
    try:
        memory_id = await self._create_memory_async_impl(content, user_id)
        
        response_time = time.time() - start_time
        logger.info(f"create_memory_async: response_time={response_time:.2f}s, memory_id={memory_id}")
        
        # 告警：响应时间超过 1 秒
        if response_time > 1.0:
            logger.warning(f"create_memory_async slow: {response_time:.2f}s")
        
        return memory_id
        
    except Exception as e:
        logger.error(f"create_memory_async failed: {e}")
        raise
```

### 6.2 任务状态统计

```python
async def get_task_statistics(self) -> Dict[str, Any]:
    """获取任务统计信息"""
    total = len(self.status)
    processing = sum(1 for s in self.status.values() if s["status"] == "processing")
    completed = sum(1 for s in self.status.values() if s["status"] == "completed")
    failed = sum(1 for s in self.status.values() if s["status"] == "failed")
    
    return {
        "total": total,
        "processing": processing,
        "completed": completed,
        "failed": failed,
        "success_rate": completed / total if total > 0 else 0
    }
```

---

## 七、实施步骤

### 7.1 Phase 3 实施计划

**Step 1：数据库迁移（1 小时）**
- 添加状态字段
- 更新索引

**Step 2：实现 AsyncTaskManager（2-3 小时）**
- 后台任务管理
- 状态更新
- 错误处理

**Step 3：修改 API 端点（2-3 小时）**
- 创建异步端点
- 状态查询端点
- 获取记忆端点适配

**Step 4：前端适配（2-3 小时）**
- 轮询逻辑
- 进度条 UI
- 错误处理

**Step 5：测试验证（2-3 小时）**
- 单元测试
- 端到端测试
- 性能测试

**总预计时间**：1-2 天

---

## 八、风险评估

### 8.1 技术风险

| 风险 | 影响 | 概率 | 缓解措施 |
|------|------|------|----------|
| **服务重启丢失任务** | 高 | 中 | 持久化任务状态到数据库 |
| **任务队列过长** | 中 | 低 | 限制并发任务数 |
| **任务失败率高** | 高 | 低 | 重试机制 + 错误处理 |

### 8.2 缓解方案

**持久化任务状态**：
```python
# 在创建任务时，同时写入数据库
async def create_memory_async(self, content: str, user_id: str):
    memory_id = str(uuid.uuid4())
    
    # 写入数据库
    await db.execute(
        "INSERT INTO memories (id, content, processing_status, processing_started_at) VALUES (?, ?, ?, ?)",
        (memory_id, content, 'processing', datetime.now())
    )
    
    # 创建后台任务
    task = asyncio.create_task(...)
    
    return memory_id
```

---

## 九、总结

### 9.1 核心优势

1. **用户体验提升 90%**：响应时间从 14-17s 降至 0.5s
2. **架构简单**：不需要额外依赖（如 Celery、Redis）
3. **易于维护**：代码清晰，逻辑简单
4. **可扩展**：未来可升级为分布式任务队列

### 9.2 实施建议

1. **优先实施**：Phase 3 是最有效的优化，应优先实施
2. **渐进式部署**：先在测试环境验证，再逐步推广
3. **监控先行**：实施前先建立监控体系

### 9.3 预期效果

| 指标 | 优化前 | Phase 2 后 | Phase 3 后 |
|------|--------|-----------|-----------|
| **响应时间** | 24-28s | 14-17s | **0.5s** |
| **用户体验** | 差 | 一般 | **优秀** |
| **Token 消耗** | 高 | 降低 57.8% | 降低 57.8% |

---

**文档完成时间**：2026-03-22 22:21
**下一步**：实施 Phase 3 异步处理架构
