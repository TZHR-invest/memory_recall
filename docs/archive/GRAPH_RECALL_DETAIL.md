# 图谱召回详细实现解析

## 一、核心架构

### 1.1 数据模型

图谱召回依赖三个核心表：

```
entities (实体表)
├── id: UUID
├── name: 实体名称 (如 "张三")
├── type: 实体类型 (person/location/event/topic)
├── confidence: 置信度 (0-1)
├── mention_count: 提及次数
└── user_id: 用户ID

relations (关系表)
├── id: UUID
├── from_entity_id: 源实体ID
├── to_entity_id: 目标实体ID
├── relation_type: 关系类型 (friend/met_at/at)
├── weight: 关系权重 (0-1)
└── user_id: 用户ID

memory_entities (记忆-实体关联表)
├── id: UUID
├── memory_id: 记忆ID
├── entity_id: 实体ID
├── mention_context: 提及上下文
└── mention_position: 提及位置
```

**关系示例**：
```
张三 --[friend]--> 李四
张三 --[met_at]--> 咖啡店
我 --[at]--> 咖啡店
```

### 1.2 召回流程概览

```
查询: "张三的朋友"
    ↓
① 实体提取 (词典匹配)
    ↓
② 实体查询 (数据库查找)
    ↓
③ 关系扩展 (归一化关系)
    ↓
④ 关系遍历 (查询关系网络)
    ↓
⑤ BM25重排序 (相关性排序)
    ↓
⑥ 记忆召回 (获取相关记忆)
    ↓
返回结果
```

## 二、详细实现步骤

### 步骤 1: 实体提取

**位置**: `graph_recall_service.py:383-424`

#### 方式一：词典匹配（推荐，毫秒级）

```python
async def _extract_entities_from_query(
    self,
    query: str,
    user_id: str,
    use_dict: bool = True
) -> List[str]:
    """
    从查询中提取实体
    
    使用预先构建的实体词典，通过字符串匹配提取实体
    """
    # 1. 初始化词典（首次调用时）
    if not self.entity_dict._initialized:
        await self.entity_dict.initialize()
    
    # 2. 快速匹配
    entities = self.entity_dict.extract_entities_fast(query, user_id)
    
    return entities
```

**词典服务实现** (`entity_dictionary_service.py:22-93`):

```python
async def initialize(self):
    """
    从数据库加载所有实体到内存词典
    """
    # 获取所有用户
    users = await db.fetch("SELECT id FROM public.users")
    
    # 遍历每个用户的 schema，加载实体
    for user in users:
        async with db.user_context(user_id):
            entities = await db.fetch(
                """
                SELECT id, name, type, confidence, user_id
                FROM entities
                WHERE confidence >= 0.5
                ORDER BY mention_count DESC
                """
            )
            
            # 添加到词典
            for entity in entities:
                self.entity_dict[entity["name"]] = {
                    "id": str(entity["id"]),
                    "type": entity["type"],
                    "confidence": entity["confidence"],
                    "user_id": entity["user_id"]
                }
```

**快速匹配** (`entity_dictionary_service.py:94-142`):

```python
def extract_entities_fast(self, query: str, user_id: str) -> List[str]:
    """
    快速提取查询中的实体（字符串匹配）
    """
    entities = []
    
    # 按实体名称长度降序排序（优先匹配长实体名）
    sorted_names = sorted(
        self.entity_dict.keys(),
        key=lambda x: len(x),
        reverse=True
    )
    
    # 字符串匹配
    for name in sorted_names:
        if name in query:
            entity_info = self.entity_dict[name]
            
            # 过滤只属于该用户的实体
            if entity_info.get("user_id") == user_id:
                entities.append(name)
    
    return entities
```

**优点**：
- ⚡ 速度极快（毫秒级）
- 💾 内存占用低（只存储实体名称和元数据）
- 🎯 精确匹配，无歧义

#### 方式二：LLM 提取（降级方案，1-3秒）

```python
async def _extract_entities_with_llm(self, query: str) -> List[str]:
    """
    使用 LLM 提取实体（降级方案）
    """
    response = await self.llm_service.call_with_tools(
        system_prompt="从查询中提取实体名称。",
        user_prompt=query,
        tools=[EXTRACT_ENTITIES_TOOL]
    )
    
    if response.get("tool_calls"):
        entities = response["tool_calls"][0]["function"]["arguments"]["entities"]
        return [e["entity"] for e in entities]
    
    return []
```

### 步骤 2: 实体查询

**位置**: `graph_recall_service.py:446-476`

```python
async def _search_entities_by_name(
    self,
    entity_names: List[str],
    user_id: str
) -> List[Dict]:
    """
    通过名称搜索实体
    
    直接使用名称匹配，避免向量搜索的复杂性
    """
    entities = await db.fetch(
        """
        SELECT id, name, type, confidence
        FROM entities
        WHERE name = ANY($1)
        AND user_id = $2
        """,
        entity_names, user_id
    )
    
    return [
        {
            "id": str(e["id"]),
            "name": e["name"],
            "type": e["type"],
            "confidence": e["confidence"]
        }
        for e in entities
    ]
```

**SQL 查询示例**：

```sql
-- 查询: "张三"
SELECT id, name, type, confidence
FROM entities
WHERE name = ANY(['张三'])
AND user_id = 'test_user'

-- 结果:
-- id: "uuid-123"
-- name: "张三"
-- type: "person"
-- confidence: 0.95
```

### 步骤 3: 归一化关系扩展

**位置**: `graph_recall_service.py:520-570`

**问题**：用户可能使用不同的名称指代同一实体
- "星巴克" vs "咖啡店"
- "阿里巴巴" vs "阿里"

**解决方案**：通过归一化关系扩展实体

```python
async def _expand_entities_by_normalization(
    self,
    entity_names: List[str],
    user_id: str
) -> List[str]:
    """
    通过归一化关系扩展实体
    
    支持 same_as 和 is_a 关系
    """
    expanded = list(entity_names)
    
    # 查询归一化关系（same_as, is_a）
    for entity_name in entity_names:
        # 查询实体 ID
        entity_id = await db.fetchval(
            """
            SELECT id FROM entities 
            WHERE name = $1 AND (user_id = $2 OR user_id = 'system')
            """,
            entity_name, user_id
        )
        
        if entity_id:
            # 查询归一化关系
            related = await db.fetch(
                """
                SELECT e.name
                FROM relations r
                JOIN entities e ON e.id = r.to_entity_id OR e.id = r.from_entity_id
                WHERE (r.from_entity_id = $1 OR r.to_entity_id = $1)
                AND r.relation_type IN ('same_as', 'is_a')
                AND (r.user_id = $2 OR r.user_id = 'system')
                """,
                str(entity_id), user_id
            )
            
            expanded.extend([r["name"] for r in related])
    
    # 去重
    return list(set(expanded))
```

**示例**：

```
输入: ["星巴克"]
归一化关系: 星巴克 --[is_a]--> 咖啡店
输出: ["星巴克", "咖啡店"]
```

### 步骤 4: 关系遍历

**位置**: `graph_recall_service.py:478-518`

```python
async def _get_entity_relations(
    self,
    entity_ids: List[str],
    user_id: str
) -> List[Dict]:
    """
    获取实体的所有关系
    
    包括用户关系 + 系统归一化关系
    """
    relations = await db.fetch(
        """
        SELECT 
            e1.name AS source,
            r.relation_type AS relationship,
            e2.name AS destination,
            r.weight,
            r.confidence
        FROM relations r
        JOIN entities e1 ON r.from_entity_id = e1.id
        JOIN entities e2 ON r.to_entity_id = e2.id
        WHERE (r.user_id = $1 OR r.user_id = 'system')
        AND (r.from_entity_id = ANY($2) OR r.to_entity_id = ANY($2))
        ORDER BY r.weight DESC
        """,
        user_id, entity_ids
    )
    
    return [
        {
            "source": r["source"],
            "relationship": r["relationship"],
            "destination": r["destination"],
            "weight": r["weight"],
            "confidence": r["confidence"]
        }
        for r in relations
    ]
```

**SQL 查询示例**：

```sql
-- 查询实体 "张三" 的所有关系
SELECT 
    e1.name AS source,      -- "张三"
    r.relation_type,        -- "friend"
    e2.name AS destination, -- "李四"
    r.weight,
    r.confidence
FROM relations r
JOIN entities e1 ON r.from_entity_id = e1.id
JOIN entities e2 ON r.to_entity_id = e2.id
WHERE (r.user_id = 'test_user' OR r.user_id = 'system')
AND (r.from_entity_id = 'uuid-张三' OR r.to_entity_id = 'uuid-张三')

-- 结果:
-- source="张三", relationship="friend", destination="李四", weight=0.9
-- source="张三", relationship="colleague", destination="王五", weight=0.8
-- source="张三", relationship="met_at", destination="咖啡店", weight=0.95
```

### 步骤 5: BM25 重排序

**位置**: `graph_recall_service.py:572-618`

**问题**：一个实体可能有很多关系，需要根据查询相关性排序

**解决方案**：使用 BM25 算法对关系进行重排序

```python
def _bm25_rerank(
    self,
    query: str,
    relations: List[Dict]
) -> List[Dict]:
    """
    BM25 重排序
    
    改进点：
    1. 使用 jieba 分词提取查询关键词
    2. 将英文关系类型转换成中文
    """
    # 构建文档列表（将英文关系类型转换成中文）
    documents = []
    for r in relations:
        # 将英文关系类型转换成中文
        relationship_cn = RELATION_TYPES.get(r["relationship"], r["relationship"])
        documents.append([r["source"], relationship_cn, r["destination"]])
    
    # 示例: [["张三", "朋友", "李四"], ["张三", "同事", "王五"]]
    
    # 使用 Jieba 分词提取关键词
    tokenized_query = extract_keywords(query, min_length=1)
    # 示例: ["张三", "朋友"]
    
    # BM25 排序
    bm25 = BM25Okapi(documents)
    top_indices = bm25.get_top_n(tokenized_query, list(range(len(documents))), n=len(documents))
    
    # 返回重排序后的关系
    reranked = [relations[i] for i in top_indices]
    
    return reranked
```

**关系类型映射** (`graph_tools.py:152-179`):

```python
RELATION_TYPES = {
    # 人物关系
    "friend": "朋友",
    "colleague": "同事",
    "family": "家人",
    "met_at": "在...遇到",
    
    # 地点关系
    "at": "在...",
    "visited": "访问过",
    "lives_at": "居住在",
    "works_at": "工作在",
    
    # 事件关系
    "participated": "参与",
    "discussed": "讨论",
    "mentioned": "提及",
}
```

**示例**：

```
查询: "张三的朋友"
分词: ["张三", "朋友"]

关系列表:
1. 张三 --[friend]--> 李四  (文档: ["张三", "朋友", "李四"])
2. 张三 --[colleague]--> 王五 (文档: ["张三", "同事", "王五"])
3. 张三 --[met_at]--> 咖啡店 (文档: ["张三", "在...遇到", "咖啡店"])

BM25 评分:
- 文档1 包含 "张三" 和 "朋友"，得分最高
- 文档2 包含 "张三"，但不包含 "朋友"
- 文档3 包含 "张三"，但不包含 "朋友"

排序结果: [关系1, 关系2, 关系3]
```

### 步骤 6: 记忆召回

**位置**: `graph_recall_service.py:624-707`

```python
async def _get_memories_by_entities(
    self,
    entity_names: List[str],
    user_id: str,
    limit: int,
    time_range: Optional[Dict[str, Any]] = None
) -> List[Dict]:
    """
    通过实体获取记忆（按关系权重排序）
    
    排序逻辑：
    1. 关系权重（降序）- 包含高权重关系的记忆排前面
    2. 创建时间（降序）- 权重相同时，最新记忆排前面
    """
    sql = """
        SELECT DISTINCT
            m.id,
            m.content,
            m.created_at,
            m.time_value,
            m.location_name,
            m.people,
            MAX(r.weight) as max_relation_weight
        FROM memories m
        JOIN memory_entities me ON m.id = me.memory_id
        JOIN entities e ON me.entity_id = e.id
        LEFT JOIN relations r ON (
            (r.from_entity_id = e.id OR r.to_entity_id = e.id)
            AND (r.user_id = $2 OR r.user_id = 'system')
        )
        WHERE e.name = ANY($1)
        AND e.user_id = $2
        AND m.status = 'active'
        GROUP BY m.id
        ORDER BY 
            max_relation_weight DESC NULLS LAST,
            m.created_at DESC
        LIMIT $3
    """
    
    memories = await db.fetch(sql, entity_names, user_id, limit)
    
    return [
        {
            "memory_id": str(m["id"]),
            "content": m["content"],
            "created_at": m["created_at"].isoformat(),
            "location": m["location_name"],
            "people": m["people"],
            "max_relation_weight": m["max_relation_weight"]
        }
        for m in memories
    ]
```

**SQL 查询示例**：

```sql
-- 查询与实体 ["张三", "李四"] 相关的记忆
SELECT DISTINCT
    m.id,
    m.content,
    m.created_at,
    MAX(r.weight) as max_relation_weight
FROM memories m
JOIN memory_entities me ON m.id = me.memory_id
JOIN entities e ON me.entity_id = e.id
LEFT JOIN relations r ON (
    (r.from_entity_id = e.id OR r.to_entity_id = e.id)
    AND (r.user_id = 'test_user' OR r.user_id = 'system')
)
WHERE e.name = ANY(['张三', '李四'])
AND e.user_id = 'test_user'
AND m.status = 'active'
GROUP BY m.id
ORDER BY 
    max_relation_weight DESC NULLS LAST,
    m.created_at DESC
LIMIT 10

-- 结果:
-- content="张三和李四在咖啡店见面", max_relation_weight=0.95
-- content="张三提到李四是他的好朋友", max_relation_weight=0.9
```

## 三、完整示例

### 示例查询："张三的朋友"

```
步骤 1: 实体提取
输入: "张三的朋友"
词典匹配: ["张三"]

步骤 2: 实体查询
SQL: SELECT * FROM entities WHERE name = '张三' AND user_id = 'test'
结果: entity_id = "uuid-张三"

步骤 3: 归一化扩展
查询: 张三 --[same_as]--> 张三(别名)
结果: ["张三"] (无扩展)

步骤 4: 关系遍历
SQL: SELECT * FROM relations WHERE from_entity_id = 'uuid-张三' OR to_entity_id = 'uuid-张三'
结果:
- 张三 --[friend]--> 李四 (weight=0.9)
- 张三 --[colleague]--> 王五 (weight=0.8)
- 张三 --[met_at]--> 咖啡店 (weight=0.95)

步骤 5: BM25 重排序
查询分词: ["张三", "朋友"]
关系类型映射: friend → 朋友
文档列表:
- ["张三", "朋友", "李四"]
- ["张三", "同事", "王五"]
- ["张三", "在...遇到", "咖啡店"]

BM25 评分:
- 文档1 得分最高（包含"张三"和"朋友"）
- 文档2 得分中等（包含"张三"，不包含"朋友"）
- 文档3 得分中等（包含"张三"，不包含"朋友"）

排序结果: [张三-朋友-李四, 张三-同事-王五, 张三-met_at-咖啡店]

步骤 6: 记忆召回
SQL: 查询包含实体 ["张三", "李四", "王五", "咖啡店"] 的记忆
结果:
- memory_id="m1", content="张三和李四是大学同学", max_relation_weight=0.9
- memory_id="m2", content="张三在咖啡店见了李四", max_relation_weight=0.95

最终返回:
{
  "relations": [
    {"source": "张三", "relationship": "friend", "destination": "李四", "weight": 0.9},
    {"source": "张三", "relationship": "colleague", "destination": "王五", "weight": 0.8}
  ],
  "memories": [
    {"memory_id": "m1", "content": "张三和李四是大学同学", ...},
    {"memory_id": "m2", "content": "张三在咖啡店见了李四", ...}
  ]
}
```

## 四、性能优化

### 4.1 词典缓存

**问题**：每次查询都从数据库加载实体，速度慢

**解决方案**：预先加载所有实体到内存词典

```python
# 初始化时加载所有实体
await entity_dict.initialize()

# 后续查询直接从内存匹配
entities = entity_dict.extract_entities_fast(query, user_id)
```

**效果**：
- 从 1-3 秒（LLM 提取）→ 1-5 毫秒（词典匹配）
- 性能提升 100-1000 倍

### 4.2 关系权重排序

**问题**：一个实体可能有上百个关系，需要优先返回重要的

**解决方案**：
1. 关系表存储 `weight` 字段
2. 按权重降序排序
3. 记忆召回时优先返回高权重关系的记忆

```sql
ORDER BY 
    max_relation_weight DESC NULLS LAST,
    m.created_at DESC
```

### 4.3 时间范围过滤

**支持时间过滤**：

```python
# 添加时间过滤
if time_range:
    if time_range.get("start_time"):
        sql += " AND m.time_value >= $start_time"
    if time_range.get("end_time"):
        sql += " AND m.time_value <= $end_time"
```

**示例**：

```
查询: "上周张三的朋友"
时间过滤: 2026-03-18 ~ 2026-03-25
结果: 只返回上周的关系和记忆
```

## 五、关键设计亮点

### 5.1 三层召回策略

```
图谱召回 = 实体召回 + 关系召回 + 记忆召回

实体召回: 通过词典快速匹配查询中的实体
关系召回: 通过关系表遍历实体关系网络
记忆召回: 通过 memory_entities 表获取相关记忆
```

### 5.2 归一化关系

**支持实体别名**：

```
星巴克 --[is_a]--> 咖啡店
阿里巴巴 --[same_as]--> 阿里
腾讯 --[same_as]--> 鹅厂
```

**查询扩展**：

```
输入: "星巴克"
扩展: ["星巴克", "咖啡店"]
效果: 能召回所有提到"咖啡店"的记忆，而不仅仅是"星巴克"
```

### 5.3 BM25 重排序

**支持中文查询**：

```
查询: "张三的朋友"
关系: 张三 --[friend]--> 李四
映射: friend → 朋友
文档: ["张三", "朋友", "李四"]
评分: 文档包含"张三"和"朋友"，得分最高
```

### 5.4 多用户隔离

**Schema 隔离**：

```python
# 设置当前用户 schema
db.set_current_user(user_id)

# 后续查询自动使用该用户的 schema
SELECT * FROM entities WHERE user_id = $user_id
```

**优点**：
- 数据完全隔离
- 查询性能高（单用户数据量小）
- 支持多租户

## 六、总结

图谱召回的核心优势：

1. **关系网络**: 利用实体关系网络，召回关联性强的记忆
2. **快速匹配**: 词典缓存实现毫秒级实体提取
3. **智能排序**: BM25 根据查询相关性重排序关系
4. **归一化扩展**: 支持实体别名，提高召回率
5. **时间过滤**: 支持时间范围精确过滤

**适用场景**：
- ✅ 实体关系查询："张三的朋友"
- ✅ 地点关联查询："在咖啡店见的人"
- ✅ 事件参与者查询："参与项目的同事"
- ✅ 复杂关系查询："张三在咖啡店见的朋友"
