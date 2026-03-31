# 智能召回路由系统 - 实现总结

## 实现内容

### 1. 核心服务：`smart_recall_service.py`

**文件位置**：`apps/api/src/services/smart_recall_service.py`

**核心功能**：
- 定义 5 种召回策略的 Function Calling 工具
- 实现 LLM 自动选择召回策略
- 执行各种召回策略并返回结果

**关键代码结构**：
```python
class SmartRecallService:
    async def smart_recall(query, user_id, limit, detail_level):
        # 1. LLM 选择召回策略
        route_decision = await self._select_recall_strategy(query)
        
        # 2. 执行召回
        if route_decision["strategy"] == "vector_recall":
            memories = await self._execute_vector_recall(...)
        elif ...
        
        # 3. 生成回答
        result = await llm_recall.generate_recall_response(...)
        
        return result
```

### 2. API 端点：`/memories/smart-recall`

**文件位置**：`apps/api/src/routes/memories.py`

**新增内容**：
- 请求模型：`SmartRecallRequest`
- API 端点：`POST /api/v1/memories/smart-recall`

**响应格式**：
```json
{
  "code": 200,
  "message": "success",
  "data": {
    "answer": "自然语言回答",
    "used_memories": [...],
    "memory_count": 3,
    "route_decision": {
      "strategy": "graph_recall",
      "reason": "选择原因",
      "params": {...}
    }
  }
}
```

### 3. 文档和测试

**文档**：
- `docs/SMART_RECALL.md`：完整使用文档
- 更新 `README.md`：添加智能召回说明

**测试**：
- `tests/test_smart_recall.py`：单元测试
- `examples/smart_recall_demo.py`：快速演示

## 技术亮点

### 1. Function Calling 设计

**工具定义示例**：
```python
GRAPH_RECALL_TOOL = {
    "type": "function",
    "function": {
        "name": "graph_recall",
        "description": "使用知识图谱召回记忆。适合实体关系查询...",
        "parameters": {
            "type": "object",
            "properties": {
                "entity_name": {"type": "string", "description": "实体名称"},
                "relation_type": {"type": "string", "description": "关系类型"},
                "reason": {"type": "string", "description": "选择原因"}
            },
            "required": ["entity_name", "reason"]
        }
    }
}
```

**优点**：
- 结构化参数定义
- 清晰的描述信息
- 自动参数验证

### 2. 智能路由逻辑

**LLM 提示词设计**：
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

**决策流程**：
```
用户查询 → LLM 分析 → 选择策略 → 执行召回 → 生成回答
```

### 3. 降级机制

**自动降级**：
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

**保证可用性**：
- LLM 调用失败 → 使用混合召回
- 策略不存在 → 使用混合召回
- 参数解析失败 → 使用默认参数

### 4. 透明决策

**返回决策信息**：
```json
{
  "route_decision": {
    "strategy": "graph_recall",
    "reason": "查询涉及人物关系，适合图谱召回",
    "params": {
      "entity_name": "张三",
      "relation_type": null
    }
  }
}
```

**优点**：
- 可解释性强
- 便于调试
- 用户可理解

## 对比传统召回

### 传统召回 (`/memories/recall`)

**流程**：
```
用户查询 → 规则解析 → 固定混合召回 → 返回结果
```

**问题**：
- 无法根据查询特点调整策略
- 解析规则固定，灵活性差
- 不够智能

### 智能召回 (`/memories/smart-recall`)

**流程**：
```
用户查询 → LLM 分析意图 → 选择最佳策略 → 执行召回 → 返回结果 + 决策信息
```

**优势**：
- ✅ 理解查询语义
- ✅ 自动选择策略
- ✅ 灵活调整参数
- ✅ 透明决策过程
- ✅ 易于扩展

## 使用示例

### 示例 1：人物关系查询

**查询**：`"张三的朋友"`

**LLM 决策**：
```json
{
  "strategy": "graph_recall",
  "reason": "查询涉及人物关系，适合图谱召回",
  "params": {
    "entity_name": "张三"
  }
}
```

**召回过程**：
1. 从图谱中查找实体"张三"
2. 遍历关系：friend, colleague 等
3. 返回相关记忆

### 示例 2：时间查询

**查询**：`"最近一周做了什么"`

**LLM 决策**：
```json
{
  "strategy": "time_recall",
  "reason": "时间范围明确，使用时间召回",
  "params": {
    "start_date": "2026-03-18",
    "end_date": "2026-03-25"
  }
}
```

**召回过程**：
1. 解析时间范围
2. 按时间过滤记忆
3. 返回时间范围内的记忆

### 示例 3：复杂查询

**查询**：`"上周在咖啡店见的朋友"`

**LLM 决策**：
```json
{
  "strategy": "hybrid_recall",
  "reason": "复杂查询，结合时间、地点、人物，使用混合召回",
  "params": {
    "query": "上周在咖啡店见的朋友",
    "time_keywords": "上周",
    "location_filter": "咖啡店",
    "weights": {
      "vector": 0.5,
      "keyword": 0.3,
      "graph": 0.2
    }
  }
}
```

**召回过程**：
1. 并发执行：向量召回 + 关键词召回 + 图谱召回
2. 加权融合结果
3. 返回综合结果

## 扩展性

### 添加新的召回策略

**步骤**：

1. **定义工具**：
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

2. **添加到列表**：
```python
ALL_RECALL_TOOLS.append(NEW_RECALL_TOOL)
```

3. **实现执行方法**：
```python
async def _execute_new_recall(self, params: Dict, user_id: str, limit: int):
    # 实现新的召回逻辑
    pass
```

4. **更新路由逻辑**：
```python
elif route_decision["strategy"] == "new_recall":
    memories = await self._execute_new_recall(...)
```

**优点**：
- 不影响现有代码
- 插件式扩展
- LLM 自动识别新策略

## 性能考虑

### LLM 调用延迟

**问题**：LLM 选择策略需要 1-3 秒

**优化方案**：
1. **策略缓存**：相似查询复用策略决策
2. **规则预判**：简单查询直接使用规则路由
3. **并行调用**：混合召回并发执行多路召回

### 召回性能

**混合召回**：
```python
tasks = [
    self._vector_recall(query, user_id, limit),
    self._keyword_recall(query, user_id, limit),
    self._graph_recall(query, user_id, limit)
]

results = await asyncio.gather(*tasks)
```

**优点**：
- 并发执行
- 减少总耗时
- 提高吞吐量

## 监控和调试

### 日志记录

```python
logger.info(f"[Smart Recall] 查询: {query}")
logger.info(f"[Smart Recall] 决策: {route_decision['strategy']}")
logger.info(f"[Smart Recall] 原因: {route_decision['reason']}")
```

### 监控指标

建议监控：
1. **策略分布**：各策略使用频率
2. **决策时间**：LLM 选择策略耗时
3. **召回效果**：各策略平均召回数
4. **用户满意度**：回答质量评分

## 总结

### 核心价值

1. **智能化**：LLM 理解查询语义，自动选择最佳策略
2. **透明性**：返回决策原因，便于理解和调试
3. **灵活性**：易于扩展新的召回策略
4. **鲁棒性**：自动降级机制保证可用性

### 技术栈

- **Function Calling**：结构化策略选择
- **LLM**：查询意图理解
- **向量数据库**：语义召回
- **知识图谱**：关系召回
- **全文检索**：关键词召回

### 适用场景

- ✅ 智能记忆助手
- ✅ 个人知识管理
- ✅ 日记和笔记系统
- ✅ AI Agent 记忆模块

### 未来优化

- [ ] 策略决策缓存
- [ ] 规则预判优化
- [ ] 更多召回策略（情感、主题等）
- [ ] 用户反馈学习
- [ ] A/B 测试框架
