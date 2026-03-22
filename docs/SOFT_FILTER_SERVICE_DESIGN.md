# Memory Recall Phase 5: 软过滤服务设计

**创建时间**：2026-03-22 14:21
**作者**：颓弟
**状态**：设计完成

---

## 1. 设计目标

**软过滤服务的作用**：
- 降低不相关记忆的召回优先级
- 提升召回精准度
- 减少无效记忆的干扰

**与硬过滤的区别**：

| 特性 | 硬过滤 | 软过滤 |
|------|--------|--------|
| 过滤方式 | 直接排除 | 降低权重 |
| 适用场景 | 明确过滤条件 | 模糊判断 |
| 召回结果 | 只保留符合条件的 | 所有记忆都保留，但权重不同 |
| 风险 | 可能排除相关记忆 | 不会丢失记忆，但可能召回不相关 |

---

## 2. 软过滤评分机制

### 2.1 评分维度

| 维度 | 权重 | 说明 | 评分规则 |
|------|------|------|----------|
| **重要性评分** | 0.4 | 记忆的重要程度 | 1-10 分（用户可手动设置，默认 5） |
| **置信度评分** | 0.3 | LLM 提取的置信度 | 0-1 分（LLM 返回的 confidence 字段） |
| **时间相关性** | 0.2 | 与查询时间的相关性 | 0-1 分（越近越高） |
| **标签匹配度** | 0.1 | 标签与查询的匹配程度 | 0-1 分 |

### 2.2 综合评分公式

```python
soft_filter_score = (
    importance_score * 0.4 +
    confidence_score * 0.3 +
    time_relevance_score * 0.2 +
    tag_match_score * 0.1
)
```

### 2.3 软过滤阈值

- **阈值**：0.7
- **高于阈值**：正常召回
- **低于阈值**：降低召回权重（乘以 0.5）

---

## 3. 实现方案

### 3.1 服务接口

```python
class SoftFilterService:
    """软过滤服务"""
    
    def __init__(self, db: Database):
        self.db = db
    
    async def calculate_soft_filter_score(
        self,
        memory_id: str,
        query: str,
        query_time: Optional[datetime] = None
    ) -> float:
        """计算软过滤评分
        
        Args:
            memory_id: 记忆 ID
            query: 查询文本
            query_time: 查询时间（用于计算时间相关性）
        
        Returns:
            软过滤评分（0-1）
        """
        # 1. 获取记忆数据
        memory = await self._get_memory(memory_id)
        
        # 2. 计算各维度评分
        importance_score = memory.get("importance_score", 5) / 10
        confidence_score = memory.get("confidence", 0.8)
        time_relevance = self._calculate_time_relevance(memory, query_time)
        tag_match_score = self._calculate_tag_match(memory, query)
        
        # 3. 计算综合评分
        soft_filter_score = (
            importance_score * 0.4 +
            confidence_score * 0.3 +
            time_relevance * 0.2 +
            tag_match_score * 0.1
        )
        
        return soft_filter_score
    
    def _calculate_time_relevance(
        self,
        memory: Dict,
        query_time: Optional[datetime] = None
    ) -> float:
        """计算时间相关性
        
        规则：
        - 今天：1.0
        - 昨天：0.9
        - 本周：0.8
        - 本月：0.7
        - 更早：0.5
        """
        if not query_time:
            query_time = datetime.now()
        
        memory_time = memory.get("time_value")
        if not memory_time:
            return 0.5
        
        # 计算时间差
        delta = query_time - memory_time
        
        if delta.days == 0:
            return 1.0
        elif delta.days == 1:
            return 0.9
        elif delta.days < 7:
            return 0.8
        elif delta.days < 30:
            return 0.7
        else:
            return 0.5
    
    def _calculate_tag_match(self, memory: Dict, query: str) -> float:
        """计算标签匹配度
        
        规则：
        - 查询包含记忆标签：1.0
        - 部分匹配：0.5-0.9
        - 不匹配：0.3
        """
        memory_tags = memory.get("tags", [])
        if not memory_tags:
            return 0.5
        
        query_lower = query.lower()
        match_count = 0
        
        for tag in memory_tags:
            if tag.lower() in query_lower:
                match_count += 1
        
        if match_count == 0:
            return 0.3
        elif match_count == len(memory_tags):
            return 1.0
        else:
            return 0.5 + (match_count / len(memory_tags)) * 0.4
    
    async def apply_soft_filter(
        self,
        memories: List[Dict],
        query: str,
        query_time: Optional[datetime] = None
    ) -> List[Dict]:
        """应用软过滤
        
        Args:
            memories: 待过滤的记忆列表
            query: 查询文本
            query_time: 查询时间
        
        Returns:
            过滤后的记忆列表（已按评分调整权重）
        """
        for memory in memories:
            # 计算软过滤评分
            score = await self.calculate_soft_filter_score(
                memory["id"],
                query,
                query_time
            )
            
            # 如果评分低于阈值，降低权重
            if score < 0.7:
                memory["weight"] *= 0.5
                memory["soft_filtered"] = True
            else:
                memory["soft_filtered"] = False
        
        return memories
```

### 3.2 集成到召回流程

```python
# hybrid_recall 方法中集成软过滤
async def hybrid_recall(
    self,
    query: str,
    limit: int = 10,
    time_range: Optional[Dict] = None,
    enable_soft_filter: bool = True
) -> List[Dict]:
    """混合召回（向量 + 关键词 + 图谱 + 软过滤）"""
    
    # 1. 三路召回
    vector_results = await self._vector_recall(query, limit * 2)
    keyword_results = await self._keyword_recall(query, limit * 2)
    graph_results = await self._graph_recall(query, limit)
    
    # 2. 合并去重
    merged = self._merge_results(
        vector_results,
        keyword_results,
        graph_results
    )
    
    # 3. 应用软过滤
    if enable_soft_filter:
        soft_filter_service = SoftFilterService(self.db)
        merged = await soft_filter_service.apply_soft_filter(
            merged,
            query
        )
    
    # 4. 排序并返回 top N
    merged.sort(key=lambda x: x["weight"], reverse=True)
    return merged[:limit]
```

---

## 4. 用户交互设计

### 4.1 重要性评分设置

**用户可手动设置记忆的重要性**：

```
POST /api/v1/memories/{memory_id}/importance
{
    "importance_score": 8
}
```

**规则**：
- 1-3：低重要性（如日常琐事）
- 4-6：中等重要性（默认值）
- 7-10：高重要性（如重要事件、决策）

### 4.2 软过滤反馈

**用户可对召回结果提供反馈**：

```
POST /api/v1/recall/feedback
{
    "memory_id": "xxx",
    "query": "今天的日记",
    "relevant": true,  // 或 false
    "feedback_type": "soft_filter"  // 软过滤反馈
}
```

**反馈用途**：
- 用于优化软过滤评分模型
- 提升召回精准度

---

## 5. 性能优化

### 5.1 缓存机制

**缓存软过滤评分**：
- 缓存 key：`memory_id:query_hash`
- 缓存时间：1 小时
- 更新时机：记忆更新时清除缓存

### 5.2 异步计算

**批量计算软过滤评分**：
```python
async def batch_calculate_scores(
    self,
    memory_ids: List[str],
    query: str
) -> Dict[str, float]:
    """批量计算软过滤评分"""
    tasks = [
        self.calculate_soft_filter_score(mid, query)
        for mid in memory_ids
    ]
    scores = await asyncio.gather(*tasks)
    return dict(zip(memory_ids, scores))
```

---

## 6. 测试方案

### 6.1 单元测试

```python
# tests/test_soft_filter_service.py

async def test_calculate_soft_filter_score():
    """测试软过滤评分计算"""
    service = SoftFilterService(db)
    
    # 创建测试记忆
    memory_id = await create_test_memory(
        importance_score=8,
        confidence=0.9,
        tags=["工作", "项目"],
        time_value=datetime.now() - timedelta(days=1)
    )
    
    # 计算评分
    score = await service.calculate_soft_filter_score(
        memory_id,
        query="项目进展",
        query_time=datetime.now()
    )
    
    # 验证评分
    assert score >= 0.7  # 高重要性 + 高置信度 + 时间近 + 标签匹配

async def test_apply_soft_filter():
    """测试软过滤应用"""
    service = SoftFilterService(db)
    
    # 创建测试记忆列表
    memories = [
        {"id": "mem1", "weight": 1.0, "importance_score": 8},
        {"id": "mem2", "weight": 1.0, "importance_score": 3}
    ]
    
    # 应用软过滤
    filtered = await service.apply_soft_filter(
        memories,
        query="测试查询"
    )
    
    # 验证结果
    assert filtered[0]["soft_filtered"] == False  # 高评分
    assert filtered[1]["soft_filtered"] == True   # 低评分
```

### 6.2 端到端测试

```python
async def test_hybrid_recall_with_soft_filter():
    """测试带软过滤的混合召回"""
    recall_service = RecallService(db)
    
    # 召回记忆
    results = await recall_service.hybrid_recall(
        query="今天的日记",
        limit=10,
        enable_soft_filter=True
    )
    
    # 验证结果
    assert len(results) <= 10
    assert all("soft_filtered" in r for r in results)
```

---

## 7. 部署计划

### 7.1 实施步骤

1. **Phase 5.1**：实现软过滤服务核心逻辑（1 天）
2. **Phase 5.2**：集成到召回流程（半天）
3. **Phase 5.3**：添加用户交互接口（半天）
4. **Phase 5.4**：测试验证（1 天）
5. **Phase 5.5**：文档完善（半天）

### 7.2 风险评估

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| 评分不准确 | 召回精准度下降 | 提供用户反馈机制，持续优化 |
| 性能下降 | 召回耗时增加 | 使用缓存，异步计算 |
| 过度过滤 | 丢失相关记忆 | 默认不启用，用户可选择开启 |

---

## 8. 成功标准

- [ ] 软过滤评分计算准确率 ≥ 85%
- [ ] 召回精准度提升 ≥ 10%
- [ ] 用户反馈满意度 ≥ 80%
- [ ] 性能损耗 ≤ 10%

---

## 9. 后续优化方向

1. **机器学习优化**：使用用户反馈数据训练评分模型
2. **个性化权重**：根据用户偏好调整各维度权重
3. **动态阈值**：根据查询类型自动调整软过滤阈值
4. **A/B 测试**：对比软过滤开启前后的召回效果

---

*创建时间：2026-03-22 14:21*
*最后更新：2026-03-22 14:21*
*作者：颓弟*
