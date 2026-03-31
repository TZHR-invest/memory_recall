# Mem0 调研报告

> 调研日期：2026-03-19
> 调研目标：了解 Mem0 的架构设计和核心功能，为 memory_recall 项目提供参考

---

## 1. 项目概述

### 1.1 基本信息

| 项目 | 信息 |
|------|------|
| **名称** | Mem0 (mem-zero) |
| **GitHub** | https://github.com/mem0ai/mem0 |
| **Star** | 20,000+ ⭐ |
| **开源协议** | Apache 2.0 |
| **定位** | Universal memory layer for AI Agents |
| **核心价值** | 为 AI Agent 提供长期记忆能力 |

### 1.2 核心优势

| 指标 | 数据 |
|------|------|
| **准确率** | 比 OpenAI Memory 高 26%（LOCOMO 基准测试）|
| **响应速度** | 比全上下文快 91% |
| **Token 消耗** | 比全上下文少 90% |

### 1.3 产品形态

Mem0 提供三种产品形态：

| 产品 | 说明 | 适用场景 |
|------|------|---------|
| **Mem0 Platform** | 托管服务 | 开箱即用，无需运维 |
| **Mem0 Open Source** | 自托管 | 数据可控，可定制 |
| **OpenMemory** | 团队协作 | 多 Agent 共享记忆 |

---

## 2. 核心架构

### 2.1 整体架构

```
用户输入（对话/文本）
    ↓
┌─────────────────────────────────────────┐
│  Mem0 Memory Layer                       │
│                                          │
│  ┌────────────────────────────────────┐ │
│  │  提取层（Extraction LLM）           │ │
│  │  - 实体识别（人物、地点、事件）      │ │
│  │  - 关系推理（谁和谁、在哪儿）        │ │
│  │  - 时间戳提取                       │ │
│  └────────────────────────────────────┘ │
│              ↓                           │
│  ┌─────────────┐    ┌────────────────┐  │
│  │ Vector Store │    │  Graph Store   │  │
│  │ (Qdrant/     │    │ (Neo4j/        │  │
│  │  Pinecone)   │    │  Memgraph)     │  │
│  └─────────────┘    └────────────────┘  │
│         ↓                    ↓           │
│  ┌────────────────────────────────────┐ │
│  │  检索层（Retrieval）                │ │
│  │  - 向量相似度搜索                    │ │
│  │  - 图谱关联查询                      │ │
│  │  - 重排序（Reranker）               │ │
│  └────────────────────────────────────┘ │
└─────────────────────────────────────────┘
    ↓
AI Agent 使用记忆
```

### 2.2 默认组件

| 组件 | 默认值 | 可替换 |
|------|--------|--------|
| **LLM** | OpenAI `gpt-4.1-nano-2025-04-14` | ✅ 支持多种 LLM |
| **Embeddings** | OpenAI `text-embedding-3-small` | ✅ 支持多种模型 |
| **Vector Store** | Qdrant (本地 `/tmp/qdrant`) | ✅ 支持多种向量库 |
| **Graph Store** | 无（需配置） | ✅ Neo4j/Memgraph/Neptune/Kuzu |
| **History Store** | SQLite (`~/.mem0/history.db`) | ✅ PostgreSQL/MySQL |
| **Reranker** | 无（需配置） | ✅ 支持多种 Reranker |

---

## 3. Graph Memory - 核心功能

### 3.1 功能说明

Graph Memory 是 Mem0 的核心功能，为记忆增加图谱能力：

**解决的问题**：
- ✅ 对话历史中包含多个角色和对象，向量检索容易混淆
- ✅ 合规和审计需求，需要图谱记录谁在何时说了什么
- ✅ Agent 团队需要共享上下文，避免重复记忆

**工作流程**：

```
1. 提取实体和关系
   用户输入: "Alice met Bob at GraphConf 2025 in San Francisco"
   提取结果:
     - 实体: [Alice, Bob, GraphConf 2025, San Francisco]
     - 关系: [(Alice, met, Bob), (Alice, at, GraphConf), (GraphConf, in, San Francisco)]

2. 存储向量和边
   - 向量存储: Qdrant/Pinecone
   - 图存储: Neo4j/Memgraph

3. 检索时增强
   查询: "Who did Alice meet at GraphConf?"
   结果:
     - 向量搜索: [Alice met Bob at GraphConf 2025]
     - 图关联: [(Alice, Bob), (GraphConf, San Francisco)]
```

### 3.2 代码示例

```python
from mem0 import Memory
import os

# 配置 Graph Memory
config = {
    "graph_store": {
        "provider": "neo4j",
        "config": {
            "url": os.environ["NEO4J_URL"],
            "username": os.environ["NEO4J_USERNAME"],
            "password": os.environ["NEO4J_PASSWORD"],
            "database": "neo4j",
        }
    }
}

memory = Memory.from_config(config)

# 添加记忆
conversation = [
    {"role": "user", "content": "Alice met Bob at GraphConf 2025 in San Francisco."},
    {"role": "assistant", "content": "Great! Logging that connection."},
]

memory.add(conversation, user_id="demo-user")

# 搜索记忆
results = memory.search(
    "Who did Alice meet at GraphConf?",
    user_id="demo-user",
    limit=3,
    rerank=True
)

for hit in results["results"]:
    print(hit["memory"])
    # 输出: Alice met Bob at GraphConf 2025
```

### 3.3 图谱查询

```cypher
# Neo4j 查询示例
MATCH (p:Person)-[r]->(q:Person)
RETURN p, r, q
LIMIT 5;

# 清理过期节点
MATCH (n)
WHERE n.lastSeen < date() - duration('P90D')
DETACH DELETE n;
```

---

## 4. 核心特性

### 4.1 实体提取

**提取方式**：使用 LLM 自动提取

**提取内容**：
- 人物（Person）
- 地点（Location）
- 组织（Organization）
- 事件（Event）
- 时间（Time）

**可定制**：
```python
# 自定义提取 Prompt
config = {
    "graph_store": {
        "provider": "neo4j",
        "config": {
            "url": "...",
            "username": "...",
            "password": "...",
        },
        "custom_prompt": "Please only capture people, organisations, and project links.",
    }
}
```

### 4.2 关系推理

**推理方式**：LLM 自动推理

**关系类型**：
- 人物关系：met, friend, colleague, family
- 地点关系：at, in, near
- 事件关系：related_to, caused_by

**置信度过滤**：
```python
# 设置置信度阈值（0.75 = 75%）
config["graph_store"]["config"]["threshold"] = 0.75
```

### 4.3 混合检索

**检索流程**：
```
用户查询
    ↓
1. 向量相似度搜索（候选记忆）
    ↓
2. 图谱关联查询（相关实体）
    ↓
3. 重排序（可选）
    ↓
返回结果 + 关联信息
```

**返回结构**：
```json
{
  "results": [
    {
      "memory": "Alice met Bob at GraphConf 2025",
      "score": 0.95,
      "metadata": {...}
    }
  ],
  "relations": [
    {
      "source": "Alice",
      "target": "Bob",
      "relationship": "met",
      "created_at": "2025-03-19"
    }
  ]
}
```

### 4.4 多租户支持

**支持的隔离级别**：
- `user_id`: 用户级别
- `agent_id`: Agent 级别
- `run_id`: 会话级别

**示例**：
```python
# 不同 Agent 的记忆隔离
memory.add("I prefer Italian cuisine", user_id="bob", agent_id="food-assistant")
memory.add("I'm allergic to peanuts", user_id="bob", agent_id="health-assistant")

# 查询时指定 Agent
food = memory.search("What food do I like?", user_id="bob", agent_id="food-assistant")
allergies = memory.search("What are my allergies?", user_id="bob", agent_id="health-assistant")
```

### 4.5 开关控制

**按需启用**：
```python
# 添加时禁用图谱
memory.add(messages, user_id="demo-user", enable_graph=False)

# 搜索时禁用图谱
results = memory.search("marketing partners", user_id="demo-user", enable_graph=False)
```

---

## 5. 支持的后端

### 5.1 向量存储

| 存储类型 | 说明 | 适用场景 |
|---------|------|---------|
| **Qdrant** | 默认，本地部署 | 开发测试 |
| **Pinecone** | 云服务 | 生产环境 |
| **Weaviate** | 开源 | 自托管 |
| **Chroma** | 轻量级 | 小规模 |

### 5.2 图数据库

| 数据库 | 说明 | 适用场景 |
|--------|------|---------|
| **Neo4j** | 企业级，功能强大 | 大规模生产 |
| **Memgraph** | 内存优先，快速 | 实时查询 |
| **Neptune** | AWS 托管 | 云原生 |
| **Kuzu** | 嵌入式，轻量级 | 小规模，开发测试 |

---

## 6. 与我们的方案对比

### 6.1 功能对比

| 功能 | Mem0 | 我们的方案 | 说明 |
|------|------|-----------|------|
| **实体提取** | ✅ LLM 自动提取 | ✅ NER + LLM | 类似 |
| **关系推理** | ✅ LLM 自动推理 | ✅ LLM + 规则 | 我们多了规则 |
| **向量检索** | ✅ 支持 | ✅ 已有 | 一致 |
| **图谱检索** | ✅ 支持 | ✅ 设计中 | 类似 |
| **用户确认** | ❌ 无 | ✅ 智能确认 | **我们的优势** |
| **软过滤** | ❌ 硬过滤 | ✅ 软过滤 | **我们的优势** |
| **关系扩展** | ❌ 无 | ✅ "家人"→["老婆","孩子"] | **我们的优势** |
| **中文优化** | ⚠️ 英文为主 | ✅ jieba + 中文规则 | **我们的优势** |
| **多租户** | ✅ 支持 | ✅ 支持 | 一致 |

### 6.2 架构对比

| 维度 | Mem0 | 我们的方案 |
|------|------|-----------|
| **数据存储** | Qdrant + Neo4j | PostgreSQL + pgvector |
| **LLM** | OpenAI | 火山引擎 Doubao |
| **NER** | LLM | jieba + LLM |
| **部署复杂度** | ⚠️ 需要多个组件 | ✅ 单一数据库 |
| **学习曲线** | ⚠️ 需要学习新 API | ✅ 基于现有代码 |

### 6.3 优劣对比

**Mem0 优势**：
- ✅ 开箱即用，快速集成
- ✅ 成熟稳定，社区活跃
- ✅ 支持多种后端
- ✅ 文档完善

**Mem0 劣势**：
- ❌ 没有用户确认机制（容易出错）
- ❌ 主要是英文优化
- ❌ 硬过滤，可能漏记忆
- ❌ 需要额外部署图数据库（Neo4j）

**我们的方案优势**：
- ✅ 智能确认机制，避免错误
- ✅ 中文优化（jieba + 中文规则）
- ✅ 软过滤，不漏记忆
- ✅ 关系扩展（"家人"→["老婆","孩子"]）
- ✅ 基于现有代码，无需重构
- ✅ 单一数据库（PostgreSQL），部署简单

---

## 7. 可借鉴的设计

### 7.1 实体提取

**Mem0 的方式**：
- 使用 LLM 自动提取实体和关系
- 可自定义提取 Prompt
- 支持置信度过滤

**我们可以借鉴**：
```python
# 自定义提取 Prompt
EXTRACTION_PROMPT = """
从以下文本中提取实体和关系：

文本：{text}

请提取：
1. 人物（姓名、称呼）
2. 地点（具体地点、位置）
3. 事件（发生了什么）
4. 时间（什么时候）

输出格式：
{
  "entities": [...],
  "relations": [...],
  "confidence": 0.0-1.0
}
"""
```

### 7.2 图谱存储

**Mem0 的方式**：
- 向量存储 + 图数据库
- 支持 Neo4j、Memgraph、Neptune、Kuzu

**我们可以借鉴**：
- 继续使用 PostgreSQL + pgvector（已有）
- 新增图谱表（entities, relations, memory_entities）
- 无需额外部署图数据库

### 7.3 混合检索

**Mem0 的方式**：
- 向量搜索获取候选
- 图谱查询获取关联
- 返回结果 + 关联信息

**我们可以借鉴**：
```python
async def hybrid_recall(query: str):
    # 1. 向量搜索
    vector_results = await vector_search(query)
    
    # 2. 图谱关联
    graph_relations = await graph_query(vector_results)
    
    # 3. 返回增强结果
    return {
        "results": vector_results,
        "relations": graph_relations
    }
```

### 7.4 多租户隔离

**Mem0 的方式**：
- user_id + agent_id + run_id

**我们可以借鉴**：
- 已有 user_id
- 新增 agent_id（可选）
- 支持记忆隔离

---

## 8. 不适合我们的部分

### 8.1 无用户确认

**Mem0 的问题**：
- 完全自动提取，容易出错
- 例如："老王"可能被识别为"王"（错误）
- 没有确认机制，错误会累积

**我们的方案**：
- 智能确认机制
- 新实体、新关系、关系冲突时提示用户
- 用户反馈可以纠错

### 8.2 英文优化

**Mem0 的问题**：
- 主要是英文优化
- 中文支持不够好

**我们的方案**：
- jieba 中文分词
- 中文人物关系规则（"老王"→"朋友"）
- 中文地点归一化（"星巴克"→"咖啡店"）

### 8.3 硬过滤

**Mem0 的问题**：
- 图谱查询是硬过滤
- 可能漏掉相关记忆

**我们的方案**：
- 软过滤（提升权重，不排除）
- 避免漏记忆

---

## 9. 实施建议

### 9.1 短期（Phase 1）

**建议**：
- ✅ 借鉴 Mem0 的实体提取 Prompt
- ✅ 借鉴 Mem0 的图谱存储设计
- ✅ 使用我们的智能确认机制
- ✅ 使用我们的软过滤机制

**工作量**：2-3 天

### 9.2 中期（Phase 2）

**建议**：
- ✅ 实现关系推理和图谱构建
- ✅ 实现混合检索
- ✅ 保持 PostgreSQL 单一数据库（无需 Neo4j）

**工作量**：5-7 天

### 9.3 长期（Phase 3）

**建议**：
- 如果数据量 > 10万，考虑迁移到 Neo4j
- 如果需要更强大的图谱查询，学习 Cypher 语法

**工作量**：按需

---

## 10. 总结

### 10.1 Mem0 的价值

- ✅ 成熟的记忆管理方案
- ✅ 开箱即用，快速集成
- ✅ Graph Memory 功能强大
- ✅ 社区活跃，文档完善

### 10.2 我们的优势

- ✅ 智能确认机制（避免错误）
- ✅ 中文优化
- ✅ 软过滤（不漏记忆）
- ✅ 关系扩展
- ✅ 基于现有代码（无需重构）

### 10.3 最终建议

**采用混合策略**：

```
我们的方案 = Mem0 的架构设计
          + Mem0 的实体提取思路
          + 我们的智能确认（创新）
          + 我们的软过滤（创新）
          + 我们的中文优化（创新）
          + PostgreSQL（简化部署）
```

**关键决策**：
1. ✅ 不使用 Mem0 代码，自己实现
2. ✅ 借鉴 Mem0 的设计思路
3. ✅ 使用 PostgreSQL，不部署 Neo4j
4. ✅ 保持我们的创新点（确认、软过滤、中文优化）

---

**调研结论**：Mem0 是一个优秀的记忆管理方案，值得借鉴其架构设计和核心功能，但我们的方案在用户确认、中文优化、软过滤等方面有独特优势，更适合中文场景和高质量要求的应用。
