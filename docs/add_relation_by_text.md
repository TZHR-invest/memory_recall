# 通过自然语言添加实体关系

## 功能概述

允许用户通过自然语言输入实体关系，由 LLM 自动解析并导入图谱数据库。

## API 端点

```
POST /api/v1/graph/add-relation-by-text
```

### 请求参数

```json
{
    "text": "老张就是我大学室友张三",
    "user_id": "ou_xxx"
}
```

### 响应示例

#### 成功响应

```json
{
    "success": true,
    "relation": {
        "entity1": "老张",
        "entity2": "张三",
        "relation_type": "same_as",
        "context": "大学室友",
        "confidence": 0.9
    },
    "message": "已创建关系：老张 same_as 张三"
}
```

#### 失败响应

```json
{
    "success": false,
    "message": "无法识别关系，请更明确地描述"
}
```

## 支持的关系类型

| 关系类型 | 说明 | 示例 |
|---------|------|------|
| `same_as` | 同一实体（别名、昵称） | 老张 same_as 张三 |
| `is_a` | 归属类型 | 星巴克 is_a 咖啡店 |
| `related_to` | 相关关系 | 张三 related_to 大学室友 |
| `family` | 家人 | 我老婆叫小红 |
| `friend` | 朋友 | 小明是我的朋友 |
| `colleague` | 同事 | 张三是我同事 |

## 使用示例

### Python

```python
import requests

# 添加关系
response = requests.post(
    "http://localhost:8000/api/v1/graph/add-relation-by-text",
    json={
        "text": "老张就是我大学室友张三",
        "user_id": "user_123"
    }
)

result = response.json()
print(result)
```

### cURL

```bash
curl -X POST http://localhost:8000/api/v1/graph/add-relation-by-text \
  -H "Content-Type: application/json" \
  -d '{
    "text": "老张就是我大学室友张三",
    "user_id": "user_123"
  }'
```

## 测试用例

### 测试 LLM 解析

```bash
# 设置环境变量
export VOLC_API_KEY="your_api_key"
export VOLC_API_BASE="https://ark.cn-beijing.volces.com/api/v3"
export VOLC_LLM_MODEL="doubao-seed-2-0-pro-260215"

# 运行测试
cd projects/memory_recall
source apps/api/venv/bin/activate
python test_standalone_llm.py
```

### 测试 API 端点

```bash
# 启动 API 服务
cd projects/memory_recall/apps/api
python -m uvicorn main:app --reload

# 运行测试
python test_api_endpoint.py
```

## 测试结果

所有测试用例均通过：

✅ "老张就是我大学室友张三" → same_as  
✅ "星巴克是咖啡店" → is_a  
✅ "我老婆叫小红" → family  
✅ "张三是我同事" → colleague  
✅ "这个餐厅叫海底捞" → is_a  

## 实现细节

### 1. LLM 解析

使用 LLM 从自然语言中提取实体关系：

```python
async def parse_relation_from_text(self, text: str) -> Dict[str, Any]:
    """从自然语言文本中解析实体关系"""
    prompt = f"""用户输入："{text}"

请从这句话中提取实体关系，返回 JSON 格式：
{
    "entity1": "实体1名称",
    "entity2": "实体2名称",
    "relation_type": "关系类型",
    "context": "上下文信息（可选）",
    "confidence": 0.9
}
"""
    # 调用 LLM
    parsed = llm_client.extract_json(prompt)
    return parsed
```

### 2. 创建关系

根据解析结果创建实体和关系：

```python
async def create_relation_from_parsed(self, parsed: Dict, user_id: str):
    """根据解析结果创建关系"""
    # 1. 创建或获取实体
    e1_id = await self._upsert_entity(entity1, type1, user_id)
    e2_id = await self._upsert_entity(entity2, type2, user_id)
    
    # 2. 创建关系
    await self._upsert_relation(e1_id, e2_id, relation_type)
```

### 3. 实体类型推断

自动推断实体类型：

```python
def _infer_entity_type(self, entity_name: str, relation_type: str) -> str:
    """推断实体类型"""
    if relation_type in ["family", "friend", "colleague"]:
        return "person"
    elif relation_type == "is_a":
        return "unknown"
    return "unknown"
```

## 注意事项

1. **置信度阈值**：只接受置信度 >= 0.7 的解析结果
2. **自动类型推断**：根据关系类型自动推断实体类型
3. **幂等性**：重复创建相同关系会更新权重，不会重复创建
4. **实体词典**：新实体会自动刷新实体词典

## 后续优化

- [ ] 支持批量输入（一次输入多个关系）
- [ ] 支持关系确认机制（低置信度时询问用户）
- [ ] 支持关系修正（修改已存在的关系）
- [ ] 支持更复杂的关系类型（如多对多关系）
