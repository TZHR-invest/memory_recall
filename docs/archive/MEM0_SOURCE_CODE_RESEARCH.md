# Mem0 源码深度研究报告

> 研究日期：2026-03-19
> 研究目标：深入理解 Mem0 的核心设计思路，为 memory_recall 项目提供参考
> 代码版本：main 分支（2026-03-19）

---

## 目录

1. [核心架构分析](#1-核心架构分析)
2. [关键代码解读](#2-关键代码解读)
3. [设计模式总结](#3-设计模式总结)
4. [技术亮点](#4-技术亮点)
5. [可借鉴的设计](#5-可借鉴的设计)
6. [存在的问题与改进建议](#6-存在的问题与改进建议)

---

## 1. 核心架构分析

### 1.1 整体架构

```
┌─────────────────────────────────────────────────────────────┐
│                        用户层                                │
│  - add(): 添加记忆                                           │
│  - search(): 搜索记忆                                        │
│  - get(): 获取记忆                                           │
│  - delete(): 删除记忆                                        │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│                     Memory 核心层                            │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  LLM 层（Function Calling + JSON 响应）              │  │
│  │  - 实体提取（extract_entities 工具）                  │  │
│  │  - 关系推理（establish_relationships 工具）          │  │
│  │  - 记忆更新（ADD/UPDATE/DELETE/NOOP）                │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌──────────────┬──────────────┬──────────────┬──────────────┐
│ Vector Store │ Graph Store  │ LLM Provider │ Embedder     │
│ (Qdrant)     │ (Neo4j)      │ (OpenAI)     │ (OpenAI)     │
└──────────────┴──────────────┴──────────────┴──────────────┘
```

### 1.2 核心文件结构

```
mem0/
├── memory/
│   ├── main.py              # 核心入口（102KB）
│   ├── graph_memory.py      # 图谱记忆实现（30KB）
│   ├── utils.py             # 工具函数（8.3KB）
│   └── storage.py           # 存储管理（7.5KB）
│
├── graphs/
│   ├── tools.py             # 工具定义（16KB）
│   ├── configs.py           # 配置（5KB）
│   └── utils.py             # 图谱工具函数（5.7KB）
│
├── configs/
│   ├── base.py              # 基础配置（3.6KB）
│   ├── prompts.py           # Prompt 模板（25KB）
│   └── enums.py             # 枚举类型（151B）
│
├── utils/
│   └── factory.py           # 工厂模式（13KB）
│
└── [其他组件]
    ├── embeddings/          # Embedding 模型
    ├── llms/                # LLM 提供者
    ├── vector_stores/       # 向量存储
    └── reranker/            # 重排序器
```

---

## 2. 关键代码解读

### 2.1 Function Calling 机制（核心创新）

**位置**：`mem0/graphs/tools.py`

Mem0 使用 OpenAI 的 Function Calling 机制来提取实体和关系，而不是直接让 LLM 返回 JSON。

#### 工具定义示例

```python
# 提取实体工具
EXTRACT_ENTITIES_TOOL = {
    "type": "function",
    "function": {
        "name": "extract_entities",
        "description": "Extract entities and their types from the text.",
        "parameters": {
            "type": "object",
            "properties": {
                "entities": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "entity": {"type": "string", "description": "The name or identifier of the entity."},
                            "entity_type": {"type": "string", "description": "The type or category of the entity."}
                        },
                        "required": ["entity", "entity_type"]
                    },
                    "description": "An array of entities with their types."
                }
            },
            "required": ["entities"]
        }
    }
}

# 建立关系工具
RELATIONS_TOOL = {
    "type": "function",
    "function": {
        "name": "establish_relationships",
        "description": "Establish relationships among the entities based on the provided text.",
        "parameters": {
            "type": "object",
            "properties": {
                "entities": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "source": {"type": "string", "description": "The source entity of the relationship."},
                            "relationship": {"type": "string", "description": "The relationship between the source and destination entities."},
                            "destination": {"type": "string", "description": "The destination entity of the relationship."}
                        },
                        "required": ["source", "relationship", "destination"]
                    }
                }
            },
            "required": ["entities"]
        }
    }
}

# 添加图谱记忆工具
ADD_GRAPH_MEMORY_TOOL = {
    "type": "function",
    "function": {
        "name": "add_graph_memory",
        "description": "Add a new graph memory to the knowledge graph.",
        "parameters": {
            "type": "object",
            "properties": {
                "source": {"type": "string", "description": "源实体"},
                "destination": {"type": "string", "description": "目标实体"},
                "relationship": {"type": "string", "description": "关系类型"},
                "source_type": {"type": "string", "description": "源实体类型"},
                "destination_type": {"type": "string", "description": "目标实体类型"}
            },
            "required": ["source", "destination", "relationship", "source_type", "destination_type"]
        }
    }
}
```

#### 工具调用示例

```python
# 在 graph_memory.py 中
def _retrieve_nodes_from_data(self, data, filters):
    """提取实体"""
    _tools = [EXTRACT_ENTITIES_TOOL]
    
    # 调用 LLM Function Calling
    search_results = self.llm.generate_response(
        messages=[
            {
                "role": "system",
                "content": "You are a smart assistant who understands entities..."
            },
            {"role": "user", "content": data}
        ],
        tools=_tools  # 传入工具定义
    )
    
    # 解析工具调用结果
    entity_type_map = {}
    for tool_call in search_results["tool_calls"]:
        if tool_call["name"] == "extract_entities":
            for item in tool_call["arguments"]["entities"]:
                entity_type_map[item["entity"]] = item["entity_type"]
    
    return entity_type_map
```

**优势**：
1. ✅ 结构化输出，格式稳定
2. ✅ 支持复杂操作（ADD/UPDATE/DELETE/NOOP）
3. ✅ LLM 更容易理解和执行
4. ✅ 类型安全（parameters 有 schema）

---

### 2.2 记忆更新逻辑（智能判断）

**位置**：`mem0/configs/prompts.py`

Mem0 使用 LLM 来判断是否需要更新记忆，而不是简单的相似度匹配。

#### Prompt 设计

```python
DEFAULT_UPDATE_MEMORY_PROMPT = """You are a smart memory manager which controls the memory of a system.
You can perform four operations: (1) add into the memory, (2) update the memory, (3) delete from the memory, and (4) no change.

Based on the above four operations, the memory will change.

Compare newly retrieved facts with the existing memory. For each new fact, decide whether to:
- ADD: Add it to the memory as a new element
- UPDATE: Update an existing memory element
- DELETE: Delete an existing memory element
- NONE: Make no change (if the fact is already present or irrelevant)

There are specific guidelines to select which operation to perform:

1. **Add**: If the retrieved facts contain new information not present in the memory...
2. **Update**: If the retrieved facts contain information that is already present in the memory but the information is totally different...
3. **Delete**: If the retrieved facts contain information that contradicts the information present in the memory...
4. **No Change**: If the retrieved facts contain information that is already present in the memory...

**Example**:
- Old Memory: [{"id": "0", "text": "User is a software engineer"}]
- Retrieved facts: ["Name is John"]
- New Memory: {
    "memory": [
        {"id": "0", "text": "User is a software engineer", "event": "NONE"},
        {"id": "1", "text": "Name is John", "event": "ADD"}
    ]
}
"""
```

#### 记忆更新流程

```python
# 在 main.py 中
def _add_to_vector_store(self, messages, metadata, filters, infer):
    # 1. 提取新事实
    new_retrieved_facts = llm.generate_response(...)
    
    # 2. 搜索已有记忆
    existing_memories = vector_store.search(query=new_fact, ...)
    
    # 3. LLM 判断更新操作
    function_calling_prompt = get_update_memory_messages(
        existing_memories, 
        new_retrieved_facts
    )
    
    response = llm.generate_response(
        messages=[{"role": "user", "content": function_calling_prompt}],
        response_format={"type": "json_object"}
    )
    
    # 4. 执行操作
    for resp in json.loads(response)["memory"]:
        if resp["event"] == "ADD":
            self._create_memory(data=resp["text"], ...)
        elif resp["event"] == "UPDATE":
            self._update_memory(memory_id=resp["id"], data=resp["text"], ...)
        elif resp["event"] == "DELETE":
            self._delete_memory(memory_id=resp["id"])
```

**优势**：
1. ✅ 智能：LLM 判断是否需要更新
2. ✅ 精确：区分 ADD/UPDATE/DELETE/NONE
3. ✅ 上下文：考虑已有记忆和新事实的关系

---

### 2.3 Prompt 工程（核心竞争力）

**位置**：`mem0/configs/prompts.py`

Mem0 的 Prompt 设计非常精细，是核心竞争力之一。

#### 用户记忆提取 Prompt

```python
USER_MEMORY_EXTRACTION_PROMPT = """You are a Personal Information Organizer, specialized in accurately storing facts, user memories, and preferences. 

# [IMPORTANT]: GENERATE FACTS SOLELY BASED ON THE USER'S MESSAGES. DO NOT INCLUDE INFORMATION FROM ASSISTANT OR SYSTEM MESSAGES.

Types of Information to Remember:

1. Store Personal Preferences: Keep track of likes, dislikes, and specific preferences...
2. Maintain Important Personal Details: Remember significant personal information...
3. Track Plans and Intentions: Note upcoming events, trips, goals...
4. Remember Activity and Service Preferences...
5. Monitor Health and Wellness Preferences...
6. Store Professional Details...
7. Miscellaneous Information Management...

Here are some few shot examples:

User: Hi, my name is John. I am a software engineer.
Assistant: Nice to meet you, John! My name is Alex...
Output: {"facts": ["Name is John", "Is a Software engineer"]}

User: Me favourite movies are Inception and Interstellar. What are yours?
Assistant: Great choices! Both are fantastic movies. Mine are The Dark Knight...
Output: {"facts": ["Favourite movies are Inception and Interstellar"]}

Return the facts and preferences in a JSON format as shown above.

Remember:
- Today's date is {datetime.now().strftime("%Y-%m-%d")}.
- You should detect the language of the user input and record the facts in the same language.
"""
```

#### Agent 记忆提取 Prompt

```python
AGENT_MEMORY_EXTRACTION_PROMPT = """You are an Assistant Information Organizer, specialized in accurately storing facts, preferences, and characteristics about the AI assistant from conversations.

# [IMPORTANT]: GENERATE FACTS SOLELY BASED ON THE ASSISTANT'S MESSAGES. DO NOT INCLUDE INFORMATION FROM USER OR SYSTEM MESSAGES.

Types of Information to Remember:

1. Assistant's Preferences: Keep track of likes, dislikes...
2. Assistant's Capabilities: Note any specific skills...
3. Assistant's Hypothetical Plans or Activities...
4. Assistant's Personality Traits...
5. Assistant's Approach to Tasks...
6. Assistant's Knowledge Areas...
7. Miscellaneous Information...

Example:
User: Me favourite movies are Inception and Interstellar. What are yours?
Assistant: Great choices! Both are fantastic movies. Mine are The Dark Knight and The Shawshank Redemption.
Output: {"facts": ["Favourite movies are Dark Knight and Shawshank Redemption"]}
"""
```

**关键设计点**：
1. ✅ 区分用户记忆和 Agent 记忆
2. ✅ 明确提取范围（只从特定角色提取）
3. ✅ 多语言支持（检测并保持原语言）
4. ✅ 丰富的示例（Few-shot Learning）

---

### 2.4 并发处理（性能优化）

**位置**：`mem0/memory/main.py`

Mem0 使用 `ThreadPoolExecutor` 实现向量存储和图谱构建的并发执行。

```python
from concurrent.futures import ThreadPoolExecutor

def add(self, messages, ...):
    with ThreadPoolExecutor() as executor:
        # 并发执行
        future1 = executor.submit(self._add_to_vector_store, messages, ...)
        future2 = executor.submit(self._add_to_graph, messages, ...)
        
        # 等待完成
        concurrent.futures.wait([future1, future2])
        
        vector_store_result = future1.result()
        graph_result = future2.result()
    
    if self.enable_graph:
        return {
            "results": vector_store_result,
            "relations": graph_result
        }
    
    return {"results": vector_store_result}
```

**优势**：
1. ✅ 不阻塞用户请求
2. ✅ 充分利用多核 CPU
3. ✅ 向量和图谱构建并行

---

### 2.5 多租户隔离

**位置**：`mem0/memory/main.py`

Mem0 使用 `user_id` + `agent_id` + `run_id` 实现多级隔离。

```python
def _build_filters_and_metadata(
    user_id: Optional[str] = None,
    agent_id: Optional[str] = None,
    run_id: Optional[str] = None,
    ...
) -> tuple[Dict[str, Any], Dict[str, Any]]:
    """构建过滤器和元数据"""
    
    base_metadata_template = {}
    effective_query_filters = {}
    
    # 至少需要一个 ID
    if not any([user_id, agent_id, run_id]):
        raise ValidationError("At least one of 'user_id', 'agent_id', or 'run_id' must be provided.")
    
    # 添加所有提供的 ID
    if user_id:
        base_metadata_template["user_id"] = user_id
        effective_query_filters["user_id"] = user_id
    
    if agent_id:
        base_metadata_template["agent_id"] = agent_id
        effective_query_filters["agent_id"] = agent_id
    
    if run_id:
        base_metadata_template["run_id"] = run_id
        effective_query_filters["run_id"] = run_id
    
    return base_metadata_template, effective_query_filters
```

**使用示例**：

```python
# 不同 Agent 的记忆隔离
memory.add("I prefer Italian cuisine", user_id="bob", agent_id="food-assistant")
memory.add("I'm allergic to peanuts", user_id="bob", agent_id="health-assistant")

# 查询时指定 Agent
food = memory.search("What food do I like?", user_id="bob", agent_id="food-assistant")
allergies = memory.search("What are my allergies?", user_id="bob", agent_id="health-assistant")
```

---

## 3. 设计模式总结

### 3.1 工厂模式

**位置**：`mem0/utils/factory.py`

Mem0 使用工厂模式创建各种组件。

```python
class EmbedderFactory:
    @staticmethod
    def create(provider, config, vector_store_config=None):
        if provider == "openai":
            return OpenAIEmbedding(config)
        elif provider == "azure_openai":
            return AzureOpenAIEmbedding(config)
        elif provider == "ollama":
            return OllamaEmbedding(config)
        # ... 更多 provider

class VectorStoreFactory:
    @staticmethod
    def create(provider, config):
        if provider == "qdrant":
            return Qdrant(config)
        elif provider == "pinecone":
            return Pinecone(config)
        # ... 更多 provider

class LlmFactory:
    @staticmethod
    def create(provider, config):
        if provider == "openai":
            return OpenAILLM(config)
        elif provider == "azure_openai":
            return AzureOpenAILLM(config)
        # ... 更多 provider
```

**优势**：
- ✅ 解耦：组件创建和使用分离
- ✅ 扩展：添加新 provider 很简单
- ✅ 配置驱动：通过配置选择组件

---

### 3.2 策略模式

不同的 LLM Provider、Embedder、Vector Store 都实现了相同的接口，可以互相替换。

```python
# 所有 Embedder 都实现相同的接口
class EmbedderBase:
    def embed(self, text: str, action: str) -> List[float]:
        """生成文本的 embedding"""
        pass

# 所有 LLM 都实现相同的接口
class LLMBase:
    def generate_response(self, messages, tools=None, response_format=None):
        """生成响应"""
        pass
```

---

### 3.3 配置对象模式

使用 Pydantic 模型定义配置，提供类型安全和验证。

```python
from pydantic import BaseModel, Field

class MemoryConfig(BaseModel):
    vector_store: VectorStoreConfig = Field(default_factory=VectorStoreConfig)
    llm: LlmConfig = Field(default_factory=LlmConfig)
    embedder: EmbedderConfig = Field(default_factory=EmbedderConfig)
    graph_store: GraphStoreConfig = Field(default_factory=GraphStoreConfig)
    reranker: Optional[RerankerConfig] = Field(default=None)
    version: str = Field(default="v1.1")
    custom_fact_extraction_prompt: Optional[str] = Field(default=None)
```

**优势**：
- ✅ 类型安全
- ✅ 默认值管理
- ✅ 验证逻辑
- ✅ IDE 支持

---

## 4. 技术亮点

### 4.1 1. Function Calling 机制

**核心价值**：结构化输出，格式稳定

**实现方式**：
```python
# 定义工具
tools = [EXTRACT_ENTITIES_TOOL, RELATIONS_TOOL]

# 调用 LLM
response = llm.generate_response(
    messages=[...],
    tools=tools
)

# 解析工具调用
for tool_call in response["tool_calls"]:
    if tool_call["name"] == "extract_entities":
        entities = tool_call["arguments"]["entities"]
```

**优势**：
- 格式稳定，不会因为 LLM 输出格式变化而失败
- 支持复杂操作（多个工具组合）
- 类型安全（parameters 有 schema）

---

### 4.2 智能记忆更新

**核心价值**：LLM 判断是否需要更新，而不是简单匹配

**实现方式**：
```
新事实 + 旧记忆 → LLM 判断 → ADD/UPDATE/DELETE/NONE
```

**示例**：
```
旧记忆：[{"id": "0", "text": "User likes pizza"}]
新事实：["User loves pizza with pepperoni"]
LLM 判断：UPDATE（"likes" → "loves with pepperoni"）
```

---

### 4.3 多租户隔离

**核心价值**：灵活的隔离级别

**实现方式**：
```python
# 用户级别隔离
memory.add("...", user_id="user_123")

# Agent 级别隔离
memory.add("...", user_id="user_123", agent_id="food-bot")

# Run 级别隔离
memory.add("...", user_id="user_123", run_id="session_456")
```

---

### 4.4 并发处理

**核心价值**：性能优化

**实现方式**：
```python
with ThreadPoolExecutor() as executor:
    future1 = executor.submit(vector_store_add, ...)
    future2 = executor.submit(graph_build, ...)
    concurrent.futures.wait([future1, future2])
```

---

### 4.5 Prompt 工程

**核心价值**：精准提取

**亮点**：
1. 区分用户记忆和 Agent 记忆
2. 明确提取范围（只从特定角色提取）
3. 多语言支持
4. 丰富的示例（Few-shot Learning）

---

## 5. 可借鉴的设计

### 5.1 必须借鉴

#### 1. Function Calling 机制

**为什么**：结构化输出，格式稳定

**如何借鉴**：
```python
# 定义工具
GRAPH_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "add_relation",
            "parameters": {
                "type": "object",
                "properties": {
                    "source": {"type": "string"},
                    "destination": {"type": "string"},
                    "relationship": {"type": "string"}
                },
                "required": ["source", "destination", "relationship"]
            }
        }
    }
]

# 调用 LLM
response = llm.generate_response(
    messages=[...],
    tools=GRAPH_TOOLS
)
```

---

#### 2. 智能记忆更新

**为什么**：更智能的更新逻辑

**如何借鉴**：
```python
# 使用 LLM 判断是否需要更新
prompt = f"""
Old Memory: {existing_memories}
New Facts: {new_facts}

Decide whether to ADD, UPDATE, DELETE, or NONE for each fact.
"""

response = llm.generate_response(
    messages=[{"role": "user", "content": prompt}],
    response_format={"type": "json_object"}
)
```

---

#### 3. 多租户隔离

**为什么**：灵活的隔离级别

**如何借鉴**：
```python
# 支持 user_id + agent_id + run_id
filters = {}
if user_id:
    filters["user_id"] = user_id
if agent_id:
    filters["agent_id"] = agent_id
if run_id:
    filters["run_id"] = run_id

# 查询时应用过滤器
results = db.query("...", filters=filters)
```

---

### 5.2 可选借鉴

#### 1. 工厂模式

**为什么**：解耦组件创建

**如何借鉴**：
```python
class GraphStoreFactory:
    @staticmethod
    def create(provider, config):
        if provider == "postgres":
            return PostgresGraphStore(config)
        elif provider == "neo4j":
            return Neo4jGraphStore(config)
```

---

#### 2. 配置对象模式

**为什么**：类型安全

**如何借鉴**：
```python
from pydantic import BaseModel

class GraphConfig(BaseModel):
    enable_graph: bool = True
    threshold: float = 0.7
    custom_prompt: Optional[str] = None
```

---

### 5.3 不借鉴的部分

#### 1. 硬过滤

**问题**：Mem0 使用硬过滤，可能漏记忆

**我们的方案**：软过滤（提升权重，不排除）

---

#### 2. 无用户确认

**问题**：Mem0 没有用户确认机制，容易出错累积

**我们的方案**：智能确认（新实体、低置信度、关系冲突时确认）

---

## 6. 存在的问题与改进建议

### 6.1 Mem0 的问题

| 问题 | 影响 | 我们的改进方案 |
|------|------|--------------|
| **无用户确认** | 错误累积 | 智能确认机制 |
| **硬过滤** | 漏记忆 | 软过滤（提升权重） |
| **英文为主** | 中文支持不足 | jieba + 中文规则 |
| **需要 Neo4j** | 部署复杂 | PostgreSQL 统一存储 |

---

### 6.2 改进建议

#### 1. 添加智能确认机制

```python
async def should_confirm(self, entity, relations):
    """判断是否需要用户确认"""
    
    # 1. 新实体首次出现
    if entity not in existing_entities:
        return {
            "type": "new_entity",
            "question": f"发现新{entity_type}：'{entity}'，这是谁/什么？"
        }
    
    # 2. 置信度过低
    if confidence < 0.6:
        return {
            "type": "low_confidence",
            "question": f"对'{entity}'的识别置信度较低（{confidence:.0%}），确认吗？"
        }
    
    # 3. 关系冲突
    if has_conflict(old_relation, new_relation):
        return {
            "type": "relation_conflict",
            "question": f"'{entity}'之前是'{old_relation}'，现在是'{new_relation}'，更新吗？"
        }
    
    return None
```

---

#### 2. 使用软过滤

```python
async def apply_soft_filter(self, results, filter_value):
    """软过滤：提升权重，不排除"""
    
    for result in results:
        if filter_value in result.get("location", ""):
            result["similarity"] += 0.15  # 匹配提升权重
        elif filter_value in result.get("content", ""):
            result["similarity"] += 0.08  # 内容匹配中度提升
    
    # 重新排序
    results.sort(key=lambda x: x["similarity"], reverse=True)
    return results
```

---

#### 3. 中文优化

```python
# 人物关系规则
PERSON_RELATIONS = {
    "家人": ["老婆", "老公", "孩子", "父母", "儿子", "女儿", "妻子", "丈夫"],
    "朋友": ["老王", "小张", "张三"],
    "同事": ["小李", "王经理"]
}

# 地点归一化
LOCATION_NORMALIZATION = {
    "星巴克": "咖啡店",
    "麦当劳": "快餐店",
    "肯德基": "快餐店"
}

# 扩展关系
def expand_relation(person_type):
    """扩展关系词"""
    return PERSON_RELATIONS.get(person_type, [person_type])
```

---

## 7. 总结

### 7.1 Mem0 的核心价值

1. ✅ **Function Calling**：结构化输出，格式稳定
2. ✅ **智能更新**：LLM 判断更新操作
3. ✅ **Prompt 工程**：精准提取，多语言支持
4. ✅ **并发处理**：性能优化
5. ✅ **多租户隔离**：灵活的隔离级别

### 7.2 我们的创新点

1. ✅ **智能确认机制**：避免错误累积
2. ✅ **软过滤**：不漏记忆
3. ✅ **中文优化**：jieba + 中文规则
4. ✅ **关系扩展**：语义增强
5. ✅ **PostgreSQL 统一存储**：部署简单

### 7.3 最终方案

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

**研究成果应用**：基于本报告，我们已经优化了设计方案 v2.0，详见 `MEMORY_NETWORK_DESIGN_V2.md`
