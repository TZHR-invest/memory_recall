# Memory Recall API 使用指南

## 简介

Memory Recall API 是一个基于向量检索的个人记忆管理系统，支持自然语言查询和智能召回。

## 快速开始

### 1. 启动服务

```bash
cd apps/api
./venv/bin/python main.py
```

服务将在 `http://localhost:8000` 启动。

### 2. 访问文档

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc
- **OpenAPI JSON**: http://localhost:8000/openapi.json

## API 端点

### 健康检查

#### 检查服务状态
```bash
curl http://localhost:8000/health
```

#### 检查数据库状态
```bash
curl http://localhost:8000/health/db
```

### 记忆管理

#### 创建记忆

```bash
curl -X POST http://localhost:8000/api/v1/memories \
  -H "Content-Type: application/json" \
  -d '{
    "content": "今天和老同学在咖啡店见面聊天，聊了很多以前的事情",
    "input_type": "text",
    "tags": ["社交", "老同学"]
  }'
```

**请求参数**：
- `content` (必填): 记忆内容
- `input_type`: 输入类型（text/image/audio），默认 text
- `time`: 时间信息（可选）
- `location`: 地点信息（可选）
- `people`: 人物信息（可选）
- `emotion`: 情绪信息（可选）
- `tags`: 标签列表（可选）

**响应示例**：
```json
{
  "code": 200,
  "message": "success",
  "data": {
    "id": "mem_abc123def456",
    "content": "今天和老同学在咖啡店见面聊天，聊了很多以前的事情",
    "input_type": "text",
    "created_at": "2024-01-01T12:00:00",
    "tags": ["社交", "老同学"]
  }
}
```

#### 列出记忆

```bash
curl "http://localhost:8000/api/v1/memories?limit=10&offset=0&status=active"
```

**查询参数**：
- `limit`: 每页数量，1-100，默认 50
- `offset`: 偏移量，默认 0
- `status`: 状态过滤（active/archived/deleted），默认 active
- `order_by`: 排序字段，默认 created_at
- `order`: 排序方向（asc/desc），默认 desc

#### 获取单个记忆

```bash
curl http://localhost:8000/api/v1/memories/mem_abc123def456
```

#### 更新记忆

```bash
curl -X PUT http://localhost:8000/api/v1/memories/mem_abc123def456 \
  -H "Content-Type: application/json" \
  -d '{
    "content": "更新后的内容",
    "tags": ["社交", "老同学", "重要"]
  }'
```

#### 删除记忆

```bash
curl -X DELETE http://localhost:8000/api/v1/memories/mem_abc123def456
```

**注意**：这是软删除，记忆会被标记为 `deleted` 状态。

### 搜索与召回

#### 语义搜索

使用向量相似度和关键词混合检索。

```bash
curl -X POST http://localhost:8000/api/v1/memories/search \
  -H "Content-Type: application/json" \
  -d '{
    "query": "咖啡店见面",
    "limit": 10,
    "min_similarity": 0.5,
    "hybrid_weight": 0.7
  }'
```

**请求参数**：
- `query` (必填): 搜索查询文本
- `limit`: 返回数量，默认 10
- `min_similarity`: 最小相似度阈值，默认 0.5
- `hybrid_weight`: 向量检索权重，默认 0.7（关键词权重为 0.3）

**响应示例**：
```json
{
  "code": 200,
  "message": "success",
  "data": {
    "results": [
      {
        "id": "mem_abc123",
        "content": "今天和老同学在咖啡店见面聊天",
        "similarity": 0.95,
        "vector_score": 0.92,
        "keyword_score": 0.98
      }
    ],
    "count": 1,
    "query": "咖啡店见面"
  }
}
```

#### 自然语言召回

支持自然语言查询，自动提取时间、地点、人物等信息。

```bash
curl -X POST http://localhost:8000/api/v1/memories/recall \
  -H "Content-Type: application/json" \
  -d '{
    "query": "上周在咖啡店和老同学见面",
    "limit": 10,
    "use_parser": true,
    "min_similarity": 0.3
  }'
```

**支持的查询类型**：

1. **时间查询**
   - "上周发生了什么"
   - "最近3天"
   - "昨天"
   - "本周"
   - "本月"

2. **地点查询**
   - "在咖啡店发生了什么"
   - "去图书馆的记忆"

3. **人物查询**
   - "和老同学相关的记忆"
   - "跟朋友见面"

4. **情绪查询**
   - "最近开心的事"
   - "难过的事情"

5. **混合查询**
   - "上周在咖啡店和老同学见面"
   - "最近和老同学的社交活动"

**响应示例**：
```json
{
  "code": 200,
  "message": "success",
  "data": {
    "results": [...],
    "count": 3,
    "parsed_query": {
      "time_range": {
        "start": "2024-01-01T00:00:00",
        "end": "2024-01-07T23:59:59",
        "original_text": "上周"
      },
      "location": "咖啡店",
      "people": ["老同学"],
      "tags": ["社交"],
      "intent": "query_content"
    }
  }
}
```

### 统计分析

#### 统计概览

```bash
curl http://localhost:8000/api/stats
```

**返回信息**：
- 总记忆数量
- 各状态记忆数量
- 按输入类型分类
- 本周/本月记忆数量
- 存储使用情况

#### 时间线统计

```bash
curl "http://localhost:8000/api/stats/timeline?days=30&group_by=day"
```

**查询参数**：
- `days`: 统计最近多少天，默认 30
- `group_by`: 分组方式（day/week/month），默认 day

#### 标签统计

```bash
curl "http://localhost:8000/api/stats/tags?limit=20"
```

#### 地点统计

```bash
curl "http://localhost:8000/api/stats/locations?limit=20"
```

#### 人物统计

```bash
curl "http://localhost:8000/api/stats/people?limit=20"
```

## 错误处理

### 错误响应格式

```json
{
  "code": 404,
  "message": "Memory not found",
  "detail": "Memory with id 'mem_abc123' not found"
}
```

### 常见错误码

- `400`: 请求参数错误
- `404`: 资源不存在
- `422`: 请求验证失败
- `500`: 服务器内部错误

## 性能优化建议

1. **使用向量索引**：数据库已配置 HNSW 索引，加速向量检索
2. **合理设置相似度阈值**：根据实际需求调整 `min_similarity`
3. **分页查询**：使用 `limit` 和 `offset` 避免一次性返回大量数据
4. **批量操作**：使用批量端点减少网络请求

## 测试

运行测试脚本：

```bash
# 端到端测试
./venv/bin/python test_api.py

# API 端点测试
chmod +x test_endpoints.sh
./test_endpoints.sh
```

## 技术栈

- **Web 框架**: FastAPI
- **数据库**: PostgreSQL + pgvector
- **Embedding**: doubao-embedding-vision-251215
- **LLM**: doubao-seed-2-0-pro-260215

## 许可证

MIT License
