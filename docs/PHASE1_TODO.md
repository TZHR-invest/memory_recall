# Phase 1 待完成项清单

**生成时间**: 2026-03-19 11:45
**基于验证结果**: 86.4% 通过率（19/22 项）

---

## 🔴 高优先级（需立即修复）

### 1. 修复召回功能 ⚠️

**问题**：部分查询返回空结果

**表现**：
- API 端点 `/api/v1/memories/recall` 在某些查询下返回空结果
- 查询"老同学"返回 0 条记忆，但向量检索实际找到 5 条

**原因分析**：
- `min_similarity` 默认参数可能过高（0.3）
- 混合检索算法可能需要调整权重

**解决方案**：
```python
# 1. 降低默认相似度阈值
min_similarity = 0.1  # 从 0.3 降低到 0.1

# 2. 改进混合检索算法
hybrid_weight = 0.8  # 提高向量权重

# 3. 添加调试日志
logger.debug(f"向量检索结果: {len(vector_results)}")
logger.debug(f"关键词检索结果: {len(keyword_results)}")
logger.debug(f"混合排序结果: {len(results)}")
```

**验证方法**：
```bash
curl -X POST http://localhost:8000/api/v1/memories/recall \
  -H "Content-Type: application/json" \
  -d '{"query": "老同学", "limit": 5, "min_similarity": 0.1}'
```

**预计耗时**: 30 分钟

---

### 2. 修复统计 API ⚠️

**问题**：`/api/stats` 返回数据库错误

**错误信息**：
```
column "memories.embedding" must appear in the GROUP BY clause or be used in an aggregate function
```

**原因**：SQL 查询中 GROUP BY 语句缺少 embedding 列

**解决方案**：
```python
# 修改 src/routes/health.py 或相关统计 API
# 方案 1: 排除 embedding 列
query = """
SELECT COUNT(*) as total_memories,
       COUNT(DISTINCT location) as unique_locations
FROM memories
WHERE status = 'active'
"""

# 方案 2: 使用子查询
query = """
SELECT (SELECT COUNT(*) FROM memories WHERE status = 'active') as total_memories,
       (SELECT COUNT(DISTINCT location) FROM memories WHERE status = 'active') as unique_locations
"""
```

**验证方法**：
```bash
curl http://localhost:8000/api/stats
```

**预计耗时**: 15 分钟

---

### 3. 启动 Web 前端 ⚠️

**问题**：Web 前端代码已完成但未启动

**启动方式**：
```bash
cd /home/wbaifan/.openclaw/workspace-ai_tui/projects/memory_recall/web
python3 -m http.server 3000
```

**验证方法**：
```bash
curl http://localhost:3000
```

**访问地址**：
- 前端：http://localhost:3000
- API：http://localhost:8000

**预计耗时**: 5 分钟

---

## 🟡 中优先级（建议完成）

### 4. 优化向量检索性能

**当前性能**：~200ms
**目标性能**：< 100ms

**优化方案**：
1. 调整 IVFFlat 索引参数
```sql
-- 调整列表数
DROP INDEX IF EXISTS idx_memories_embedding;
CREATE INDEX idx_memories_embedding ON memories
USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);  -- 根据数据量调整
```

2. 使用预计算
```python
# 缓存常用查询的向量
query_cache = {
    "老同学": embedding_vector,
    "开心的事": embedding_vector,
}
```

**预计耗时**: 1-2 小时

---

### 5. 增强自然语言查询

**目标**：支持更复杂的时间表达式

**待支持的表达式**：
- "前天发生了什么"
- "上个月的第一周"
- "去年这个时候"
- "三个月前"

**实现方案**：
```python
# 扩展 src/services/query_parser.py
time_patterns = {
    r"前天": lambda: datetime.now() - timedelta(days=2),
    r"上个月的第一周": lambda: get_first_week_of_last_month(),
    r"去年这个时候": lambda: datetime.now() - timedelta(days=365),
}
```

**预计耗时**: 2-3 小时

---

### 6. 完善测试用例

**目标**：
- 单元测试覆盖率 > 80%
- 集成测试
- 性能测试

**测试文件**：
```
tests/
├── test_api/
│   ├── test_memories.py
│   ├── test_recall.py
│   └── test_stats.py
├── test_services/
│   ├── test_memory_service.py
│   ├── test_recall_service.py
│   └── test_embedding.py
└── test_performance/
    └── test_search_performance.py
```

**预计耗时**: 4-6 小时

---

## 🟢 低优先级（可选）

### 7. 文档完善

**待完善文档**：
- API 使用示例
- 部署文档
- 开发者指南

**预计耗时**: 2-3 小时

---

### 8. 性能监控

**目标**：
- 添加日志
- 性能指标收集
- 告警机制

**实现方案**：
```python
import logging
from prometheus_client import Counter, Histogram

# 日志
logging.basicConfig(level=logging.INFO)

# 性能指标
search_latency = Histogram('search_latency_seconds', 'Search latency')
memory_count = Counter('memory_total', 'Total memories created')
```

**预计耗时**: 3-4 小时

---

## 📊 完成时间估算

| 优先级 | 任务数 | 预计总耗时 |
|--------|--------|-----------|
| 🔴 高 | 3 项 | ~1 小时 |
| 🟡 中 | 3 项 | ~8-12 小时 |
| 🟢 低 | 2 项 | ~5-7 小时 |
| **总计** | **8 项** | **~14-20 小时** |

---

## 🎯 建议执行顺序

### 第一阶段（立即执行，~1 小时）
1. ✅ 启动 Web 前端（5 分钟）
2. ✅ 修复统计 API（15 分钟）
3. ✅ 修复召回功能（30 分钟）
4. ✅ 完整验证（10 分钟）

### 第二阶段（后续优化，~10 小时）
1. 优化向量检索性能
2. 增强自然语言查询
3. 完善测试用例

### 第三阶段（可选改进，~5 小时）
1. 文档完善
2. 性能监控

---

## 📝 下一步行动

1. **立即执行**：修复高优先级问题（~1 小时）
2. **验证通过后**：更新开发计划文档
3. **继续开发**：Phase 2 多模态功能

---

**负责人**: AI Agent（颓弟）
**生成时间**: 2026-03-19 11:45
