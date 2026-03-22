# 多关系解析功能文档

## 功能概述

增强智能关系解析，支持从一句话中解析出多个实体关系。

## 背景

### 之前的问题

用户输入一句话可能包含多个关系，但之前的实现只能解析一个关系。

**示例：**

输入："老张就是我的大学室友张三"

期望识别：
- 关系1：老张 same_as 张三
- 关系2：张三 related_to 大学室友

之前的实现只能识别其中一个关系。

### 解决方案

修改 LLM prompt 和解析逻辑，使其能够识别并返回多个关系。

## 技术实现

### 1. 修改 LLM Prompt

**之前：**
```python
prompt = f"""用户输入："{text}"

请从这句话中提取实体关系，返回 JSON 格式：
{{
    "entity1": "实体1名称",
    "entity2": "实体2名称",
    "relation_type": "关系类型",
    ...
}}
"""
```

**现在：**
```python
prompt = f"""用户输入："{text}"

请从这句话中提取所有实体关系，返回 JSON 数组格式：
[
    {{
        "entity1": "实体1名称",
        "entity2": "实体2名称",
        "relation_type": "关系类型",
        ...
    }},
    ...
]

注意：
1. 一句话可能包含多个关系，请全部提取
2. 只返回 JSON 数组，不要其他说明
"""
```

### 2. 修改解析方法

**方法签名变更：**

```python
# 之前：返回单个关系
async def parse_relation_from_text(self, text: str) -> Dict[str, Any]

# 现在：返回关系列表
async def parse_relation_from_text(self, text: str) -> List[Dict[str, Any]]
```

**解析逻辑：**

```python
async def parse_relation_from_text(self, text: str) -> List[Dict[str, Any]]:
    """从自然语言文本中解析实体关系（支持多个关系）"""
    
    # 调用 LLM
    parsed = llm_client.extract_json(prompt, ...)
    
    # 确保返回的是列表
    if isinstance(parsed, dict):
        # 如果是单个关系对象，转换为列表
        if "error" in parsed:
            return [parsed]
        parsed = [parsed]
    
    # 验证每个关系的必要字段
    validated_relations = []
    for relation in parsed:
        if "error" in relation:
            continue
        
        required_fields = ["entity1", "entity2", "relation_type"]
        if all(field in relation for field in required_fields):
            # 确保置信度在有效范围内
            if "confidence" not in relation:
                relation["confidence"] = 0.8
            else:
                relation["confidence"] = max(0.0, min(1.0, float(relation["confidence"])))
            validated_relations.append(relation)
    
    return validated_relations if validated_relations else [{"error": "未提取到有效关系"}]
```

### 3. 新增批量创建方法

```python
async def create_relations_from_parsed(
    self,
    parsed_list: List[Dict[str, Any]],
    user_id: str
) -> Dict[str, Any]:
    """根据解析结果创建多个关系
    
    Returns:
        {
            "created": [...],  # 成功创建的关系列表
            "failed": [...],   # 创建失败的关系列表
            "total": int,      # 总数
            "success_count": int  # 成功数量
        }
    """
    created = []
    failed = []
    
    for parsed in parsed_list:
        # 跳过包含错误的关系
        if parsed.get("error"):
            failed.append({**parsed, "error": parsed["error"]})
            continue
        
        # 验证必要字段
        entity1 = parsed.get("entity1")
        entity2 = parsed.get("entity2")
        relation_type = parsed.get("relation_type")
        
        if not all([entity1, entity2, relation_type]):
            failed.append({
                **parsed,
                "error": "缺少必要字段：entity1、entity2 或 relation_type"
            })
            continue
        
        # 创建实体和关系
        try:
            e1_id = await self._upsert_entity(entity1, ...)
            e2_id = await self._upsert_entity(entity2, ...)
            success = await self._upsert_relation(e1_id, e2_id, ...)
            
            if success:
                created.append({**parsed, "entity1_id": e1_id, "entity2_id": e2_id})
            else:
                failed.append({**parsed, "error": "创建关系失败"})
        except Exception as e:
            failed.append({**parsed, "error": str(e)})
    
    # 刷新实体词典
    if created:
        await self.entity_dict.refresh()
    
    return {
        "created": created,
        "failed": failed,
        "total": len(parsed_list),
        "success_count": len(created)
    }
```

### 4. 修改 API 接口

**之前：**
```python
@router.post("/api/v1/graph/add-relation-by-text")
async def add_relation_by_text(request: AddRelationByTextRequest):
    # 1. 解析单个关系
    parsed = await builder_service.parse_relation_from_text(request.text)
    
    # 2. 创建单个关系
    result = await builder_service.create_relation_from_parsed(parsed, user_id)
    
    return {
        "success": True,
        "relation": parsed,  # 单个关系
        "message": "已创建关系"
    }
```

**现在：**
```python
@router.post("/api/v1/graph/add-relation-by-text")
async def add_relation_by_text(request: AddRelationByTextRequest):
    # 1. 解析多个关系
    relations = await builder_service.parse_relation_from_text(request.text)
    
    # 2. 过滤低置信度的关系
    valid_relations = [
        r for r in relations
        if not r.get("error") and r.get("confidence", 0) >= 0.7
    ]
    
    # 3. 批量创建关系
    result = await builder_service.create_relations_from_parsed(valid_relations, user_id)
    
    return {
        "success": True,
        "relations": result["created"],  # 多个关系
        "created_count": result["success_count"],
        "message": f"已创建 {result['success_count']} 个关系"
    }
```

## API 变更

### 请求

```http
POST /api/v1/graph/add-relation-by-text
Content-Type: application/json

{
    "text": "老张就是我的大学室友张三",
    "user_id": "user_123"
}
```

### 响应

**之前（单个关系）：**
```json
{
    "success": true,
    "relation": {
        "entity1": "老张",
        "entity2": "张三",
        "relation_type": "same_as",
        "confidence": 0.9
    },
    "message": "已创建关系：老张 same_as 张三"
}
```

**现在（多个关系）：**
```json
{
    "success": true,
    "relations": [
        {
            "entity1": "老张",
            "entity2": "张三",
            "relation_type": "same_as",
            "confidence": 0.9
        },
        {
            "entity1": "张三",
            "entity2": "大学室友",
            "relation_type": "related_to",
            "confidence": 0.8
        }
    ],
    "created_count": 2,
    "message": "已创建 2 个关系：老张 same_as 张三、张三 related_to 大学室友"
}
```

## 测试用例

### 测试1：包含多个关系

**输入：** "老张就是我的大学室友张三"

**期望输出：**
```json
[
    {"entity1": "老张", "entity2": "张三", "relation_type": "same_as", "confidence": 0.9},
    {"entity1": "张三", "entity2": "大学室友", "relation_type": "related_to", "confidence": 0.8}
]
```

### 测试2：包含多个关系（复杂场景）

**输入：** "我老婆小红是我同事李四的表妹"

**期望输出：**
```json
[
    {"entity1": "小红", "entity2": "老婆", "relation_type": "family", "confidence": 0.9},
    {"entity1": "李四", "entity2": "同事", "relation_type": "colleague", "confidence": 0.9},
    {"entity1": "小红", "entity2": "李四", "relation_type": "family", "confidence": 0.85}
]
```

### 测试3：单个关系

**输入：** "星巴克是咖啡店"

**期望输出：**
```json
[
    {"entity1": "星巴克", "entity2": "咖啡店", "relation_type": "is_a", "confidence": 0.9}
]
```

### 测试4：无关系

**输入：** "今天天气不错"

**期望输出：**
```json
[
    {"error": "未提取到有效关系"}
]
```

## 向后兼容

### 单个关系创建

`create_relation_from_parsed` 方法保持向后兼容：

```python
async def create_relation_from_parsed(
    self,
    parsed: Dict[str, Any],
    user_id: str
) -> Dict[str, Any]:
    """根据解析结果创建关系（支持单个关系，向后兼容）"""
    
    # 将单个关系包装成列表，调用批量创建方法
    results = await self.create_relations_from_parsed([parsed], user_id)
    
    # 返回单个关系的结果格式
    if results["success_count"] > 0:
        return {
            "success": True,
            "entity1_id": results["created"][0].get("entity1_id"),
            "entity2_id": results["created"][0].get("entity2_id"),
            "relation_type": results["created"][0].get("relation_type")
        }
    else:
        return {
            "success": False,
            "error": results["failed"][0].get("error", "创建关系失败")
        }
```

## 修改的文件

1. `projects/memory_recall/apps/api/src/services/graph_builder_service.py`
   - 修改 `parse_relation_from_text` 方法：返回 `List[Dict]` 而非 `Dict`
   - 新增 `create_relations_from_parsed` 方法：批量创建关系
   - 保留 `create_relation_from_parsed` 方法：向后兼容

2. `projects/memory_recall/apps/api/src/routes/graph.py`
   - 修改 `/api/v1/graph/add-relation-by-text` 接口：支持多个关系
   - 返回 `relations` 数组而非单个 `relation` 对象
   - 添加 `created_count` 字段

3. 测试文件
   - `projects/memory_recall/apps/api/test_multi_relation_unit.py`：单元测试

## 部署注意事项

1. **数据库迁移**：无需修改数据库 schema
2. **API 兼容性**：响应格式变更，需要前端适配
3. **LLM 提示词**：已更新，需要验证 LLM 是否正确返回 JSON 数组

## 未来优化

1. **性能优化**：并发创建多个关系
2. **错误处理**：更详细的错误分类和提示
3. **关系去重**：避免创建重复关系
4. **置信度调优**：根据实际情况调整置信度阈值

## 更新日期

2026-03-20
