# 记忆网络构建系统 - 最终设计方案 v3.0

> 版本：v3.0（基于 Mem0 源码深度研究）
> 日期：2026-03-19
> 作者：颓弟 AI Agent

---

## 🎯 设计理念

**借鉴 Mem0 核心设计 + 我们的创新改进**

```
我们的方案 = Mem0 的 Function Calling 机制
          + Mem0 的智能更新逻辑
          + Mem0 的 Prompt 工程
          + 我们的智能确认（创新）
          + 我们的软过滤（创新）
          + 我们的中文优化（创新）
          + PostgreSQL 统一存储（简化部署）
```

---

## 📐 核心架构

### 整体架构

```
用户输入记忆
    ↓
┌──────────────────────────────────────────────────────────┐
│  MemoryService (统一入口)                                 │
│  - add(): 添加记忆（并发处理向量 + 图谱）                   │
│  - search(): 搜索记忆（向量 + 图谱混合）                   │
│  - recall(): 召回记忆（LLM 增强）                         │
└──────────────────────────────────────────────────────────┘
    ↓
┌──────────────────────────────────────────────────────────┐
│  核心组件层                                               │
│                                                          │
│  ┌────────────────┐  ┌────────────────┐  ┌────────────┐ │
│  │ LLM Service    │  │ Graph Builder  │  │ Confirmation│ │
│  │ (Function      │  │ Service        │  │ Service    │ │
│  │  Calling)      │  │ (图谱构建)      │  │ (智能确认) │ │
│  └────────────────┘  └────────────────┘  └────────────┘ │
└──────────────────────────────────────────────────────────┘
    ↓
┌──────────────────────────────────────────────────────────┐
│  存储层（PostgreSQL 统一存储）                            │
│                                                          │
│  ┌────────────────┐  ┌────────────────┐  ┌────────────┐ │
│  │ memories 表    │  │ entities 表    │  │ relations │ │
│  │ (记忆主表)     │  │ (实体表)       │  │ 表        │ │
│  │ + pgvector     │  │                │  │ (关系表)  │ │
│  └────────────────┘  └────────────────┘  └────────────┘ │
└──────────────────────────────────────────────────────────┘
```

---

## 🔧 核心组件设计

### 1. Function Calling 工具定义

**文件位置**：`apps/api/src/services/graph_tools.py`

```python
"""
图谱工具定义（借鉴 Mem0）

使用 OpenAI Function Calling 机制，实现结构化输出
"""

# 提取实体工具
EXTRACT_ENTITIES_TOOL = {
    "type": "function",
    "function": {
        "name": "extract_entities",
        "description": "从文本中提取实体（人物、地点、事件等）及其类型。",
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
                                "description": "实体名称（如'张三'、'咖啡店'）"
                            },
                            "entity_type": {
                                "type": "string",
                                "description": "实体类型",
                                "enum": ["person", "location", "event", "topic", "emotion"]
                            },
                            "confidence": {
                                "type": "number",
                                "description": "置信度（0-1）",
                                "minimum": 0,
                                "maximum": 1
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

# 建立关系工具
ESTABLISH_RELATIONS_TOOL = {
    "type": "function",
    "function": {
        "name": "establish_relations",
        "description": "建立实体之间的关系。",
        "parameters": {
            "type": "object",
            "properties": {
                "relations": {
                    "type": "array",
                    "items": {
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
                                "description": "关系类型（如'met_at', 'friend', 'at'）"
                            },
                            "confidence": {
                                "type": "number",
                                "description": "置信度（0-1）"
                            }
                        },
                        "required": ["source", "destination", "relationship"]
                    },
                    "description": "关系列表"
                }
            },
            "required": ["relations"]
        }
    }
}

# 添加图谱记忆工具
ADD_GRAPH_MEMORY_TOOL = {
    "type": "function",
    "function": {
        "name": "add_graph_memory",
        "description": "添加新的图谱记忆（实体和关系）。如果实体不存在则自动创建。",
        "parameters": {
            "type": "object",
            "properties": {
                "source": {"type": "string", "description": "源实体名称"},
                "destination": {"type": "string", "description": "目标实体名称"},
                "relationship": {"type": "string", "description": "关系类型"},
                "source_type": {"type": "string", "description": "源实体类型"},
                "destination_type": {"type": "string", "description": "目标实体类型"},
                "confidence": {"type": "number", "description": "置信度"}
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
        "description": "更新已有图谱记忆的关系。",
        "parameters": {
            "type": "object",
            "properties": {
                "source": {"type": "string", "description": "源实体名称"},
                "destination": {"type": "string", "description": "目标实体名称"},
                "old_relationship": {"type": "string", "description": "旧关系类型"},
                "new_relationship": {"type": "string", "description": "新关系类型"}
            },
            "required": ["source", "destination", "old_relationship", "new_relationship"]
        }
    }
}

# 无操作工具
NOOP_TOOL = {
    "type": "function",
    "function": {
        "name": "noop",
        "description": "无操作。不需要对图谱进行任何修改时调用。",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": []
        }
    }
}

# 所有工具列表
GRAPH_TOOLS = [
    EXTRACT_ENTITIES_TOOL,
    ESTABLISH_RELATIONS_TOOL,
    ADD_GRAPH_MEMORY_TOOL,
    UPDATE_GRAPH_MEMORY_TOOL,
    NOOP_TOOL
]
```

---

### 2. Prompt 工程（借鉴 Mem0）

**文件位置**：`apps/api/src/services/prompts.py`

```python
"""
Prompt 模板（借鉴 Mem0）

核心设计：
1. 区分用户记忆和 Agent 记忆
2. 明确提取范围（只从特定角色）
3. 多语言支持
4. 丰富的示例（Few-shot Learning）
"""

from datetime import datetime

# 用户记忆提取 Prompt
USER_MEMORY_EXTRACTION_PROMPT = f"""你是一个个人信息整理专家，专门负责从对话中提取用户的记忆和偏好。

# [重要]：只从用户的消息中提取信息，不要包含助手或系统消息的内容。

需要记录的信息类型：

1. **个人偏好**：喜欢什么、不喜欢什么、特定偏好（食物、产品、活动、娱乐等）
2. **重要个人信息**：姓名、关系、重要日期
3. **计划和意图**：即将发生的事件、旅行、目标
4. **活动和服务偏好**：餐饮、旅行、爱好、其他服务
5. **健康和健康偏好**：饮食限制、健身习惯、其他健康相关信息
6. **职业信息**：职位、工作习惯、职业目标
7. **其他信息**：喜欢的书籍、电影、品牌等

以下是几个示例：

用户：嗨。
助手：你好！很高兴为你服务。
输出：{{"facts": []}}

用户：嗨，我正在找旧金山的餐厅。
助手：好的，我可以帮你。你对哪种菜系感兴趣？
输出：{{"facts": ["正在找旧金山的餐厅"]}}

用户：昨天下午3点和约翰开会，我们讨论了新项目。
助手：听起来是一个高效的会议。
输出：{{"facts": ["昨天下午3点和约翰开会并讨论了新项目"]}}

用户：嗨，我叫约翰。我是一名软件工程师。
助手：很高兴认识你，约翰！
输出：{{"facts": ["名字是约翰", "是一名软件工程师"]}}

用户：我最喜欢的电影是《盗梦空间》和《星际穿越》。你呢？
助手：很好的选择！两部电影都很棒。我最喜欢《黑暗骑士》和《肖申克的救赎》。
输出：{{"facts": ["最喜欢的电影是《盗梦空间》和《星际穿越》"]}}

请以 JSON 格式返回事实和偏好。

记住：
- [重要] 只从用户消息中提取信息，不要包含助手或系统消息的内容
- 今天的日期是 {datetime.now().strftime("%Y-%m-%d")}
- 检测用户输入的语言，并用相同的语言记录事实
- 如果找不到相关信息，可以返回空列表
- 返回格式必须是 JSON，包含 "facts" 键，值为字符串列表
"""

# Agent 记忆提取 Prompt
AGENT_MEMORY_EXTRACTION_PROMPT = f"""你是一个助手信息整理专家，专门负责从对话中提取关于 AI 助手的记忆、偏好和特征。

# [重要]：只从助手的消息中提取信息，不要包含用户或系统消息的内容。

需要记录的信息类型：

1. **助手的偏好**：喜欢什么、不喜欢什么、特定偏好
2. **助手的能力**：特定技能、知识领域、可以执行的任务
3. **助手的假设性计划或活动**：假设性活动或计划
4. **助手的个性特征**：个性特征或特征
5. **助手的工作方式**：如何处理不同类型的任务或问题
6. **助手的知识领域**：展示知识的主题或领域
7. **其他信息**：其他有趣或独特的细节

示例：

用户：我最喜欢的电影是《盗梦空间》和《星际穿越》。你呢？
助手：很好的选择！两部电影都很棒。我最喜欢《黑暗骑士》和《肖申克的救赎》。
输出：{{"facts": ["最喜欢的电影是《黑暗骑士》和《肖申克的救赎》"]}}

请以 JSON 格式返回事实和偏好。

记住：
- [重要] 只从助手消息中提取信息，不要包含用户或系统消息的内容
- 检测助手输入的语言，并用相同的语言记录事实
"""

# 智能记忆更新 Prompt
MEMORY_UPDATE_PROMPT = """你是一个智能记忆管理器，负责管理系统的记忆。

你可以执行四种操作：(1) 添加到记忆，(2) 更新记忆，(3) 从记忆中删除，(4) 不改变。

根据以上四种操作，记忆会发生变化。

将新检索的事实与现有记忆进行比较。对于每个新事实，决定是否：
- ADD：将其作为新元素添加到记忆中
- UPDATE：更新现有的记忆元素
- DELETE：从记忆中删除现有记忆元素
- NONE：不做任何更改（如果事实已经存在或无关）

选择执行哪种操作的具体准则：

1. **添加**：如果检索的事实包含记忆中不存在的新信息，则需要添加它，方法是在 id 字段中生成新的 ID。
   
   示例：
   旧记忆：
   [
       {{"id": "0", "text": "用户是一名软件工程师"}}
   ]
   新检索的事实：["名字是约翰"]
   新记忆：
   {{
       "memory": [
           {{"id": "0", "text": "用户是一名软件工程师", "event": "NONE"}},
           {{"id": "1", "text": "名字是约翰", "event": "ADD"}}
       ]
   }}

2. **更新**：如果检索的事实包含记忆中已经存在但完全不同的信息，则需要更新它。如果检索的事实包含与记忆中存在的元素传达相同信息的信息，则需要保留具有最多信息的事实。
   
   示例：
   旧记忆：
   [
       {{"id": "0", "text": "我喜欢奶酪披萨"}},
       {{"id": "1", "text": "用户是一名软件工程师"}},
       {{"id": "2", "text": "用户喜欢打板球"}}
   ]
   新检索的事实：["喜欢鸡肉披萨", "喜欢和朋友一起打板球"]
   新记忆：
   {{
       "memory": [
           {{"id": "0", "text": "喜欢奶酪和鸡肉披萨", "event": "UPDATE", "old_memory": "我喜欢奶酪披萨"}},
           {{"id": "1", "text": "用户是一名软件工程师", "event": "NONE"}},
           {{"id": "2", "text": "喜欢和朋友一起打板球", "event": "UPDATE", "old_memory": "用户喜欢打板球"}}
       ]
   }}

3. **删除**：如果检索的事实包含与记忆中信息矛盾的信息，则需要删除它。
   
   示例：
   旧记忆：
   [
       {{"id": "0", "text": "名字是约翰"}},
       {{"id": "1", "text": "喜欢奶酪披萨"}}
   ]
   新检索的事实：["不喜欢奶酪披萨"]
   新记忆：
   {{
       "memory": [
           {{"id": "0", "text": "名字是约翰", "event": "NONE"}},
           {{"id": "1", "text": "喜欢奶酪披萨", "event": "DELETE"}}
       ]
   }}

4. **不改变**：如果检索的事实包含记忆中已经存在的信息，则不需要进行任何更改。

你必须仅以以下 JSON 结构返回响应：

{{
    "memory": [
        {{
            "id": "<记忆ID>",
            "text": "<记忆内容>",
            "event": "<操作>",
            "old_memory": "<旧记忆内容>"  // 仅在 event 为 "UPDATE" 时需要
        }}
    ]
}}

遵循以下指令：
- 不要返回上面提供的自定义示例中的任何内容
- 如果当前记忆为空，则需要将新检索的事实添加到记忆中
- 你应该仅以 JSON 格式返回更新的记忆
- 如果有添加，生成新的键并添加对应的新记忆
- 如果有删除，应该从记忆中删除记忆键值对
- 如果有更新，ID 键应该保持不变，只有值需要更新

不要返回 JSON 格式以外的任何内容。
"""


def get_memory_update_messages(old_memories, new_facts):
    """生成记忆更新的 Prompt"""
    
    if old_memories:
        current_memory = f"""
下面是我到目前为止收集的当前记忆内容。你必须仅以以下格式更新它：

```
{old_memories}
```

"""
    else:
        current_memory = """
当前记忆为空。

"""
    
    return f"""{MEMORY_UPDATE_PROMPT}

{current_memory}

新检索的事实如下所述。你需要分析新检索的事实，并确定这些事实是应该被添加、更新还是从记忆中删除。

```
{new_facts}
```

你必须仅以以下 JSON 结构返回响应：

{{
    "memory": [
        {{
            "id": "<记忆ID>",
            "text": "<记忆内容>",
            "event": "<操作>",
            "old_memory": "<旧记忆内容>"
        }}
    ]
}}
"""
```

---

### 3. 图谱构建服务（核心）

**文件位置**：`apps/api/src/services/graph_builder_service.py`

```python
"""
图谱构建服务

借鉴 Mem0 的设计：
1. 使用 Function Calling 提取实体和关系
2. 智能更新逻辑（LLM 判断 ADD/UPDATE/DELETE/NONE）
3. 并发处理
"""

import asyncio
import json
from typing import List, Dict, Optional
from concurrent.futures import ThreadPoolExecutor

from .graph_tools import GRAPH_TOOLS
from .prompts import USER_MEMORY_EXTRACTION_PROMPT, get_memory_update_messages


class GraphBuilderService:
    """图谱构建服务"""
    
    def __init__(self, db_pool, llm_service):
        self.db_pool = db_pool
        self.llm_service = llm_service
    
    async def build_graph(
        self,
        content: str,
        user_id: str,
        agent_id: Optional[str] = None,
        run_id: Optional[str] = None
    ) -> Dict:
        """
        构建图谱
        
        流程：
        1. 使用 Function Calling 提取实体
        2. 使用 Function Calling 提取关系
        3. 存储实体和关系
        4. 返回构建结果
        """
        
        # 1. 提取实体（Function Calling）
        entities = await self._extract_entities(content)
        
        # 2. 提取关系（Function Calling）
        relations = await self._extract_relations(content, entities)
        
        # 3. 存储实体
        entity_ids = {}
        for entity in entities:
            entity_id = await self._upsert_entity(
                name=entity["entity"],
                entity_type=entity["entity_type"],
                user_id=user_id,
                agent_id=agent_id,
                confidence=entity.get("confidence", 0.8)
            )
            entity_ids[entity["entity"]] = entity_id
        
        # 4. 存储关系
        for relation in relations:
            await self._upsert_relation(
                from_entity=relation["source"],
                to_entity=relation["destination"],
                relation_type=relation["relationship"],
                confidence=relation.get("confidence", 0.8),
                user_id=user_id,
                agent_id=agent_id
            )
        
        return {
            "entities": entities,
            "relations": relations,
            "entity_count": len(entities),
            "relation_count": len(relations)
        }
    
    async def _extract_entities(self, content: str) -> List[Dict]:
        """提取实体（Function Calling）"""
        
        # 调用 LLM Function Calling
        response = await self.llm_service.call_with_tools(
            system_prompt=USER_MEMORY_EXTRACTION_PROMPT,
            user_prompt=f"输入：\n{content}",
            tools=[GRAPH_TOOLS[0]]  # EXTRACT_ENTITIES_TOOL
        )
        
        # 解析工具调用结果
        entities = []
        if response.get("tool_calls"):
            for tool_call in response["tool_calls"]:
                if tool_call["function"]["name"] == "extract_entities":
                    entities = tool_call["function"]["arguments"]["entities"]
        
        return entities
    
    async def _extract_relations(self, content: str, entities: List[Dict]) -> List[Dict]:
        """提取关系（Function Calling）"""
        
        entity_names = [e["entity"] for e in entities]
        
        # 调用 LLM Function Calling
        response = await self.llm_service.call_with_tools(
            system_prompt="你是一个关系提取专家。根据实体列表和文本，提取实体之间的关系。",
            user_prompt=f"实体列表：{entity_names}\n\n文本：{content}",
            tools=[GRAPH_TOOLS[1]]  # ESTABLISH_RELATIONS_TOOL
        )
        
        # 解析工具调用结果
        relations = []
        if response.get("tool_calls"):
            for tool_call in response["tool_calls"]:
                if tool_call["function"]["name"] == "establish_relations":
                    relations = tool_call["function"]["arguments"]["relations"]
        
        return relations
    
    async def _upsert_entity(self, name, entity_type, user_id, agent_id, confidence):
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
                        last_mentioned_at = NOW(),
                        confidence = GREATEST(confidence, $1)
                    WHERE id = $2
                    """,
                    confidence, existing["id"]
                )
                return existing["id"]
            else:
                # 创建新实体
                result = await conn.fetchrow(
                    """
                    INSERT INTO entities (name, type, user_id, agent_id, confidence)
                    VALUES ($1, $2, $3, $4, $5)
                    RETURNING id
                    """,
                    name, entity_type, user_id, agent_id, confidence
                )
                return result["id"]
    
    async def _upsert_relation(self, from_entity, to_entity, relation_type, confidence, user_id, agent_id):
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
                    SET weight = LEAST(weight + 0.1, 1.0),
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


class ConfirmationService:
    """智能确认服务"""
    
    # 需要确认的场景
    CONFIRMATION_TRIGGERS = {
        "new_entity": {
            "description": "发现新实体",
            "threshold": 0.8,  # 置信度 < 0.8 需要确认
            "template": "发现新{type}：'{name}'（置信度：{confidence:.0%}），确认吗？"
        },
        "relation_conflict": {
            "description": "关系冲突",
            "template": "'{entity}'之前是'{old_relation}'，现在是'{new_relation}'，更新吗？"
        },
        "low_confidence": {
            "description": "置信度过低",
            "threshold": 0.6,
            "template": "对'{entity}'的识别置信度较低（{confidence:.0%}），确认吗？"
        }
    }
    
    async def should_confirm(
        self,
        entity: Dict,
        relations: List[Dict],
        existing_entities: List[Dict],
        existing_relations: List[Dict]
    ) -> Optional[Dict]:
        """
        判断是否需要用户确认
        
        规则：
        1. 新实体且置信度 < 0.8 → 需要确认
        2. 置信度 < 0.6 → 需要确认
        3. 关系冲突 → 需要确认
        """
        
        confidence = entity.get("confidence", 1.0)
        entity_name = entity["entity"]
        entity_type = entity["entity_type"]
        
        # 1. 检查是否是新实体
        existing_names = [e["name"] for e in existing_entities]
        if entity_name not in existing_names:
            # 新实体，检查置信度
            if confidence < self.CONFIRMATION_TRIGGERS["new_entity"]["threshold"]:
                return {
                    "type": "new_entity",
                    "question": self.CONFIRMATION_TRIGGERS["new_entity"]["template"].format(
                        type=entity_type,
                        name=entity_name,
                        confidence=confidence
                    ),
                    "options": [
                        {"text": "确认", "action": "confirm"},
                        {"text": "修改类型", "action": "modify_type"},
                        {"text": "跳过", "action": "skip"}
                    ],
                    "entity": entity
                }
        
        # 2. 检查置信度
        if confidence < self.CONFIRMATION_TRIGGERS["low_confidence"]["threshold"]:
            return {
                "type": "low_confidence",
                "question": self.CONFIRMATION_TRIGGERS["low_confidence"]["template"].format(
                    entity=entity_name,
                    confidence=confidence
                ),
                "options": [
                    {"text": "确认", "action": "confirm"},
                    {"text": "修改", "action": "modify"},
                    {"text": "跳过", "action": "skip"}
                ],
                "entity": entity
            }
        
        # 3. 检查关系冲突
        for relation in relations:
            # 检查是否有冲突的关系
            for existing in existing_relations:
                if (existing["from_entity"] == relation["source"] and
                    existing["to_entity"] == relation["destination"] and
                    existing["relation_type"] != relation["relationship"]):
                    return {
                        "type": "relation_conflict",
                        "question": self.CONFIRMATION_TRIGGERS["relation_conflict"]["template"].format(
                            entity=relation["source"],
                            old_relation=existing["relation_type"],
                            new_relation=relation["relationship"]
                        ),
                        "options": [
                            {"text": "更新为新关系", "action": "update"},
                            {"text": "保持旧关系", "action": "keep_old"},
                            {"text": "两个都保留", "action": "keep_both"}
                        ],
                        "relation": relation,
                        "existing_relation": existing
                    }
        
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

### 5. 软过滤服务（我们的创新）

**文件位置**：`apps/api/src/services/soft_filter_service.py`

```python
"""
软过滤服务（我们的创新）

Mem0 缺失的功能：
- 硬过滤，可能漏记忆

我们的方案：
- 软过滤（提升权重，不排除）
- 关系扩展（"家人" → ["老婆", "老公", "孩子"]）
"""

from typing import List, Dict, Optional


# 人物关系扩展映射
PERSON_RELATION_EXPANSION = {
    "家人": ["老婆", "老公", "孩子", "父母", "儿子", "女儿", "妻子", "丈夫", "家人"],
    "朋友": ["老王", "小张", "张三", "李四", "朋友"],
    "同事": ["小李", "王经理", "同事"],
    "同学": ["老同学", "大学同学", "高中同学", "同学"]
}

# 地点归一化映射
LOCATION_NORMALIZATION = {
    "星巴克": "咖啡店",
    "Costa": "咖啡店",
    "麦当劳": "快餐店",
    "肯德基": "快餐店",
    "必胜客": "餐厅"
}


class SoftFilterService:
    """软过滤服务"""
    
    async def apply_soft_filter(
        self,
        results: List[Dict],
        location_filter: Optional[str] = None,
        person_filter: Optional[str] = None
    ) -> List[Dict]:
        """
        应用软过滤
        
        策略：
        1. 不排除任何结果
        2. 匹配的结果提升权重
        3. 关系扩展（如"家人" → ["老婆", "老公", "孩子"]）
        """
        
        if location_filter:
            results = self._apply_location_filter(results, location_filter)
        
        if person_filter:
            results = self._apply_person_filter(results, person_filter)
        
        # 重新排序
        results.sort(key=lambda x: x.get("similarity", 0), reverse=True)
        
        return results
    
    def _apply_location_filter(self, results: List[Dict], location_filter: str) -> List[Dict]:
        """地点软过滤"""
        
        # 归一化地点
        normalized_location = LOCATION_NORMALIZATION.get(location_filter, location_filter)
        
        for result in results:
            location = result.get("location_name") or ""
            content = result.get("content") or ""
            
            # 1. location_name 字段精确匹配 → 大幅提升
            if location_filter in location:
                result["similarity"] = result.get("similarity", 0) + 0.15
                result["location_match"] = "exact"
            
            # 2. 归一化匹配 → 中度提升
            elif normalized_location in location:
                result["similarity"] = result.get("similarity", 0) + 0.10
                result["location_match"] = "normalized"
            
            # 3. content 包含地点 → 轻度提升
            elif location_filter in content or normalized_location in content:
                result["similarity"] = result.get("similarity", 0) + 0.05
                result["location_match"] = "content"
        
        return results
    
    def _apply_person_filter(self, results: List[Dict], person_filter: str) -> List[Dict]:
        """人物软过滤 + 关系扩展"""
        
        # 扩展人物关系
        expanded_names = PERSON_RELATION_EXPANSION.get(person_filter, [person_filter])
        expanded_names.append(person_filter)
        
        for result in results:
            people_str = str(result.get("people") or [])
            content = result.get("content") or ""
            
            # 检查任意扩展词是否匹配
            matched = any(
                name in people_str or name in content
                for name in expanded_names
            )
            
            if matched:
                result["similarity"] = result.get("similarity", 0) + 0.12
                result["person_match"] = "yes"
        
        return results
```

---

## 📊 数据库设计

### 表结构

```sql
-- 1. 实体表
CREATE TABLE entities (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(200) NOT NULL,
    type VARCHAR(20) NOT NULL,  -- person/location/event/topic/emotion
    confidence FLOAT DEFAULT 0.8,
    
    -- 统计字段
    mention_count INT DEFAULT 1,
    last_mentioned_at TIMESTAMP,
    
    -- 多租户
    user_id VARCHAR(100) NOT NULL,
    agent_id VARCHAR(100),
    run_id VARCHAR(100),
    
    -- 元数据
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    
    -- 索引
    CONSTRAINT unique_entity UNIQUE (name, type, user_id)
);

-- 2. 关系表
CREATE TABLE relations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    from_entity_id UUID NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    to_entity_id UUID NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    relation_type VARCHAR(50) NOT NULL,
    weight FLOAT DEFAULT 1.0,
    confidence FLOAT DEFAULT 0.8,
    
    -- 多租户
    user_id VARCHAR(100) NOT NULL,
    agent_id VARCHAR(100),
    run_id VARCHAR(100),
    
    -- 元数据
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    
    -- 索引
    CONSTRAINT unique_relation UNIQUE (from_entity_id, to_entity_id, relation_type)
);

-- 3. 索引
CREATE INDEX idx_entities_user ON entities(user_id);
CREATE INDEX idx_entities_name ON entities USING gin(to_tsvector('simple', name));
CREATE INDEX idx_relations_from ON relations(from_entity_id);
CREATE INDEX idx_relations_to ON relations(to_entity_id);
```

---

## 🚀 实施计划

### Phase 1: 核心基础（2-3 天）

**任务**：
- [ ] 创建数据库表
- [ ] 实现 `graph_tools.py`（工具定义）
- [ ] 实现 `prompts.py`（Prompt 模板）
- [ ] 实现 `GraphBuilderService` 基础框架

**工作量**：20 小时

---

### Phase 2: Function Calling 集成（2-3 天）

**任务**：
- [ ] 实现 LLM Function Calling 调用
- [ ] 实现实体提取
- [ ] 实现关系推理
- [ ] 测试验证

**工作量**：20 小时

---

### Phase 3: 智能确认和软过滤（2-3 天）

**任务**：
- [ ] 实现 `ConfirmationService`
- [ ] 实现 `SoftFilterService`
- [ ] 集成到图谱构建流程
- [ ] 测试验证

**工作量**：20 小时

---

### Phase 4: 并发处理和集成（1-2 天）

**任务**：
- [ ] 实现 ThreadPoolExecutor 并发
- [ ] 集成到 `MemoryService`
- [ ] 性能测试

**工作量**：12 小时

---

### Phase 5: 测试和优化（1-2 天）

**任务**：
- [ ] 端到端测试
- [ ] 性能优化
- [ ] 文档完善

**工作量**：12 小时

---

## 📈 预期效果

| 指标 | v2.0 | v3.0 |
|------|------|------|
| **实体提取准确率** | 90% | **95%+** ✅ |
| **关系推理准确率** | 85% | **90%+** ✅ |
| **格式稳定性** | 高 | **极高** ✅ |
| **构建时间** | < 2s | **< 1.5s** ✅ |
| **用户感知** | 无阻塞 | **无阻塞 + 智能确认** ✅ |

---

## 🎯 总结

### 核心创新

| 创新 | 来源 | 说明 |
|------|------|------|
| **Function Calling** | Mem0 | 结构化输出，格式稳定 |
| **智能更新逻辑** | Mem0 | LLM 判断 ADD/UPDATE/DELETE/NONE |
| **Prompt 工程** | Mem0 | 精准提取，多语言支持 |
| **智能确认机制** | 我们 | 避免错误累积 |
| **软过滤** | 我们 | 不漏记忆 |
| **中文优化** | 我们 | jieba + 中文规则 |
| **PostgreSQL 统一存储** | 我们 | 简化部署 |

### 最终方案

```
我们的方案 = Mem0 的 Function Calling 机制
          + Mem0 的智能更新逻辑
          + Mem0 的 Prompt 工程
          + 我们的智能确认（创新）
          + 我们的软过滤（创新）
          + 我们的中文优化（创新）
          + PostgreSQL 统一存储（简化部署）
```

**实施周期**：7-12 天  
**预期效果**：实体提取准确率 95%+，关系推理准确率 90%+
