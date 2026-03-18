# Memory Recall - 数据模型

> **文档说明**：本文档定义 memory_recall 的核心数据结构，包括记忆数据、人物档案、人脸特征等，以及 PostgreSQL 数据库 schema。

---

## 核心数据结构

### 1. 记忆数据结构（Memory）

**完整 JSON Schema**：

```json
{
  "id": "mem_abc123def456",
  "content": "今天在咖啡店遇到老同学，聊了很久关于创业的想法",
  "created_at": "2026-03-19T00:10:00Z",
  "updated_at": "2026-03-19T00:10:00Z",
  "input_type": "text",
  "time": {
    "value": "2026-03-19T14:30:00+08:00",
    "source": "inferred",
    "confidence": 0.8,
    "original_text": "今天下午"
  },
  "location": {
    "name": "星巴克咖啡店",
    "address": null,
    "latitude": null,
    "longitude": null,
    "need_confirm": true,
    "original_text": "咖啡店"
  },
  "people": [
    {
      "name": "老同学",
      "person_id": null,
      "need_confirm": true,
      "role": "朋友",
      "original_text": "老同学"
    }
  ],
  "emotion": {
    "value": "开心",
    "confidence": 0.7
  },
  "tags": ["社交", "友谊", "聊天", "创业"],
  "duration": {
    "value": "2小时",
    "source": "inferred"
  },
  "topic": {
    "main": "创业想法",
    "keywords": ["创业", "想法", "讨论"]
  },
  "attachments": [
    {
      "type": "image",
      "path": "/storage/images/img_001.jpg",
      "metadata": {
        "width": 1920,
        "height": 1080,
        "size": 2048576
      }
    }
  ],
  "embedding": null,
  "access_count": 0,
  "last_accessed_at": null,
  "importance_score": 0.5,
  "status": "active"
}
```

### 2. 字段分类

| 字段类型 | 字段名 | 是否必填 | 缺失处理 | 说明 |
|---------|--------|---------|---------|------|
| **系统字段** | id | ✅ 必填 | 自动生成 | 记忆唯一标识 |
| | created_at | ✅ 必填 | 自动生成 | 创建时间 |
| | updated_at | ✅ 必填 | 自动更新 | 更新时间 |
| | input_type | ✅ 必填 | 必填 | 输入类型（text/image/audio） |
| **核心字段** | content | ✅ 必填 | 必填 | 记忆主要内容 |
| | time | ✅ 关键字段 | 缺失时询问 | 事件发生时间 |
| | location | ⚠️ 关键字段 | 模糊时确认 | 事件发生位置 |
| | people | ⚠️ 关键字段 | 未知时确认 | 相关人物 |
| **可选字段** | emotion | ❌ 可选 | 大模型推断 | 情绪状态 |
| | tags | ❌ 可选 | 大模型推断 | 标签列表 |
| | duration | ❌ 可选 | 大模型推断 | 持续时间 |
| | topic | ❌ 可选 | 大模型推断 | 主题信息 |
| **系统管理** | attachments | ❌ 可选 | 无附件时为空 | 附件列表 |
| | embedding | ❌ 可选 | 异步生成 | 向量表示 |
| | access_count | ✅ 必填 | 默认 0 | 访问次数 |
| | last_accessed_at | ❌ 可选 | 每次访问更新 | 最后访问时间 |
| | importance_score | ✅ 必填 | 默认 0.5 | 重要性评分 |
| | status | ✅ 必填 | 默认 active | 记忆状态 |

### 3. 关键字段结构详解

#### 3.1 时间字段（time）

```json
{
  "time": {
    "value": "2026-03-19T14:30:00+08:00",
    "source": "inferred",
    "confidence": 0.8,
    "original_text": "今天下午"
  }
}
```

| 子字段 | 类型 | 说明 |
|--------|------|------|
| value | string | ISO 8601 格式时间 |
| source | enum | extracted（明确提取）/ inferred（推断）/ metadata（图片 EXIF） |
| confidence | float | 置信度（0-1） |
| original_text | string | 原始文本中的时间表述 |

**来源类型**：
- `extracted`：用户明确说明，如"明天下午 3 点"
- `inferred`：大模型推断，如"今天"（需要确认具体日期）
- `metadata`：从图片 EXIF 获取

#### 3.2 位置字段（location）

```json
{
  "location": {
    "name": "星巴克咖啡店",
    "address": "北京市朝阳区xxx街道",
    "latitude": 39.9042,
    "longitude": 116.4074,
    "need_confirm": true,
    "original_text": "咖啡店"
  }
}
```

| 子字段 | 类型 | 说明 |
|--------|------|------|
| name | string | 位置名称 |
| address | string | 详细地址 |
| latitude | float | 纬度 |
| longitude | float | 经度 |
| need_confirm | boolean | 是否需要用户确认 |
| original_text | string | 原始文本中的位置表述 |

**need_confirm 判断规则**：
- 位置模糊（如"某咖啡店"）→ `true`
- 位置明确（如"星巴克（国贸店）"）→ `false`
- 无法确定 → `true`

#### 3.3 人物字段（people）

```json
{
  "people": [
    {
      "name": "老同学",
      "person_id": "person_xyz789",
      "need_confirm": true,
      "role": "朋友",
      "original_text": "老同学"
    }
  ]
}
```

| 子字段 | 类型 | 说明 |
|--------|------|------|
| name | string | 人物名称或称呼 |
| person_id | string | 关联的人物档案 ID（已知人物） |
| need_confirm | boolean | 是否需要确认人物身份 |
| role | string | 人物角色（朋友/同事/家人等） |
| original_text | string | 原始文本中的人物表述 |

**人物识别流程**：
1. 提取人物名称 → 在人物档案中匹配
2. 匹配成功 → 填充 `person_id`，`need_confirm = false`
3. 匹配失败 → `person_id = null`，`need_confirm = true`

---

## 人物档案结构（Person Profile）

### 1. 完整 JSON Schema

```json
{
  "id": "person_xyz789abc012",
  "name": "张三",
  "aliases": ["老张", "张哥"],
  "relationship": "朋友",
  "first_mentioned": "2025-01-15T10:00:00Z",
  "last_mentioned": "2026-03-19T14:30:00Z",
  "mention_count": 15,
  "profile": {
    "age": null,
    "occupation": "程序员",
    "company": "某科技公司",
    "hometown": "北京",
    "interests": ["编程", "篮球", "旅行"],
    "personality": ["开朗", "幽默"]
  },
  "face_features": [
    {
      "feature_id": "face_001",
      "image_path": "/storage/images/img_001.jpg",
      "quality_score": 0.95,
      "created_at": "2026-03-19T14:30:00Z"
    }
  ],
  "interactions": [
    {
      "memory_id": "mem_abc123",
      "date": "2026-03-19T14:30:00Z",
      "location": "咖啡店",
      "topic": "创业想法"
    }
  ],
  "notes": "大学同学，毕业后在科技公司工作",
  "tags": ["大学同学", "程序员", "篮球爱好者"],
  "created_at": "2025-01-15T10:00:00Z",
  "updated_at": "2026-03-19T14:30:00Z"
}
```

### 2. 字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| id | string | 人物档案唯一标识 |
| name | string | 正式名称 |
| aliases | list | 别名/昵称列表 |
| relationship | string | 与用户的关系 |
| first_mentioned | datetime | 首次提及时间 |
| last_mentioned | datetime | 最后提及时间 |
| mention_count | integer | 被提及次数 |
| profile | object | 详细档案信息 |
| face_features | list | 人脸特征列表 |
| interactions | list | 互动记录 |
| notes | string | 备注信息 |
| tags | list | 标签列表 |

### 3. 人物档案自动更新

**触发条件**：
- 新记忆中提到该人物
- 图片中识别到该人物
- 用户手动编辑

**自动更新字段**：
- `last_mentioned`：更新为当前时间
- `mention_count`：计数 +1
- `interactions`：添加互动记录
- `profile`：根据新信息补充（如有）

---

## 人脸特征结构（Face Feature）

### 1. 完整 JSON Schema

```json
{
  "id": "face_abc123xyz789",
  "person_id": "person_xyz789abc012",
  "image_path": "/storage/images/img_001.jpg",
  "face_box": {
    "x": 100,
    "y": 150,
    "width": 200,
    "height": 200
  },
  "landmarks": [
    {"x": 150, "y": 200},
    {"x": 250, "y": 200},
    {"x": 200, "y": 250},
    {"x": 160, "y": 300},
    {"x": 240, "y": 300}
  ],
  "embedding": [0.123, 0.456, ...],
  "quality_score": 0.95,
  "blur_score": 0.02,
  "brightness": 0.7,
  "created_at": "2026-03-19T14:30:00Z",
  "source_memory": "mem_abc123def456"
}
```

### 2. 字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| id | string | 人脸特征唯一标识 |
| person_id | string | 关联的人物档案 ID |
| image_path | string | 图片存储路径 |
| face_box | object | 人脸框坐标 |
| landmarks | list | 面部关键点坐标 |
| embedding | list | 人脸特征向量（**128 维**，face_recognition 标准） |
| quality_score | float | 人脸质量评分（0-1） |
| blur_score | float | 模糊度评分（0-1，越小越清晰） |
| brightness | float | 亮度评分（0-1） |
| created_at | datetime | 创建时间 |
| source_memory | string | 来源记忆 ID |

### 3. 人脸识别流程

```
图片输入
    ↓
人脸检测
    ├─ 检测到人脸 → 继续
    └─ 未检测到 → 结束
    ↓
人脸质量评估
    ├─ 质量达标（quality_score > 0.7）→ 继续
    └─ 质量不足 → 跳过
    ↓
特征提取
    ↓
人脸匹配
    ├─ 匹配成功（相似度 > 0.6）→ 关联到现有人物
    └─ 匹配失败 → 创建新人物档案或标记为未知
    ↓
存储人脸特征
```

---

## PostgreSQL Schema

### 1. 记忆表（memories）

```sql
-- 启用 pgvector 扩展
CREATE EXTENSION IF NOT EXISTS vector;

-- 记忆表
CREATE TABLE memories (
    id VARCHAR(24) PRIMARY KEY,
    content TEXT NOT NULL,
    input_type VARCHAR(10) NOT NULL CHECK (input_type IN ('text', 'image', 'audio')),
    
    -- 时间字段
    time_value TIMESTAMP WITH TIME ZONE,
    time_source VARCHAR(10) CHECK (time_source IN ('extracted', 'inferred', 'metadata')),
    time_confidence FLOAT,
    time_original_text TEXT,
    
    -- 位置字段
    location_name TEXT,
    location_address TEXT,
    location_latitude FLOAT,
    location_longitude FLOAT,
    location_need_confirm BOOLEAN DEFAULT false,
    location_original_text TEXT,
    
    -- 人物字段（JSON 数组）
    people JSONB DEFAULT '[]'::jsonb,
    
    -- 可选字段
    emotion JSONB,
    tags JSONB DEFAULT '[]'::jsonb,
    duration JSONB,
    topic JSONB,
    
    -- 附件
    attachments JSONB DEFAULT '[]'::jsonb,
    
    -- 向量（**1024 维**，对应 doubao-embedding-vision）
    embedding vector(1024),
    
    -- 系统字段
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    access_count INTEGER DEFAULT 0,
    last_accessed_at TIMESTAMP WITH TIME ZONE,
    importance_score FLOAT DEFAULT 0.5,
    status VARCHAR(10) DEFAULT 'active' CHECK (status IN ('active', 'archived', 'deleted'))
);

-- 创建索引
CREATE INDEX idx_memories_created_at ON memories(created_at DESC);
CREATE INDEX idx_memories_time_value ON memories(time_value);
CREATE INDEX idx_memories_location_name ON memories USING gin(to_tsvector('simple', location_name));
CREATE INDEX idx_memories_tags ON memories USING gin(tags);
CREATE INDEX idx_memories_people ON memories USING gin(people);
CREATE INDEX idx_memories_status ON memories(status);

-- 向量索引（使用 HNSW）
CREATE INDEX idx_memories_embedding ON memories USING hnsw (embedding vector_cosine_ops);

-- 全文搜索索引
CREATE INDEX idx_memories_content_fts ON memories USING gin(to_tsvector('simple', content));

-- 更新时间触发器
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_memories_updated_at
    BEFORE UPDATE ON memories
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at();
```

### 2. 人物档案表（persons）

```sql
-- 人物档案表
CREATE TABLE persons (
    id VARCHAR(24) PRIMARY KEY,
    name TEXT NOT NULL,
    aliases JSONB DEFAULT '[]'::jsonb,
    relationship VARCHAR(50),
    
    first_mentioned TIMESTAMP WITH TIME ZONE,
    last_mentioned TIMESTAMP WITH TIME ZONE,
    mention_count INTEGER DEFAULT 0,
    
    profile JSONB DEFAULT '{}'::jsonb,
    interactions JSONB DEFAULT '[]'::jsonb,
    notes TEXT,
    tags JSONB DEFAULT '[]'::jsonb,
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 索引
CREATE INDEX idx_persons_name ON persons USING gin(to_tsvector('simple', name));
CREATE INDEX idx_persons_aliases ON persons USING gin(aliases);
CREATE INDEX idx_persons_last_mentioned ON persons(last_mentioned DESC);

-- 更新时间触发器
CREATE TRIGGER trigger_persons_updated_at
    BEFORE UPDATE ON persons
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at();
```

### 3. 人脸特征表（face_features）

```sql
-- 人脸特征表
CREATE TABLE face_features (
    id VARCHAR(24) PRIMARY KEY,
    person_id VARCHAR(24) REFERENCES persons(id) ON DELETE SET NULL,
    image_path TEXT NOT NULL,
    
    -- 人脸框
    face_box JSONB,
    landmarks JSONB,
    
    -- 人脸特征向量（128 维，face_recognition 标准）
    embedding vector(128),
    
    -- 质量评分
    quality_score FLOAT,
    blur_score FLOAT,
    brightness FLOAT,
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    source_memory VARCHAR(24) REFERENCES memories(id) ON DELETE SET NULL
);

-- 向量索引
CREATE INDEX idx_face_features_embedding ON face_features USING hnsw (embedding vector_cosine_ops);
CREATE INDEX idx_face_features_person_id ON face_features(person_id);
CREATE INDEX idx_face_features_quality ON face_features(quality_score DESC);
```

### 4. 索引缓存表（index_cache）

```sql
-- 索引缓存表（用于加速查询）
CREATE TABLE index_cache (
    id SERIAL PRIMARY KEY,
    index_type VARCHAR(20) NOT NULL,  -- time/location/people/tags
    key_value TEXT NOT NULL,           -- 索引键值
    memory_ids JSONB NOT NULL,         -- 记忆 ID 列表
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    UNIQUE(index_type, key_value)
);

CREATE INDEX idx_index_cache_type ON index_cache(index_type);
```

---

## 数据操作示例

### 1. 插入记忆

```python
import json
from datetime import datetime
import uuid

def create_memory(content: str, input_type: str = 'text', **kwargs) -> dict:
    """创建记忆"""
    memory_id = f"mem_{uuid.uuid4().hex[:12]}"
    
    memory = {
        "id": memory_id,
        "content": content,
        "input_type": input_type,
        "created_at": datetime.utcnow().isoformat() + "Z",
        "time": kwargs.get('time', {}),
        "location": kwargs.get('location', {}),
        "people": kwargs.get('people', []),
        "emotion": kwargs.get('emotion', {}),
        "tags": kwargs.get('tags', []),
        "attachments": kwargs.get('attachments', []),
        "access_count": 0,
        "importance_score": 0.5,
        "status": "active"
    }
    
    # 插入数据库
    db.execute("""
        INSERT INTO memories (
            id, content, input_type, created_at,
            time_value, time_source, time_confidence, time_original_text,
            location_name, location_address, location_latitude, location_longitude,
            location_need_confirm, location_original_text,
            people, emotion, tags, attachments, access_count, importance_score, status
        ) VALUES (
            %s, %s, %s, %s,
            %s, %s, %s, %s,
            %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s, %s, %s
        )
    """, (
        memory['id'], memory['content'], memory['input_type'], memory['created_at'],
        memory['time'].get('value'), memory['time'].get('source'),
        memory['time'].get('confidence'), memory['time'].get('original_text'),
        memory['location'].get('name'), memory['location'].get('address'),
        memory['location'].get('latitude'), memory['location'].get('longitude'),
        memory['location'].get('need_confirm'), memory['location'].get('original_text'),
        json.dumps(memory['people']), json.dumps(memory['emotion']),
        json.dumps(memory['tags']), json.dumps(memory['attachments']),
        memory['access_count'], memory['importance_score'], memory['status']
    ))
    
    return memory
```

### 2. 查询记忆

```python
def query_memories_by_time(start_time: datetime, end_time: datetime) -> list:
    """按时间范围查询记忆"""
    results = db.fetch_all("""
        SELECT * FROM memories
        WHERE time_value >= %s AND time_value <= %s
        AND status = 'active'
        ORDER BY time_value DESC
    """, (start_time, end_time))
    
    return results

def query_memories_by_location(location_name: str) -> list:
    """按位置查询记忆"""
    results = db.fetch_all("""
        SELECT * FROM memories
        WHERE to_tsvector('simple', location_name) @@ to_tsquery('simple', %s)
        AND status = 'active'
        ORDER BY created_at DESC
    """, (location_name,))

def query_memories_by_person(person_name: str) -> list:
    """按人物查询记忆"""
    results = db.fetch_all("""
        SELECT * FROM memories
        WHERE people @> %s::jsonb
        AND status = 'active'
        ORDER BY created_at DESC
    """, (json.dumps([{"name": person_name}]),))
    
    return results

def semantic_search(query_embedding: list, top_k: int = 10) -> list:
    """语义相似度搜索"""
    results = db.fetch_all("""
        SELECT id, content, created_at,
               1 - (embedding <=> %s::vector) as similarity
        FROM memories
        WHERE status = 'active' AND embedding IS NOT NULL
        ORDER BY embedding <=> %s::vector
        LIMIT %s
    """, (query_embedding, query_embedding, top_k))
    
    return results
```

---

*文档版本：v0.1*  
*最后更新：2026-03-19*  
*维护者：颓弟*
*
档版本：v0.1*  
*最后更新：2026-03-19*  
*维护者：颓弟*
