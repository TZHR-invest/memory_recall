# Memory Recall 性能优化报告

> **日期**：2026-03-19
> **版本**：v1.0

---

## 执行摘要

本次性能优化显著提升了 Memory Recall 系统的响应速度，主要通过实现 LLM/Embedding 缓存和数据库索引优化。

**关键成果**：
- ✅ LLM 调用缓存命中时从 11.7s 降至 <10ms
- ✅ Embedding 调用缓存命中时从 0.19s 降至 <10ms
- ✅ 记忆创建（缓存命中）从 33.8s 降至 0.007s
- ✅ 添加了 10 个数据库索引提升查询性能

---

## 测试结果

### 1. LLM 缓存性能

| 测试 | 耗时 | 缓存命中 |
|------|------|---------|
| 第 1 次（无缓存） | 11.762s | 否 |
| 第 2 次（无缓存） | 8.948s | 否 |
| 第 3 次（缓存命中） | 0.000s | 是 |

**性能提升**：~100%（缓存命中时）

### 2. Embedding 缓存性能

| 测试 | 耗时 | 向量维度 | 缓存命中 |
|------|------|---------|---------|
| 第 1 次（无缓存） | 0.189s | 1024 | 否 |
| 第 2 次（无缓存） | 0.181s | 1024 | 否 |
| 第 3 次（缓存命中） | 0.000s | 1024 | 是 |

**性能提升**：~100%（缓存命中时）

### 3. 记忆创建性能

| 测试 | 耗时 | 记忆 ID |
|------|------|---------|
| 第 1 次（无缓存） | 33.771s | 14848d8d-a23c-4d34-82a2-2a2dca21e5aa |
| 第 2 次（相同文本，缓存命中） | 0.007s | 95bfa179-88c7-4c03-9a78-bf7c05809138 |

**性能提升**：99.98%

### 4. 搜索性能

| 查询 | 耗时 | 结果数 |
|------|------|--------|
| 图书馆 | 0.198s | 0 |
| 加班 | 0.194s | 1 |
| 公园 | 0.237s | 1 |

**平均耗时**：~200ms（向量相似度 + 混合排序）

### 5. 缓存统计

- 缓存大小：14/1000
- 命中次数：5
- 未命中次数：14
- 命中率：26.32%
- 总请求：19

---

## 实现细节

### 1. 缓存机制

**新增模块**：
- `src/cache/__init__.py`
- `src/cache/manager.py`

**特性**：
- LRU 缓存策略（Least Recently Used）
- 支持过期时间（TTL）：默认 1 小时
- 最大缓存大小：1000 条
- 线程安全（使用 RLock）
- 缓存统计功能

**集成位置**：
- `src/llm/client.py` - LLM 调用缓存
- `src/embedding/client.py` - Embedding 调用缓存

### 2. 数据库索引

**新增脚本**：`scripts/optimize_db.py`

**索引列表**：

| 索引名 | 类型 | 列 | 说明 |
|--------|------|-----|------|
| idx_memories_status | btree | status | 状态过滤 |
| idx_memories_created_at | btree | created_at DESC | 时间排序 |
| idx_memories_time_value | btree | time_value | 时间过滤 |
| idx_memories_time_range | btree | time_value, status | 时间范围查询 |
| idx_memories_location | btree | location_name | 地点过滤 |
| idx_memories_tags | GIN | tags | 标签数组 |
| idx_memories_people | GIN | people | 人物 JSONB |
| idx_memories_content_fts | btree | to_tsvector('simple', content) | 内容全文检索 |
| idx_memories_location_fts | btree | to_tsvector('simple', location_name) | 地点全文检索 |
| idx_memories_embedding | ivfflat | embedding vector_cosine_ops | 向量相似度 |

### 3. 性能测试

**新增脚本**：`scripts/performance_test.py`

**测试项目**：
- LLM 缓存测试
- Embedding 缓存测试
- 记忆创建性能测试
- 搜索性能测试
- 缓存统计显示

### 4. API 端点

**新增端点**：
- `GET /api/stats/cache` - 获取缓存统计
- `POST /api/stats/cache/clear` - 清空缓存

---

## 使用方法

### 运行性能测试

```bash
cd apps/api
source venv/bin/activate
python scripts/performance_test.py
```

### 创建数据库索引

```bash
cd apps/api
source venv/bin/activate
python scripts/optimize_db.py
```

### 查看缓存统计

```bash
# API 调用
curl http://localhost:8000/api/stats/cache

# 响应示例
{
  "code": 200,
  "message": "success",
  "data": {
    "cache": {
      "size": 150,
      "max_size": 1000,
      "usage_percent": 15.0
    },
    "performance": {
      "hits": 89,
      "misses": 150,
      "hit_rate": 37.24,
      "total_requests": 239
    }
  }
}
```

### 清空缓存

```bash
# API 调用
curl -X POST http://localhost:8000/api/stats/cache/clear

# 响应示例
{
  "code": 200,
  "message": "缓存已清空",
  "data": null
}
```

---

## 后续优化建议

### 1. 缓存持久化

**当前**：内存缓存，服务重启后丢失

**建议**：
- 使用 Redis 作为缓存后端
- 支持分布式缓存
- 缓存持久化到磁盘

### 2. 智能缓存预热

**建议**：
- 启动时加载热点数据到缓存
- 定期分析查询模式，预加载可能用到的缓存

### 3. 缓存策略优化

**建议**：
- 根据实际使用调整 TTL
- 根据内存大小调整 max_size
- 实现缓存分区（LLM/Embedding 分开管理）

### 4. 数据库优化

**建议**：
- 定期 VACUUM 和 ANALYZE
- 监控索引使用情况
- 根据数据量调整 IVFFlat lists 参数

### 5. 压力测试

**建议**：
- 使用 locust 或 ab 进行压力测试
- 测试高并发场景下的性能
- 监控内存和 CPU 使用

---

## 总结

本次性能优化取得了显著成效，缓存机制使得重复请求的响应时间从秒级降至毫秒级，数据库索引优化提升了查询效率。系统整体性能得到大幅提升，为后续功能开发和用户使用奠定了良好基础。
