# 实体归一化功能使用指南

## 概述

实体归一化功能通过图谱关系实现了：
- **地点归一化**：自动识别地点类型（星巴克 → 咖啡店）
- **人物归一化**：智能询问确认人物关系（老张 = 张三）
- **关系扩展**：查询时自动扩展归一化关系

---

## 快速开始

### 1. 地点归一化（自动）

**原理**：系统预定义了常见地点的归一化映射

**示例**：
```python
# 用户输入
"昨天在星巴克和小李见面"

# 系统自动创建
星巴克 is_a 咖啡店  # user_id='system'

# 查询时
查询: "咖啡店"
召回: 包含"星巴克"的记忆
```

**支持的地点映射**：
```
星巴克 → 咖啡店
瑞幸 → 咖啡店
肯德基 → 快餐店
麦当劳 → 快餐店
海底捞 → 火锅店
万达 → 商场
颐和园 → 公园
腾讯 → 公司
...
```

### 2. 人物归一化（智能询问）

**原理**：使用相似度匹配，询问用户确认

**示例**：
```python
# 第一次输入
"和张三吃饭"

# 第二次输入
"老张请客"

# 系统判断
"老张" 与 "张三" 相似度 = 0.75 > 0.6
→ 返回确认请求

# 用户确认后创建
老张 same_as 张三  # user_id='system'

# 查询时
查询: "老张"
召回: 包含"张三"的记忆
```

### 3. 使用 API 确认归一化关系

**API 端点**：
```
POST /api/v1/graph/confirm-normalization
```

**请求示例**：
```bash
curl -X POST http://localhost:8000/api/v1/graph/confirm-normalization \
  -H "Content-Type: application/json" \
  -d '{
    "entity1": "老张",
    "entity2": "张三",
    "relation_type": "same_as",
    "user_id": "user_123"
  }'
```

**响应**：
```json
{
  "success": true,
  "message": "已创建归一化关系: 老张 same_as 张三",
  "entity1": "老张",
  "entity2": "张三",
  "relation_type": "same_as"
}
```

---

## 关系类型说明

| 关系类型 | 说明 | 示例 |
|---------|------|------|
| `same_as` | 同一实体 | 老张 same_as 张三 |
| `is_a` | 归属类型 | 星巴克 is_a 咖啡店 |

---

## 图谱召回流程

```
查询: "咖啡店"
    ↓
1. 实体提取: ["咖啡店"]
    ↓
2. 归一化关系扩展: ["咖啡店", "星巴克", "瑞幸", ...]
    ↓
3. 查询相关记忆
    ↓
4. 返回结果（包含"星巴克"的记忆）
```

---

## 自定义归一化规则

### 方法 1：修改代码

编辑 `apps/api/src/services/graph_builder_service.py`：

```python
self.location_normalization = {
    # 添加你的规则
    "你的地点": "归一化类型",
    ...
}
```

### 方法 2：使用 API

```bash
# 创建自定义归一化关系
curl -X POST http://localhost:8000/api/v1/graph/confirm-normalization \
  -H "Content-Type: application/json" \
  -d '{
    "entity1": "你的地点",
    "entity2": "归一化类型",
    "relation_type": "is_a",
    "user_id": "system"
  }'
```

---

## 测试验证

运行测试脚本：
```bash
cd projects/memory_recall/apps/api
source venv/bin/activate
python scripts/test_normalization_minimal.py
```

---

## 常见问题

### Q: 为什么人物归一化需要确认？
A: 人物名称相似度匹配可能误识别，需要用户确认避免错误归一化。

### Q: 归一化关系存储在哪里？
A: 存储在 `relations` 表中，`user_id='system'` 表示系统级共享关系。

### Q: 如何查看已有的归一化关系？
A: 查询数据库：
```sql
SELECT 
    e1.name as source,
    r.relation_type,
    e2.name as target
FROM relations r
JOIN entities e1 ON r.from_entity_id = e1.id
JOIN entities e2 ON r.to_entity_id = e2.id
WHERE r.user_id = 'system'
AND r.relation_type IN ('same_as', 'is_a');
```

### Q: 如何删除归一化关系？
A: 直接在数据库中删除：
```sql
DELETE FROM relations 
WHERE user_id = 'system' 
AND relation_type IN ('same_as', 'is_a');
```

---

## 技术架构

```
┌─────────────────────────────────────────┐
│         GraphBuilderService             │
│  - 实体提取 + 归一化                     │
│  - 地点归一化（自动）                    │
│  - 人物归一化（智能询问）                │
└─────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────┐
│         GraphRecallService              │
│  - 图谱召回                              │
│  - 归一化关系扩展                        │
│  - 实体扩展查询                          │
└─────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────┐
│         Database (PostgreSQL)           │
│  - entities 表                           │
│  - relations 表（含归一化关系）          │
│  - user_id='system' 共享归一化知识       │
└─────────────────────────────────────────┘
```

---

## 更新日志

**2026-03-20**:
- ✅ 移除软过滤服务
- ✅ 新增 `same_as` 和 `is_a` 关系类型
- ✅ 实现地点归一化（自动）
- ✅ 实现人物归一化（智能询问）
- ✅ 更新图谱召回逻辑
- ✅ 添加确认 API
- ✅ 测试验证通过

---

## 相关文档

- [测试报告](./normalization_test_report_final.md)
- [技术实现](./normalization_test_report.md)

---

**最后更新**: 2026-03-20
