# Memory Recall API 文档

> 版本: v1  
> 更新时间: 2026-03-20

## 概述

Memory Recall API 是一个基于向量检索的个人记忆管理系统，支持自然语言查询和智能召回。

### 基础 URL

```
http://192.168.0.206:8000
```

### 认证

当前版本无需认证。

---

## 端点列表

### 记忆管理

| 方法 | 路径 | 描述 |
|------|------|------|
| POST | `/api/v1/memories` | 创建记忆 |
| POST | `/api/v1/memories/with-graph` | 创建记忆（带图谱构建） |
| GET | `/api/v1/memories` | 列出记忆 |
| GET | `/api/v1/memories/{id}` | 获取单个记忆 |
| PUT | `/api/v1/memories/{id}` | 更新记忆 |
| DELETE | `/api/v1/memories/{id}` | 删除记忆 |

### 搜索与召回

| 方法 | 路径 | 描述 |
|------|------|------|
| POST | `/api/v1/memories/search` | 语义搜索 |
| POST | `/api/v1/memories/recall` | 自然语言召回 |

---

## 详细说明

### 1. 创建记忆（带图谱构建）

**POST** `/api/v1/memories/with-graph`

并发执行向量存储和图谱构建，实现高性能记忆创建。

#### 请求参数

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| content | string | 是 | 记忆内容 |
| user_id | string | 是 | 用户 ID |
| enable_graph | boolean | 否 | 是否启用图谱构建（默认 true） |
| enable_confirmation | boolean | 否 | 是否启用智能确认（默认 false） |

#### 请求示例

```bash
curl -X POST http://192.168.0.206:8000/api/v1/memories/with-graph \
  -H "Content-Type: application/json" \
  -d '{
    "content": "今天和张三在咖啡店聊天，讨论了机器学习项目",
    "user_id": "user_123",
    "enable_graph": true
  }'
```

#### 响应示例

```json
{
  "success": true,
  "memory_id": "550e8400-e29b-41d4-a716-446655440000",
  "graph": {
    "type": "graph",
    "entities": [
      {"entity": "张三", "entity_type": "person", "confidence": 0.95},
      {"entity": "咖啡店", "entity_type": "location", "confidence": 0.90},
      {"entity": "机器学习项目", "entity_type": "topic", "confidence": 0.85}
    ],
    "relations": [
      {"source": "张三", "destination": "咖啡店", "relationship": "met_at", "confidence": 0.85}
    ],
    "entity_count": 3,
    "relation_count": 1,
    "status": "success"
  }
}
```

#### 响应字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| success | boolean | 是否成功 |
| memory_id | string | 记忆 ID（UUID 格式） |
| graph.entities | array | 提取的实体列表 |
| graph.relations | array | 推理的关系列表 |
| graph.entity_count | number | 实体数量 |
| graph.relation_count | number | 关系数量 |

---

### 2. 语义搜索

**POST** `/api/v1/memories/search`

使用向量相似度和关键词混合检索记忆。

#### 请求参数

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| query | string | 是 | 搜索查询文本 |
| limit | number | 否 | 返回数量（默认 10，最大 100） |
| min_similarity | number | 否 | 最小相似度阈值（默认 0.15） |
| hybrid_weight | number | 否 | 向量检索权重（默认 0.6） |

#### 请求示例

```bash
curl -X POST http://192.168.0.206:8000/api/v1/memories/search \
  -H "Content-Type: application/json" \
  -d '{
    "query": "咖啡店 聊天",
    "limit": 5,
    "min_similarity": 0.1
  }'
```

#### 响应示例

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "results": [
      {
        "id": "mem_abc123",
        "content": "今天和张三在咖啡店聊天，讨论了机器学习项目",
        "similarity": 0.95,
        "vector_score": 0.92,
        "keyword_score": 0.98,
        "created_at": "2026-03-20T10:00:00"
      }
    ],
    "count": 1,
    "query": "咖啡店 聊天"
  }
}
```

---

### 3. 自然语言召回

**POST** `/api/v1/memories/recall`

使用自然语言查询召回相关记忆，并生成自然语言回答。

#### 请求参数

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| query | string | 是 | 自然语言查询 |
| limit | number | 否 | 返回数量（默认 10） |
| use_parser | boolean | 否 | 是否使用自然语言解析（默认 true） |
| detail_level | string | 否 | 回答详情级别（brief/medium/detailed） |

#### 请求示例

```bash
curl -X POST http://192.168.0.206:8000/api/v1/memories/recall \
  -H "Content-Type: application/json" \
  -d '{
    "query": "最近在咖啡店做了什么",
    "detail_level": "medium"
  }'
```

---

## 错误码

| 错误码 | 说明 |
|--------|------|
| 200 | 成功 |
| 400 | 参数错误 |
| 404 | 资源不存在 |
| 500 | 服务器内部错误 |

---

## 性能指标

| 指标 | 数值 | 说明 |
|------|------|------|
| 平均响应时间 | 0.80s | 创建记忆（带图谱） |
| 实体提取准确率 | ≥ 90% | 命名实体识别 |
| 关系推理准确率 | ≥ 85% | 实体关系推理 |
| Embedding 缓存命中率 | > 50% | 相同内容复用 |

---

## 变更日志

### v1.0.0 (2026-03-20)

- 初始版本
- 支持记忆创建、搜索、召回
- 支持知识图谱构建
- 支持 Embedding 缓存
- 支持并发处理
