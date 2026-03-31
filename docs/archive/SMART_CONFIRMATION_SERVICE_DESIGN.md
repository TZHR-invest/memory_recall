# 阶段 4：智能确认服务设计文档

**创建时间**：2026-03-22 03:21
**状态**：设计完成，待实施
**关联项目**：memory_recall 回归设计文档计划

---

## 1. 设计目标

智能确认服务用于确认实体提取结果，避免错误数据入库，提高数据质量。

**核心功能**：
- 当实体提取结果不确定时，向用户确认
- 用户可以修正、拒绝或接受提取结果
- 支持批量确认和单条确认

---

## 2. 服务架构

### 2.1 核心组件

```
用户输入
    ↓
unified_processor（统一提取）
    ↓
smart_confirmation_service（智能确认服务）
    ↓
├─ 置信度 ≥ 0.8 → 直接入库
└─ 置信度 < 0.8 → 向用户确认
    ↓
用户确认结果
    ↓
修正/拒绝/接受
    ↓
入库存储
```

### 2.2 接口设计

```python
class SmartConfirmationService:
    """智能确认服务"""
    
    async def should_confirm(self, extraction_result: Dict) -> bool:
        """判断是否需要确认
        
        Args:
            extraction_result: 提取结果（包含实体、关系、置信度）
            
        Returns:
            True: 需要确认
            False: 不需要确认（直接入库）
        """
        pass
    
    async def generate_confirmation_request(
        self, 
        extraction_result: Dict
    ) -> Dict:
        """生成确认请求
        
        Args:
            extraction_result: 提取结果
            
        Returns:
            {
                "type": "confirmation_required",
                "entities": [...],  # 待确认的实体
                "relations": [...],  # 待确认的关系
                "message": "请确认以下实体是否正确"
            }
        """
        pass
    
    async def process_user_response(
        self,
        user_response: Dict
    ) -> Dict:
        """处理用户确认响应
        
        Args:
            user_response: 用户确认结果
            {
                "action": "accept" | "reject" | "modify",
                "entities": [...],  # 修正后的实体（如有）
                "relations": [...]  # 修正后的关系（如有）
            }
            
        Returns:
            处理结果
        """
        pass
```

---

## 3. 判断逻辑

### 3.1 置信度计算

```python
def calculate_confidence(extraction_result: Dict) -> float:
    """计算提取结果置信度
    
    考虑因素：
    1. LLM 返回的置信度（如有）
    2. 实体类型一致性
    3. 关系合理性
    4. 时间解析成功率
    """
    confidence = 1.0
    
    # 因素 1：实体类型一致性
    entity_types = [e["type"] for e in extraction_result.get("entities", [])]
    if len(set(entity_types)) > 3:  # 类型过多，降低置信度
        confidence *= 0.8
    
    # 因素 2：关系合理性
    relations = extraction_result.get("relations", [])
    for rel in relations:
        if rel.get("confidence", 1.0) < 0.7:
            confidence *= 0.9
    
    # 因素 3：时间解析成功率
    time_info = extraction_result.get("structured", {}).get("time", {})
    if time_info.get("value") is None:
        confidence *= 0.95  # 时间缺失，略微降低
    
    return confidence
```

### 3.2 确认阈值

| 置信度范围 | 行为 |
|-----------|------|
| ≥ 0.8 | 直接入库，不需要确认 |
| 0.5 - 0.8 | 向用户确认 |
| < 0.5 | 自动拒绝，返回错误 |

---

## 4. 交互流程

### 4.1 确认请求格式

```json
{
  "type": "confirmation_required",
  "memory_id": "temp_xxx",
  "message": "请确认以下实体是否正确：",
  "entities": [
    {
      "name": "张三",
      "type": "人物",
      "confidence": 0.65,
      "suggested_action": "accept"  # accept/reject/modify
    }
  ],
  "relations": [
    {
      "source": "张三",
      "target": "李四",
      "type": "朋友",
      "confidence": 0.72
    }
  ],
  "options": [
    {"label": "全部接受", "action": "accept_all"},
    {"label": "逐条确认", "action": "confirm_each"},
    {"label": "全部拒绝", "action": "reject_all"}
  ]
}
```

### 4.2 用户响应格式

```json
{
  "memory_id": "temp_xxx",
  "action": "modify",
  "entities": [
    {
      "original": {"name": "张三", "type": "人物"},
      "modified": {"name": "张三丰", "type": "人物"}  // 用户修正
    }
  ],
  "relations": [
    {
      "original": {"source": "张三", "target": "李四", "type": "朋友"},
      "action": "accept"  // 用户接受
    }
  ]
}
```

---

## 5. 实施计划

### 5.1 实施步骤

1. **创建服务文件**：`src/services/smart_confirmation_service.py`
2. **实现核心方法**：
   - `should_confirm()` - 判断是否需要确认
   - `generate_confirmation_request()` - 生成确认请求
   - `process_user_response()` - 处理用户响应
3. **集成到创建流程**：
   - 修改 `memory_service.py`，在入库前调用智能确认服务
4. **添加 API 端点**：
   - `POST /api/v1/confirm` - 用户确认端点
5. **前端集成**：
   - 确认请求展示
   - 用户操作交互

### 5.2 预估时间

| 步骤 | 预估时间 |
|------|---------|
| 创建服务文件 | 0.5 天 |
| 实现核心方法 | 1 天 |
| 集成到创建流程 | 0.5 天 |
| 添加 API 端点 | 0.5 天 |
| 前端集成 | 1 天 |
| **总计** | **3.5 天** |

---

## 6. 成功标准

- 确认请求生成成功率：≥ 95%
- 用户响应处理成功率：≥ 99%
- 数据质量提升：错误入库率降低 50%+
- 用户满意度：确认流程流畅、不繁琐

---

## 7. 风险与挑战

### 7.1 风险点

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| 用户确认负担 | 交互繁琐 | 设置合理阈值，减少不必要确认 |
| 置信度计算不准 | 误判确认需求 | 多因素综合判断，持续优化 |
| 前端交互复杂 | 开发成本高 | 先实现简单版本，逐步优化 |

### 7.2 降级方案

如果用户长时间未响应确认请求：
- 超时 5 分钟：自动接受（置信度 ≥ 0.6）或拒绝（置信度 < 0.6）
- 超时 30 分钟：自动拒绝，删除临时数据

---

## 8. 与其他组件关系

- **统一处理器（unified_processor）**：智能确认服务接收提取结果
- **记忆服务（memory_service）**：智能确认服务在入库前介入
- **图谱构建（graph_builder_service）**：确认后的实体和关系传递给图谱构建

---

**下一步**：实施阶段 5 - 软过滤服务

---

*设计者：颓弟*
*设计时间：2026-03-22 03:21*
