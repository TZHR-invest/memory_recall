# 记忆点提取 - 核心改进总结

## 用户需求

**存储 LLM 提取和组织的记忆内容，而不是原文片段。**

---

## 核心差异

### 改进前（原文存储）

```
输入："早上9点在咖啡厅和张三讨论项目，涉及AI功能设计。"
    ↓
存储：
{
  "content": "早上9点在咖啡厅和张三讨论项目，涉及AI功能设计。"  // 原文
  "input_type": "text"
}
```

### 改进后（记忆点存储）

```
输入："早上9点在咖啡厅和张三讨论项目，涉及AI功能设计。"
    ↓
LLM 提取：
{
  "type": "event",
  "content": "在咖啡厅和张三讨论项目的AI功能设计方案",  // 提取的记忆
  "time": {"value": "2026-03-21T09:00:00"},
  "location": {"name": "咖啡厅"},
  "people": [{"name": "张三"}],
  "importance": 0.8
}
    ↓
存储：
{
  "content": "在咖啡厅和张三讨论项目的AI功能设计方案",  // 提取的记忆
  "input_type": "memory_point",
  "memory_point_type": "event",
  "importance_score": 0.8
}
```

---

## Prompt 改进

**关键改动**：

```python
# ❌ 改进前
"content": "完整的内容描述（包含所有上下文）"

# ✅ 改进后
"content": "用简洁清晰的语言描述这个记忆点（不是原文，而是重新组织的描述）"
```

**示例**：

| 原文 | 提取的 content |
|------|---------------|
| "早上9点在咖啡厅和张三讨论项目，涉及AI功能设计。" | "在咖啡厅和张三讨论项目的AI功能设计方案" |
| "路上听了个AI播客很有启发。" | "听AI播客对技术发展产生新思考" |

---

## 实施状态

| 项目 | 状态 | 说明 |
|------|------|------|
| **Prompt 优化** | ✅ 完成 | `unified_processor.py` 已更新 |
| **数据库字段** | ✅ 完成 | 已添加 `memory_point_type`, `summary` |
| **存储逻辑** | ⚠️ 待修复 | `memory_service.py` 需要更新 |

---

## 下一步

修改 `memory_service.py` 中的 `create_memory_with_graph()` 方法：

```python
async def create_memory_with_graph(self, content, user_id, enable_graph=True):
    # 1. 调用 process_long_text() 提取记忆点
    processor = get_unified_processor()
    result = processor.process_long_text(content)
    
    # 2. 存储提取的记忆点（而不是原文）
    segments = result.get("segments", [])
    
    if len(segments) == 1:
        # 单个记忆点
        segment = segments[0]
        memory_id = await self._store_memory_point(segment, user_id, enable_graph)
        
    else:
        # 多个记忆点
        for segment in segments:
            await self._store_memory_point(segment, user_id, enable_graph)
    
    return {"memory_id": memory_id, ...}

async def _store_memory_point(self, segment, user_id, enable_graph):
    """存储单个记忆点"""
    content = segment.get("content")  # ✅ 提取的内容
    point_type = segment.get("type", "event")
    importance = segment.get("importance", 0.5)
    
    # 存储
    await db.execute("""
        INSERT INTO memories (
            id, content, input_type, memory_point_type, importance_score, ...
        ) VALUES ($1, $2, 'memory_point', $3, $4, ...)
    """, ...)
```

---

## 核心原则

**提取 > 原文**：
- LLM 提取的记忆点更简洁、更结构化
- 包含完整的上下文信息
- 独立可理解，不依赖原文

**示例对比**：

| 类型 | 原文（60字）| 提取的记忆（25字）|
|------|-----------|------------------|
| 事件 | "早上9点在咖啡厅和张三讨论项目，涉及AI功能设计。" | "在咖啡厅和张三讨论项目的AI功能设计方案" |
| 学习 | "路上听了个AI播客，讲了一些技术发展趋势，我觉得很有启发。" | "听AI播客对技术发展产生新思考" |

---

## 总结

**核心改进**：存储 LLM 提取的记忆内容，而不是原文。

**优势**：
1. ✅ 更简洁（节省 Token）
2. ✅ 更结构化（便于召回）
3. ✅ 更准确（LLM 理解后的描述）
4. ✅ 更独立（不依赖原文上下文）

**Prompt 已优化，存储逻辑待修复。**
