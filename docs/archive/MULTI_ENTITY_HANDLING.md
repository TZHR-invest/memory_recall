# 图谱召回 - 多实体和无实体场景处理

## 核心逻辑

```
查询 → 提取实体 → 判断实体数量
    ↓
    ├─ 多个实体 → OR 查询所有关系 → 合并记忆
    ├─ 单个实体 → 查询单个关系 → 返回记忆
    └─ 无实体   → 返回空（但混合召回仍可工作）
```

## 场景 1: 多个实体

### 查询示例

```
查询: "张三和李四在咖啡店做了什么"

提取实体: ["张三", "李四", "咖啡店"]
```

### 处理流程

#### 步骤 1: 提取实体

```python
entities = extract_entities("张三和李四在咖啡店做了什么")
# 返回: ["张三", "李四", "咖啡店"]
```

#### 步骤 2: 查询实体 ID

```sql
SELECT id, name FROM entities
WHERE name = ANY(['张三', '李四', '咖啡店'])

结果:
- 张三 → uuid-1
- 李四 → uuid-2
- 咖啡店 → uuid-3
```

#### 步骤 3: 查询所有实体的关系（关键：OR 条件）

```sql
-- 关键：使用 OR 条件查询多个实体的关系
SELECT 
    e1.name AS source,
    r.relation_type,
    e2.name AS destination
FROM relations r
JOIN entities e1 ON r.from_entity_id = e1.id
JOIN entities e2 ON r.to_entity_id = e2.id
WHERE (r.from_entity_id = ANY(['uuid-1', 'uuid-2', 'uuid-3'])
       OR r.to_entity_id = ANY(['uuid-1', 'uuid-2', 'uuid-3']))
       --     ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
       --     关键：OR 条件，查询所有实体的关系

结果（所有关系）:
- 张三 --[friend]--> 李四
- 张三 --[met_at]--> 咖啡店
- 李四 --[at]--> 咖啡店
- 张三 --[colleague]--> 王五  （间接关系，王五不在查询中）
```

**关键点**：
- 使用 `OR` 条件查询所有实体的关系
- 能发现间接关系（如张三的同事王五）
- 扩大了召回范围

#### 步骤 4: BM25 重排序

```python
# 查询分词
query_keywords = ["张三", "李四", "咖啡店"]

# 文档列表（关系三元组）
documents = [
    ["张三", "朋友", "李四"],
    ["张三", "在...遇到", "咖啡店"],
    ["李四", "在...", "咖啡店"],
    ["张三", "同事", "王五"]
]

# BM25 评分
scores = bm25.get_scores(query_keywords)
# 根据查询相关性排序关系
```

#### 步骤 5: 合并所有实体的记忆

```sql
SELECT DISTINCT 
    m.content,
    MAX(r.weight) as max_relation_weight
FROM memories m
JOIN memory_entities me ON m.id = me.memory_id
JOIN entities e ON me.entity_id = e.id
WHERE e.name IN ('张三', '李四', '咖啡店', '王五')
--                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
--                 包含所有相关实体
GROUP BY m.id
ORDER BY max_relation_weight DESC

结果:
- "张三和李四在咖啡店见面聊了新项目" (weight: 0.95)
- "张三提到李四是他的大学同学" (weight: 0.9)
- "李四喜欢在咖啡店工作" (weight: 0.85)
- "王五是张三的同事" (weight: 0.8)
```

### 返回结果

```json
{
  "relations": [
    {"source": "张三", "relationship": "friend", "destination": "李四", "weight": 0.9},
    {"source": "张三", "relationship": "met_at", "destination": "咖啡店", "weight": 0.95},
    {"source": "李四", "relationship": "at", "destination": "咖啡店", "weight": 0.85}
  ],
  "memories": [
    {"content": "张三和李四在咖啡店见面聊了新项目", "max_relation_weight": 0.95},
    {"content": "张三提到李四是他的大学同学", "max_relation_weight": 0.9},
    {"content": "李四喜欢在咖啡店工作", "max_relation_weight": 0.85}
  ]
}
```

### 多实体优势

1. **关系网络扩展**：能找到间接关系（张三 → 王五）
2. **召回范围广**：多个实体的记忆都会被召回
3. **关联性强**：BM25 根据查询相关性排序
4. **适合复杂查询**：如"张三和李四在咖啡店做了什么"

---

## 场景 2: 没有实体

### 查询示例

```
查询: "最近开心的事情"

提取实体: [] （未找到任何实体）
```

### 图谱召回处理

```python
# 步骤 1: 提取实体
entities = extract_entities("最近开心的事情")
# entities = []  # 未匹配到任何实体

# 步骤 2: 直接返回空结果
if not entities:
    logger.info("查询中未提取到实体")
    return {"relations": [], "memories": []}

# 结果
{
  "relations": [],
  "memories": []
}
```

**原因**：图谱召回依赖实体关系网络，没有实体就无法遍历关系。

### 混合召回的容错机制

```python
async def hybrid_recall(query, user_id):
    # 并发执行三路召回
    tasks = [
        vector_recall(query),   # ✅ 向量召回
        keyword_recall(query),  # ✅ 关键词召回
        graph_recall(query),    # ❌ 图谱召回返回空
    ]
    
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # 处理结果
    vector_results = results[0] if not isinstance(results[0], Exception) else []
    keyword_results = results[1] if not isinstance(results[1], Exception) else []
    graph_results = results[2] if not isinstance(results[2], Exception) else []
    # graph_results = []  # 图谱召回为空
    
    # 合并结果（图谱为空不影响）
    merged = merge_and_rank(
        vector_results,   # 有结果
        keyword_results,  # 有结果
        []                # 图谱结果为空
    )
    
    return merged
```

### 向量召回处理无实体查询

```python
# 查询: "最近开心的事情"

# 1. 生成查询向量
query_vec = embed("最近开心的事情")

# 2. 向量相似度搜索
SELECT content, 1 - (embedding <=> query_vec) as similarity
FROM memories
ORDER BY similarity DESC

结果:
- "今天和朋友聚会很开心" (相似度: 0.92)
- "完成了一个重要的项目" (相似度: 0.87)
- "收到了惊喜礼物" (相似度: 0.85)

# ✅ 可以召回语义相似的记忆
```

### 关键词召回处理无实体查询

```python
# 查询: "最近开心的事情"

# 1. 提取关键词
keywords = ["最近", "开心", "事情"]

# 2. LIKE 搜索
SELECT content FROM memories
WHERE content LIKE '%开心%'
   OR content LIKE '%最近%'
   OR content LIKE '%事情%'

结果:
- "最近很开心"
- "开心的事情"
- "最近发生了一件开心的事"

# ✅ 可以召回关键词匹配的记忆
```

### 混合召回结果

```json
[
  {
    "content": "今天和朋友聚会很开心",
    "similarity": 0.92,
    "recall_type": "vector"
  },
  {
    "content": "最近完成了一个重要的项目",
    "similarity": 0.87,
    "recall_type": "vector"
  },
  {
    "content": "收到了惊喜礼物，很开心",
    "similarity": 0.85,
    "recall_type": "keyword"
  }
]
```

**特点**：
- 图谱召回失败（无实体）
- 向量召回成功（语义匹配）
- 关键词召回成功（关键词匹配）
- 混合召回保证了召回率

---

## 对比总结

| 维度 | 单个实体 | 多个实体 | 无实体 |
|------|---------|---------|--------|
| 查询示例 | "张三的朋友" | "张三和李四在咖啡店" | "开心的事情" |
| 实体提取 | ["张三"] | ["张三", "李四", "咖啡店"] | [] |
| 关系查询 | 张三的关系 | 所有实体的关系（OR） | 无 |
| 记忆召回 | 张三相关记忆 | 所有实体相关记忆 | 向量/关键词召回 |
| 召回方式 | 图谱召回 | 图谱召回 | 向量 + 关键词召回 |
| 召回效果 | 精确 | 广泛 | 语义相关 |
| 适用场景 | 实体关系查询 | 复杂查询 | 语义查询 |

---

## 代码关键位置

### 多实体查询

**位置**: `graph_recall_service.py:543-576`

```python
async def _get_entity_relations(self, entity_ids: List[str], user_id: str):
    """获取实体的所有关系（OR 条件）"""
    relations = await db.fetch(
        """
        SELECT e1.name, r.relation_type, e2.name
        FROM relations r
        JOIN entities e1 ON r.from_entity_id = e1.id
        JOIN entities e2 ON r.to_entity_id = e2.id
        WHERE (r.from_entity_id = ANY($1) OR r.to_entity_id = ANY($1))
        --    ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
        --    关键：OR 条件，查询所有实体的关系
        """,
        entity_ids
    )
    return relations
```

### 无实体处理

**位置**: `graph_recall_service.py:277-279`

```python
# 未找到实体时直接返回
if not entities:
    logger.info(f"查询中未提取到实体: {query}")
    return {"relations": [], "memories": []}
```

### 混合召回容错

**位置**: `graph_recall_service.py:354-368`

```python
# 并发执行三路召回
results = await asyncio.gather(
    self._vector_recall(query, user_id, limit * 2, time_range),
    self._keyword_recall(query, user_id, limit * 2, time_range),
    self._graph_recall(query, user_id, limit * 2, time_range),
    return_exceptions=True  # ⭐ 异常不中断
)

# 处理结果（图谱为空不影响）
vector_results = results[0] if not isinstance(results[0], Exception) else []
keyword_results = results[1] if not isinstance(results[1], Exception) else []
graph_results = results[2] if not isinstance(results[2], Exception) else []
```

---

## 最佳实践

### 1. 推荐使用混合召回

```python
# 混合召回自动处理各种情况
result = await recall_service.search(
    query="最近开心的事情",  # 无实体
    user_id="test_user",
    enable_graph=True  # 启用图谱召回
)

# 自动降级：
# - 图谱召回失败 → 使用向量 + 关键词召回
# - 保证召回率
```

### 2. 多实体查询的优势

```
查询: "张三和李四在咖啡店做了什么"

优势:
1. 关系网络扩展（发现间接关系）
2. 召回范围更广（所有相关记忆）
3. 适合复杂查询
```

### 3. 智能路由建议

```python
# 智能召回路由（推荐）
result = await smart_recall_service.smart_recall(
    query="张三和李四在咖啡店做了什么",
    user_id="test_user"
)

# 自动决策:
# - 有实体 → 图谱召回
# - 无实体 → 向量/关键词召回
# - 复杂查询 → 混合召回
```

### 4. 监控指标

```python
# 记录实体数量分布
entity_count_stats = {
    "0_entities": 20,   # 无实体查询数量
    "1_entity": 100,    # 单个实体查询数量
    "2+_entities": 50   # 多个实体查询数量
}

# 监控召回效果
recall_success_rate = {
    "graph_recall": 0.85,   # 图谱召回成功率
    "vector_recall": 0.95,  # 向量召回成功率
    "hybrid_recall": 0.98   # 混合召回成功率
}
```

---

## 总结

### 核心机制

1. **多个实体**：
   - OR 条件查询所有关系
   - 合并所有实体的记忆
   - BM25 重排序

2. **无实体**：
   - 图谱召回返回空
   - 但混合召回仍可工作（向量 + 关键词）
   - 自动降级，用户无感

3. **混合召回**：
   - 三路并发
   - 互不影响
   - 保证召回率

### 一句话总结

**多实体用 OR 扩展召回，无实体自动降级，混合召回保证成功率**
