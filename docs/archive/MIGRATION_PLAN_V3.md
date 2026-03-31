# 回归设计文档实施计划

> 目标：从当前实现逐步迁移到 MEMORY_NETWORK_DESIGN_V3.md 设计
> 策略：渐进式迁移，每个阶段都可独立验证和回退
> 时间：2-3 周

---

## 📊 偏离度分析

| 功能模块 | 设计文档 | 当前实现 | 偏离度 | 优先级 |
|---------|---------|---------|--------|--------|
| Function Calling | 使用 tools 参数 | Prompt + JSON | 100% | P0 |
| 智能更新逻辑 | ADD/UPDATE/DELETE/NONE | 无 | 100% | P1 |
| Prompt 工程 | 区分用户/Agent，Few-shot | 单一 Prompt | 70% | P1 |
| 智能确认服务 | 飞书消息卡片确认 | 未实现 | 100% | P2 |
| 软过滤服务 | 权重提升，关系扩展 | 未实现 | 100% | P2 |
| PostgreSQL 存储 | 已实现 | ✅ 已实现 | 0% | ✅ |

---

## 🗓️ 实施时间线

```
Week 1：
  Day 1-2：阶段 1 - Function Calling 基础设施
  Day 3-4：阶段 2 - 智能更新逻辑（核心）
  Day 5：阶段 3 - Prompt 工程优化

Week 2：
  Day 1-2：阶段 4 - 智能确认服务
  Day 3-4：阶段 5 - 软过滤服务
  Day 5：阶段 6 - 清理旧代码 + 测试

Week 3（可选）：
  Day 1-3：性能优化 + 文档完善
```

---

## 📋 分阶段详细方案

### 阶段 1：Function Calling 基础设施（2-3 天）

**目标**：添加 Function Calling 支持，但不破坏现有功能

**工作内容**：

1. **创建工具定义文件**（已完成）
   - 文件：`src/services/graph_tools.py`
   - 内容：5 个工具定义（提取实体、建立关系、添加记忆、更新记忆、无操作）

2. **扩展 LLM 客户端**
   - 文件：`src/llm/client.py`
   - 新增方法：`call_with_tools(messages, tools, tool_choice="auto")`
   - 返回：工具调用结果或文本响应

3. **创建新的处理器**
   - 文件：`src/processors/function_calling_processor.py`
   - 方法：
     - `extract_entities_with_fc(text)` - 使用 Function Calling 提取实体
     - `extract_relations_with_fc(text, entities)` - 使用 Function Calling 提取关系

4. **并行运行（A/B 测试）**
   - 保留现有的 `unified_processor.py`
   - 新增配置项：`USE_FUNCTION_CALLING=true/false`
   - 默认：`false`（使用现有逻辑）
   - 测试通过后切换为 `true`

**验证方法**：
```python
# 测试脚本
test_cases = [
    "今天下午和张三在咖啡厅讨论项目进展",
    "上周五完成了数据库设计工作",
    "决定采用 JWT+Refresh Token 的技术架构"
]

# 对比结果
for text in test_cases:
    # 旧方法
    old_result = unified_processor.process_long_text(text)
    
    # 新方法
    new_result = fc_processor.extract_entities_with_fc(text)
    
    # 对比准确率、耗时
```

**回退策略**：
- 配置项 `USE_FUNCTION_CALLING=false`
- 旧代码保留，不删除

**完成标准**：
- ✅ Function Calling 可用
- ✅ 实体提取准确率 ≥ 90%
- ✅ 可随时切换回旧逻辑

---

### 阶段 2：智能更新逻辑（2-3 天，核心）

**目标**：实现 ADD/UPDATE/DELETE/NONE 逻辑

**工作内容**：

1. **创建 Prompt 模板文件**
   - 文件：`src/services/memory_prompts.py`
   - 内容：
     - `USER_MEMORY_EXTRACTION_PROMPT`（用户记忆提取）
     - `AGENT_MEMORY_EXTRACTION_PROMPT`（Agent 记忆提取）
     - `MEMORY_UPDATE_PROMPT`（智能更新）

2. **实现智能更新服务**
   - 文件：`src/services/memory_update_service.py`
   - 方法：
     - `should_add(entity, existing_entities)` - 判断是否添加
     - `should_update(new_entity, existing_entity)` - 判断是否更新
     - `should_delete(new_fact, existing_memory)` - 判断是否删除
     - `update_memory(old_memories, new_facts)` - 智能更新

3. **集成到图谱构建流程**
   - 修改：`graph_builder_service.py`
   - 流程：
     ```
     提取实体/关系
         ↓
     查询现有图谱
         ↓
     LLM 判断 ADD/UPDATE/DELETE/NONE
         ↓
     执行对应操作
     ```

**验证方法**：
```python
# 测试智能更新
old_memories = [
    {"id": "0", "text": "喜欢奶酪披萨"}
]
new_facts = ["喜欢鸡肉披萨"]

result = update_service.update_memory(old_memories, new_facts)

# 期望结果：
# {"id": "0", "text": "喜欢奶酪和鸡肉披萨", "event": "UPDATE"}
```

**回退策略**：
- 配置项 `USE_SMART_UPDATE=false`
- 跳过智能更新，直接插入

**完成标准**：
- ✅ ADD/UPDATE/DELETE/NONE 逻辑可用
- ✅ 更新准确率 ≥ 85%
- ✅ 避免重复记忆

---

### 阶段 3：Prompt 工程优化（1-2 天）

**目标**：优化 Prompt，提高提取质量

**工作内容**：

1. **添加 Few-shot 示例**
   - 修改：`memory_prompts.py`
   - 添加：10-20 个示例（覆盖各种场景）

2. **区分用户记忆和 Agent 记忆**
   - 新增方法：`extract_user_memory()`, `extract_agent_memory()`
   - 只从特定角色的消息中提取

3. **添加当前日期**
   - 已实现（修复时间推断问题）
   - 保留现有逻辑

**验证方法**：
```python
# 对比 Few-shot 前后的提取质量
test_cases = [...]

# 无 Few-shot
result_without = extract_without_few_shot(test_cases)

# 有 Few-shot
result_with = extract_with_few_shot(test_cases)

# 对比准确率
```

**完成标准**：
- ✅ Few-shot 示例添加
- ✅ 提取准确率提升 5-10%
- ✅ Prompt 长度 < 2000 字符

---

### 阶段 4：智能确认服务（2-3 天）

**目标**：实现飞书消息卡片确认

**工作内容**：

1. **创建确认服务**
   - 文件：`src/services/confirmation_service.py`
   - 方法：
     - `should_confirm(entity, relations, existing)` - 判断是否需要确认
     - `send_confirmation(user_id, confirmation)` - 发送确认请求
     - `handle_response(confirmation_id, response)` - 处理用户回复

2. **实现飞书消息卡片**
   - 文件：`src/integrations/feishu_card.py`
   - 内容：确认卡片的 JSON 模板

3. **创建确认队列**
   - 数据库表：`confirmations`
   - 字段：`id, user_id, type, data, status, created_at`

**验证方法**：
```python
# 测试确认触发
entity = {"entity": "张三", "entity_type": "person", "confidence": 0.7}
existing = []

confirmation = confirmation_service.should_confirm(entity, [], existing)

# 期望：返回确认请求（置信度 < 0.8）
```

**完成标准**：
- ✅ 确认逻辑可用
- ✅ 飞书卡片发送成功
- ✅ 用户可回复确认/修改/跳过

---

### 阶段 5：软过滤服务（2-3 天）

**目标**：实现权重提升和关系扩展

**工作内容**：

1. **创建软过滤服务**
   - 文件：`src/services/soft_filter_service.py`
   - 方法：
     - `apply_soft_filter(results, location, person)` - 应用软过滤
     - `_expand_person_relation(person)` - 关系扩展

2. **定义扩展映射**
   - 文件：`src/config/expansion_maps.py`
   - 内容：
     - `PERSON_RELATION_EXPANSION`（家人→老婆/老公/孩子...）
     - `LOCATION_NORMALIZATION`（星巴克→咖啡店...）

3. **集成到召回流程**
   - 修改：`recall_service.py`
   - 在向量召回后应用软过滤

**验证方法**：
```python
# 测试关系扩展
results = [...]
location_filter = "咖啡店"
person_filter = "家人"

filtered = soft_filter.apply_soft_filter(results, location_filter, person_filter)

# 期望：
# - 匹配的结果权重提升 0.1-0.15
# - "家人" 扩展为 ["老婆", "老公", "孩子", ...]
```

**完成标准**：
- ✅ 软过滤可用
- ✅ 权重提升合理（0.05-0.15）
- ✅ 关系扩展准确

---

### 阶段 6：清理旧代码（1 天）

**目标**：删除不再使用的代码

**工作内容**：

1. **删除旧的处理器**
   - 文件：`unified_processor.py`（保留作为备份）
   - 重命名为：`unified_processor_legacy.py`

2. **更新配置**
   - 移除：`USE_FUNCTION_CALLING`（默认使用新逻辑）
   - 移除：`USE_SMART_UPDATE`

3. **更新文档**
   - README.md
   - API 文档

**完成标准**：
- ✅ 旧代码移至 `legacy/` 目录
- ✅ 文档更新
- ✅ 所有测试通过

---

## 🎯 验证计划

### 功能验证

每个阶段完成后，运行以下验证：

```bash
# 1. 单元测试
pytest tests/

# 2. 集成测试
python3 tests/test_integration.py

# 3. 端到端测试
python3 tests/test_e2e.py
```

### 性能验证

```python
# 对比新旧实现的性能
metrics = {
    "实体提取准确率": [],
    "关系推理准确率": [],
    "提取耗时": [],
    "格式稳定性": []
}
```

### 用户验证

- 部署到测试环境
- 邀请 2-3 位用户试用
- 收集反馈

---

## ⚠️ 风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| **Function Calling 不稳定** | 高 | A/B 测试，可随时回退 |
| **智能更新逻辑错误** | 中 | 人工审核机制 |
| **性能下降** | 中 | 性能测试，优化 Prompt 长度 |
| **用户不接受确认** | 低 | 配置项关闭确认 |

---

## 📈 成功标准

### 功能标准

| 指标 | 当前 | 目标 | 验证方法 |
|------|------|------|---------|
| **实体提取准确率** | 85% | **95%+** | 人工标注测试集 |
| **关系推理准确率** | 80% | **90%+** | 人工标注测试集 |
| **格式稳定性** | 90% | **99%+** | Function Calling |
| **重复记忆率** | 20% | **<5%** | 智能更新 |

### 性能标准

| 指标 | 当前 | 目标 |
|------|------|------|
| **记忆提取耗时** | 30-60s | **<30s** |
| **图谱构建耗时** | 5-10s | **<5s** |
| **召回延迟** | 2-3s | **<2s** |

---

## 🚀 下一步行动

### 立即开始（明天）

1. ✅ **阶段 0 完成**：确认火山引擎支持 Function Calling
2. ⏭️ **阶段 1 开始**：扩展 LLM 客户端，添加 `call_with_tools` 方法

### 本周目标

- 完成阶段 1：Function Calling 基础设施
- 开始阶段 2：智能更新逻辑

### 需要决策

1. **是否并行运行**：新旧逻辑并行运行多久？（建议：2-3 天）
2. **确认机制**：是否立即实现飞书卡片？（建议：阶段 4）
3. **测试数据**：是否需要准备标注数据集？（建议：准备 50-100 条）

---

## 📝 备注

- 每个阶段都可独立部署和回退
- 优先保证功能可用，性能优化次之
- 保持与设计文档的一致性
- 定期向用户汇报进展

**准备好开始实施了吗？**
