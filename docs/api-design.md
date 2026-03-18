# Memory Recall - API 设计

> **文档说明**：本文档定义 memory_recall 的 RESTful API 接口，包括记忆管理、输入处理、人物管理、召回等模块。

---

## API 概览

### 基础信息

- **Base URL**: `http://localhost:8000/api/v1`
- **Content-Type**: `application/json`
- **认证方式**: Bearer Token

### 通用响应格式

**成功响应**：

```json
{
  "code": 200,
  "message": "success",
  "data": { ... }
}
```

**错误响应**：

```json
{
  "code": 400,
  "message": "Invalid request",
  "error": "field 'content' is required"
}
```

---

## 记忆管理 API

### 1. 创建记忆

**POST** `/memories`

**请求体**：

```json
{
  "content": "今天在咖啡店遇到老同学，聊了很久",
  "input_type": "text",
  "time": {
    "value": "2026-03-19T14:30:00+08:00",
    "source": "inferred"
  },
  "location": {
    "name": "咖啡店",
    "need_confirm": true
  },
  "people": [
    {
      "name": "老同学",
      "need_confirm": true
    }
  ],
  "tags": ["社交", "聊天"],
  "attachments": []
}
```

**响应**：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "id": "mem_abc123def456",
    "content": "今天在咖啡店遇到老同学，聊了很久",
    "input_type": "text",
    "created_at": "2026-03-19T00:10:00Z",
    "time": {
      "value": "2026-03-19T14:30:00+08:00",
      "source": "inferred",
      "confidence": 0.8
    },
    "location": {
      "name": "咖啡店",
      "need_confirm": true
    },
    "people": [
      {
        "name": "老同学",
        "need_confirm": true
      }
    ],
    "tags": ["社交", "聊天"],
    "status": "active",
    "need_confirmation": true,
    "confirmation_questions": [
      {
        "field": "location",
        "question": "具体是哪家咖啡店？",
        "options": []
      },
      {
        "field": "people",
        "question": "老同学是谁？",
        "options": [
          {"name": "张三", "person_id": "person_001"},
          {"name": "李四", "person_id": "person_002"},
          {"name": "新建人物", "person_id": null}
        ]
      }
    ]
  }
}
```

### 2. 获取记忆

**GET** `/memories/{memory_id}`

**响应**：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "id": "mem_abc123def456",
    "content": "今天在咖啡店遇到老同学，聊了很久",
    "input_type": "text",
    "created_at": "2026-03-19T00:10:00Z",
    "updated_at": "2026-03-19T00:10:00Z",
    "time": {
      "value": "2026-03-19T14:30:00+08:00",
      "source": "inferred",
      "confidence": 0.8
    },
    "location": {
      "name": "星巴克（国贸店）",
      "address": "北京市朝阳区建国门外大街1号",
      "latitude": 39.9086,
      "longitude": 116.4595,
      "need_confirm": false
    },
    "people": [
      {
        "name": "张三",
        "person_id": "person_001",
        "need_confirm": false
      }
    ],
    "emotion": {
      "value": "开心",
      "confidence": 0.7
    },
    "tags": ["社交", "聊天", "友谊"],
    "attachments": [],
    "access_count": 3,
    "importance_score": 0.6,
    "status": "active"
  }
}
```

### 3. 更新记忆

**PATCH** `/memories/{memory_id}`

**请求体**：

```json
{
  "content": "今天在咖啡店遇到老同学张三，聊了很久关于创业的想法",
  "location": {
    "name": "星巴克（国贸店）",
    "need_confirm": false
  },
  "people": [
    {
      "name": "张三",
      "person_id": "person_001",
      "need_confirm": false
    }
  ],
  "tags": ["社交", "聊天", "创业"]
}
```

**响应**：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "id": "mem_abc123def456",
    "updated_at": "2026-03-19T01:00:00Z"
  }
}
```

### 4. 删除记忆

**DELETE** `/memories/{memory_id}`

**响应**：

```json
{
  "code": 200,
  "message": "success",
  "data": null
}
```

### 5. 批量获取记忆

**GET** `/memories?ids=mem_001,mem_002,mem_003`

**响应**：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "memories": [
      { "id": "mem_001", "content": "..." },
      { "id": "mem_002", "content": "..." },
      { "id": "mem_003", "content": "..." }
    ]
  }
}
```

---

## 输入处理 API

### 1. 文本输入处理

**POST** `/input/text`

**请求体**：

```json
{
  "content": "今天下午在咖啡店遇到老同学，聊了创业的事",
  "auto_extract": true,
  "auto_inquiry": true
}
```

**参数说明**：
- `content`: 文本内容（必填）
- `auto_extract`: 是否自动提取结构化信息（默认 true）
- `auto_inquiry`: 是否自动询问缺失字段（默认 true）

**响应**：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "memory_id": "mem_abc123def456",
    "extracted": {
      "time": {
        "value": "2026-03-19T14:00:00+08:00",
        "source": "inferred"
      },
      "location": {
        "name": "咖啡店",
        "need_confirm": true
      },
      "people": [
        {
          "name": "老同学",
          "need_confirm": true
        }
      ],
      "tags": ["社交", "创业", "聊天"]
    },
    "need_confirmation": true,
    "confirmation_questions": [
      {
        "field": "location",
        "question": "具体是哪家咖啡店？"
      },
      {
        "field": "people",
        "question": "老同学是谁？",
        "options": ["张三", "李四", "新建人物"]
      }
    ]
  }
}
```

### 2. 图片输入处理

**POST** `/input/image`

**请求体**：`multipart/form-data`

```
image: [图片文件]
auto_extract: true
auto_ocr: true
auto_face_detection: true
```

**参数说明**：
- `image`: 图片文件（必填）
- `auto_extract`: 是否自动提取结构化信息（默认 true）
- `auto_ocr`: 是否执行 OCR（默认 true）
- `auto_face_detection`: 是否执行人脸检测（默认 true）

**响应**：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "memory_id": "mem_xyz789abc012",
    "image_info": {
      "width": 1920,
      "height": 1080,
      "size": 2048576,
      "format": "JPEG"
    },
    "exif": {
      "datetime": "2026-03-19T14:30:00",
      "gps": {
        "latitude": 39.9086,
        "longitude": 116.4595
      },
      "device": {
        "make": "Apple",
        "model": "iPhone 14 Pro"
      }
    },
    "ocr_result": {
      "text": "",
      "regions": []
    },
    "scene": {
      "type": "室内",
      "objects": ["桌子", "椅子", "咖啡杯", "人物"]
    },
    "faces": [
      {
        "bbox": [100, 150, 200, 250],
        "quality_score": 0.95,
        "person_match": {
          "person_id": "person_001",
          "name": "张三",
          "confidence": 0.85
        }
      }
    ],
    "extracted": {
      "content": "在咖啡店里，有一个人坐在桌前",
      "time": {
        "value": "2026-03-19T14:30:00+08:00",
        "source": "metadata"
      },
      "location": {
        "name": "咖啡店",
        "need_confirm": true
      },
      "people": [
        {
          "name": "张三",
          "person_id": "person_001",
          "need_confirm": false
        }
      ],
      "tags": ["咖啡", "室内", "社交"]
    },
    "need_confirmation": true,
    "confirmation_questions": [
      {
        "field": "location",
        "question": "照片是在哪里拍的？"
      }
    ]
  }
}
```

### 3. 确认缺失字段

**POST** `/input/confirm`

**请求体**：

```json
{
  "memory_id": "mem_abc123def456",
  "confirmations": [
    {
      "field": "location",
      "value": {
        "name": "星巴克（国贸店）",
        "address": "北京市朝阳区建国门外大街1号"
      }
    },
    {
      "field": "people",
      "value": {
        "name": "张三",
        "person_id": "person_001"
      }
    }
  ]
}
```

**响应**：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "memory_id": "mem_abc123def456",
    "updated": true
  }
}
```

---

## 人物管理 API

### 1. 创建人物档案

**POST** `/persons`

**请求体**：

```json
{
  "name": "张三",
  "aliases": ["老张", "张哥"],
  "relationship": "朋友",
  "profile": {
    "occupation": "程序员",
    "company": "某科技公司",
    "interests": ["编程", "篮球"]
  },
  "tags": ["大学同学", "程序员"],
  "notes": "大学同学，毕业后在科技公司工作"
}
```

**响应**：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "id": "person_xyz789abc012",
    "name": "张三",
    "aliases": ["老张", "张哥"],
    "relationship": "朋友",
    "first_mentioned": "2026-03-19T00:10:00Z",
    "mention_count": 0,
    "profile": {
      "occupation": "程序员",
      "company": "某科技公司",
      "interests": ["编程", "篮球"]
    },
    "tags": ["大学同学", "程序员"],
    "created_at": "2026-03-19T00:10:00Z"
  }
}
```

### 2. 获取人物档案

**GET** `/persons/{person_id}`

**响应**：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "id": "person_xyz789abc012",
    "name": "张三",
    "aliases": ["老张", "张哥"],
    "relationship": "朋友",
    "first_mentioned": "2025-01-15T10:00:00Z",
    "last_mentioned": "2026-03-19T14:30:00Z",
    "mention_count": 15,
    "profile": {
      "occupation": "程序员",
      "company": "某科技公司",
      "interests": ["编程", "篮球"]
    },
    "face_features": [
      {
        "feature_id": "face_001",
        "image_path": "/storage/images/img_001.jpg",
        "quality_score": 0.95
      }
    ],
    "recent_interactions": [
      {
        "memory_id": "mem_abc123",
        "date": "2026-03-19T14:30:00Z",
        "location": "咖啡店",
        "topic": "创业想法"
      }
    ],
    "tags": ["大学同学", "程序员"],
    "notes": "大学同学，毕业后在科技公司工作",
    "created_at": "2025-01-15T10:00:00Z",
    "updated_at": "2026-03-19T14:30:00Z"
  }
}
```

### 3. 更新人物档案

**PATCH** `/persons/{person_id}`

**请求体**：

```json
{
  "profile": {
    "occupation": "高级程序员",
    "company": "某大厂"
  },
  "tags": ["大学同学", "程序员", "大厂员工"]
}
```

**响应**：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "id": "person_xyz789abc012",
    "updated_at": "2026-03-19T01:00:00Z"
  }
}
```

### 4. 搜索人物

**GET** `/persons/search?name=张三`

**响应**：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "persons": [
      {
        "id": "person_xyz789abc012",
        "name": "张三",
        "relationship": "朋友",
        "mention_count": 15
      }
    ]
  }
}
```

### 5. 获取人物相关记忆

**GET** `/persons/{person_id}/memories?limit=10`

**响应**：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "person_id": "person_xyz789abc012",
    "memories": [
      {
        "id": "mem_abc123",
        "content": "今天在咖啡店遇到张三...",
        "time": {
          "value": "2026-03-19T14:30:00+08:00"
        },
        "location": {
          "name": "星巴克（国贸店）"
        }
      }
    ]
  }
}
```

---

## 召回 API

### 1. 自然语言查询

**POST** `/recall/query`

**请求体**：

```json
{
  "query": "上周和老同学在咖啡店聊了什么",
  "top_k": 10,
  "include_highlights": true,
  "include_summary": true
}
```

**参数说明**：
- `query`: 查询文本（必填）
- `top_k`: 返回结果数量（默认 10）
- `include_highlights`: 是否包含高亮片段（默认 true）
- `include_summary`: 是否包含结果摘要（默认 true）

**响应**：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "query": "上周和老同学在咖啡店聊了什么",
    "parsed_query": {
      "time_range": {
        "start": "2026-03-12T00:00:00+08:00",
        "end": "2026-03-19T23:59:59+08:00"
      },
      "people": ["老同学"],
      "location": "咖啡店",
      "keywords": ["聊"],
      "intent": "query_content"
    },
    "total": 5,
    "results": [
      {
        "id": "mem_abc123",
        "content": "今天在咖啡店遇到老同学，聊了很久关于创业的想法",
        "time": {
          "value": "2026-03-15T14:30:00+08:00",
          "display": "3月15日 周五 14:30"
        },
        "location": {
          "name": "星巴克（国贸店）"
        },
        "people": [
          {
            "name": "张三",
            "person_id": "person_001"
          }
        ],
        "tags": ["社交", "创业", "聊天"],
        "score": 0.92,
        "matched_fields": ["时间", "人物", "位置"],
        "highlights": [
          "在<span class='highlight'>咖啡店</span>遇到<span class='highlight'>老同学</span>",
          "聊了很久关于<span class='highlight'>创业</span>的想法"
        ]
      }
    ],
    "summary": "找到 5 条相关记忆，主要涉及创业话题",
    "suggestions": [
      "查看更多关于创业的记忆",
      "查看与张三相关的其他记忆"
    ]
  }
}
```

### 2. 结构化查询

**POST** `/recall/structured`

**请求体**：

```json
{
  "time_range": {
    "start": "2026-03-12T00:00:00+08:00",
    "end": "2026-03-19T23:59:59+08:00"
  },
  "people": ["张三"],
  "location": "咖啡店",
  "tags": ["创业"],
  "keywords": ["聊天", "讨论"],
  "top_k": 10,
  "sort_by": "relevance",
  "sort_order": "desc"
}
```

**参数说明**：
- `time_range`: 时间范围
- `people`: 人物列表
- `location`: 位置
- `tags`: 标签列表
- `keywords`: 关键词列表
- `top_k`: 返回结果数量
- `sort_by`: 排序字段（relevance/time/access_count）
- `sort_order`: 排序方向（asc/desc）

**响应**：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "total": 3,
    "results": [
      {
        "id": "mem_abc123",
        "content": "今天在咖啡店遇到张三，聊了很久关于创业的想法",
        "time": {
          "value": "2026-03-15T14:30:00+08:00"
        },
        "score": 0.95,
        "matched_fields": ["时间", "人物", "位置", "标签"]
      }
    ]
  }
}
```

### 3. 相似记忆

**GET** `/recall/similar/{memory_id}?top_k=5`

**响应**：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "source_memory": {
      "id": "mem_abc123",
      "content": "今天在咖啡店遇到张三..."
    },
    "similar_memories": [
      {
        "id": "mem_def456",
        "content": "上次和张三在咖啡店讨论项目...",
        "similarity": 0.85
      }
    ]
  }
}
```

### 4. 时间线查询

**GET** `/recall/timeline?start=2026-03-01&end=2026-03-31`

**响应**：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "start": "2026-03-01T00:00:00+08:00",
    "end": "2026-03-31T23:59:59+08:00",
    "timeline": [
      {
        "date": "2026-03-01",
        "count": 5,
        "memories": [
          {
            "id": "mem_001",
            "content": "...",
            "time": "2026-03-01T10:00:00+08:00"
          }
        ]
      },
      {
        "date": "2026-03-02",
        "count": 3,
        "memories": []
      }
    ]
  }
}
```

---

## 统计 API

### 1. 记忆统计

**GET** `/stats/memories`

**响应**：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "total": 1250,
    "by_type": {
      "text": 800,
      "image": 450,
      "audio": 0
    },
    "by_time": {
      "today": 15,
      "this_week": 78,
      "this_month": 234,
      "this_year": 1250
    },
    "top_locations": [
      {"name": "咖啡店", "count": 45},
      {"name": "办公室", "count": 38}
    ],
    "top_people": [
      {"name": "张三", "count": 23},
      {"name": "李四", "count": 15}
    ],
    "top_tags": [
      {"name": "社交", "count": 120},
      {"name": "工作", "count": 98}
    ]
  }
}
```

### 2. 人物统计

**GET** `/stats/persons`

**响应**：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "total": 50,
    "by_relationship": {
      "朋友": 20,
      "同事": 15,
      "家人": 10,
      "其他": 5
    },
    "most_mentioned": [
      {"name": "张三", "mention_count": 23},
      {"name": "李四", "mention_count": 15}
    ]
  }
}
```

---

## API 错误码

| 错误码 | 说明 |
|--------|------|
| 200 | 成功 |
| 400 | 请求参数错误 |
| 401 | 未授权 |
| 403 | 无权限 |
| 404 | 资源不存在 |
| 409 | 资源冲突 |
| 500 | 服务器内部错误 |
| 503 | 服务不可用 |

---

## API 实现示例（FastAPI）

```python
from fastapi import FastAPI, HTTPException, UploadFile, File
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

app = FastAPI(title="Memory Recall API", version="1.0.0")

# ========== 记忆管理 API ==========

class MemoryCreate(BaseModel):
    content: str
    input_type: str = "text"
    time: Optional[dict] = None
    location: Optional[dict] = None
    people: Optional[List[dict]] = None
    tags: Optional[List[str]] = None
    attachments: Optional[List[str]] = None

@app.post("/api/v1/memories")
async def create_memory(memory: MemoryCreate):
    """创建记忆"""
    # 调用记忆存储服务
    memory_id = await memory_store.create(memory.dict())
    
    # 返回结果
    return {
        "code": 200,
        "message": "success",
        "data": {
            "id": memory_id,
            **memory.dict(),
            "created_at": datetime.utcnow().isoformat()
        }
    }

@app.get("/api/v1/memories/{memory_id}")
async def get_memory(memory_id: str):
    """获取记忆"""
    memory = await memory_store.get(memory_id)
    
    if not memory:
        raise HTTPException(status_code=404, detail="Memory not found")
    
    return {
        "code": 200,
        "message": "success",
        "data": memory
    }

@app.patch("/api/v1/memories/{memory_id}")
async def update_memory(memory_id: str, updates: dict):
    """更新记忆"""
    success = await memory_store.update(memory_id, updates)
    
    if not success:
        raise HTTPException(status_code=404, detail="Memory not found")
    
    return {
        "code": 200,
        "message": "success",
        "data": {
            "id": memory_id,
            "updated_at": datetime.utcnow().isoformat()
        }
    }

# ========== 输入处理 API ==========

@app.post("/api/v1/input/text")
async def process_text_input(content: str, auto_extract: bool = True):
    """处理文本输入"""
    # 调用文本处理器
    processed = await text_processor.process(content)
    
    # 结构化提取
    if auto_extract:
        extracted = await llm_service.extract_memory(content)
        processed['extracted'] = extracted
    
    # 存储记忆
    memory_id = await memory_store.create(processed)
    
    return {
        "code": 200,
        "message": "success",
        "data": {
            "memory_id": memory_id,
            **processed
        }
    }

@app.post("/api/v1/input/image")
async def process_image_input(
    image: UploadFile = File(...),
    auto_extract: bool = True,
    auto_ocr: bool = True,
    auto_face_detection: bool = True
):
    """处理图片输入"""
    # 保存图片
    image_path = await save_image(image)
    
    # 调用图片处理器
    processed = await image_processor.process(
        image_path,
        auto_ocr=auto_ocr,
        auto_face_detection=auto_face_detection
    )
    
    # 结构化提取
    if auto_extract:
        extracted = await llm_service.extract_from_image(processed)
        processed['extracted'] = extracted
    
    # 存储记忆
    memory_id = await memory_store.create(processed)
    
    return {
        "code": 200,
        "message": "success",
        "data": {
            "memory_id": memory_id,
            **processed
        }
    }

# ========== 召回 API ==========

class RecallQuery(BaseModel):
    query: str
    top_k: int = 10
    include_highlights: bool = True
    include_summary: bool = True

@app.post("/api/v1/recall/query")
async def recall_by_query(request: RecallQuery):
    """自然语言查询"""
    # 解析查询
    parsed_query = await query_parser.parse(request.query)
    
    # 执行召回
    results = await recall_service.recall(parsed_query, request.top_k)
    
    # 生成高亮和摘要
    if request.include_highlights:
        results = await highlighter.add_highlights(results, parsed_query['keywords'])
    
    if request.include_summary:
        summary = await summarizer.summarize(request.query, results)
    
    return {
        "code": 200,
        "message": "success",
        "data": {
            "query": request.query,
            "parsed_query": parsed_query,
            "total": len(results),
            "results": results,
            "summary": summary if request.include_summary else None
        }
    }
```

---

*文档版本：v0.1*  
*最后更新：2026-03-19*  
*维护者：颓弟*
