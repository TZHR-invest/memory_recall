# AI Agent 记忆召回服务设计文档 v2.0

> **版本：** v2.0  
> **日期：** 2026-03-26  
> **状态：** 设计完成  
> **定位：** 在现有混合召回系统基础上，扩展 Lossless DAG 压缩能力，实现无限上下文管理

---

## 一、项目概述

### 1.1 核心定位

**Memory Recall v2.0 = 原有混合召回能力 + Lossless DAG 压缩**

```
┌─────────────────────────────────────────────────────────────────────┐
│                    Memory Recall v2.0 架构                          │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                    原有能力（保留）                           │   │
│  │  ✅ 向量检索（HNSW 索引）                                     │   │
│  │  ✅ 关键词检索（PostgreSQL FTS）                              │   │
│  │  ✅ 图谱检索（实体-关系-记忆）                                 │   │
│  │  ✅ 混合召回策略                                              │   │
│  │  ✅ Function Calling 实体提取                                 │   │
│  │  ✅ 多用户 Schema 隔离                                        │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                              +                                      │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                    新增能力（扩展）                           │   │
│  │  🆕 Raw Immutable 消息层（永不丢失）                          │   │
│  │  🆕 DAG 压缩（三阶段：normal→aggressive→fallback）            │   │
│  │  🆕 Context 动态组装（基于 context_items）                    │   │
│  │  🆕 DAG 展开工具（lcm_grep/lcm_describe/lcm_expand）          │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                              =                                      │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                    融合能力                                   │   │
│  │  🔗 摘要节点参与混合召回（向量+图谱）                          │   │
│  │  🔗 压缩时自动提取实体，建立图谱关联                           │   │
│  │  🔗 召回结果可展开查看原始内容                                 │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### 1.2 核心指标

| 指标 | 目标值 | 说明 |
|------|--------|------|
| 召回延迟（P95） | < 200ms | 混合召回 |
| Context 组装延迟 | < 150ms | DAG 组装 |
| 压缩成功率 | > 95% | 三阶段兜底 |
| 原始数据保留率 | 100% | Raw 消息永不删除 |

---

## 二、核心架构

### 2.1 四层记忆架构

```
┌────────────────────────────────────────────────────────────────────┐
│ Layer 4: Context Assembly（上下文组装层）                           │
│ ┌────────────────────────────────────────────────────────────────┐ │
│ │  context_items 表：有序序列（message + summary 混合）           │ │
│ │  → 按 token 预算选择 + 保护 fresh tail                         │ │
│ │  → 输出：AgentMessage[] 给 LLM                                 │ │
│ └────────────────────────────────────────────────────────────────┘ │
└────────────────────────────────────────────────────────────────────┘
                              ↑ 组装
┌────────────────────────────────────────────────────────────────────┐
│ Layer 3: Semantic Memory（语义记忆层）                              │
│ ┌────────────────────────────────────────────────────────────────┐ │
│ │  summaries 表（condensed, depth > 0）                          │ │
│ │  - 高层摘要，永久保存                                           │ │
│ │  - 参与向量召回 + 图谱关联                                       │ │
│ └────────────────────────────────────────────────────────────────┘ │
└────────────────────────────────────────────────────────────────────┘
                              ↑ 压缩
┌────────────────────────────────────────────────────────────────────┐
│ Layer 2: Episodic Memory（情景记忆层）                              │
│ ┌────────────────────────────────────────────────────────────────┐ │
│ │  summaries 表（leaf, depth = 0）                               │ │
│ │  - 叶级摘要，保留 30-90 天                                      │ │
│ │  - 参与向量召回 + 图谱关联                                       │ │
│ └────────────────────────────────────────────────────────────────┘ │
└────────────────────────────────────────────────────────────────────┘
                              ↑ 压缩
┌────────────────────────────────────────────────────────────────────┐
│ Layer 1: Raw Messages（原始消息层）【新增】                         │
│ ┌────────────────────────────────────────────────────────────────┐ │
│ │  raw_messages 表：永久保存，永不删除                            │ │
│ │  - 每条 user/assistant 消息完整存储                             │ │
│ │  - 作为 DAG 展开的最终数据源                                    │ │
│ └────────────────────────────────────────────────────────────────┘ │
└────────────────────────────────────────────────────────────────────┘
```

### 2.2 数据流向图

```
┌─────────────────────────────────────────────────────────────────────┐
│                         完整数据流向                                 │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  【写入流程】                                                        │
│                                                                     │
│  用户消息 ──→ raw_messages 表（永久存储）                            │
│       │                                                             │
│       ├──→ 实体提取（原有能力）──→ entities / relations 表          │
│       │                                                             │
│       └──→ context_items 表（追加）                                 │
│                    │                                                │
│                    ↓                                                │
│              触发压缩？                                              │
│                    │                                                │
│          ┌────────┴────────┐                                       │
│          ↓ 是              ↓ 否                                    │
│      Leaf 压缩         等待下次                                     │
│          │                                                          │
│          ↓                                                          │
│      summaries 表（leaf）                                           │
│          │                                                          │
│          ├──→ 生成 embedding（用于向量召回）                        │
│          │                                                          │
│          └──→ 提取实体 → summary_entities 表（用于图谱召回）        │
│                                                                     │
│  ───────────────────────────────────────────────────────────────   │
│                                                                     │
│  【召回流程】                                                        │
│                                                                     │
│  用户查询 ──→ 向量召回 ──┐                                          │
│              关键词召回 ─┼──→ 融合排序 ──→ 返回结果                  │
│              图谱召回 ──┘           │                               │
│       （同时搜索 raw_messages,      │                               │
│        summaries, memories）        ↓                               │
│                              结果包含摘要？                          │
│                                    │                                │
│                           ┌────────┴────────┐                      │
│                           ↓ 是              ↓ 否                   │
│                       DAG 展开         直接返回                     │
│                           │                                         │
│                           ↓                                         │
│                     raw_messages                                    │
│                                                                     │
│  ───────────────────────────────────────────────────────────────   │
│                                                                     │
│  【组装流程】                                                        │
│                                                                     │
│  Context 请求 ──→ context_items 表                                  │
│                         │                                           │
│                         ↓                                           │
│                  解析每个 item                                       │
│                  （message/summary）                                 │
│                         │                                           │
│                         ↓                                           │
│                  按 token 预算选择                                   │
│                  + 保护 fresh tail                                   │
│                         │                                           │
│                         ↓                                           │
│                  输出 AgentMessage[]                                 │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 三、数据模型

### 3.1 表结构总览

| 表名 | 类型 | 说明 |
|------|------|------|
| `raw_messages` | **新增** | 原始消息，永久存储 |
| `summaries` | **新增** | DAG 摘要节点（leaf + condensed） |
| `summary_messages` | **新增** | 摘要-消息关系 |
| `summary_parents` | **新增** | 摘要-摘要关系（DAG） |
| `summary_entities` | **新增** | 摘要-实体关系（图谱关联） |
| `context_items` | **新增** | 有序上下文序列 |
| `memories` | **保留** | 原有记忆表（兼容） |
| `entities` | **保留** | 原有实体表 |
| `relations` | **保留** | 原有关系表 |
| `memory_entities` | **保留** | 原有记忆-实体关系 |

### 3.2 新增表定义

#### 3.2.1 raw_messages 表

```sql
-- 原始消息表：永久存储，永不删除
CREATE TABLE raw_messages (
    id VARCHAR(24) PRIMARY KEY,
    agent_id VARCHAR(100) NOT NULL,
    session_id VARCHAR(100),
    
    -- 消息内容
    role VARCHAR(20) NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content TEXT NOT NULL,
    token_count INTEGER DEFAULT 0,
    
    -- 向量嵌入（用于语义召回）
    embedding VECTOR(1024),
    
    -- 元数据
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    is_archived BOOLEAN DEFAULT FALSE
);

-- 索引
CREATE INDEX idx_raw_messages_agent_session 
    ON raw_messages(agent_id, session_id, created_at DESC);
CREATE INDEX idx_raw_messages_embedding 
    ON raw_messages USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
```

#### 3.2.2 summaries 表

```sql
-- 摘要节点表：存储 DAG 结构
CREATE TABLE summaries (
    summary_id VARCHAR(24) PRIMARY KEY,
    agent_id VARCHAR(100) NOT NULL,
    session_id VARCHAR(100),
    
    -- 节点类型
    kind VARCHAR(20) NOT NULL CHECK (kind IN ('leaf', 'condensed')),
    depth INTEGER NOT NULL DEFAULT 0,
    
    -- 内容
    content TEXT NOT NULL,
    token_count INTEGER NOT NULL DEFAULT 0,
    
    -- 向量嵌入（用于语义召回）
    embedding VECTOR(1024),
    
    -- 统计字段
    earliest_at TIMESTAMP WITH TIME ZONE,
    latest_at TIMESTAMP WITH TIME ZONE,
    descendant_count INTEGER NOT NULL DEFAULT 0,
    descendant_token_count INTEGER NOT NULL DEFAULT 0,
    source_message_token_count INTEGER NOT NULL DEFAULT 0,
    
    -- 元数据
    model VARCHAR(100) DEFAULT 'unknown',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    -- 兼容原有字段
    importance_score FLOAT DEFAULT 0.5
);

-- 索引
CREATE INDEX idx_summaries_agent_session 
    ON summaries(agent_id, session_id, created_at DESC);
CREATE INDEX idx_summaries_embedding 
    ON summaries USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
```

#### 3.2.3 summary_messages 表

```sql
-- 摘要-消息关系表：leaf 摘要引用的原始消息
CREATE TABLE summary_messages (
    summary_id VARCHAR(24) NOT NULL REFERENCES summaries(summary_id) ON DELETE CASCADE,
    message_id VARCHAR(24) NOT NULL REFERENCES raw_messages(id) ON DELETE RESTRICT,
    ordinal INTEGER NOT NULL,
    PRIMARY KEY (summary_id, message_id)
);
```

#### 3.2.4 summary_parents 表

```sql
-- 摘要-父摘要关系表：DAG 结构
-- 重要：parent_summary_id 是被压缩的节点，展开时向上遍历
CREATE TABLE summary_parents (
    summary_id VARCHAR(24) NOT NULL REFERENCES summaries(summary_id) ON DELETE CASCADE,
    parent_summary_id VARCHAR(24) NOT NULL REFERENCES summaries(summary_id) ON DELETE RESTRICT,
    ordinal INTEGER NOT NULL,
    PRIMARY KEY (summary_id, parent_summary_id)
);
```

#### 3.2.5 summary_entities 表

```sql
-- 摘要-实体关系表：用于图谱召回
CREATE TABLE summary_entities (
    summary_id VARCHAR(24) NOT NULL REFERENCES summaries(summary_id) ON DELETE CASCADE,
    entity_id UUID NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    role VARCHAR(50) DEFAULT 'mentioned',
    confidence FLOAT DEFAULT 0.8,
    PRIMARY KEY (summary_id, entity_id)
);

CREATE INDEX idx_summary_entities_entity ON summary_entities(entity_id);
```

#### 3.2.6 context_items 表

```sql
-- 上下文序列表：维护有序消息/摘要序列
CREATE TABLE context_items (
    agent_id VARCHAR(100) NOT NULL,
    session_id VARCHAR(100) NOT NULL,
    ordinal INTEGER NOT NULL,
    item_type VARCHAR(20) NOT NULL CHECK (item_type IN ('message', 'summary')),
    message_id VARCHAR(24) REFERENCES raw_messages(id) ON DELETE RESTRICT,
    summary_id VARCHAR(24) REFERENCES summaries(summary_id) ON DELETE RESTRICT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    PRIMARY KEY (agent_id, session_id, ordinal),
    CHECK (
        (item_type = 'message' AND message_id IS NOT NULL AND summary_id IS NULL) OR
        (item_type = 'summary' AND summary_id IS NOT NULL AND message_id IS NULL)
    )
);
```

---

## 四、核心服务

### 4.1 服务架构

```
┌─────────────────────────────────────────────────────────────────────┐
│                        服务架构图                                    │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                    AgentMemoryService                        │   │
│  │                    （统一入口服务）                           │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                              │                                      │
│         ┌────────────────────┼────────────────────┐                │
│         ↓                    ↓                    ↓                │
│  ┌─────────────┐     ┌─────────────┐     ┌─────────────┐          │
│  │ 写入服务     │     │ 召回服务     │     │ 组装服务     │          │
│  │ MemoryWriter│     │ MemoryRecall│     │ContextAsmblr│          │
│  └─────────────┘     └─────────────┘     └─────────────┘          │
│         │                    │                    │                │
│         ↓                    ↓                    ↓                │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                    底层服务                                  │   │
│  ├─────────────────────────────────────────────────────────────┤   │
│  │                                                              │   │
│  │  【原有服务】                    【新增服务】                  │   │
│  │  ┌─────────────────┐           ┌─────────────────┐          │   │
│  │  │ EntityExtractor │           │ RawMessageStore │          │   │
│  │  │ GraphBuilder    │           │ SummaryStore    │          │   │
│  │  │ VectorIndexer   │           │ DAGManager      │          │   │
│  │  │ HybridRecall    │           │ CompactionEng   │          │   │
│  │  └─────────────────┘           └─────────────────┘          │   │
│  │                                                              │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                              │                                      │
│                              ↓                                      │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                    数据存储                                  │   │
│  ├─────────────────────────────────────────────────────────────┤   │
│  │  PostgreSQL + pgvector                                       │   │
│  │  - raw_messages, summaries, context_items（新增）            │   │
│  │  - memories, entities, relations（原有）                     │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### 4.2 核心流程

#### 4.2.1 消息写入流程

```python
class MemoryWriter:
    """消息写入服务（融合原有能力 + 新增压缩）"""
    
    def __init__(self):
        # 原有服务
        self.entity_extractor = EntityExtractor()
        self.graph_builder = GraphBuilder()
        self.vector_indexer = VectorIndexer()
        
        # 新增服务
        self.raw_store = RawMessageStore()
        self.compaction_engine = CompactionEngine()
        self.context_store = ContextStore()
    
    async def write(
        self,
        agent_id: str,
        session_id: str,
        role: str,
        content: str
    ) -> Dict[str, Any]:
        """
        写入消息（融合流程）
        
        步骤：
        1. 存储原始消息（新增）
        2. 实体提取（原有）
        3. 更新图谱（原有）
        4. 生成向量嵌入（原有）
        5. 追加到 context_items（新增）
        6. 检查是否需要压缩（新增）
        """
        # 1. 存储原始消息
        raw_id = await self.raw_store.store(
            agent_id=agent_id,
            session_id=session_id,
            role=role,
            content=content
        )
        
        # 2. 实体提取（复用原有能力）
        entities, relations = await self.entity_extractor.extract(content)
        
        # 3. 更新图谱（复用原有能力）
        entity_ids = await self.graph_builder.save_entities(
            entities, agent_id
        )
        await self.graph_builder.save_relations(
            relations, entity_ids, agent_id
        )
        
        # 4. 生成向量嵌入
        embedding = await self.vector_indexer.embed(content)
        await self.raw_store.update_embedding(raw_id, embedding)
        
        # 5. 追加到 context_items
        await self.context_store.append_message(
            agent_id, session_id, raw_id
        )
        
        # 6. 检查是否需要压缩
        compaction_result = None
        if await self._should_compact(agent_id, session_id):
            compaction_result = await self.compaction_engine.leaf_compact(
                agent_id, session_id
            )
        
        return {
            "raw_message_id": raw_id,
            "entities": entities,
            "compaction_triggered": compaction_result is not None
        }
```

#### 4.2.2 混合召回流程

```python
class MemoryRecall:
    """混合召回服务（融合原有能力 + 摘要搜索）"""
    
    def __init__(self):
        # 原有服务
        self.vector_recall = VectorRecall()
        self.keyword_recall = KeywordRecall()
        self.graph_recall = GraphRecall()
        
        # 新增服务
        self.dag_manager = DAGManager()
    
    async def recall(
        self,
        query: str,
        agent_id: str,
        weights: Dict[str, float] = None
    ) -> List[Dict[str, Any]]:
        """
        混合召回（三路并行，扩展搜索摘要）
        """
        weights = weights or {"vector": 0.5, "keyword": 0.3, "graph": 0.2}
        
        # 并行三路召回（同时搜索 raw_messages, summaries, memories）
        vector_results, keyword_results, graph_results = await asyncio.gather(
            self._vector_recall_extended(query, agent_id),
            self._keyword_recall_extended(query, agent_id),
            self._graph_recall_extended(query, agent_id)
        )
        
        # 融合结果
        return self._merge_results(
            vector_results, keyword_results, graph_results, weights
        )
    
    async def _vector_recall_extended(
        self, query: str, agent_id: str
    ) -> List[Dict]:
        """向量召回（扩展：同时搜索摘要）"""
        query_embedding = await self.vector_recall.embed(query)
        
        results = []
        
        # 搜索原始消息
        raw_results = await db.fetch("""
            SELECT id, content, 1 - (embedding <=> $1) AS similarity
            FROM raw_messages
            WHERE agent_id = $2
            ORDER BY embedding <=> $1
            LIMIT 10
        """, query_embedding, agent_id)
        results.extend([
            {"type": "raw_message", "id": r["id"], "content": r["content"],
             "similarity": r["similarity"], "source": "vector"}
            for r in raw_results
        ])
        
        # 搜索摘要（★新增★）
        summary_results = await db.fetch("""
            SELECT summary_id, content, kind, depth,
                   1 - (embedding <=> $1) AS similarity
            FROM summaries
            WHERE agent_id = $2
            ORDER BY embedding <=> $1
            LIMIT 10
        """, query_embedding, agent_id)
        results.extend([
            {"type": "summary", "id": r["summary_id"], "content": r["content"],
             "kind": r["kind"], "depth": r["depth"],
             "similarity": r["similarity"], "source": "vector",
             "expandable": True}
            for r in summary_results
        ])
        
        return results
    
    async def _graph_recall_extended(
        self, query: str, agent_id: str
    ) -> List[Dict]:
        """图谱召回（扩展：通过实体找摘要）"""
        # 提取查询实体
        entities = await self._extract_query_entities(query)
        results = []
        
        for entity_name in entities:
            # 查找实体
            entity = await db.fetchrow("""
                SELECT id FROM entities 
                WHERE name ILIKE $1 AND user_id = (
                    SELECT user_id FROM agents WHERE agent_id = $2
                )
            """, f"%{entity_name}%", agent_id)
            
            if not entity:
                continue
            
            # 通过 memory_entities 找记忆（原有逻辑）
            memory_results = await db.fetch("""
                SELECT m.id, m.content
                FROM memories m
                JOIN memory_entities me ON me.memory_id = m.id
                WHERE me.entity_id = $1
                LIMIT 5
            """, entity["id"])
            results.extend([
                {"type": "memory", "id": r["id"], "content": r["content"],
                 "entity": entity_name, "source": "graph"}
                for r in memory_results
            ])
            
            # 通过 summary_entities 找摘要（★新增★）
            summary_results = await db.fetch("""
                SELECT s.summary_id, s.content, s.kind, s.depth
                FROM summaries s
                JOIN summary_entities se ON se.summary_id = s.summary_id
                WHERE se.entity_id = $1
                LIMIT 5
            """, entity["id"])
            results.extend([
                {"type": "summary", "id": r["summary_id"], "content": r["content"],
                 "kind": r["kind"], "depth": r["depth"],
                 "entity": entity_name, "source": "graph", "expandable": True}
                for r in summary_results
            ])
        
        return results
    
    async def expand_summary(
        self,
        summary_id: str,
        max_tokens: int = 5000
    ) -> List[Dict[str, Any]]:
        """
        展开摘要（新增能力）
        
        返回被压缩的原始消息或子摘要
        """
        summary = await db.fetchrow(
            "SELECT * FROM summaries WHERE summary_id = $1", summary_id
        )
        
        if not summary:
            return []
        
        if summary["kind"] == "leaf":
            # Leaf: 返回原始消息
            return await self._expand_leaf(summary_id, max_tokens)
        else:
            # Condensed: 返回子摘要
            return await self._expand_condensed(summary_id, max_tokens)
```

#### 4.2.3 Context 组装流程

```python
class ContextAssembler:
    """Context 组装服务（新增能力）"""
    
    async def assemble(
        self,
        agent_id: str,
        session_id: str,
        token_budget: int,
        fresh_tail_count: int = 8
    ) -> Dict[str, Any]:
        """
        组装上下文
        
        流程：
        1. 从 context_items 获取有序序列
        2. 分割 evictable 和 fresh tail
        3. 按 token 预算选择
        4. 解析每个 item 为 AgentMessage
        """
        # 1. 获取有序序列
        items = await db.fetch("""
            SELECT ordinal, item_type, message_id, summary_id
            FROM context_items
            WHERE agent_id = $1 AND session_id = $2
            ORDER BY ordinal
        """, agent_id, session_id)
        
        # 2. 分割
        tail_start = max(0, len(items) - fresh_tail_count)
        evictable = items[:tail_start]
        fresh_tail = items[tail_start:]
        
        # 3. 按 token 预算选择
        fresh_tokens = await self._count_tokens(fresh_tail)
        remaining_budget = token_budget - fresh_tokens
        
        selected = evictable
        if remaining_budget < 0:
            # fresh tail 超预算，全部保留
            selected = []
        else:
            # 从最新开始保留 evictable
            kept = []
            accum = 0
            for item in reversed(evictable):
                tokens = await self._get_item_tokens(item)
                if accum + tokens <= remaining_budget:
                    kept.append(item)
                    accum += tokens
                else:
                    break
            selected = list(reversed(kept))
        
        # 4. 合并并解析
        final_items = selected + fresh_tail
        messages = []
        
        for item in final_items:
            if item["item_type"] == "message":
                msg = await db.fetchrow(
                    "SELECT role, content FROM raw_messages WHERE id = $1",
                    item["message_id"]
                )
                messages.append({
                    "role": msg["role"],
                    "content": msg["content"]
                })
            else:
                summary = await db.fetchrow(
                    "SELECT content, kind, depth FROM summaries WHERE summary_id = $1",
                    item["summary_id"]
                )
                messages.append({
                    "role": "user",
                    "content": self._format_summary(summary)
                })
        
        return {
            "messages": messages,
            "estimated_tokens": fresh_tokens + accum,
            "stats": {
                "raw_message_count": sum(1 for i in final_items if i["item_type"] == "message"),
                "summary_count": sum(1 for i in final_items if i["item_type"] == "summary")
            }
        }
```

#### 4.2.4 压缩流程

```python
class CompactionEngine:
    """压缩引擎（新增能力，三阶段策略）"""
    
    async def leaf_compact(
        self,
        agent_id: str,
        session_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Leaf 压缩
        
        流程：
        1. 选择可压缩的消息块（保护 fresh tail）
        2. 三阶段压缩生成摘要
        3. 提取实体（复用原有能力）
        4. 存储摘要 + 建立关联
        5. 更新 context_items
        """
        # 1. 选择消息块
        chunk = await self._select_leaf_chunk(agent_id, session_id)
        if not chunk:
            return None
        
        # 2. 三阶段压缩
        source_text = self._format_messages(chunk["messages"])
        summary_result = await self._summarize_with_escalation(source_text)
        
        if not summary_result:
            return None
        
        summary_content, level = summary_result
        
        # 3. 提取实体（复用原有能力）
        entities = await self.entity_extractor.extract(summary_content)
        
        # 4. 存储摘要
        summary_id = generate_id("sum")
        embedding = await self.vector_indexer.embed(summary_content)
        
        await db.execute("""
            INSERT INTO summaries (
                summary_id, agent_id, session_id, kind, depth,
                content, token_count, embedding,
                earliest_at, latest_at, source_message_token_count
            ) VALUES ($1, $2, $3, 'leaf', 0, $4, $5, $6, $7, $8, $9)
        """,
            summary_id, agent_id, session_id,
            summary_content,
            self._estimate_tokens(summary_content),
            embedding,
            min(m["created_at"] for m in chunk["messages"]),
            max(m["created_at"] for m in chunk["messages"]),
            sum(m["token_count"] for m in chunk["messages"])
        )
        
        # 关联消息
        for idx, msg in enumerate(chunk["messages"]):
            await db.execute("""
                INSERT INTO summary_messages (summary_id, message_id, ordinal)
                VALUES ($1, $2, $3)
            """, summary_id, msg["id"], idx)
        
        # 关联实体
        for entity_info in entities:
            entity = await self._get_or_create_entity(agent_id, entity_info)
            await db.execute("""
                INSERT INTO summary_entities (summary_id, entity_id, confidence)
                VALUES ($1, $2, $3)
            """, summary_id, entity["id"], entity_info.get("confidence", 0.8))
        
        # 5. 更新 context_items
        await self._replace_with_summary(
            agent_id, session_id, chunk["ordinals"], summary_id
        )
        
        return {
            "summary_id": summary_id,
            "level": level,
            "compression_ratio": self._estimate_tokens(summary_content) / chunk["total_tokens"]
        }
    
    async def _summarize_with_escalation(
        self, source_text: str
    ) -> Optional[Tuple[str, str]]:
        """
        三阶段压缩策略
        
        阶段 1: normal - 正常 LLM 压缩
        阶段 2: aggressive - 激进压缩
        阶段 3: fallback - 确定性截断
        """
        input_tokens = self._estimate_tokens(source_text)
        
        # 阶段 1: Normal
        summary = await self._call_llm(source_text, aggressive=False)
        if summary and self._estimate_tokens(summary) < input_tokens:
            return (summary, "normal")
        
        # 阶段 2: Aggressive
        summary = await self._call_llm(source_text, aggressive=True)
        if summary and self._estimate_tokens(summary) < input_tokens:
            return (summary, "aggressive")
        
        # 阶段 3: Fallback
        truncated = source_text[:2000]  # ~500 tokens
        return (f"{truncated}\n[Truncated from {input_tokens} tokens]", "fallback")
```

---

## 五、API 接口

### 5.1 接口列表

| 端点 | 方法 | 说明 | 类型 |
|------|------|------|------|
| `/memory/write` | POST | 写入消息 | 新增（扩展） |
| `/memory/recall` | POST | 混合召回 | 原有（扩展） |
| `/memory/expand` | POST | 展开摘要 | **新增** |
| `/memory/context` | POST | 组装上下文 | **新增** |
| `/memory/compact` | POST | 触发压缩 | **新增** |
| `/graph/entities` | GET | 查询实体 | 原有 |
| `/graph/relations` | GET | 查询关系 | 原有 |

### 5.2 核心接口定义

#### 5.2.1 写入消息

```json
POST /memory/write

Request:
{
  "agent_id": "agent_001",
  "session_id": "session_001",
  "role": "user",
  "content": "今天和张三讨论了项目进展"
}

Response:
{
  "raw_message_id": "raw_abc123",
  "entities": [
    {"name": "张三", "type": "person"}
  ],
  "compaction": {
    "triggered": false
  }
}
```

#### 5.2.2 混合召回

```json
POST /memory/recall

Request:
{
  "query": "张三的项目进展",
  "agent_id": "agent_001",
  "weights": {
    "vector": 0.5,
    "keyword": 0.3,
    "graph": 0.2
  },
  "expand_summaries": false
}

Response:
{
  "results": [
    {
      "type": "raw_message",
      "id": "raw_001",
      "content": "今天和张三讨论了项目进展",
      "similarity": 0.92,
      "source": "vector"
    },
    {
      "type": "summary",
      "id": "sum_001",
      "content": "用户与张三讨论项目，决定了技术方案...",
      "kind": "leaf",
      "depth": 0,
      "similarity": 0.85,
      "source": "vector",
      "expandable": true
    }
  ],
  "stats": {
    "vector_count": 5,
    "keyword_count": 3,
    "graph_count": 2,
    "summary_count": 2
  }
}
```

#### 5.2.3 展开摘要

```json
POST /memory/expand

Request:
{
  "summary_id": "sum_001",
  "max_tokens": 5000
}

Response:
{
  "summary": {
    "id": "sum_001",
    "kind": "leaf",
    "depth": 0,
    "content": "用户与张三讨论项目..."
  },
  "expanded_items": [
    {
      "type": "raw_message",
      "id": "raw_001",
      "role": "user",
      "content": "今天和张三讨论了项目进展",
      "token_count": 50
    },
    {
      "type": "raw_message",
      "id": "raw_002",
      "role": "assistant",
      "content": "项目进展顺利...",
      "token_count": 80
    }
  ],
  "total_tokens": 130
}
```

#### 5.2.4 组装上下文

```json
POST /memory/context

Request:
{
  "agent_id": "agent_001",
  "session_id": "session_001",
  "token_budget": 100000,
  "fresh_tail_count": 8
}

Response:
{
  "messages": [
    {
      "role": "user",
      "content": "<summary id=\"sum_001\" kind=\"leaf\" depth=\"0\">...</summary>"
    },
    {
      "role": "user",
      "content": "今天和张三讨论了项目进展"
    },
    {
      "role": "assistant",
      "content": "项目进展顺利..."
    }
  ],
  "estimated_tokens": 85432,
  "stats": {
    "raw_message_count": 8,
    "summary_count": 3
  }
}
```

---

## 六、实施计划

### 6.1 总体规划

| 阶段 | 周期 | 目标 | 依赖 |
|------|------|------|------|
| Phase 1 | 1 周 | 数据库迁移 + 基础存储 | 无 |
| Phase 2 | 1.5 周 | 压缩引擎 + DAG 管理 | Phase 1 |
| Phase 3 | 1 周 | 召回整合 + Context 组装 | Phase 1 |
| Phase 4 | 0.5 周 | API 接口 + 测试 | Phase 2, 3 |

### 6.2 Phase 1: 数据库迁移（1 周）

#### 任务分解

| 任务 | 优先级 | 预估时间 | 交付物 |
|------|--------|----------|--------|
| 1.1 创建 raw_messages 表 | P0 | 0.5 天 | 迁移脚本 |
| 1.2 创建 summaries 表 | P0 | 0.5 天 | 迁移脚本 |
| 1.3 创建关系表（summary_messages, summary_parents, summary_entities） | P0 | 0.5 天 | 迁移脚本 |
| 1.4 创建 context_items 表 | P0 | 0.5 天 | 迁移脚本 |
| 1.5 实现 RawMessageStore | P0 | 1 天 | Python 模块 |
| 1.6 实现 SummaryStore | P0 | 1 天 | Python 模块 |
| 1.7 单元测试 | P0 | 0.5 天 | 测试用例 |

#### 迁移脚本示例

```python
# migrations/017_add_lossless_tables.py

def upgrade():
    # 1. raw_messages
    op.execute("""
        CREATE TABLE raw_messages (
            id VARCHAR(24) PRIMARY KEY,
            agent_id VARCHAR(100) NOT NULL,
            session_id VARCHAR(100),
            role VARCHAR(20) NOT NULL,
            content TEXT NOT NULL,
            token_count INTEGER DEFAULT 0,
            embedding VECTOR(1024),
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            is_archived BOOLEAN DEFAULT FALSE
        );
        
        CREATE INDEX idx_raw_messages_agent_session 
            ON raw_messages(agent_id, session_id, created_at DESC);
        CREATE INDEX idx_raw_messages_embedding 
            ON raw_messages USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
    """)
    
    # 2. summaries
    op.execute("""
        CREATE TABLE summaries (
            summary_id VARCHAR(24) PRIMARY KEY,
            agent_id VARCHAR(100) NOT NULL,
            session_id VARCHAR(100),
            kind VARCHAR(20) NOT NULL CHECK (kind IN ('leaf', 'condensed')),
            depth INTEGER NOT NULL DEFAULT 0,
            content TEXT NOT NULL,
            token_count INTEGER NOT NULL DEFAULT 0,
            embedding VECTOR(1024),
            earliest_at TIMESTAMP WITH TIME ZONE,
            latest_at TIMESTAMP WITH TIME ZONE,
            descendant_count INTEGER NOT NULL DEFAULT 0,
            descendant_token_count INTEGER NOT NULL DEFAULT 0,
            source_message_token_count INTEGER NOT NULL DEFAULT 0,
            model VARCHAR(100) DEFAULT 'unknown',
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            importance_score FLOAT DEFAULT 0.5
        );
        
        CREATE INDEX idx_summaries_agent_session 
            ON summaries(agent_id, session_id, created_at DESC);
        CREATE INDEX idx_summaries_embedding 
            ON summaries USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
    """)
    
    # 3. summary_messages
    op.execute("""
        CREATE TABLE summary_messages (
            summary_id VARCHAR(24) NOT NULL REFERENCES summaries(summary_id) ON DELETE CASCADE,
            message_id VARCHAR(24) NOT NULL REFERENCES raw_messages(id) ON DELETE RESTRICT,
            ordinal INTEGER NOT NULL,
            PRIMARY KEY (summary_id, message_id)
        );
    """)
    
    # 4. summary_parents
    op.execute("""
        CREATE TABLE summary_parents (
            summary_id VARCHAR(24) NOT NULL REFERENCES summaries(summary_id) ON DELETE CASCADE,
            parent_summary_id VARCHAR(24) NOT NULL REFERENCES summaries(summary_id) ON DELETE RESTRICT,
            ordinal INTEGER NOT NULL,
            PRIMARY KEY (summary_id, parent_summary_id)
        );
    """)
    
    # 5. summary_entities
    op.execute("""
        CREATE TABLE summary_entities (
            summary_id VARCHAR(24) NOT NULL REFERENCES summaries(summary_id) ON DELETE CASCADE,
            entity_id UUID NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
            role VARCHAR(50) DEFAULT 'mentioned',
            confidence FLOAT DEFAULT 0.8,
            PRIMARY KEY (summary_id, entity_id)
        );
        
        CREATE INDEX idx_summary_entities_entity ON summary_entities(entity_id);
    """)
    
    # 6. context_items
    op.execute("""
        CREATE TABLE context_items (
            agent_id VARCHAR(100) NOT NULL,
            session_id VARCHAR(100) NOT NULL,
            ordinal INTEGER NOT NULL,
            item_type VARCHAR(20) NOT NULL CHECK (item_type IN ('message', 'summary')),
            message_id VARCHAR(24) REFERENCES raw_messages(id) ON DELETE RESTRICT,
            summary_id VARCHAR(24) REFERENCES summaries(summary_id) ON DELETE RESTRICT,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            PRIMARY KEY (agent_id, session_id, ordinal),
            CHECK (
                (item_type = 'message' AND message_id IS NOT NULL AND summary_id IS NULL) OR
                (item_type = 'summary' AND summary_id IS NOT NULL AND message_id IS NULL)
            )
        );
        
        CREATE INDEX idx_context_items_session 
            ON context_items(agent_id, session_id, ordinal);
    """)
```

#### RawMessageStore 实现

```python
# services/lossless/raw_message_store.py

class RawMessageStore:
    """原始消息存储"""
    
    async def store(
        self,
        agent_id: str,
        session_id: str,
        role: str,
        content: str
    ) -> str:
        """存储原始消息"""
        raw_id = generate_id("raw")
        token_count = self._estimate_tokens(content)
        
        await db.execute("""
            INSERT INTO raw_messages (id, agent_id, session_id, role, content, token_count)
            VALUES ($1, $2, $3, $4, $5, $6)
        """, raw_id, agent_id, session_id, role, content, token_count)
        
        return raw_id
    
    async def update_embedding(self, raw_id: str, embedding: List[float]):
        """更新向量嵌入"""
        await db.execute("""
            UPDATE raw_messages SET embedding = $1 WHERE id = $2
        """, embedding, raw_id)
    
    async def get_by_id(self, raw_id: str) -> Optional[Dict]:
        """获取消息"""
        return await db.fetchrow(
            "SELECT * FROM raw_messages WHERE id = $1", raw_id
        )
    
    async def get_fresh_tail(
        self,
        agent_id: str,
        session_id: str,
        count: int = 8
    ) -> List[Dict]:
        """获取 fresh tail（通过 context_items）"""
        return await db.fetch("""
            SELECT rm.* FROM raw_messages rm
            JOIN context_items ci ON ci.message_id = rm.id
            WHERE ci.agent_id = $1 AND ci.session_id = $2
              AND ci.item_type = 'message'
            ORDER BY ci.ordinal DESC
            LIMIT $3
        """, agent_id, session_id, count)
    
    def _estimate_tokens(self, text: str) -> int:
        return max(1, len(text) // 4)
```

### 6.3 Phase 2: 压缩引擎（1.5 周）

#### 任务分解

| 任务 | 优先级 | 预估时间 | 交付物 |
|------|--------|----------|--------|
| 2.1 实现 CompactionEngine 核心框架 | P0 | 1 天 | Python 模块 |
| 2.2 实现三阶段压缩策略 | P0 | 1 天 | Python 模块 |
| 2.3 实现 Fresh Tail 保护 | P0 | 0.5 天 | Python 模块 |
| 2.4 实现消息块选择算法 | P0 | 0.5 天 | Python 模块 |
| 2.5 实现 DAGManager | P0 | 1 天 | Python 模块 |
| 2.6 实现 summary_entities 提取 | P1 | 0.5 天 | Python 模块 |
| 2.7 实现 context_items 更新 | P0 | 0.5 天 | Python 模块 |
| 2.8 单元测试 + 集成测试 | P0 | 1 天 | 测试用例 |

#### 核心代码框架

```python
# services/lossless/compaction_engine.py

class CompactionEngine:
    """压缩引擎"""
    
    def __init__(self, config: CompactionConfig):
        self.config = config
        self.llm_client = get_llm_client()
        self.raw_store = RawMessageStore()
        self.summary_store = SummaryStore()
        self.context_store = ContextStore()
        self.entity_extractor = EntityExtractor()  # 复用原有
    
    async def leaf_compact(
        self,
        agent_id: str,
        session_id: str
    ) -> Optional[CompactionResult]:
        """Leaf 压缩"""
        # 1. 评估是否需要压缩
        if not await self._should_compact(agent_id, session_id):
            return None
        
        # 2. 选择消息块
        chunk = await self._select_leaf_chunk(agent_id, session_id)
        if not chunk["items"]:
            return None
        
        # 3. 三阶段压缩
        source_text = self._format_messages(chunk["messages"])
        summary_result = await self._summarize_with_escalation(source_text)
        
        if not summary_result:
            return None
        
        summary_content, level = summary_result
        
        # 4. 存储摘要
        summary_id = await self._create_leaf_summary(
            agent_id, session_id, summary_content, chunk
        )
        
        # 5. 提取实体并关联
        await self._extract_and_link_entities(summary_id, summary_content, agent_id)
        
        # 6. 更新 context_items
        await self._update_context_items(
            agent_id, session_id, chunk["ordinals"], summary_id
        )
        
        return CompactionResult(
            summary_id=summary_id,
            level=level,
            tokens_before=chunk["total_tokens"],
            tokens_after=self._estimate_tokens(summary_content)
        )
    
    async def _summarize_with_escalation(
        self, source_text: str
    ) -> Optional[Tuple[str, str]]:
        """三阶段压缩"""
        input_tokens = self._estimate_tokens(source_text)
        
        # Phase 1: Normal
        summary = await self._call_llm(source_text, aggressive=False)
        if summary and self._estimate_tokens(summary) < input_tokens:
            return (summary, "normal")
        
        # Phase 2: Aggressive
        summary = await self._call_llm(source_text, aggressive=True)
        if summary and self._estimate_tokens(summary) < input_tokens:
            return (summary, "aggressive")
        
        # Phase 3: Fallback
        truncated = source_text[:2000]
        return (f"{truncated}\n[Truncated from {input_tokens} tokens]", "fallback")
```

### 6.4 Phase 3: 召回整合（1 周）

#### 任务分解

| 任务 | 优先级 | 预估时间 | 交付物 |
|------|--------|----------|--------|
| 3.1 扩展向量召回（搜索 summaries） | P0 | 1 天 | Python 模块 |
| 3.2 扩展图谱召回（通过 summary_entities） | P0 | 1 天 | Python 模块 |
| 3.3 实现结果融合算法 | P0 | 0.5 天 | Python 模块 |
| 3.4 实现 DAG 展开功能 | P0 | 1 天 | Python 模块 |
| 3.5 实现 ContextAssembler | P0 | 1 天 | Python 模块 |
| 3.6 单元测试 + 集成测试 | P0 | 0.5 天 | 测试用例 |

#### 召回服务整合

```python
# services/recall/hybrid_recall_service.py（修改现有文件）

class HybridRecallService:
    """混合召回服务（扩展支持摘要）"""
    
    async def recall(
        self,
        query: str,
        agent_id: str,
        **kwargs
    ) -> List[Dict]:
        """混合召回（扩展：同时搜索摘要）"""
        # 获取查询向量
        query_embedding = await self.embedding_service.embed(query)
        
        # 并行搜索
        results = []
        
        # 1. 搜索原始消息
        raw_results = await self._search_raw_messages(query_embedding, agent_id)
        results.extend(raw_results)
        
        # 2. 搜索摘要（★新增★）
        summary_results = await self._search_summaries(query_embedding, agent_id)
        results.extend(summary_results)
        
        # 3. 搜索原有记忆（兼容）
        memory_results = await self._search_memories(query_embedding, agent_id)
        results.extend(memory_results)
        
        # 4. 图谱召回
        graph_results = await self._graph_recall(query, agent_id)
        results.extend(graph_results)
        
        # 5. 融合排序
        return self._merge_and_rank(results, kwargs.get("weights"))
    
    async def _search_summaries(
        self,
        query_embedding: List[float],
        agent_id: str
    ) -> List[Dict]:
        """搜索摘要（新增）"""
        results = await db.fetch("""
            SELECT 
                summary_id, content, kind, depth,
                1 - (embedding <=> $1) AS similarity
            FROM summaries
            WHERE agent_id = $2
            ORDER BY embedding <=> $1
            LIMIT 10
        """, query_embedding, agent_id)
        
        return [
            {
                "type": "summary",
                "id": r["summary_id"],
                "content": r["content"],
                "kind": r["kind"],
                "depth": r["depth"],
                "similarity": r["similarity"],
                "source": "vector",
                "expandable": True
            }
            for r in results
        ]
```

### 6.5 Phase 4: API 接口（0.5 周）

#### 任务分解

| 任务 | 优先级 | 预估时间 | 交付物 |
|------|--------|----------|--------|
| 4.1 实现 /memory/write 接口 | P0 | 0.5 天 | FastAPI 路由 |
| 4.2 实现 /memory/recall 接口（扩展） | P0 | 0.5 天 | FastAPI 路由 |
| 4.3 实现 /memory/expand 接口 | P0 | 0.5 天 | FastAPI 路由 |
| 4.4 实现 /memory/context 接口 | P0 | 0.5 天 | FastAPI 路由 |
| 4.5 API 文档 | P1 | 0.5 天 | OpenAPI 文档 |
| 4.6 端到端测试 | P0 | 0.5 天 | 测试用例 |

### 6.6 里程碑验收标准

| 里程碑 | 验收标准 |
|--------|----------|
| Phase 1 完成 | ✅ 6 张新表创建成功<br>✅ RawMessageStore 单元测试通过<br>✅ SummaryStore 单元测试通过 |
| Phase 2 完成 | ✅ 三阶段压缩策略正常工作<br>✅ Fresh Tail 保护机制生效<br>✅ summary_entities 正确关联 |
| Phase 3 完成 | ✅ 混合召回能搜索到摘要<br>✅ DAG 展开返回原始消息<br>✅ Context 组装延迟 < 150ms |
| Phase 4 完成 | ✅ 所有 API 接口正常响应<br>✅ 端到端测试通过<br>✅ API 文档完整 |

---

## 七、测试方案

### 7.1 单元测试

```python
# tests/test_compaction_engine.py

class TestCompactionEngine:
    
    @pytest.mark.asyncio
    async def test_three_phase_summarization(self):
        """测试三阶段压缩"""
        engine = CompactionEngine(config)
        
        # 测试 normal 阶段
        result = await engine._summarize_with_escalation("短文本")
        assert result[1] == "normal"
        
        # 测试 fallback 阶段
        long_text = "x" * 10000
        result = await engine._summarize_with_escalation(long_text)
        assert result[1] in ["normal", "aggressive", "fallback"]
    
    @pytest.mark.asyncio
    async def test_fresh_tail_protection(self):
        """测试 fresh tail 保护"""
        engine = CompactionEngine(config)
        
        # 创建 20 条消息
        await create_test_messages(agent_id, session_id, count=20)
        
        # 选择消息块
        chunk = await engine._select_leaf_chunk(agent_id, session_id)
        
        # 最后 8 条不应被选中
        assert all(item.ordinal < 12 for item in chunk["items"])

# tests/test_hybrid_recall.py

class TestHybridRecall:
    
    @pytest.mark.asyncio
    async def test_recall_includes_summaries(self):
        """测试召回包含摘要"""
        service = HybridRecallService()
        
        # 创建测试数据
        await create_test_summary(agent_id, "测试摘要内容")
        
        # 召回
        results = await service.recall("测试摘要", agent_id)
        
        # 应包含摘要类型
        assert any(r["type"] == "summary" for r in results)
```

### 7.2 集成测试

```python
# tests/integration/test_full_flow.py

class TestFullFlow:
    
    @pytest.mark.asyncio
    async def test_write_recall_expand_flow(self):
        """测试完整流程：写入 → 召回 → 展开"""
        
        # 1. 写入消息
        write_result = await api.post("/memory/write", {
            "agent_id": "test_agent",
            "session_id": "test_session",
            "role": "user",
            "content": "今天和张三讨论了项目进展，决定使用 Python 重构"
        })
        assert write_result["raw_message_id"]
        
        # 2. 触发压缩
        await api.post("/memory/compact", {
            "agent_id": "test_agent",
            "session_id": "test_session"
        })
        
        # 3. 召回
        recall_result = await api.post("/memory/recall", {
            "query": "张三 项目",
            "agent_id": "test_agent"
        })
        
        # 应包含摘要
        summary = next(
            (r for r in recall_result["results"] if r["type"] == "summary"),
            None
        )
        assert summary is not None
        
        # 4. 展开摘要
        expand_result = await api.post("/memory/expand", {
            "summary_id": summary["id"]
        })
        
        # 应包含原始消息
        assert len(expand_result["expanded_items"]) > 0
        assert expand_result["expanded_items"][0]["type"] == "raw_message"
```

---

## 八、监控与告警

### 8.1 核心指标

| 指标 | 类型 | 说明 |
|------|------|------|
| `memory_recall_latency` | Histogram | 召回延迟 |
| `memory_context_assembly_latency` | Histogram | Context 组装延迟 |
| `memory_compaction_count` | Counter | 压缩次数 |
| `memory_compaction_fallback_count` | Counter | Fallback 压缩次数 |
| `memory_summary_count` | Gauge | 摘要节点数 |
| `memory_dag_max_depth` | Gauge | DAG 最大深度 |

### 8.2 告警规则

```yaml
groups:
  - name: memory_alerts
    rules:
      - alert: CompactionFallbackHigh
        expr: rate(memory_compaction_fallback_count[5m]) > 0.1
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Fallback 压缩率过高"
      
      - alert: DAGDepthTooDeep
        expr: memory_dag_max_depth > 5
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "DAG 深度过深"
```

---

## 九、风险与应对

| 风险 | 影响 | 应对措施 |
|------|------|----------|
| 压缩质量不佳 | 召回准确率下降 | 三阶段压缩兜底 + 保留原始消息 |
| DAG 深度过深 | 展开性能下降 | 限制最大深度 + 定期 condensation |
| 存储空间增长 | 成本增加 | 原始消息归档 + 低重要性摘要清理 |
| 向量索引性能 | 召回延迟增加 | 分区索引 + 热数据缓存 |

---

## 十、附录

### A. 与 Lossless-Claw 对比

| 维度 | Lossless-Claw | Memory Recall v2.0 |
|------|---------------|-------------------|
| 存储 | SQLite | PostgreSQL |
| 向量索引 | ❌ | ✅ HNSW |
| 图谱 | ❌ | ✅ 实体-关系 |
| DAG 结构 | ✅ | ✅ 完全一致 |
| 三阶段压缩 | ✅ | ✅ 完全一致 |
| Fresh Tail | ✅ | ✅ 完全一致 |
| context_items | ✅ | ✅ 完全一致 |

### B. 版本历史

| 版本 | 日期 | 变更 |
|------|------|------|
| v1.0 | 2026-03-26 | 初始设计 |
| v1.1 | 2026-03-26 | 融入 Lossless-Claw 最佳实践 |
| v2.0 | 2026-03-26 | 重构：融合原始能力 + 新增能力，详细实施计划 |
