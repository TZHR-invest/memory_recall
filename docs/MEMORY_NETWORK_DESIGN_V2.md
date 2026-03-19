# 记忆网络构建系统 - 优化设计方案 v2.0

> 版本：v2.0（基于 Mem0 代码分析优化）
> 日期：2026-03-19
> 作者：颓弟 AI Agent

---

## 🎯 优化要点

基于 Mem0 代码分析，我们发现了以下关键设计思路：

### 1. 使用 Function Calling 机制

Mem0 使用 LLM 的 Function Calling（工具调用）来提取实体和关系，而不是直接让 LLM 返回 JSON。

**优势**：
- ✅ 结构化输出，格式稳定
- ✅ 支持复杂操作（ADD/UPDATE/DELETE/NOOP）
- ✅ LLM 更容易理解和执行

### 2. 工具化设计

Mem0 定义了多个工具函数：
- `add_graph_memory`: 添加关系
- `update_graph_memory`: 更新关系
- `delete_graph_memory`: 删除关系
- `extract_entities`: 提取实体
- `establish_relationships`: 建立关系
- `noop`: 无操作

### 3. 并发处理

Mem0 使用 `ThreadPoolExecutor` 并发执行向量存储和图谱操作。

### 4. 多租户隔离

Mem0 使用 `user_id` + `agent_id` + `run_id` 实现多级隔离。

---

## 📐 优化后的架构设计

### 整体架构

```
用户输入记忆
    ↓
┌─────────────────────────────────────────┐
│  Memory Service (统一入口)               │
│                                          │
│  async def add(messages, user_id, ...)  │
└─────────────────────────────────────────┘
    ↓
┌──────────────────────────────────────────┐
│  并发处理层 (ThreadPoolExecutor)          │
│                                          │
│  ┌──────────────┐   ┌─────────────────┐  │
│  │ Vector Store │   │  Graph Builder  │  │
│  │  (异步)      │   │    (异步)       │  │
│  └──────────────┘   └─────────────────┘  │
└──────────────────────────────────────────┘
    ↓                       ↓
┌─────────────┐      ┌──────────────────┐
│ PostgreSQL  │      │  Graph Store     │
│ + pgvector  │      │  (PostgreSQL)    │
└─────────────┘      └──────────────────┘
```

---

## 🔧 核心组件设计

### 1. 工具定义（借鉴 Mem0）

**文件位置**：`apps/api/src/services/graph_tools.py`

```python
"""
图谱工具定义

借鉴 Mem0 的 Function Calling 机制，定义图谱操作工具
"""

# 添加图谱记忆工具
ADD_GRAPH_MEMORY_TOOL = {
    "type": "function",
    "function": {
        "name": "add_graph_memory",
        "description": "添加新的图谱记忆（实体和关系）。创建新的关系，如果实体不存在则自动创建。",
        "parameters": {
            "type": "object",
            "properties": {
                "source": {
                    "type": "string",
                    "description": "源实体名称（如'张三'）"
                },
                "destination": {
                    "type": "string",
                    "description": "目标实体名称（如'咖啡店'）"
                },
                "relationship": {
                    "type": "string",
                    "description": "关系类型（如'met_at', 'friend', 'at'）"
                },
                "source_type": {
                    "type": "string",
                    "description": "源实体类型（person/location/event）",
                    "enum": ["person", "location", "event", "topic", "emotion"]
                },
                "destination_type": {
                    "type": "string",
                    "description": "目标实体类型（person/location/event）",
                    "enum": ["person", "location", "event", "topic", "emotion"]
                },
                "confidence": {
                    "type": "number",
                    "description": "置信度（0-1）",
                    "minimum": 0,
                    "maximum": 1
                }
            },
            "required": ["source", "destination", "relationship", "source_type", "destination_type"]
        }
    }
}

# 更新图谱记忆工具
UPDATE_GRAPH_MEMORY_TOOL = {
    "type": "function",
    "function": {
        "name": "update_graph_memory",
        "description": "更新已有图谱记忆的关系。仅更新关系，不改变源和目标实体。",
        "parameters": {
            "type": "object",
            "properties": {
                "source": {
                    "type": "string",
                    "description": "源实体名称"
                },
                "destination": {
                    "type": "string",
                    "description": "目标实体名称"
                },
                "relationship": {
                    "type": "string",
                    "description": "新的关系类型"
                }
            },
            "required": ["source", "destination", "relationship"]
        }
    }
}

# 删除图谱记忆工具
DELETE_GRAPH_MEMORY_TOOL = {
    "type": "function",
    "function": {
        "name": "delete_graph_memory",
        "description": "删除图谱中的关系。",
        "parameters": {
            "type": "object",
            "properties": {
                "source": {
                    "type": "string",
                    "description": "源实体名称"
                },
                "destination": {
                    "type": "string",
                    "description": "目标实体名称"
                },
                "relationship": {
                    "type": "string",
                    "description": "要删除的关系类型"
                }
            },
            "required": ["source", "destination", "relationship"]
        }
    }
}

# 提取实体工具
EXTRACT_ENTITIES_TOOL = {
    "type": "function",
    "function": {
        "name": "extract_entities",
        "description": "从文本中提取实体及其类型。",
        "parameters": {
            "type": "object",
            "properties": {
                "entities": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "entity": {
                                "type": "string",
                                "description": "实体名称"
                            },
                            "entity_type": {
                                "type": "string",
                                "description": "实体类型",
                                "enum": ["person", "location", "event", "topic", "emotion"]
                            }
                        },
                        "required": ["entity", "entity_type"]
                    },
                    "description": "实体列表"
                }
            },
            "required": ["entities"]
        }
    }
}

# 无操作工具
NOOP_TOOL = {
    "type": "function",
    "function": {
        "name": "noop",
        "description": "无操作。当不需要对图谱进行任何修改时调用。",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": []
        }
    }
}

# 所有工具列表
GRAPH_TOOLS = [
    ADD_GRAPH_MEMORY_TOOL,
    UPDATE_GRAPH_MEMORY_TOOL,
    DELETE_GRAPH_MEMORY_TOOL,
    EXTRACT_ENTITIES_TOOL,
    NOOP_TOOL
]
```

---

### 2. 图谱构建服务（核心）

**文件位置**：`apps/api/src/services/graph_builder_service.py`

```python
"""
图谱构建服务

借鉴 Mem0 的设计：
1. 使用 Function Calling 提取实体和关系
2. 并发处理向量存储和图谱构建
3. 支持多租户隔离
"""

import asyncio
import json
from typing import List, Dict, Any, Optional
from concurrent.futures import ThreadPoolExecutor

from .graph_tools import GRAPH_TOOLS
from .llm_recall_service import LLMRecallService


class GraphBuilderService:
    """图谱构建服务"""
    
    def __init__(self, db_pool):
        self.db_pool = db_pool
        self.llm_service = LLMRecallService()
    
    async def build_graph(
        self,
        content: str,
        user_id: str,
        agent_id: Optional[str] = None,
        run_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        构建图谱
        
        流程：
        1. 使用 LLM Function Calling 提取实体和关系
        2. 存储实体和关系到数据库
        3. 返回构建结果
        """
        
        # 1. 构造 Prompt
        system_prompt = self._build_extraction_prompt()
        user_prompt = f"请从以下文本中提取实体和关系：\n\n{content}"
        
        # 2. 调用 LLM Function Calling
        response = await self.llm_service.call_with_tools(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            tools=GRAPH_TOOLS,
            tool_choice="auto"
        )
        
        # 3. 处理工具调用结果
        entities = []
        relations = []
        
        if response.get("tool_calls"):
            for tool_call in response["tool_calls"]:
                function_name = tool_call["function"]["name"]
                arguments = json.loads(tool_call["function"]["arguments"])
                
                if function_name == "extract_entities":
                    entities.extend(arguments.get("entities", []))
                
                elif function_name == "add_graph_memory":
                    relations.append({
                        "source": arguments["source"],
                        "destination": arguments["destination"],
                        "relationship": arguments["relationship"],
                        "source_type": arguments["source_type"],
                        "destination_type": arguments["destination_type"],
                        "confidence": arguments.get("confidence", 0.8)
                    })
                
                elif function_name == "update_graph_memory":
                    # 处理更新
                    await self._update_relation(arguments)
                
                elif function_name == "delete_graph_memory":
                    # 处理删除
                    await self._delete_relation(arguments)
        
        # 4. 存储实体
        entity_ids = {}
        for entity in entities:
            entity_id = await self._upsert_entity(
                name=entity["entity"],
                entity_type=entity["entity_type"],
                user_id=user_id,
                agent_id=agent_id
            )
            entity_ids[entity["entity"]] = entity_id
        
        # 5. 存储关系
        for relation in relations:
            await self._upsert_relation(
                from_entity=relation["source"],
                to_entity=relation["destination"],
                relation_type=relation["relationship"],
                confidence=relation["confidence"],
                user_id=user_id,
                agent_id=agent_id
            )
        
        return {
            "entities": entities,
            "relations": relations,
            "entity_count": len(entities),
            "relation_count": len(relations)
        }
    
    def _build_extraction_prompt(self) -> str:
        """构建提取 Prompt"""
        return """你是一个专业的实体和关系提取专家。

请从用户提供的文本中提取以下内容：

1. **实体**：
   - 人物（person）：人名、称呼、关系（如"张三"、"老王"、"家人"）
   - 地点（location）：具体地点、场所（如"咖啡店"、"公司"、"郊外"）
   - 事件（event）：发生了什么（如"开会"、"野餐"）
   - 主题（topic）：讨论的话题（如"机器学习"、"投资"）
   - 情绪（emotion）：情绪状态（如"开心"、"焦虑"）

2. **关系**：
   - 人物关系：met（遇见）、friend（朋友）、colleague（同事）、family（家人）
   - 地点关系：at（在某地）、in（在某地内部）
   - 事件关系：related_to（相关）、caused_by（由...引起）

**示例**：

输入："今天和张三在咖啡店聊天，聊了机器学习的事"

输出：
- 实体：[{"entity": "张三", "entity_type": "person"}, {"entity": "咖啡店", "entity_type": "location"}, {"entity": "机器学习", "entity_type": "topic"}]
- 关系：[{"source": "张三", "destination": "咖啡店", "relationship": "at", "source_type": "person", "destination_type": "location"}]

请使用提供的工具函数来提取实体和关系。"""
    
    async def _upsert_entity(
        self,
        name: str,
        entity_type: str,
        user_id: str,
        agent_id: Optional[str] = None
    ) -> str:
        """存储或更新实体"""
        async with self.db_pool.acquire() as conn:
            # 检查实体是否存在
            existing = await conn.fetchrow(
                """
                SELECT id FROM entities 
                WHERE name = $1 AND type = $2 AND user_id = $3
                """,
                name, entity_type, user_id
            )
            
            if existing:
                # 更新提及次数
                await conn.execute(
                    """
                    UPDATE entities 
                    SET mention_count = mention_count + 1,
                        last_mentioned_at = NOW()
                    WHERE id = $1
                    """,
                    existing["id"]
                )
                return existing["id"]
            else:
                # 创建新实体
                result = await conn.fetchrow(
                    """
                    INSERT INTO entities (name, type, user_id, agent_id)
                    VALUES ($1, $2, $3, $4)
                    RETURNING id
                    """,
                    name, entity_type, user_id, agent_id
                )
                return result["id"]
    
    async def _upsert_relation(
        self,
        from_entity: str,
        to_entity: str,
        relation_type: str,
        confidence: float,
        user_id: str,
        agent_id: Optional[str] = None
    ):
        """存储或更新关系"""
        async with self.db_pool.acquire() as conn:
            # 获取实体 ID
            from_id = await conn.fetchval(
                "SELECT id FROM entities WHERE name = $1 AND user_id = $2",
                from_entity, user_id
            )
            to_id = await conn.fetchval(
                "SELECT id FROM entities WHERE name = $1 AND user_id = $2",
                to_entity, user_id
            )
            
            if not from_id or not to_id:
                return
            
            # 检查关系是否存在
            existing = await conn.fetchrow(
                """
                SELECT id FROM relations 
                WHERE from_entity_id = $1 AND to_entity_id = $2 AND relation_type = $3
                """,
                from_id, to_id, relation_type
            )
            
            if existing:
                # 更新权重
                await conn.execute(
                    """
                    UPDATE relations 
                    SET weight = weight + 0.1,
                        updated_at = NOW()
                    WHERE id = $1
                    """,
                    existing["id"]
                )
            else:
                # 创建新关系
                await conn.execute(
                    """
                    INSERT INTO relations (from_entity_id, to_entity_id, relation_type, weight, user_id)
                    VALUES ($1, $2, $3, $4, $5)
                    """,
                    from_id, to_id, relation_type, confidence, user_id
                )
    
    async def _update_relation(self, arguments: Dict):
        """更新关系"""
        # TODO: 实现更新逻辑
        pass
    
    async def _delete_relation(self, arguments: Dict):
        """删除关系"""
        # TODO: 实现删除逻辑
        pass
```

---

### 3. 记忆服务集成

**文件位置**：`apps/api/src/services/memory_service.py`（扩展现有服务）

```python
"""
记忆服务 - 扩展支持图谱构建

借鉴 Mem0 的并发处理设计
"""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import List, Dict, Optional

from .graph_builder_service import GraphBuilderService


class MemoryService:
    """记忆服务（扩展）"""
    
    def __init__(self, db_pool):
        self.db_pool = db_pool
        self.graph_builder = GraphBuilderService(db_pool)
    
    async def create_memory(
        self,
        content: str,
        user_id: str,
        agent_id: Optional[str] = None,
        run_id: Optional[str] = None,
        enable_graph: bool = True
    ) -> Dict:
        """
        创建记忆
        
        借鉴 Mem0 的并发处理：
        1. 存储记忆到数据库
        2. 异步构建图谱（不阻塞）
        """
        
        # 1. 存储记忆（主要操作）
        memory_id = await self._store_memory(content, user_id, agent_id)
        
        # 2. 异步构建图谱（不阻塞）
        if enable_graph:
            # 使用 ThreadPoolExecutor 并发处理
            with ThreadPoolExecutor() as executor:
                # 图谱构建在后台执行
                loop = asyncio.get_event_loop()
                graph_task = loop.run_in_executor(
                    executor,
                    self.graph_builder.build_graph,
                    content,
                    user_id,
                    agent_id
                )
                
                # 不等待图谱构建完成
                # graph_task 会在后台完成
        
        return {
            "id": memory_id,
            "content": content,
            "user_id": user_id,
            "agent_id": agent_id
        }
    
    async def _store_memory(self, content: str, user_id: str, agent_id: Optional[str]) -> str:
        """存储记忆到数据库"""
        # TODO: 实现存储逻辑
        pass
```

---

### 4. 智能确认服务（我们的创新）

**文件位置**：`apps/api/src/services/confirmation_service.py`

```python
"""
智能确认服务（我们的创新）

Mem0 缺失的功能：
- 无用户确认机制，容易出错累积

我们的方案：
- 智能判断何时需要用户确认
- 飞书消息卡片交互
- 确认队列管理
"""

from typing import List, Dict, Optional
import json


class ConfirmationService:
    """智能确认服务"""
    
    # 需要确认的场景
    CONFIRMATION_TRIGGERS = {
        "new_entity": {
            "description": "发现新实体",
            "template": "发现新{type}：'{name}'，这是谁/什么？"
        },
        "low_confidence": {
            "description": "置信度过低",
            "threshold": 0.6,
            "template": "对'{entity}'的识别置信度较低（{confidence:.0%}），确认吗？"
        },
        "relation_conflict": {
            "description": "关系冲突",
            "template": "'{entity}'之前是'{old_relation}'，现在是'{new_relation}'，更新吗？"
        }
    }
    
    async def should_confirm(
        self,
        entity: Dict,
        relations: List[Dict],
        existing_entities: List[Dict]
    ) -> Optional[Dict]:
        """
        判断是否需要用户确认
        
        规则：
        1. 新实体首次出现 → 需要确认
        2. 置信度 < 0.6 → 需要确认
        3. 关系冲突 → 需要确认
        """
        
        # 1. 检查是否是新实体
        entity_names = [e["name"] for e in existing_entities]
        if entity["entity"] not in entity_names:
            return {
                "type": "new_entity",
                "question": self.CONFIRMATION_TRIGGERS["new_entity"]["template"].format(
                    type=entity["entity_type"],
                    name=entity["entity"]
                ),
                "options": [
                    {"text": "确认", "action": "confirm"},
                    {"text": "修改类型", "action": "modify"},
                    {"text": "跳过", "action": "skip"}
                ]
            }
        
        # 2. 检查置信度
        confidence = entity.get("confidence", 1.0)
        if confidence < self.CONFIRMATION_TRIGGERS["low_confidence"]["threshold"]:
            return {
                "type": "low_confidence",
                "question": self.CONFIRMATION_TRIGGERS["low_confidence"]["template"].format(
                    entity=entity["entity"],
                    confidence=confidence
                ),
                "options": [
                    {"text": "确认", "action": "confirm"},
                    {"text": "修改", "action": "modify"},
                    {"text": "跳过", "action": "skip"}
                ]
            }
        
        # 3. 检查关系冲突
        # TODO: 实现冲突检测逻辑
        
        return None
    
    async def send_confirmation(
        self,
        user_id: str,
        confirmation: Dict
    ):
        """
        发送确认请求到飞书
        
        使用飞书消息卡片
        """
        # TODO: 实现飞书消息卡片发送
        pass
    
    async def handle_response(
        self,
        confirmation_id: str,
        response: str
    ):
        """
        处理用户回复
        
        更新实体/关系状态
        """
        # TODO: 实现回复处理逻辑
        pass
```

---

### 5. 召回增强服务

**文件位置**：`apps/api/src/services/recall_service.py`（扩展现有服务）

```python
"""
召回服务 - 扩展支持图谱增强

借鉴 Mem0 的混合检索设计
"""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import List, Dict, Optional


class RecallService:
    """召回服务（扩展）"""
    
    async def recall(
        self,
        query: str,
        user_id: str,
        agent_id: Optional[str] = None,
        enable_graph: bool = True
    ) -> Dict:
        """
        召回记忆
        
        借鉴 Mem0 的并发处理：
        1. 向量检索
        2. 图谱关联查询
        3. 合并结果
        """
        
        with ThreadPoolExecutor() as executor:
            loop = asyncio.get_event_loop()
            
            # 并发执行向量检索和图谱查询
            vector_task = loop.run_in_executor(
                executor,
                self._vector_search,
                query,
                user_id
            )
            
            graph_task = None
            if enable_graph:
                graph_task = loop.run_in_executor(
                    executor,
                    self._graph_search,
                    query,
                    user_id
                )
            
            # 等待结果
            vector_results = await vector_task
            graph_results = await graph_task if graph_task else None
        
        # 合并结果
        return {
            "results": vector_results,
            "relations": graph_results
        }
    
    def _vector_search(self, query: str, user_id: str) -> List[Dict]:
        """向量检索"""
        # TODO: 实现向量检索逻辑
        return []
    
    def _graph_search(self, query: str, user_id: str) -> List[Dict]:
        """图谱关联查询"""
        # TODO: 实现图谱查询逻辑
        return []
```

---

## 📊 对比：优化前 vs 优化后

| 维度 | v1.0（优化前） | v2.0（优化后） |
|------|---------------|---------------|
| **实体提取** | NER + LLM JSON | LLM Function Calling ✅ |
| **关系推理** | LLM JSON | LLM Function Calling ✅ |
| **并发处理** | 无 | ThreadPoolExecutor ✅ |
| **工具化** | 无 | 5 个工具函数 ✅ |
| **多租户** | user_id | user_id + agent_id + run_id ✅ |
| **用户确认** | 有 | 保留 ✅ |
| **软过滤** | 有 | 保留 ✅ |

---

## 🚀 实施计划（优化后）

### Phase 1: 工具定义和基础设施（1-2 天）

**任务**：
- [ ] 创建 `graph_tools.py`（工具定义）
- [ ] 创建数据库表（entities, relations）
- [ ] 实现 `GraphBuilderService` 基础框架

**工作量**：12 小时

### Phase 2: 图谱构建核心（2-3 天）

**任务**：
- [ ] 实现 Function Calling 调用
- [ ] 实现实体存储和更新
- [ ] 实现关系存储和更新

**工作量**：20 小时

### Phase 3: 并发处理和集成（1-2 天）

**任务**：
- [ ] 集成到 `MemoryService`
- [ ] 实现 ThreadPoolExecutor 并发
- [ ] 测试并发性能

**工作量**：12 小时

### Phase 4: 智能确认和召回增强（2-3 天）

**任务**：
- [ ] 实现 `ConfirmationService`
- [ ] 实现图谱召回增强
- [ ] 集成到现有召回流程

**工作量**：20 小时

### Phase 5: 测试和优化（1-2 天）

**任务**：
- [ ] 端到端测试
- [ ] 性能优化
- [ ] 文档完善

**工作量**：12 小时

---

## 📈 预期效果

| 指标 | 当前 | 优化后 |
|------|------|--------|
| **实体提取准确率** | 80% | 90%+ ✅ |
| **关系推理准确率** | 70% | 85%+ ✅ |
| **构建时间** | 未知 | < 2s ✅ |
| **并发性能** | 无 | 支持 ✅ |

---

## 🎯 关键创新点

### 1. Function Calling 机制

**借鉴 Mem0**：
- 使用 LLM Function Calling 替代 JSON 输出
- 结构化输出，格式稳定

**我们的实现**：
- 定义 5 个工具函数
- 支持 ADD/UPDATE/DELETE/NOOP 操作

### 2. 并发处理

**借鉴 Mem0**：
- 使用 ThreadPoolExecutor 并发执行
- 向量存储和图谱构建并行

**我们的实现**：
- 图谱构建不阻塞主流程
- 用户无感知

### 3. 智能确认（我们的创新）

**Mem0 缺失**：
- 无用户确认机制

**我们的方案**：
- 新实体、低置信度、关系冲突 → 自动确认
- 飞书消息卡片交互

### 4. 软过滤（我们的创新）

**Mem0 缺失**：
- 硬过滤，可能漏记忆

**我们的方案**：
- 软过滤（提升权重，不排除）
- 避免漏记忆

---

## 📝 总结

基于 Mem0 代码分析，我们优化了设计方案：

**借鉴 Mem0**：
1. ✅ Function Calling 机制（结构化输出）
2. ✅ 工具化设计（5 个工具函数）
3. ✅ 并发处理（ThreadPoolExecutor）
4. ✅ 多租户隔离（user_id + agent_id + run_id）

**保留我们的创新**：
1. ✅ 智能确认机制（避免错误累积）
2. ✅ 软过滤（不漏记忆）
3. ✅ 中文优化（jieba + 中文规则）
4. ✅ 关系扩展（"家人"→["老婆","孩子"]）

**预期效果**：
- 实体提取准确率：80% → 90%+
- 关系推理准确率：70% → 85%+
- 构建时间：< 2s
- 用户感知：无阻塞，流畅体验
