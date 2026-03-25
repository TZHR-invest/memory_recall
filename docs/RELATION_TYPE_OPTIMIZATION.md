# 关系提取优化 - 添加 classmate 关系类型

## 问题描述

### 用户输入

```
"我和张三李四都是大学同学"
```

### 原来提取的结果

```json
{
  "relations": [
    {"source": "我", "destination": "张三", "relationship": "related_to"},
    {"source": "我", "destination": "李四", "relationship": "related_to"}
  ]
}
```

### 问题

- ❌ 使用了泛化的 `related_to` 关系
- ❌ 缺少 `classmate`（同学）关系类型
- ❌ 未提取张三和李四之间的关系

---

## 根本原因

### 1. 缺少关系类型定义

**原来**：

```python
RELATION_TYPES = {
    "friend": "朋友",
    "colleague": "同事",  # ⚠️ 只有同事，没有同学
    "family": "家人",
    ...
}
```

**问题**：LLM 找不到"同学"关系，降级使用 `related_to`。

### 2. Prompt 示例不足

**原来的 Prompt** 缺少"同学"关系的示例，导致 LLM 不确定如何处理。

---

## 修复方案

### 1. 添加关系类型

**修复后**：

```python
RELATION_TYPES = {
    # 人物关系
    "friend": "朋友",
    "colleague": "同事",
    "classmate": "同学",        # ✅ 新增
    "family": "家人",
    "acquaintance": "熟人",     # ✅ 新增
    
    # 地点关系
    "at": "在...",
    "visited": "访问过",
    "lives_at": "居住在",
    "works_at": "工作在",
    "studied_at": "学习在",     # ✅ 新增
    
    # 事件关系
    "participated": "参与",
    "discussed": "讨论",
    "mentioned": "提及",
    "attended": "参加",          # ✅ 新增
    
    # 主题关系
    "interested_in": "对...感兴趣",
    "knows_about": "了解...",
    "expert_in": "专长于",       # ✅ 新增
    
    # 情感关系
    "likes": "喜欢",
    "dislikes": "不喜欢",
    "loves": "爱",
    "respects": "尊敬",          # ✅ 新增
    
    # 通用关系（兜底）
    "related_to": "相关",
}
```

### 2. 更新 Prompt 示例

**新增示例**：

```
文本：我和张三李四都是大学同学
实体：["我", "张三", "李四", "大学同学"]
输出：
{
    "relations": [
        {"source": "我", "destination": "张三", "relationship": "classmate", "confidence": 0.95},
        {"source": "我", "destination": "李四", "relationship": "classmate", "confidence": 0.95},
        {"source": "张三", "destination": "李四", "relationship": "classmate", "confidence": 0.90},
        {"source": "我", "destination": "大学", "relationship": "studied_at", "confidence": 0.90}
    ]
}
```

### 3. 更新工具描述

```python
ESTABLISH_RELATIONS_TOOL = {
    "type": "function",
    "function": {
        "name": "establish_relations",
        "description": """建立实体之间的关系。

支持的关系类型：
- 人物关系: friend（朋友）, colleague（同事）, classmate（同学）, family（家人）, acquaintance（熟人）
- 地点关系: at（在...）, visited（访问过）, lives_at（居住在）, works_at（工作在）, studied_at（学习在）
...

重要：优先使用具体关系类型（如 classmate），避免使用泛化的 related_to。"""
    }
}
```

---

## 修复后的效果

### 用户输入

```
"我和张三李四都是大学同学"
```

### 修复后提取的结果

```json
{
  "relations": [
    {"source": "我", "destination": "张三", "relationship": "classmate", "confidence": 0.95},
    {"source": "我", "destination": "李四", "relationship": "classmate", "confidence": 0.95},
    {"source": "张三", "destination": "李四", "relationship": "classmate", "confidence": 0.90},
    {"source": "我", "destination": "大学", "relationship": "studied_at", "confidence": 0.90}
  ]
}
```

### 改进点

1. ✅ 使用了具体的 `classmate` 关系
2. ✅ 提取了张三和李四之间的关系
3. ✅ 提取了"在大学学习"的关系
4. ✅ 关系更加准确和丰富

---

## 关系类型对比

### 修复前

| 关系类型 | 数量 | 说明 |
|---------|------|------|
| 人物关系 | 4 | friend, colleague, family, met_at |
| 地点关系 | 4 | at, visited, lives_at, works_at |
| 事件关系 | 3 | participated, discussed, mentioned |
| 主题关系 | 2 | interested_in, knows_about |
| 情感关系 | 3 | likes, dislikes, loves |
| **总计** | **16** | |

### 修复后

| 关系类型 | 数量 | 说明 |
|---------|------|------|
| 人物关系 | 6 | +classmate, +acquaintance |
| 地点关系 | 5 | +studied_at |
| 事件关系 | 4 | +attended |
| 主题关系 | 3 | +expert_in |
| 情感关系 | 4 | +respects |
| 通用关系 | 1 | +related_to（兜底） |
| **总计** | **23** | **增加 7 个** |

---

## 最佳实践

### 1. 优先使用具体关系

```python
# ✅ 推荐
{"relationship": "classmate"}

# ❌ 不推荐
{"relationship": "related_to"}
```

### 2. 避免过度泛化

```
错误示例：
"张三是我的朋友" → related_to

正确示例：
"张三是我的朋友" → friend
"张三是我的同学" → classmate
"张三是我的同事" → colleague
```

### 3. 提取多边关系

```
"我和张三李四都是大学同学"

应该提取：
- 我 → 张三: classmate
- 我 → 李四: classmate
- 张三 → 李四: classmate  # ⚠️ 不要遗漏
```

---

## 监控建议

### 1. 监控 related_to 使用率

```python
# 如果 related_to 使用率过高，说明需要添加更多具体关系类型
related_to_rate = related_to_count / total_relations_count

# 目标: < 5%
if related_to_rate > 0.05:
    logger.warning("related_to 使用率过高，需要添加更多具体关系类型")
```

### 2. 记录未识别的关系

```python
# 如果 LLM 使用了未定义的关系类型，记录下来
unknown_relations = []
for relation in extracted_relations:
    if relation['relationship'] not in RELATION_TYPES:
        unknown_relations.append(relation['relationship'])

# 用于后续优化
if unknown_relations:
    logger.info(f"未定义的关系类型: {unknown_relations}")
```

---

## 未来优化

### 1. 动态关系类型

```python
# 允许 LLM 自定义关系类型（需要审核）
custom_relations = await get_custom_relations(user_id)

RELATION_TYPES.update(custom_relations)
```

### 2. 关系强度

```python
# 添加关系强度字段
{
    "source": "我",
    "destination": "张三",
    "relationship": "classmate",
    "strength": "strong",  # strong/medium/weak
    "confidence": 0.95
}
```

### 3. 时态关系

```python
# 添加时间范围
{
    "source": "我",
    "destination": "张三",
    "relationship": "classmate",
    "time_range": {
        "start": "2018-09",
        "end": "2022-06"
    }
}
```

---

## 总结

### 问题

- ❌ 缺少 `classmate` 关系类型
- ❌ LLM 使用泛化的 `related_to`

### 解决方案

- ✅ 添加 `classmate` 等具体关系类型
- ✅ 更新 Prompt 添加示例
- ✅ 更新工具描述

### 效果

- ✅ 关系提取更准确
- ✅ 图谱更丰富
- ✅ 召回效果更好

### 一句话总结

**添加 `classmate` 等具体关系类型，避免使用泛化的 `related_to`，提升关系提取准确性。**
