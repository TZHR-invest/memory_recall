# 记忆存储流程

## 当前完整流程（Phase 3 修正后）

```
用户输入记忆
    ↓
┌────────────────────────────────────────────────────────────┐
│  1. 文本处理（TextProcessor）                               │
│  - 分词、实体识别（jieba）                                   │
│  - 时间提取                                                 │
│  - 地点提取                                                 │
│  - 人物提取                                                 │
│  - 情感分析                                                 │
│  - 判断是否需要用户确认                                      │
└────────────────────────────────────────────────────────────┘
    ↓
┌────────────────────────────────────────────────────────────┐
│  2. 记忆创建（MemoryService.create）                        │
│  - 生成 UUID                                                │
│  - 生成 Embedding 向量（doubao-embedding-vision-251215）    │
│  - 存储到 memories 表                                       │
│  - 字段：content, time, location, people, emotion, tags 等  │
└────────────────────────────────────────────────────────────┘
    ↓
┌────────────────────────────────────────────────────────────┐
│  3. 图谱构建（GraphBuilderService.build_graph）             │
│                                                             │
│  3.1 实体提取（Function Calling）                           │
│  - 提取实体：person/location/event/time/task/emotion 等    │
│  - 返回置信度                                               │
│                                                             │
│  3.2 智能确认判断（可选）                                    │
│  - 新实体首次出现 → 需要确认                                 │
│  - 置信度过低（< 0.6）→ 需要确认                             │
│  - 关系冲突 → 需要确认                                       │
│                                                             │
│  3.3 关系推理                                                │
│  - 提取实体之间的关系                                        │
│  - 关系类型：at, met_at, friend, colleague, caused_by 等   │
│                                                             │
│  3.4 存储到图谱表                                            │
│  - entities 表：存储实体                                     │
│  - relations 表：存储关系                                    │
│  - memory_entities 表：记忆-实体关联                         │
│  - pending_confirmations 表：待确认队列                      │
└────────────────────────────────────────────────────────────┘
    ↓
返回结果
{
    "memory_id": "uuid",
    "content": "...",
    "entities": [...],
    "relations": [...],
    "confirmations": [...]  // 如果启用智能确认
}
```

---

## ⚠️ 重要修正：移除场景自适应提取

**原因**：场景判断应该是**召回时的任务**，不是存储时的任务

| 阶段 | 任务 | 说明 |
|------|------|------|
| **存储时** | 实体提取 + 关系推理 | 不需要场景判断 |
| **召回时** | 向量搜索 + 语义匹配 | 用户问题决定需要什么 |

**修正理由**：
1. 场景信息已隐含在内容中
2. 预判场景可能错
3. 召回时判断更准确

**修正内容**：
- 移除 `EXTRACT_ENTITIES_WITH_SCENARIO_TOOL`
- 移除 `SCENARIO_AWARE_EXTRACTION_PROMPT`
- 移除 `_extract_entities_adaptive` 方法
- 简化 `build_graph` 流程

---

## 数据库表结构

### memories 表（主记忆表）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID | 记忆 ID |
| content | TEXT | 记忆内容 |
| input_type | VARCHAR | 输入类型（text/file/segment） |
| created_at | TIMESTAMP | 创建时间 |
| time_value | TIMESTAMP | 时间值 |
| time_source | VARCHAR | 时间来源 |
| time_confidence | FLOAT | 时间置信度 |
| location_name | VARCHAR | 地点名称 |
| location_address | VARCHAR | 地点地址 |
| location_latitude | FLOAT | 纬度 |
| location_longitude | FLOAT | 经度 |
| people | JSONB | 人物列表 |
| emotion | JSONB | 情感信息 |
| tags | JSONB | 标签列表 |
| embedding | VECTOR(1024) | 向量（pgvector） |
| status | VARCHAR | 状态（active/deleted） |

---

### entities 表（实体表）【Phase 1 新增】

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID | 实体 ID |
| name | VARCHAR(200) | 实体名称 |
| type | VARCHAR(20) | 实体类型（person/location/event/time/task/emotion/topic/decision/concept/solution/problem） |
| confidence | FLOAT | 置信度 |
| mention_count | INT | 提及次数 |
| last_mentioned_at | TIMESTAMP | 最后提及时间 |
| user_id | VARCHAR(100) | 用户 ID |
| created_at | TIMESTAMP | 创建时间 |

---

### relations 表（关系表）【Phase 1 新增】

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID | 关系 ID |
| from_entity_id | UUID | 源实体 ID |
| to_entity_id | UUID | 目标实体 ID |
| relation_type | VARCHAR(50) | 关系类型（at/met_at/friend/colleague/family/related_to/caused_by） |
| weight | FLOAT | 权重 |
| confidence | FLOAT | 置信度 |
| user_id | VARCHAR(100) | 用户 ID |
| created_at | TIMESTAMP | 创建时间 |

---

### memory_entities 表（记忆-实体关联表）【Phase 1 新增】

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID | 关联 ID |
| memory_id | UUID | 记忆 ID |
| entity_id | UUID | 实体 ID |
| mention_context | TEXT | 提及上下文 |
| created_at | TIMESTAMP | 创建时间 |

---

### pending_confirmations 表（待确认队列）【Phase 1 新增】

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID | 确认 ID |
| user_id | VARCHAR(100) | 用户 ID |
| entity_id | UUID | 实体 ID |
| confirmation_type | VARCHAR(50) | 确认类型（new_entity/low_confidence/relation_conflict） |
| question | TEXT | 确认问题 |
| options | JSONB | 选项列表 |
| status | VARCHAR(20) | 状态（pending/confirmed/rejected） |
| created_at | TIMESTAMP | 创建时间 |

---

## API 端点

### 创建记忆

**POST** `/api/v1/memories`

```json
{
    "content": "今天和张三在咖啡店聊天，讨论了机器学习项目",
    "user_id": "user_123",
    "enable_graph": true,  // 是否启用图谱构建
    "enable_confirmation": false  // 是否启用智能确认
}
```

**响应**：

```json
{
    "memory_id": "550e8400-e29b-41d4-a716-446655440000",
    "content": "今天和张三在咖啡店聊天，讨论了机器学习项目",
    "entities": [
        {"entity": "张三", "entity_type": "person", "confidence": 0.95},
        {"entity": "咖啡店", "entity_type": "location", "confidence": 0.9},
        {"entity": "聊天", "entity_type": "event", "confidence": 0.85},
        {"entity": "机器学习项目", "entity_type": "topic", "confidence": 0.8}
    ],
    "relations": [
        {"source": "张三", "destination": "咖啡店", "relationship": "met_at", "confidence": 0.9},
        {"source": "张三", "destination": "聊天", "relationship": "related_to", "confidence": 0.85}
    ],
    "entity_count": 4,
    "relation_count": 2
}
```

---

## 流程说明

### 存储流程

1. **文本处理** → 提取结构化信息
2. **记忆创建** → 存储 memories 表 + 向量
3. **图谱构建** → 存储 entities/relations 表
4. **智能确认**（可选）→ 待确认队列

### 核心优化

- ✅ 实体提取 + 关系推理
- ✅ 智能确认避免错误累积
- ✅ 软过滤不漏记忆
- ✅ PostgreSQL 统一存储（向量 + 图谱）

---

## 总结

### 完整存储流程

1. **文本处理** → 提取结构化信息
2. **记忆创建** → 存储 memories 表 + 向量
3. **图谱构建** → 存储 entities/relations 表
4. **智能确认**（可选）→ 待确认队列

### 核心原则

**存储时不做场景判断，召回时根据用户问题决定**

- ✅ 实体提取 + 关系推理
- ✅ 智能确认避免错误累积
- ✅ 软过滤不漏记忆
- ✅ PostgreSQL 统一存储（向量 + 图谱）
