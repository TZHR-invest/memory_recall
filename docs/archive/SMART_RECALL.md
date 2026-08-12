# 智能召回路由系统

## 概述

智能召回路由系统通过 **Function Calling** 让 LLM 自动选择最佳召回策略，实现更智能的记忆查询。

## 核心设计

### 1. 召回策略分类

系统支持 5 种召回策略：

| 策略 | 适用场景 | 优点 | 示例查询 |
|------|---------|------|---------|
| **vector_recall** | 语义化查询 | 理解语义相似性 | "开心的事情"、"有意义的对话" |
| **keyword_recall** | 明确关键词 | 精确匹配，召回率高 | "咖啡店"、"张三"、"项目X" |
| **graph_recall** | 实体关系查询 | 利用关系网络 | "张三的朋友"、"在咖啡店见的人" |
| **time_recall** | 时间明确查询 | 精确时间过滤 | "上周"、"最近3天"、"2024年1月" |
| **hybrid_recall** | 复杂/不确定查询 | 综合多种方式 | "上周在咖啡店见的朋友" |

### 2. Function Calling 工具定义

每种召回策略都定义为独立的 Function Calling 工具：

```python
VECTOR_RECALL_TOOL = {
    "type": "function",
    "function": {
        "name": "vector_recall",
        "description": "使用向量相似度召回记忆。适合语义化查询...",
        "parameters": {
            "query": "查询文本",
            "min_similarity": "最小相似度阈值",
            "reason": "选择此策略的原因"
        }
    }
}
```

### 3. 智能路由流程

```
用户查询
    ↓
LLM 分析查询意图
    ↓
选择召回策略（Function Calling）
    ↓
执行召回
    ↓
生成自然语言回答
```

## API 使用

### 接口地址

```
POST /api/v1/memories/smart-recall
```

### 请求示例

```bash
curl -X POST http://localhost:8000/api/v1/memories/smart-recall \
  -H "Content-Type: application/json" \
  -d '{
    "query": "张三的朋友",
    "user_id": "test_user",
    "limit": 10,
    "detail_level": "medium"
  }'
```

### 响应示例

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "answer": "张三的朋友包括李四和王五...",
    "used_memories": [
      {
        "memory_id": "xxx",
        "content": "张三和李四在咖啡店见面",
        "similarity": 0.95
      }
    ],
    "memory_count": 2,
    "route_decision": {
      "strategy": "graph_recall",
      "reason": "查询涉及人物关系，适合图谱召回",
      "params": {
        "entity_name": "张三",
        "relation_type": null
      }
    }
  }
}
```

## 策略选择逻辑

### LLM 决策提示词

```
你是一个智能记忆召回路由助手。

你的任务是根据用户查询，选择最合适的召回策略。

**选择原则：**
- 时间明确的查询 → time_recall
- 明确关键词 → keyword_recall
- 实体关系查询 → graph_recall
- 语义化查询 → vector_recall
- 复杂/不确定查询 → hybrid_recall
```

### 查询示例与策略映射

| 查询 | LLM 选择策略 | 原因 |
|------|------------|------|
| "张三的朋友" | graph_recall | 涉及人物关系，适合图谱召回 |
| "最近一周" | time_recall | 时间明确，使用时间召回 |
| "咖啡店" | keyword_recall | 明确关键词，精确匹配 |
| "开心的事情" | vector_recall | 语义化查询，理解情感 |
| "上周在咖啡店见的朋友" | hybrid_recall | 复杂查询，结合多种方式 |

## 降级策略

### 自动降级

当 LLM 决策失败时，系统会自动降级到 `hybrid_recall`：

```python
try:
    route_decision = await self._select_recall_strategy(query)
except Exception as e:
    # 降级到混合召回
    route_decision = {
        "strategy": "hybrid_recall",
        "reason": f"决策失败: {str(e)}，使用默认混合召回",
        "params": {"query": query}
    }
```

### 性能监控

系统记录每次召回的路由决策：

```python
logger.info(f"[Smart Recall] 查询: {query}")
logger.info(f"[Smart Recall] 决策: {route_decision['strategy']}")
logger.info(f"[Smart Recall] 原因: {route_decision['reason']}")
```

## 测试

### 单元测试

```bash
cd apps/api
pytest tests/test_smart_recall.py
```

### 手动测试

```python
from src.services.smart_recall_service import get_smart_recall_service

smart_recall = get_smart_recall_service()

result = await smart_recall.smart_recall(
    query="张三的朋友",
    user_id="test_user",
    limit=10
)

print(f"策略: {result['route_decision']['strategy']}")
print(f"回答: {result['answer']}")
```

## 对比传统召回

### 传统召回（/memories/recall）

- 固定使用混合召回策略
- 需要手动解析查询意图
- 无法根据查询特点调整策略

### 智能召回（/memories/smart-recall）

- LLM 自动选择最佳策略
- 理解查询语义和意图
- 灵活调整召回参数
- 提供决策透明度（返回选择原因）

## 扩展性

### 添加新的召回策略

1. 定义 Function Calling 工具：

```python
NEW_RECALL_TOOL = {
    "type": "function",
    "function": {
        "name": "new_recall",
        "description": "新的召回策略...",
        "parameters": {...}
    }
}
```

2. 添加到工具列表：

```python
ALL_RECALL_TOOLS.append(NEW_RECALL_TOOL)
```

3. 实现执行方法：

```python
async def _execute_new_recall(self, params: Dict, user_id: str, limit: int):
    # 实现新的召回逻辑
    pass
```

4. 更新路由逻辑：

```python
elif route_decision["strategy"] == "new_recall":
    memories = await self._execute_new_recall(...)
```

## 性能优化

### 缓存策略决策

对于相似查询，可以缓存 LLM 的策略决策：

```python
# TODO: 实现策略决策缓存
strategy_cache = {}

def get_cached_strategy(query: str) -> Optional[str]:
    # 相似查询复用策略
    pass
```

### 并发执行

混合召回可以并发执行多路召回：

```python
tasks = [
    self._vector_recall(query, user_id, limit),
    self._keyword_recall(query, user_id, limit),
    self._graph_recall(query, user_id, limit)
]

results = await asyncio.gather(*tasks)
```

## 监控指标

建议监控以下指标：

1. **策略分布**：各召回策略的使用频率
2. **决策时间**：LLM 选择策略的耗时
3. **召回效果**：各策略的平均召回数量
4. **用户满意度**：回答质量评分

## 最佳实践

### 查询优化

- 使用明确的关键词 → 提高召回准确率
- 包含时间信息 → 加速时间过滤
- 指定实体名称 → 利用图谱关系

### 参数调优

- `limit`: 根据查询类型调整（时间召回建议 20，其他 10）
- `detail_level`: 简短查询用 "brief"，复杂查询用 "detailed"
- `min_similarity`: 精确查询可提高阈值（0.2），模糊查询降低阈值（0.05）

## 常见问题

**Q: LLM 选择策略不准确怎么办？**

A: 可以调整系统提示词，添加更多示例，或实现自定义路由逻辑。

**Q: 召回速度慢怎么办？**

A: 启用策略缓存，或使用混合召回的并发执行。

**Q: 如何知道 LLM 为什么选择某个策略？**

A: 响应中包含 `route_decision.reason` 字段，说明选择原因。

## 总结

智能召回路由系统通过 Function Calling 实现了查询意图的自动识别和策略选择，相比传统固定策略召回，具有以下优势：

1. **智能化**：LLM 理解查询语义，自动选择最佳策略
2. **透明性**：返回决策原因，便于理解和调试
3. **灵活性**：易于扩展新的召回策略
4. **鲁棒性**：自动降级机制保证可用性
