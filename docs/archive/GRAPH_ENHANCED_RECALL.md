# 记忆网络如何服务召回

## 问题：当前图谱未被充分利用

### 当前实现

**存储阶段**：
- ✅ 实体提取和存储（entities 表）
- ✅ 关系推理和存储（relations 表）
- ✅ 记忆-实体关联（memory_entities 表）

**召回阶段**：
- ❌ 只使用向量搜索 + 关键词搜索
- ❌ **图谱数据未被利用**

---

## 图谱增强召回的价值

### 1. 实体扩展召回

**场景**：搜索"张三"

**当前方案**：
```sql
-- 只返回包含"张三"文本的记忆
SELECT * FROM memories 
WHERE content LIKE '%张三%'
ORDER BY embedding <-> query_vector
```

**图谱增强方案**：
```sql
-- 1. 查找实体
SELECT id FROM entities WHERE name = '张三';

-- 2. 通过 memory_entities 找到所有相关记忆
SELECT m.* 
FROM memories m
JOIN memory_entities me ON m.id = me.memory_id
WHERE me.entity_id = '张三的entity_id';

-- 3. 返回结果 + 向量相似度排序
```

**优势**：
- 更精准（实体匹配 > 文本匹配）
- 更全面（包含别名、昵称等）

---

### 2. 关系扩展召回

**场景**：搜索"朋友"

**当前方案**：
```sql
-- 只返回包含"朋友"文本的记忆
SELECT * FROM memories WHERE content LIKE '%朋友%'
```

**图谱增强方案**：
```sql
-- 1. 查找所有"朋友"关系的实体
SELECT from_entity_id, to_entity_id
FROM relations
WHERE relation_type = 'friend';

-- 2. 查找这些实体的记忆
SELECT m.* FROM memories m
JOIN memory_entities me ON m.id = me.memory_id
WHERE me.entity_id IN (朋友实体列表);

-- 3. 合并向量搜索结果
```

**优势**：
- 语义扩展（"朋友" → 具体的朋友姓名）
- 关系推理（"张三的朋友" → 自动扩展）

---

### 3. 多跳推理召回

**场景**：搜索"张三的老婆"

**当前方案**：
```
❌ 无法处理，只能搜索包含"张三的老婆"文本的记忆
```

**图谱增强方案**：
```sql
-- 1. 查找张三实体
SELECT id FROM entities WHERE name = '张三';

-- 2. 查找张三的家庭关系
SELECT to_entity_id FROM relations
WHERE from_entity_id = '张三的ID'
AND relation_type = 'family';

-- 3. 查找老婆相关的记忆
SELECT m.* FROM memories m
JOIN memory_entities me ON m.id = me.memory_id
WHERE me.entity_id IN (张三的家人实体列表);
```

**优势**：
- 支持复杂查询
- 关系推理

---

### 4. 子图召回

**场景**：查询"上个月在咖啡店的社交活动"

**当前方案**：
```
❌ 需要多次查询，无法关联
```

**图谱增强方案**：
```sql
-- 1. 查找咖啡店实体
SELECT id FROM entities WHERE name LIKE '%咖啡店%';

-- 2. 查找咖啡店相关的人物关系
SELECT from_entity_id, to_entity_id
FROM relations
WHERE (from_entity_id = '咖啡店ID' OR to_entity_id = '咖啡店ID')
AND relation_type IN ('at', 'met_at');

-- 3. 返回这些人物的记忆子图
```

**优势**：
- 多维度关联
- 子图可视化

---

## 缺失的功能

### 1. 图谱增强召回接口

**需要新增**：

```python
class GraphEnhancedRecallService:
    """图谱增强召回服务"""
    
    async def search_by_entity(
        self,
        entity_name: str,
        user_id: str,
        limit: int = 10
    ) -> List[Dict]:
        """通过实体搜索记忆"""
        # 1. 查找实体
        # 2. 通过 memory_entities 找记忆
        # 3. 向量相似度排序
        pass
    
    async def search_by_relation(
        self,
        relation_type: str,
        user_id: str,
        limit: int = 10
    ) -> List[Dict]:
        """通过关系类型搜索记忆"""
        # 1. 查找所有该类型的关系
        # 2. 找相关实体
        # 3. 找相关记忆
        pass
    
    async def search_by_multi_hop(
        self,
        query: str,
        user_id: str,
        max_hops: int = 2
    ) -> List[Dict]:
        """多跳推理搜索"""
        # 1. 解析查询（LLM）
        # 2. 提取实体和关系
        # 3. 多跳推理
        # 4. 返回相关记忆
        pass
    
    async def get_memory_subgraph(
        self,
        memory_ids: List[str],
        user_id: str
    ) -> Dict:
        """获取记忆的子图"""
        # 1. 查找记忆的所有实体
        # 2. 查找实体之间的关系
        # 3. 返回子图数据（可视化）
        pass
```

---

### 2. 混合召回策略

**当前方案**：
```
向量搜索 + 关键词搜索
```

**增强方案**：
```
向量搜索 + 关键词搜索 + 图谱增强
```

**权重分配**：
```python
final_score = (
    vector_score * 0.5 +      # 向量相似度
    keyword_score * 0.3 +     # 关键词匹配
    graph_score * 0.2         # 图谱关联度
)
```

---

## 下一步计划

### 短期（v1.1）

1. **实现实体扩展召回**
   - `search_by_entity` 接口
   - 在 `search` 方法中集成实体匹配

2. **实现关系扩展召回**
   - `search_by_relation` 接口
   - 软过滤服务集成

### 中期（v1.2）

3. **实现多跳推理召回**
   - LLM 解析查询
   - 图谱推理引擎

4. **实现子图召回**
   - 记忆网络可视化
   - 子图查询接口

### 长期（v2.0）

5. **图谱推理优化**
   - 图神经网络（GNN）
   - 知识图谱推理

6. **个性化召回**
   - 用户偏好学习
   - 召回策略优化

---

## 总结

**当前状态**：
- ✅ 图谱构建完成
- ❌ 图谱召回未实现

**核心价值**：
- 实体扩展召回（精准匹配）
- 关系扩展召回（语义扩展）
- 多跳推理召回（复杂查询）
- 子图召回（多维度关联）

**优先级**：
- P0：实体扩展召回（快速实现，价值大）
- P1：关系扩展召回（已有软过滤基础）
- P2：多跳推理召回（需要更多开发）
