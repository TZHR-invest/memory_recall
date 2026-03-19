# Memory Recall 用户指南

> 版本: v1  
> 更新时间: 2026-03-20

## 快速开始

### 1. 环境要求

- Python 3.10+
- PostgreSQL 14+ (with pgvector)
- 虚拟环境

### 2. 安装

```bash
# 克隆项目
cd /home/wbaifan/.openclaw/workspace-ai_tui/projects/memory_recall

# 激活虚拟环境
cd apps/api
source venv/bin/activate

# 安装依赖
pip install -r requirements.txt
```

### 3. 配置

创建 `.env` 文件：

```bash
# 数据库配置
DATABASE_URL=postgresql://user:password@localhost:5432/memory_recall

# 火山引擎 API
VOLC_API_KEY=your_api_key_here
```

### 4. 启动服务

```bash
# 启动 API 服务
python3 -m uvicorn main:app --host 0.0.0.0 --port 8000
```

---

## 基本使用

### 创建记忆

**方式 1: 简单创建**

```bash
curl -X POST http://192.168.0.206:8000/api/v1/memories \
  -H "Content-Type: application/json" \
  -d '{
    "content": "今天和张三在咖啡店聊天",
    "input_type": "text"
  }'
```

**方式 2: 带图谱创建（推荐）**

```bash
curl -X POST http://192.168.0.206:8000/api/v1/memories/with-graph \
  -H "Content-Type: application/json" \
  -d '{
    "content": "今天和张三在咖啡店聊天，讨论了机器学习项目",
    "user_id": "my_user_id",
    "enable_graph": true
  }'
```

### 搜索记忆

**语义搜索**

```bash
curl -X POST http://192.168.0.206:8000/api/v1/memories/search \
  -H "Content-Type: application/json" \
  -d '{
    "query": "和朋友在咖啡店",
    "limit": 5
  }'
```

**自然语言召回**

```bash
curl -X POST http://192.168.0.206:8000/api/v1/memories/recall \
  -H "Content-Type: application/json" \
  -d '{
    "query": "最近在咖啡店发生了什么",
    "detail_level": "medium"
  }'
```

### 查询图谱

```bash
curl -X GET "http://192.168.0.206:8000/api/v1/graph/entities?user_id=my_user_id&entity_name=张三"
```

---

## 功能说明

### 1. 知识图谱

系统会自动从记忆内容中提取实体和关系：

- **实体类型**: person（人物）、location（地点）、topic（话题）、time（时间）等
- **关系类型**: met_at（见面地点）、friend（朋友）、discussed（讨论）等

示例：

```json
{
  "entities": [
    {"entity": "张三", "entity_type": "person", "confidence": 0.95},
    {"entity": "咖啡店", "entity_type": "location", "confidence": 0.90}
  ],
  "relations": [
    {"source": "张三", "destination": "咖啡店", "relationship": "met_at"}
  ]
}
```

### 2. 智能确认

对于不确定的实体，系统会生成确认请求：

```bash
# 启用智能确认
curl -X POST http://192.168.0.206:8000/api/v1/memories/with-graph \
  -H "Content-Type: application/json" \
  -d '{
    "content": "今天和老王见面",
    "user_id": "my_user_id",
    "enable_graph": true,
    "enable_confirmation": true
  }'
```

### 3. 软过滤

在搜索时，系统会自动扩展查询：

- **人物关系扩展**: "家人" → ["爸爸", "妈妈", "哥哥", "妹妹"]
- **地点归一化**: "星巴克" → "咖啡店"

### 4. Embedding 缓存

系统会缓存相同内容的向量表示，提升性能：

- 缓存命中率目标: > 50%
- 缓存大小: 1000 条

---

## 性能优化

### 1. 并发处理

创建记忆时，系统会并发执行：
- 向量存储（生成 embedding）
- 图谱构建（提取实体和关系）

### 2. 批量处理

批量创建记忆，减少数据库连接：

```python
# 批量创建
result = await memory_service.batch_create_memories(
    contents=["记忆1", "记忆2", "记忆3"],
    user_id="user_123",
    enable_graph=True
)
```

### 3. 数据库索引

优化查询性能的索引：

```sql
-- 实体索引
CREATE INDEX idx_entities_user_name ON entities(user_id, name);

-- 关系索引
CREATE INDEX idx_relations_user_from ON relations(user_id, from_entity_id);

-- 记忆索引
CREATE INDEX idx_memories_user_created ON memories(user_id, created_at DESC);
```

---

## 常见问题

### Q: 如何查看系统状态？

```bash
curl http://192.168.0.206:8000/health
```

### Q: 如何查看 API 文档？

访问 Swagger UI: `http://192.168.0.206:8000/docs`

### Q: 实体提取不准确怎么办？

1. 检查内容是否清晰
2. 启用智能确认（`enable_confirmation: true`）
3. 查看提取的实体和置信度

### Q: 搜索结果不相关怎么办？

1. 调整 `min_similarity` 阈值（降低以获取更多结果）
2. 调整 `hybrid_weight` 参数（增加关键词权重）
3. 使用更具体的查询

---

## 联系支持

- 项目路径: `/home/wbaifan/.openclaw/workspace-ai_tui/projects/memory_recall`
- API 文档: `docs/API_DOCUMENTATION.md`
- 部署文档: `docs/DEPLOYMENT.md`
