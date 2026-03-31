# AI Agent 记忆召回服务设计文档

> **版本：** v1.0  
> **日期：** 2026-03-26  
> **状态：** 设计阶段

---

## 一、项目背景与目标

### 1.1 现状分析

**✅ 已实现能力：**
- 向量检索（HNSW索引，1024维）
- 关键词检索（PostgreSQL全文搜索）
- 图谱检索（实体-关系-记忆三层结构）
- 混合召回策略
- Function Calling 自动提取
- 多用户 Schema 隔离
- same_as 别称映射

**❌ 缺失能力：**
- 工作记忆（会话级别短期记忆）
- 记忆类型分类（working/episodic/semantic）
- 记忆生命周期管理（TTL、过期、归档）
- Agent 上下文隔离（agent_id/run_id）
- 记忆重要性动态计算
- 批量操作优化

### 1.2 项目目标

**核心指标：**

| 指标 | 目标值 | 优先级 |
|------|--------|--------|
| 召回延迟（P95） | < 200ms | P0 |
| 缓存命中率 | > 60% | P1 |
| 记忆分类准确率 | > 80% | P1 |
| Agent 集成时间 | < 1小时 | P2 |

### 1.3 适用场景

**P0 场景（必须支持）：**
1. 多轮对话上下文理解
2. 用户偏好记忆

**P1 场景（高优先级）：**
1. 长任务状态跟踪
2. 中断任务恢复
3. 用户反馈学习

**P2 场景（按需支持）：**
1. 知识库构建
2. 用户画像构建

---

## 二、核心设计理念

### 2.1 三层记忆模型

```
┌──────────────────────────────────────┐
│  工作记忆（Working Memory）          │
│  - 当前对话上下文                    │
│  - TTL: 1-24小时                    │
│  - 存储: 内存缓存 + 数据库          │
│  - 延迟: < 10ms                     │
└──────────────────────────────────────┘
          ↓ 沉淀
┌──────────────────────────────────────┐
│  情景记忆（Episodic Memory）         │
│  - 具体事件和经历                    │
│  - TTL: 30-90天                     │
│  - 存储: 数据库 + 向量索引          │
│  - 延迟: < 200ms                    │
└──────────────────────────────────────┘
          ↓ 抽象
┌──────────────────────────────────────┐
│  语义记忆（Semantic Memory）         │
│  - 知识、事实、用户偏好              │
│  - TTL: 永久                        │
│  - 存储: 数据库 + 知识图谱          │
│  - 延迟: < 200ms                    │
└──────────────────────────────────────┘
```

### 2.2 记忆类型判定规则

```python
# 规则优先，LLM 兜底
working_keywords = ["正在", "当前", "现在", "待处理"]
semantic_patterns = ["用户(喜欢|偏好|习惯)", "系统规则"]
episodic_keywords = ["昨天", "今天", "上周", "之前"]

if any(kw in content for kw in working_keywords):
    return "working"
elif any(正则匹配 for pattern in semantic_patterns):
    return "semantic"
elif any(kw in content for kw in episodic_keywords):
    return "episodic"
else:
    return llm_classify(content)  # 兜底
```

### 2.3 记忆重要性计算

```python
# 重要性 = 基础重要性 × 时间衰减 × 访问频率因子 × 类型因子

base = memory.importance_score  # 0.5
time_decay = exp(-decay_rate * days_old)  # 指数衰减
access_factor = 1 + log(1 + access_count) / 10  # 对数增长
type_factor = {"working": 1.5, "episodic": 1.0, "semantic": 1.2}

importance = base * time_decay * access_factor * type_factor
```

---

## 三、数据模型设计

### 3.1 memories 表扩展

```sql
-- migrations/015_add_agent_fields.sql

ALTER TABLE memories ADD COLUMN IF NOT EXISTS
    memory_type VARCHAR(20) DEFAULT 'episodic',
    agent_id VARCHAR(100),
    run_id VARCHAR(100),
    session_id VARCHAR(100),
    ttl_days INTEGER DEFAULT NULL,
    expires_at TIMESTAMP WITH TIME ZONE,
    decay_rate FLOAT DEFAULT 0.01,
    merged_from JSONB DEFAULT '[]'::jsonb,
    merged_into VARCHAR(24);

CREATE INDEX idx_memories_agent ON memories(agent_id);
CREATE INDEX idx_memories_session ON memories(session_id);
CREATE INDEX idx_memories_expires ON memories(expires_at) WHERE status = 'active';
```

### 3.2 agent_configs 表

```sql
CREATE TABLE agent_configs (
    agent_id VARCHAR(100) PRIMARY KEY,
    user_id VARCHAR(100) NOT NULL,
    memory_scope VARCHAR(20) DEFAULT 'isolated',
    max_working_memory INTEGER DEFAULT 20,
    default_ttl_days INTEGER DEFAULT 30,
    recall_strategy VARCHAR(20) DEFAULT 'hybrid',
    recall_weights JSONB DEFAULT '{"vector": 0.5, "keyword": 0.3, "graph": 0.2}',
    enable_cache BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

### 3.3 memory_access_logs 表

```sql
CREATE TABLE memory_access_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    memory_id VARCHAR(24) NOT NULL,
    agent_id VARCHAR(100),
    access_type VARCHAR(20) NOT NULL,
    access_context TEXT,
    accessed_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

---

## 四、API 接口设计

### 4.1 核心接口列表

| 端点 | 方法 | 用途 |
|------|------|------|
| `/agent/memory/store` | POST | 存储记忆（智能分类） |
| `/agent/memory/recall` | POST | 召回记忆（智能策略） |
| `/agent/memory/working` | GET | 获取工作记忆 |
| `/agent/memory/working` | DELETE | 清空工作记忆 |
| `/agent/memory/batch` | POST | 批量操作 |
| `/agent/memory/merge` | POST | 合并记忆 |
| `/agent/memory/cleanup` | POST | 清理过期记忆 |

### 4.2 存储接口示例

```python
POST /agent/memory/store

Request:
{
    "agent_id": "assistant_001",
    "run_id": "run_abc123",
    "content": "用户偏好使用中文回复",
    "memory_type": "semantic"  # 可选，不填则自动分类
}

Response:
{
    "code": 200,
    "data": {
        "memory_id": "mem_abc123",
        "memory_type": "semantic",
        "importance_score": 0.8,
        "ttl_days": null
    }
}
```

### 4.3 召回接口示例

```python
POST /agent/memory/recall

Request:
{
    "agent_id": "assistant_001",
    "query": "关于张三的记忆",
    "recall_strategy": "auto",
    "limit": 10
}

Response:
{
    "code": 200,
    "data": {
        "working_memory": [...],
        "episodic_memory": [...],
        "semantic_memory": [...],
        "total_count": 12,
        "recall_time_ms": 150
    }
}
```

---

## 五、服务架构设计

### 5.1 核心服务

```python
class AgentMemoryService:
    """Agent 记忆服务"""
    
    def __init__(self):
        # 复用现有服务
        self.base_memory_service = memory_service
        self.recall_service = get_recall_service()
        self.graph_service = get_graph_recall_service()
        
        # Agent 专用能力
        self.classifier = MemoryClassifier()
        self.importance_calculator = ImportanceCalculator()
        self.cache = MemoryCache()
    
    async def store(self, agent_id, content, **kwargs):
        """存储记忆（智能分类）"""
        # 1. 自动分类
        if not kwargs.get('memory_type'):
            kwargs['memory_type'] = await self.classifier.classify(content)
        
        # 2. 计算 TTL
        if not kwargs.get('ttl_days'):
            kwargs['ttl_days'] = self._get_default_ttl(kwargs['memory_type'])
        
        # 3. 存储到数据库（复用现有服务）
        result = await self.base_memory_service.create({
            "content": content,
            "agent_id": agent_id,
            **kwargs
        })
        
        # 4. 更新工作记忆缓存
        if kwargs['memory_type'] == 'working':
            await self.cache.set_working_memory(agent_id, kwargs.get('run_id'), result)
        
        return result
    
    async def recall(self, agent_id, query, **kwargs):
        """召回记忆（智能策略）"""
        # 1. 检查缓存
        cached = await self.cache.get_recall_result(agent_id, query)
        if cached:
            return cached
        
        # 2. 获取工作记忆
        working = await self.cache.get_working_memory(
            agent_id, kwargs.get('run_id')
        )
        
        # 3. 执行召回（复用现有服务）
        memories = await self.recall_service.search(
            query=query,
            limit=kwargs.get('limit', 10),
            agent_id=agent_id,
            enable_graph=True
        )
        
        # 4. 分组返回
        result = {
            "working_memory": working,
            "episodic_memory": [m for m in memories if m.get('memory_type') == 'episodic'],
            "semantic_memory": [m for m in memories if m.get('memory_type') == 'semantic'],
            "total_count": len(working) + len(memories)
        }
        
        # 5. 缓存结果
        await self.cache.set_recall_result(agent_id, query, result)
        
        return result
```

### 5.2 记忆分类器

```python
class MemoryClassifier:
    """记忆分类器"""
    
    async def classify(self, content: str) -> str:
        # 规则判断（快速，< 5ms）
        if any(kw in content for kw in ["正在", "当前", "现在"]):
            return "working"
        
        if any(正则匹配 for pattern in ["用户(喜欢|偏好)", "系统规则"]):
            return "semantic"
        
        if any(kw in content for kw in ["昨天", "今天", "上周"]):
            return "episodic"
        
        # LLM 兜底（~200ms）
        return await self._llm_classify(content)
```

### 5.3 记忆缓存

```python
class MemoryCache:
    """多级缓存"""
    
    def __init__(self):
        # L1: 工作记忆缓存（TTL 1小时）
        self.working_cache = {}
        
        # L2: 召回结果缓存（TTL 5分钟）
        self.recall_cache = {}
    
    async def get_working_memory(self, agent_id, run_id):
        """获取工作记忆"""
        cache_key = f"{agent_id}:{run_id}:working"
        return self.working_cache.get(cache_key, [])
    
    async def set_working_memory(self, agent_id, run_id, memory):
        """设置工作记忆"""
        cache_key = f"{agent_id}:{run_id}:working"
        if cache_key not in self.working_cache:
            self.working_cache[cache_key] = []
        
        self.working_cache[cache_key].append(memory)
        
        # 限制容量
        if len(self.working_cache[cache_key]) > 20:
            self.working_cache[cache_key] = self.working_cache[cache_key][-20:]
```

---

## 六、性能优化方案

### 6.1 多级缓存架构

```
L1 Cache: 工作记忆（内存）
  - TTL: 1小时
  - 延迟: < 10ms
  - 命中率目标: > 90%
       ↓ Miss
L2 Cache: 召回结果（内存）
  - TTL: 5分钟
  - 延迟: < 5ms
  - 命中率目标: > 60%
       ↓ Miss
Database: PostgreSQL
  - 延迟: 50-200ms
```

### 6.2 批量操作优化

```python
async def batch_store_optimized(agent_id, contents):
    # 1. 批量生成向量（1次HTTP调用）
    embeddings = await embedding_client.embed_batch(contents)
    
    # 2. 批量分类（规则优先）
    memory_types = [classifier._rule_based_classify(c) for c in contents]
    
    # 3. 事务批量写入
    async with db.transaction() as conn:
        for i, content in enumerate(contents):
            await conn.execute("""
                INSERT INTO memories (id, content, embedding, agent_id, memory_type)
                VALUES ($1, $2, $3, $4, $5)
            """, generate_id(), content, embeddings[i], agent_id, memory_types[i])
```

### 6.3 查询优化

```sql
-- 复合索引
CREATE INDEX idx_memories_agent_created 
    ON memories(agent_id, created_at DESC) 
    WHERE status = 'active';

CREATE INDEX idx_memories_agent_importance 
    ON memories(agent_id, importance_score DESC) 
    WHERE status = 'active';
```

---

## 七、实施计划

### 7.1 Phase 1: 基础适配（1周）

**目标：** 支持 Agent 基本使用

**任务清单：**
```
Day 1-2: 数据库扩展
├── 编写迁移脚本 015_add_agent_fields.sql
├── 添加 memory_type, agent_id 等字段
├── 创建索引
└── 测试迁移

Day 3-4: 核心服务实现
├── 实现 AgentMemoryService
│   ├── store() 方法
│   └── recall() 方法
├── 实现 MemoryClassifier
└── 实现 MemoryCache

Day 5-7: API 接口实现
├── 实现 /agent/memory/store
├── 实现 /agent/memory/recall
├── 实现 /agent/memory/working (GET/DELETE)
└── 集成测试
```

**验收标准：**
- ✅ Agent 可以存储和召回记忆
- ✅ 工作记忆正常工作
- ✅ 召回延迟 < 500ms

### 7.2 Phase 2: 性能优化（1周）

**目标：** 提升高频调用场景性能

**任务清单：**
```
Day 1-3: 缓存优化
├── 实现多级缓存架构
├── 实现缓存预热
└── 缓存命中率监控

Day 4-5: 批量操作优化
├── 实现批量存储接口
└── 实现批量召回接口

Day 6-7: 查询优化
├── 创建复合索引
└── 压力测试
```

**验收标准：**
- ✅ 缓存命中率 > 60%
- ✅ 召回延迟（P95）< 200ms
- ✅ 批量存储吞吐量 > 100 TPS

### 7.3 Phase 3: 高级特性（1-2周）

**目标：** 记忆生命周期管理

**任务清单：**
```
Week 1: 生命周期管理
├── 实现重要性计算
├── 实现 TTL 管理
└── 实现记忆清理

Week 2: 记忆合并
├── 实现相似记忆检测
└── 实现记忆合并
```

**验收标准：**
- ✅ 记忆自动过期率 > 90%
- ✅ 重要性计算准确率 > 80%

---

## 八、测试方案

### 8.1 单元测试

```python
# tests/test_agent_memory_service.py

@pytest.mark.asyncio
async def test_store_memory():
    result = await service.store(
        agent_id="test_agent",
        content="用户喜欢Python",
        memory_type="semantic"
    )
    assert result["memory_type"] == "semantic"

@pytest.mark.asyncio
async def test_recall_memory():
    result = await service.recall(
        agent_id="test_agent",
        query="Python"
    )
    assert result["total_count"] > 0
```

### 8.2 性能测试

```python
@pytest.mark.asyncio
async def test_recall_latency():
    # 测试召回延迟（P95 < 200ms）
    latencies = []
    for _ in range(100):
        start = time.time()
        await service.recall(agent_id="test", query="test")
        latencies.append((time.time() - start) * 1000)
    
    p95 = sorted(latencies)[95]
    assert p95 < 200
```

### 8.3 压力测试

```bash
# 使用 Locust
locust -f tests/locustfile.py --host=http://localhost:8000
```

---

## 九、监控与运维

### 9.1 监控指标

```python
# Prometheus 指标
memory_recall_latency_seconds = Histogram(
    'memory_recall_latency_seconds',
    'Memory recall latency',
    ['agent_id', 'strategy']
)

cache_hit_rate = Gauge(
    'cache_hit_rate',
    'Cache hit rate',
    ['cache_level']
)

memory_total_count = Gauge(
    'memory_total_count',
    'Total memory count',
    ['agent_id', 'memory_type']
)
```

### 9.2 告警规则

```yaml
groups:
  - name: memory_alerts
    rules:
      - alert: HighRecallLatency
        expr: histogram_quantile(0.95, recall_latency_seconds) > 0.5
        for: 5m
        annotations:
          summary: "召回延迟过高"
      
      - alert: LowCacheHitRate
        expr: cache_hit_rate < 0.5
        for: 10m
        annotations:
          summary: "缓存命中率过低"
```

### 9.3 定时清理任务

```python
# scripts/cleanup_memories.py

async def cleanup_expired_memories():
    # 1. 归档过期记忆
    expired = await db.fetch("""
        UPDATE memories
        SET status = 'archived'
        WHERE expires_at < NOW()
          AND status = 'active'
        RETURNING id
    """)
    
    # 2. 归档低重要性记忆
    low_importance = await db.fetch("""
        UPDATE memories
        SET status = 'archived'
        WHERE importance_score < 0.2
          AND created_at < NOW() - INTERVAL '90 days'
          AND status = 'active'
        RETURNING id
    """)
    
    # 3. 删除90天前的归档记忆
    deleted = await db.fetch("""
        DELETE FROM memories
        WHERE status = 'archived'
          AND updated_at < NOW() - INTERVAL '90 days'
        RETURNING id
    """)
```

---

## 十、风险评估

### 10.1 技术风险

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| LLM 分类不稳定 | 中 | 规则优先，LLM 兜底 |
| 缓存一致性 | 低 | TTL 短，主动失效 |
| 数据库性能瓶颈 | 高 | 索引优化，查询优化 |
| 向量索引失效 | 高 | 定期重建索引，监控 |

### 10.2 业务风险

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| 记忆数据泄漏 | 高 | 权限控制，数据加密 |
| 记忆丢失 | 高 | 多副本，定期备份 |
| 存储成本过高 | 中 | TTL 管理，重要性清理 |

---

## 附录

### A. 完整的数据库迁移脚本

详见：`migrations/015_add_agent_fields.sql`

### B. 性能基准

```
存储性能：
- 单条存储：< 500ms
- 批量存储（100条）：< 5s

召回性能：
- 工作记忆召回：< 10ms
- 普通召回（P95）：< 200ms

缓存性能：
- 缓存命中率：> 60%
```

### C. 参考资料

1. 认知心理学记忆理论
2. PostgreSQL 向量索引优化
3. FastAPI 性能优化
4. Redis 缓存最佳实践

---

**文档版本历史：**

| 版本 | 日期 | 变更说明 |
|------|------|----------|
| v1.0 | 2026-03-26 | 初始版本 |
