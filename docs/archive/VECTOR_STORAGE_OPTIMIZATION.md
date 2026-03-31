# 向量存储优化方案

## 用户需求

**向量存储改为提取的记忆内容的向量，而不是原文向量。**

---

## 当前问题

```python
# ❌ 当前逻辑
content = "昨天下午在星巴克和老朋友张三喝了咖啡..."  # 原文
embedding = generate_embedding(content)  # 原文向量
store(content, embedding)

# 问题：向量代表的是原文的语义，而不是提取的记忆点
```

---

## 改进方案

```python
# ✅ 新逻辑
result = processor.process_long_text(content)
segments = result.get("segments", [])

for segment in segments:
    memory_content = segment.get("content")  # 提取的记忆内容
    embedding = generate_embedding(memory_content)  # ✅ 记忆内容向量
    store(memory_content, embedding)
```

---

## 对比示例

| 项目 | 原文 | 提取的记忆 | 向量效果 |
|------|------|-----------|---------|
| **文本** | "昨天下午在星巴克和老朋友张三喝了咖啡，讨论了他的AI创业项目。张三是我的大学同学..." | "在星巴克和张三讨论AI创业项目" | 更聚焦、更精准 |
| **长度** | 60+ 字符 | 15 字符 | Token 更少 |
| **语义** | 包含多个事件 | 单一事件 | 向量更纯粹 |
| **召回** | 可能召回不相关内容 | 精准召回 | ✅ 效果更好 |

---

## 实施步骤

### 1. 修改 `create_memory_with_graph()`

**文件**：`apps/api/src/services/memory_service.py`

```python
async def create_memory_with_graph(self, content, user_id, enable_graph=True):
    from ..processors.unified_processor import get_unified_processor
    processor = get_unified_processor()
    
    # 1. 提取记忆点
    result = processor.process_long_text(content)
    
    if not result.get("success"):
        # 降级：对原文生成向量
        embedding = await self._generate_embedding(content)
        memory_id = await self._store_memory(content, embedding, user_id)
        return {"memory_id": memory_id, "graph": None}
    
    segments = result.get("segments", [])
    
    if len(segments) == 0:
        # 降级
        embedding = await self._generate_embedding(content)
        memory_id = await self._store_memory(content, embedding, user_id)
        return {"memory_id": memory_id, "graph": None}
    
    # 2. 存储每个记忆点
    memory_ids = []
    all_entities = []
    all_relations = []
    
    for segment in segments:
        # ✅ 对提取的记忆内容生成向量
        memory_content = segment.get("content", "")
        embedding = await self._generate_embedding(memory_content)
        
        # 提取结构化信息
        time_info = segment.get("time", {})
        location_info = segment.get("location", {})
        people = segment.get("people", [])
        point_type = segment.get("type", "event")
        importance = segment.get("importance", 0.5)
        summary = segment.get("summary", "")
        
        # 存储记忆点
        memory_id = await self._store_memory_point(
            content=memory_content,  # ✅ 提取的内容
            embedding=embedding,      # ✅ 提取内容的向量
            user_id=user_id,
            time_info=time_info,
            location_info=location_info,
            people=people,
            point_type=point_type,
            importance=importance,
            summary=summary
        )
        
        memory_ids.append(memory_id)
        
        # 收集图谱信息
        all_entities.extend(segment.get("entities", []))
        all_relations.extend(segment.get("relations", []))
    
    # 3. 存储图谱
    if enable_graph and (all_entities or all_relations):
        await self._store_graph_unified(
            {"entities": all_entities, "relations": all_relations},
            user_id,
            memory_ids[0]  # 主记忆 ID
        )
    
    return {
        "memory_id": memory_ids[0],
        "graph": {
            "entities": all_entities,
            "relations": all_relations,
            "entity_count": len(all_entities),
            "relation_count": len(all_relations)
        },
        "extracted": {
            "segments": len(segments),
            "memory_ids": memory_ids
        }
    }
```

### 2. 添加 `_store_memory_point()` 方法

```python
async def _store_memory_point(
    self,
    content: str,
    embedding: List[float],
    user_id: str,
    time_info: Dict,
    location_info: Dict,
    people: List,
    point_type: str,
    importance: float,
    summary: str
) -> str:
    """存储单个记忆点"""
    db.set_current_user(user_id)
    
    memory_id = str(uuid.uuid4())
    now = datetime.utcnow()
    
    # 提取时间
    time_value = time_info.get("value") if isinstance(time_info, dict) else None
    time_original = time_info.get("original_text") if isinstance(time_info, dict) else None
    
    if time_value and isinstance(time_value, str):
        try:
            time_value = datetime.fromisoformat(time_value.replace('Z', '+00:00'))
        except:
            time_value = None
    
    # 提取地点
    location_name = location_info.get("name") if isinstance(location_info, dict) else None
    
    # 存储到数据库
    await db.execute("""
        INSERT INTO memories (
            id, content, input_type, created_at,
            time_value, time_original_text, location_name, people,
            memory_point_type, importance_score, summary,
            embedding, status
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
    """,
        memory_id,
        content,  # ✅ 提取的记忆内容
        "memory_point",
        now,
        time_value,
        time_original,
        location_name,
        json.dumps(people) if people else None,
        point_type,
        importance,
        summary if summary else None,
        "[" + ",".join(map(str, embedding)) + "]" if embedding else None,
        "active"
    )
    
    return memory_id
```

---

## 召回优化

### 原文向量 vs 记忆向量

**查询**："张三在做什么"

| 向量类型 | 召回结果 | 说明 |
|---------|---------|------|
| **原文向量** | "昨天下午在星巴克和老朋友张三喝了咖啡，讨论了他的AI创业项目。张三是我的大学同学..." | 包含很多无关信息 |
| **记忆向量** | "张三在做AI教育" | ✅ 精准匹配 |

---

## 核心原则

**记忆向量 > 原文向量**：
1. ✅ 更精准（向量代表记忆点语义）
2. ✅ 更高效（Token 更少）
3. ✅ 更独立（不依赖原文上下文）
4. ✅ 更易召回（向量聚焦单一事件）

---

## 示例对比

### 输入

```
"昨天下午在星巴克和老朋友张三喝了咖啡，讨论了他的AI创业项目。
张三是我的大学同学，现在在做AI教育。
路上听了人工智能播客，学到很多。
决定下周约张三详细介绍项目。"
```

### 提取的记忆点

| 记忆点 | 内容 | 向量语义 |
|--------|------|---------|
| 1 | "在星巴克和张三讨论AI创业项目" | 讨论 + 张三 + AI创业 |
| 2 | "张三是大学同学，做AI教育" | 张三 + 大学同学 + AI教育 |
| 3 | "听AI播客有启发" | 学习 + AI播客 |
| 4 | "决定下周约张三详细介绍项目" | 决策 + 张三 + 项目 |

### 召回效果

**查询**："张三的职业"

- **原文向量**：可能召回整篇文档（包含咖啡、播客等无关信息）
- **记忆向量**：精准召回"张三是大学同学，做AI教育" ✅

---

## 实施优先级

- **P0**：修改 `create_memory_with_graph()` 使用记忆向量
- **P1**：测试召回效果
- **P2**：优化 Prompt 提高记忆点质量
