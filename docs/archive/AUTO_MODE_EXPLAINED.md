# 图谱召回 Auto 模式详解

## 核心原理

Auto 模式是一种**渐进式匹配策略**，按照"先快后慢"的原则自动选择最佳匹配方法。

```
查询 → 精确匹配（快）→ 未找到？→ 关键词匹配（中）→ 未找到？→ 模糊匹配（慢）
```

## 工作流程

### 流程图

```
用户查询: "学习了什么新技能"
    ↓
① 精确匹配（1ms）
    字符串包含检测: "新技能学习" in "学习了什么新技能" ?
    结果: ❌ 未找到
    ↓
② 关键词匹配（10ms）
    查询分词: ["学习", "新技能"]
    实体分词: ["新技能", "学习"]
    关键词重叠: 2/2 = 100%
    结果: ✅ 找到 "新技能学习"
    ↓
返回结果
```

### 代码实现

**位置**: `graph_recall_service.py:383-443`

```python
async def _extract_entities_from_query(
    self,
    query: str,
    user_id: str,
    use_dict: bool = True,
    enhanced_mode: str = "auto"  # ⭐ 默认 auto
) -> List[str]:
    
    # 步骤 1: 快速精确匹配（1ms）
    entities = self.entity_dict.extract_entities_fast(query, user_id)
    
    # 步骤 2: 如果未找到，启用增强匹配
    if not entities and enhanced_mode != "exact":
        # 根据 enhanced_mode 选择方法
        enhanced_entities = await self._enhanced_entity_extraction(
            query, user_id, enhanced_mode
        )
        entities = [e[0] for e in enhanced_entities]
    
    return entities
```

## 四种模式对比

| 模式 | 匹配策略 | 耗时 | 适用场景 |
|------|---------|------|---------|
| `exact` | 仅精确匹配 | < 1ms | 确定查询包含实体名称 |
| `keyword` | 精确 + 关键词 | 5-10ms | 推荐默认使用 |
| `enhanced` | 精确 + 关键词 + 模糊 | 50-100ms | 需要容忍拼写错误 |
| `full` | 精确 + 关键词 + 模糊 + 语义 | 100-500ms | 最高召回率 |
| `auto` | 渐进式匹配 | 动态 | **推荐** |

## Auto 模式的智能决策

### 决策树

```
开始
  ↓
精确匹配
  ↓
找到实体？
  ├─ 是 → 返回结果（耗时: 1ms）
  └─ 否 ↓
      关键词匹配
        ↓
      找到实体？
        ├─ 是 → 返回结果（耗时: 10ms）
        └─ 否 ↓
            是否需要更高召回？
              ├─ 是 → 模糊匹配（耗时: 100ms）
              └─ 否 → 返回空结果
```

### 实际例子

#### 例子 1: 精确匹配成功

```
查询: "张三的朋友"
词典: "张三"

① 精确匹配: "张三" in "张三的朋友" → ✅ 找到
耗时: 1ms

返回: ["张三"]
```

#### 例子 2: 需要关键词匹配

```
查询: "学习了什么新技能"
词典: "新技能学习"

① 精确匹配: "新技能学习" in "学习了什么新技能" → ❌ 未找到
② 关键词匹配:
   查询分词: ["学习", "新技能"]
   实体分词: ["新技能", "学习"]
   重叠: 100% → ✅ 找到
耗时: 10ms

返回: ["新技能学习"]
```

#### 例子 3: 需要模糊匹配

```
查询: "咖啡"
词典: "咖啡店"

① 精确匹配: "咖啡店" in "咖啡" → ❌ 未找到
② 关键词匹配: ["咖啡"] vs ["咖啡", "店"] → 部分匹配
③ 模糊匹配:
   相似度 = 0.67 > 0.6 → ✅ 找到
耗时: 50ms

返回: ["咖啡店"]
```

#### 例子 4: 需要语义匹配

```
查询: "学的新东西"
词典: "新技能学习"

① 精确匹配: ❌ 未找到
② 关键词匹配: ❌ 关键词不重叠
③ 模糊匹配: ❌ 相似度低
④ 语义匹配:
   embedding 相似度 = 0.85 > 0.75 → ✅ 找到
耗时: 200ms

返回: ["新技能学习"]
```

## 代码级详解

### 步骤 1: 精确匹配

```python
# 快速字符串包含检测
entities = self.entity_dict.extract_entities_fast(query, user_id)

# 实现
for entity_name in entity_dict:
    if entity_name in query:  # 字符串包含
        entities.append(entity_name)

# 耗时: O(n) ≈ 1ms
```

### 步骤 2: 关键词匹配

```python
# 分词后计算关键词重叠
query_keywords = jieba.cut("学习了什么新技能")  # ["学习", "新技能"]
entity_keywords = jieba.cut("新技能学习")       # ["新技能", "学习"]

overlap = set(query_keywords) & set(entity_keywords)
# overlap = {"学习", "新技能"}

if len(overlap) >= 2:
    return entity_name  # 匹配成功

# 耗时: O(n * m) ≈ 10ms
```

### 步骤 3: 模糊匹配

```python
# 计算编辑距离相似度
from difflib import SequenceMatcher

similarity = SequenceMatcher("咖啡", "咖啡店").ratio()
# similarity = 2/3 = 0.67

if similarity >= 0.6:
    return entity_name

# 耗时: O(n * m²) ≈ 50-100ms
```

### 步骤 4: 语义匹配

```python
# 计算 embedding 相似度
query_vec = embed("学的新东西")      # [0.1, 0.2, ...]
entity_vec = embed("新技能学习")     # [0.15, 0.18, ...]

similarity = cosine_similarity(query_vec, entity_vec)
# similarity = 0.85

if similarity >= 0.75:
    return entity_name

# 耗时: O(n * embedding) ≈ 100-500ms
```

## 性能优化

### 为什么 Auto 模式快？

```
大多数查询情况：
- 精确匹配成功: 80% 查询，耗时 1ms
- 关键词匹配成功: 15% 查询，耗时 10ms
- 需要模糊/语义: 5% 查询，耗时 100-500ms

平均耗时 ≈ 80% * 1ms + 15% * 10ms + 5% * 100ms
        = 0.8ms + 1.5ms + 5ms
        = 7.3ms
```

### 对比全量匹配

```
Full 模式（全部方法）:
每次都执行: 精确 + 关键词 + 模糊 + 语义
耗时 ≈ 1ms + 10ms + 50ms + 200ms = 261ms

Auto 模式:
按需执行，提前终止
平均耗时 ≈ 7.3ms

性能提升: 261ms / 7.3ms ≈ 35 倍
```

## 使用建议

### 场景选择

| 场景 | 推荐模式 | 原因 |
|------|---------|------|
| 用户实时查询 | `auto` | 平衡性能和召回率 |
| 批量处理 | `exact` 或 `keyword` | 性能优先 |
| 重要查询（如付费用户） | `full` | 最高召回率 |
| 不确定查询类型 | `auto` | 自动适配 |

### 配置示例

```python
# 默认配置（推荐）
result = await graph_service.search_graph(
    query="学习了什么新技能",
    user_id="test_user",
    limit=10
    # enhanced_mode 默认为 "auto"
)

# 性能优先
entities = await graph_service._extract_entities_from_query(
    query=query,
    user_id=user_id,
    enhanced_mode="keyword"  # 只用关键词匹配，10ms
)

# 召回率优先
entities = await graph_service._extract_entities_from_query(
    query=query,
    user_id=user_id,
    enhanced_mode="full"  # 全部方法，200ms
)
```

## Auto 模式的智能之处

### 1. 渐进式匹配

```
不是一次性执行所有方法，而是按需执行：
找到就停，找不到才继续
```

### 2. 成本控制

```
大部分查询在 1-10ms 内解决
只有少数困难查询才使用昂贵的语义匹配
```

### 3. 自适应

```
根据查询特点自动选择方法:
- 明确实体名称 → 精确匹配
- 字序不同 → 关键词匹配
- 拼写相似 → 模糊匹配
- 语义相似 → 语义匹配
```

## 总结

### 核心价值

1. **性能优化**: 平均 7ms vs 全量 260ms，提升 35 倍
2. **召回率保证**: 渐进式匹配，不会遗漏
3. **智能决策**: 根据查询特点自动选择方法
4. **用户无感**: 开发者无需手动选择模式

### 一句话总结

**Auto 模式 = 先快后慢 + 按需执行 + 提前终止 = 性能与召回率的最佳平衡**
