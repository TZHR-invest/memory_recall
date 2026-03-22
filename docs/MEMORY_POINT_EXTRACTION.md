# 记忆点提取标准化方案

## 背景

当前方案：按时间段分段（粗粒度）

优化方案：提取记忆点（细粒度），每个记忆点是一个独立的信息单元

---

## 核心概念

### 什么是记忆点？

**记忆点（Memory Point）** = 一个独立的信息单元，包含完整的上下文

**示例**：
```
输入："早上9点在咖啡厅和张三讨论项目，涉及AI功能设计。"

❌ 错误理解（碎片化）：
- 记忆点1：咖啡厅（地点）
- 记忆点2：张三（人物）
- 记忆点3：讨论项目（事件）
- 记忆点4：AI功能设计（话题）

✅ 正确理解（完整上下文）：
- 记忆点1：早上9点在咖啡厅和张三讨论项目，涉及AI功能设计（完整事件）
  - 时间：早上9点
  - 地点：咖啡厅
  - 人物：张三
  - 事件：讨论项目
  - 话题：AI功能设计
```

---

## 记忆点分类

### 1. 事件记忆点（Event）

**定义**：发生了什么事

**特征**：
- 有明确的时间
- 有参与者
- 有地点
- 有行动/过程

**示例**：
```json
{
  "type": "event",
  "content": "早上9点在咖啡厅和张三讨论项目，涉及AI功能设计",
  "time": {"value": "2026-03-21T09:00:00", "original_text": "早上9点"},
  "location": {"name": "咖啡厅"},
  "people": [{"name": "张三", "role": "讨论对象"}],
  "action": "讨论项目",
  "topics": ["AI功能设计"],
  "importance": 0.8
}
```

### 2. 人物记忆点（Person）

**定义**：关于某个人的信息

**特征**：
- 有具体的人物
- 有关系描述
- 有属性信息

**示例**：
```json
{
  "type": "person",
  "content": "张三是我的大学同学，现在在做AI创业项目",
  "person": {"name": "张三", "relation": "大学同学"},
  "attributes": ["AI创业"],
  "importance": 0.7
}
```

### 3. 地点记忆点（Location）

**定义**：关于某个地点的信息

**特征**：
- 有明确的地点
- 有特征描述
- 有用途信息

**示例**：
```json
{
  "type": "location",
  "content": "楼下餐厅是公司最近的餐厅，人均消费30元",
  "location": {"name": "楼下餐厅", "type": "餐厅"},
  "attributes": ["离公司近", "人均30元"],
  "importance": 0.5
}
```

### 4. 情感记忆点（Emotion）

**定义**：情感状态或感受

**特征**：
- 有明确的情感
- 有触发因素
- 有时间背景

**示例**：
```json
{
  "type": "emotion",
  "content": "听到AI播客后对未来技术发展有了新思考，心情舒畅",
  "emotion": {"type": "舒畅", "intensity": 8},
  "trigger": "听AI播客",
  "time": {"value": "2026-03-21T09:30:00"},
  "importance": 0.6
}
```

### 5. 学习记忆点（Learning）

**定义**：学到了什么

**特征**：
- 有知识内容
- 有来源
- 有应用场景

**示例**：
```json
{
  "type": "learning",
  "content": "从播客中学到AI将改变软件开发模式",
  "knowledge": "AI改变软件开发模式",
  "source": "播客",
  "application": "技术规划",
  "importance": 0.9
}
```

### 6. 决策记忆点（Decision）

**定义**：做出的决定或计划

**特征**：
- 有明确的决策
- 有原因/背景
- 有执行计划

**示例**：
```json
{
  "type": "decision",
  "content": "决定在项目中引入AI辅助开发工具",
  "decision": "引入AI辅助开发工具",
  "reason": "提高开发效率",
  "plan": "下周开始调研",
  "importance": 0.85
}
```

---

## 记忆点提取规则

### 规则 1：独立性原则

每个记忆点应该是独立可理解的，不依赖其他记忆点。

**示例**：
```
❌ 错误：记忆点1 = "他说"，记忆点2 = "项目进展顺利"
✅ 正确：记忆点1 = "张三说项目进展顺利"
```

### 规则 2：完整性原则

每个记忆点应该包含完整的上下文信息。

**示例**：
```
❌ 错误：
{
  "content": "讨论项目",
  "time": "早上9点"
}

✅ 正确：
{
  "content": "早上9点在咖啡厅和张三讨论项目，涉及AI功能设计",
  "time": {"value": "2026-03-21T09:00:00", "original_text": "早上9点"},
  "location": {"name": "咖啡厅"},
  "people": [{"name": "张三"}],
  "action": "讨论项目",
  "topics": ["AI功能设计"]
}
```

### 规则 3：唯一性原则

同一个记忆点不应该重复提取。

**示例**：
```
输入："早上9点和张三讨论项目，中午12点又和张三讨论项目"

✅ 正确：提取两个记忆点（时间不同）
- 记忆点1：早上9点和张三讨论项目
- 记忆点2：中午12点又和张三讨论项目
```

### 规则 4：重要性原则

记忆点应该有重要性评分，用于排序和筛选。

**评分标准**：
- 0.9-1.0：重大决策、关键事件、重要人物
- 0.7-0.8：有意义的事件、有价值的学习
- 0.5-0.6：日常事件、常规信息
- 0.3-0.4：琐碎细节、背景信息
- 0.1-0.2：无关紧要的信息

---

## 提取 Prompt 设计

```
你是一个记忆提取专家。请从以下文本中提取所有记忆点。

## 记忆点类型

1. **事件记忆点**：发生了什么事（时间、地点、人物、行动）
2. **人物记忆点**：关于某个人的信息（关系、属性）
3. **地点记忆点**：关于某个地点的信息（特征、用途）
4. **情感记忆点**：情感状态或感受（情感类型、触发因素）
5. **学习记忆点**：学到了什么（知识、来源、应用）
6. **决策记忆点**：做出的决定或计划（决策、原因、计划）

## 提取规则

1. **独立性**：每个记忆点应该独立可理解
2. **完整性**：每个记忆点应该包含完整上下文
3. **唯一性**：不重复提取相同记忆点
4. **重要性**：评估记忆点的重要性（0.1-1.0）

## 输出格式

```json
{
  "memory_points": [
    {
      "type": "event",
      "content": "完整的内容描述",
      "time": {"value": "ISO时间", "original_text": "原文时间"},
      "location": {"name": "地点名称", "type": "地点类型"},
      "people": [{"name": "姓名", "role": "角色"}],
      "action": "行动描述",
      "topics": ["话题1", "话题2"],
      "importance": 0.8,
      "summary": "一句话摘要"
    }
  ]
}
```

## 输入文本

{输入文本}

请提取记忆点：
```

---

## 存储方案

### 方案 A：每个记忆点一条记录（推荐）

```sql
-- 记忆点表
CREATE TABLE memory_points (
    id UUID PRIMARY KEY,
    user_id VARCHAR(255),
    type VARCHAR(50),  -- event/person/location/emotion/learning/decision
    content TEXT,
    time_value TIMESTAMP,
    time_original_text VARCHAR(100),
    location_name VARCHAR(255),
    people JSONB,
    importance FLOAT,
    summary VARCHAR(500),
    embedding VECTOR(1024),
    created_at TIMESTAMP,
    
    -- 关联字段
    source_memory_id UUID,  -- 来源记忆 ID
    parent_point_id UUID    -- 父记忆点 ID（可选，用于层级关系）
);
```

### 方案 B：记忆点作为记忆的扩展

```sql
-- 在 memories 表中添加字段
ALTER TABLE memories ADD COLUMN memory_point_type VARCHAR(50);
ALTER TABLE memories ADD COLUMN importance FLOAT;
ALTER TABLE memories ADD COLUMN summary VARCHAR(500);
```

---

## 召回优化

### 召回策略

```python
def recall_memory_points(query, limit=10):
    """
    召回记忆点
    
    策略：
    1. 向量搜索（按相似度）
    2. 重要性排序（importance 权重）
    3. 时间排序（最近的优先）
    """
    # 1. 向量搜索
    query_embedding = generate_embedding(query)
    results = search_by_vector(query_embedding, limit=limit*3)
    
    # 2. 重要性排序
    results = sorted(results, key=lambda x: x.importance, reverse=True)
    
    # 3. 取 top N
    return results[:limit]
```

### 召回结果展示

```
查询："和张三讨论了什么"

召回结果：
- 📅 2026/3/21 09:00 | 和张三在咖啡厅讨论项目，涉及AI功能设计（重要性: 0.8）
- 📅 2026/3/20 14:00 | 和张三讨论了项目进展（重要性: 0.7）
- 📅 2026/3/19 10:00 | 和张三第一次见面，讨论合作可能性（重要性: 0.85）
```

---

## 实施步骤

### Phase 1：Prompt 优化

1. 设计记忆点提取 Prompt
2. 测试不同类型的文本
3. 调整 Prompt 提高提取质量

### Phase 2：数据模型设计

1. 选择存储方案（A or B）
2. 设计索引策略
3. 实现去重逻辑

### Phase 3：召回优化

1. 实现重要性排序
2. 实现多维度过滤
3. 优化展示格式

---

## 示例

### 输入

```
昨天是非常充实的一天。早上8点起床，给自己做了份早餐。煎了两个鸡蛋，烤了几片面包，还煮了一杯香浓的咖啡。9点半出门，开车去公司。路上听了一个关于人工智能的播客节目，非常有启发性，让我对未来的技术发展有了新的思考。10点到达公司，遇到了老同学小李。我们聊了一会儿，他现在在做AI创业项目，听起来很有前景。中午和同事们一起去楼下餐厅吃饭，讨论了最近的技术趋势和行业动态。下午1点半回到工位，开始写代码优化系统性能。晚上6点半下班，开车回家。7点半和家人一起吃晚饭，妻子做了红烧肉和清蒸鱼，非常美味。8点半陪孩子们做作业，大女儿在学Python，小儿子在练钢琴。10点半准备睡觉，躺在床上看了几页书。
```

### 输出

```json
{
  "memory_points": [
    {
      "type": "event",
      "content": "早上8点起床做早餐，煎了两个鸡蛋、烤面包、煮咖啡",
      "time": {"value": "2026-03-20T08:00:00", "original_text": "早上8点"},
      "location": {"name": "家"},
      "people": [],
      "action": "做早餐",
      "importance": 0.4,
      "summary": "做早餐"
    },
    {
      "type": "learning",
      "content": "路上听AI播客，对未来技术发展有新思考",
      "time": {"value": "2026-03-20T09:30:00", "original_text": "9点半"},
      "location": {"name": "通勤路上"},
      "knowledge": "AI技术发展趋势",
      "source": "播客节目",
      "importance": 0.85,
      "summary": "听AI播客有启发"
    },
    {
      "type": "person",
      "content": "遇到老同学小李，他在做AI创业项目",
      "time": {"value": "2026-03-20T10:00:00", "original_text": "10点"},
      "location": {"name": "公司"},
      "person": {"name": "小李", "relation": "老同学"},
      "attributes": ["AI创业"],
      "importance": 0.75,
      "summary": "小李在做AI创业"
    },
    {
      "type": "event",
      "content": "中午和同事们一起在楼下餐厅吃饭，讨论技术趋势",
      "time": {"value": "2026-03-20T12:00:00", "original_text": "中午"},
      "location": {"name": "楼下餐厅", "type": "餐厅"},
      "people": [{"name": "同事们", "role": "同事"}],
      "topics": ["技术趋势", "行业动态"],
      "importance": 0.6,
      "summary": "和同事吃饭聊技术"
    },
    {
      "type": "event",
      "content": "下午写代码优化系统性能",
      "time": {"value": "2026-03-20T13:30:00", "original_text": "下午1点半"},
      "location": {"name": "公司"},
      "action": "写代码优化系统性能",
      "importance": 0.7,
      "summary": "优化系统性能"
    },
    {
      "type": "emotion",
      "content": "晚饭妻子做了红烧肉和清蒸鱼，非常美味",
      "time": {"value": "2026-03-20T19:30:00", "original_text": "7点半"},
      "location": {"name": "家"},
      "emotion": {"type": "满足", "intensity": 8},
      "trigger": "妻子做的晚餐",
      "importance": 0.5,
      "summary": "晚饭美味"
    },
    {
      "type": "person",
      "content": "陪大女儿学Python，小儿子练钢琴",
      "time": {"value": "2026-03-20T20:30:00", "original_text": "8点半"},
      "location": {"name": "家"},
      "people": [
        {"name": "大女儿", "relation": "女儿", "activity": "学Python"},
        {"name": "小儿子", "relation": "儿子", "activity": "练钢琴"}
      ],
      "importance": 0.65,
      "summary": "陪孩子学习"
    }
  ]
}
```

---

## 总结

**核心改进**：
1. ✅ 从"按时间段分段"进化为"按记忆点提取"
2. ✅ 每个记忆点包含完整上下文
3. ✅ 支持多类型记忆点（事件、人物、地点、情感、学习、决策）
4. ✅ 重要性评分，优化召回排序

**实施优先级**：
- P0：Prompt 优化（立即可做）
- P1：数据模型调整（短期）
- P2：召回优化（中期）
