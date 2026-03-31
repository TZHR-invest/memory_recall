# AI Agent 记忆召回服务设计文档 v3.0

> **版本：** v3.0  
> **日期：** 2026-03-26  
> **状态：** 设计完成  
> **定位：** 统一 DAG 记忆架构 + OpenClaw 插件集成

---

## 一、项目概述

### 1.1 核心定位

**Memory Recall v3.0 = 统一 DAG 记忆架构 + 混合召回 + OpenClaw 插件**

```
┌─────────────────────────────────────────────────────────────────────┐
│                    Memory Recall v3.0 架构                          │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                    统一 DAG 记忆架构                          │   │
│  │  • 所有记忆统一存储为 raw_messages                           │   │
│  │  • 通过 agent_id 区分来源（用户手动 / Agent 对话）            │   │
│  │  • DAG 压缩 → summaries                                      │   │
│  │  • 消息级别存储，废弃记忆点拆分                               │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                              +                                      │
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
│  │                    OpenClaw 插件集成                          │   │
│  │  🔌 实现 ContextEngine 接口                                   │   │
│  │  🔌 支持 ingest / assemble / compact                         │   │
│  │  🔌 注册为 OpenClaw ContextEngine 插件                        │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### 1.2 核心设计决策

| 决策 | 说明 |
|------|------|
| **消息级别存储** | 废弃记忆点提取，统一存储原始消息 |
| **来源区分** | agent_id = NULL（用户手动）vs 非NULL（Agent 对话） |
| **统一 DAG 架构** | 用户偏好 + Agent 对话都走 raw_messages → summaries 流程 |
| **长文本分段** | 通过 document_id 关联，可选压缩成摘要 |
| **插件集成** | 实现 ContextEngine 接口，注册为 OpenClaw 插件 |

### 1.3 核心指标

| 指标 | 目标值 | 说明 |
|------|--------|------|
| 召回延迟（P95） | < 200ms | 混合召回 |
| Context 组装延迟 | < 150ms | DAG 组装 |
| 压缩成功率 | > 95% | 三阶段兜底 |
| 原始数据保留率 | 100% | Raw 消息永不删除 |

---

## 二、核心架构

### 2.1 统一 DAG 记忆架构

```
┌────────────────────────────────────────────────────────────────────┐
│                    统一 DAG 记忆架构                                │
├────────────────────────────────────────────────────────────────────┤
│                                                                    │
│  ┌──────────────────────────────────────────────────────────────┐ │
│  │                    输入来源（统一入口）                        │ │
│  │                                                               │ │
│  │  用户手动输入                    Agent 对话                   │ │
│  │  ┌──────────────────┐          ┌──────────────────┐         │ │
│  │  │ "我是素食主义者"   │          │ user: "今天..."  │         │ │
│  │  │ "我喜欢喝咖啡"     │          │ assistant: "..." │         │ │
│  │  │ 长文档/日记        │          │ 多轮对话消息      │         │ │
│  │  └────────┬─────────┘          └────────┬─────────┘         │ │
│  │           │                              │                   │ │
│  │           │ agent_id=NULL                │ agent_id=xxx      │ │
│  │           │ memory_type=preference/note  │ memory_type=      │ │
│  │           │                              │   dialogue        │ │
│  │           └──────────────┬───────────────┘                   │ │
│  └──────────────────────────┼───────────────────────────────────┘ │
│                             ↓                                     │
│  ┌──────────────────────────────────────────────────────────────┐ │
│  │              Layer 1: Raw Messages（原始消息层）              │ │
│  │                                                               │ │
│  │  raw_messages 表                                              │ │
│  │  ┌────────────────────────────────────────────────────────┐  │ │
│  │  │ id | agent_id | memory_type | content | embedding |...│  │ │
│  │  ├────────────────────────────────────────────────────────┤  │ │
│  │  │ raw_001 | NULL      | preference | "我是素食主义者" |...│  │ │
│  │  │ raw_002 | NULL      | note       | "长文档段落1"   |...│  │ │
│  │  │ raw_003 | NULL      | note       | "长文档段落2"   |...│  │ │
│  │  │ raw_004 | agent_001 | dialogue   | "今天天气不错"  |...│  │ │
│  │  │ raw_005 | agent_001 | dialogue   | "是的，适合出门" |...│  │ │
│  │  └────────────────────────────────────────────────────────┘  │ │
│  │                                                               │ │
│  │  特点：                                                       │ │
│  │  • 消息级别存储（不拆分记忆点）                                │ │
│  │  • 长文本分段共享 document_id                                  │ │
│  │  • 每条消息独立 embedding + 实体关联                           │ │
│  └──────────────────────────────────────────────────────────────┘ │
│                             ↓ DAG 压缩                            │
│  ┌──────────────────────────────────────────────────────────────┐ │
│  │              Layer 2-3: Summaries（摘要层）                   │ │
│  │                                                               │ │
│  │  summaries 表                                                 │ │
│  │  ┌────────────────────────────────────────────────────────┐  │ │
│  │  │ summary_id | agent_id | kind | depth | content | ...   │  │ │
│  │  ├────────────────────────────────────────────────────────┤  │ │
│  │  │ sum_001 | agent_001 | leaf  | 0 | "对话摘要..." | ...   │  │ │
│  │  │ sum_002 | agent_001 | condensed | 1 | "高层摘要" | ...  │  │ │
│  │  │ sum_003 | NULL      | leaf  | 0 | "偏好汇总..." | ...   │  │ │
│  │  └────────────────────────────────────────────────────────┘  │ │
│  │                                                               │ │
│  │  压缩规则：                                                   │ │
│  │  • Agent 对话：多轮消息 → leaf summary → condensed summary    │ │
│  │  • 用户偏好：多条相关偏好可选压缩成汇总                         │ │
│  │  • 长文档：多个分段 → 单个摘要（关联 document_id）              │ │
│  └──────────────────────────────────────────────────────────────┘ │
│                             ↓ 组装                               │
│  ┌──────────────────────────────────────────────────────────────┐ │
│  │              Layer 4: Context Assembly（上下文组装）          │ │
│  │                                                               │ │
│  │  context_items 表：有序序列                                   │ │
│  │  ┌────────────────────────────────────────────────────────┐  │ │
│  │  │ ordinal | item_type | message_id | summary_id | ...    │  │ │
│  │  ├────────────────────────────────────────────────────────┤  │ │
│  │  │ 0 | summary  | NULL       | sum_003  | ...             │  │ │
│  │  │ 1 | summary  | NULL       | sum_001  | ...             │  │ │
│  │  │ 2 | message | raw_004     | NULL     | ...             │  │ │
│  │  │ 3 | message | raw_005     | NULL     | ...             │  │ │
│  │  └────────────────────────────────────────────────────────┘  │ │
│  │                                                               │ │
│  │  输出：AgentMessage[] 给 LLM                                  │ │
│  └──────────────────────────────────────────────────────────────┘ │
│                                                                    │
└────────────────────────────────────────────────────────────────────┘
```

### 2.2 记忆来源区分（基于 agent_id）

```
┌─────────────────────────────────────────────────────────────────────┐
│                    记忆来源区分设计                                  │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  判断逻辑：                                                          │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  agent_id IS NULL      → 用户手动输入（user_manual）         │   │
│  │  agent_id IS NOT NULL  → Agent 对话自动提取（agent_dialogue）│   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  场景示例：                                                          │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │ 用户手动输入                                                 │   │
│  │                                                              │   │
│  │ API: POST /memories                                         │   │
│  │ {                                                            │   │
│  │   "content": "我是素食主义者，不喜欢吃肉",                    │   │
│  │   "user_id": "user_001"                                     │   │
│  │   // agent_id 不传，默认为 NULL                              │   │
│  │ }                                                            │   │
│  │                                                              │   │
│  │ 存储：raw_messages (agent_id=NULL, memory_type='preference') │   │
│  │      entities (agent_id=NULL)                               │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │ Agent 对话自动提取                                           │   │
│  │                                                              │   │
│  │ ContextEngine.ingest({                                       │   │
│  │   agent_id: "agent_001",                                     │   │
│  │   session_id: "session_001",                                 │   │
│  │   message: { role: "user", content: "..." }                  │   │
│  │ })                                                           │   │
│  │                                                              │   │
│  │ 存储：raw_messages (agent_id='agent_001')                    │   │
│  │      summaries (agent_id='agent_001')                        │   │
│  │      entities (agent_id='agent_001')                         │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  召回场景：                                                          │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │ 场景 A - 用户查询个人偏好：                                   │   │
│  │   WHERE agent_id IS NULL                                     │   │
│  │   → 只返回用户手动输入的记忆                                  │   │
│  │                                                              │   │
│  │ 场景 B - Agent 执行任务需要历史上下文：                        │   │
│  │   WHERE agent_id = ?                                         │   │
│  │   → 只返回该 Agent 的对话历史                                 │   │
│  │                                                              │   │
│  │ 场景 C - Agent 需要知道用户偏好：                              │   │
│  │   WHERE agent_id IS NULL OR agent_id = ?                     │   │
│  │   → 同时返回用户偏好 + Agent 历史                             │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### 2.3 OpenClaw 插件集成架构

```
┌─────────────────────────────────────────────────────────────────────┐
│                    OpenClaw 插件集成架构                             │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  OpenClaw Gateway                                                   │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  Agent 执行循环                                              │   │
│  │                                                              │   │
│  │  1. receive user message                                     │   │
│  │           ↓                                                  │   │
│  │  2. contextEngine.assemble() → 获取上下文                     │   │
│  │           ↓                                                  │   │
│  │  3. call LLM with context                                    │   │
│  │           ↓                                                  │   │
│  │  4. contextEngine.ingest() → 存储消息                         │   │
│  │           ↓                                                  │   │
│  │  5. contextEngine.compact() → 可选压缩                        │   │
│  │                                                              │   │
│  └─────────────────────────────────────────────────────────────┘   │
│           │                                                         │
│           ↓ 插件接口                                                │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  Memory Recall Plugin                                        │   │
│  │  implements ContextEngine                                    │   │
│  │                                                              │   │
│  │  ┌─────────────────────────────────────────────────────┐    │   │
│  │  │  ContextEngine 接口实现                              │    │   │
│  │  │                                                      │    │   │
│  │  │  bootstrap(params)                                   │    │   │
│  │  │    → 初始化会话，加载 context_items                  │    │   │
│  │  │                                                      │    │   │
│  │  │  ingest(params)                                      │    │   │
│  │  │    → 存储消息到 raw_messages                         │    │   │
│  │  │    → 提取实体，更新图谱                               │    │   │
│  │  │    → 追加到 context_items                             │    │   │
│  │  │    → 检查是否需要压缩                                 │    │   │
│  │  │                                                      │    │   │
│  │  │  assemble(params)                                    │    │   │
│  │  │    → 从 context_items 组装上下文                      │    │   │
│  │  │    → 按 token 预算选择                                │    │   │
│  │  │    → 返回 AgentMessage[]                              │    │   │
│  │  │                                                      │    │   │
│  │  │  compact(params)                                     │    │   │
│  │  │    → DAG 压缩（三阶段策略）                           │    │   │
│  │  │    → 更新 context_items                               │    │   │
│  │  │                                                      │    │   │
│  │  │  afterTurn(params)                                   │    │   │
│  │  │    → 回合后处理                                       │    │   │
│  │  └─────────────────────────────────────────────────────┘    │   │
│  │                                                              │   │
│  │  ┌─────────────────────────────────────────────────────┐    │   │
│  │  │  扩展接口                                            │    │   │
│  │  │                                                      │    │   │
│  │  │  recall(query, agent_id, scope)                      │    │   │
│  │  │    → 混合召回（向量+关键词+图谱）                      │    │   │
│  │  │                                                      │    │   │
│  │  │  expand(summary_id)                                  │    │   │
│  │  │    → DAG 展开查看原始内容                              │    │   │
│  │  └─────────────────────────────────────────────────────┘    │   │
│  └─────────────────────────────────────────────────────────────┘   │
│           │                                                         │
│           ↓                                                         │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  PostgreSQL + pgvector                                       │   │
│  │                                                              │   │
│  │  新增表：                                                    │   │
│  │  • raw_messages（原始消息，替代 memories）                   │   │
│  │  • summaries（摘要节点）                                     │   │
│  │  • summary_messages（摘要-消息关系）                         │   │
│  │  • summary_parents（DAG 关系）                               │   │
│  │  • summary_entities（摘要-实体关系）                         │   │
│  │  • context_items（有序上下文序列）                           │   │
│  │                                                              │   │
│  │  保留表：                                                    │   │
│  │  • entities（实体表）                                        │   │
│  │  • relations（关系表）                                       │   │
│  │  • memory_entities（记忆-实体关系，逐步迁移）                │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 三、数据模型

### 3.1 表结构总览

| 表名 | 类型 | 说明 |
|------|------|------|
| `raw_messages` | **新增** | 统一原始消息存储（替代 memories） |
| `summaries` | **新增** | DAG 摘要节点 |
| `summary_messages` | **新增** | 摘要-消息关系 |
| `summary_parents` | **新增** | 摘要-DAG 关系 |
| `summary_entities` | **新增** | 摘要-实体关系 |
| `context_items` | **新增** | 有序上下文序列 |
| `entities` | **保留** | 实体表（扩展 agent_id） |
| `relations` | **保留** | 关系表（扩展 agent_id） |
| `memory_entities` | **保留** | 记忆-实体关系（兼容过渡期） |

### 3.2 raw_messages 表（核心）

```sql
-- 原始消息表：统一存储所有记忆（替代 memories 表）
CREATE TABLE raw_messages (
    id VARCHAR(24) PRIMARY KEY,
    user_id VARCHAR(100) NOT NULL,
    agent_id VARCHAR(100),              -- NULL=用户手动，非NULL=Agent对话
    
    -- 来源类型
    memory_type VARCHAR(20) NOT NULL 
        CHECK (memory_type IN ('preference', 'note', 'dialogue')),
    -- preference: 用户偏好（如"我喜欢咖啡"）
    -- note: 用户笔记/日记/长文档
    -- dialogue: Agent 对话消息
    
    -- 会话关联
    session_id VARCHAR(100),
    document_id VARCHAR(24),            -- 长文档分段共享此 ID
    
    -- 消息内容
    role VARCHAR(20) NOT NULL 
        CHECK (role IN ('user', 'assistant', 'system')),
    content TEXT NOT NULL,
    token_count INTEGER DEFAULT 0,
    
    -- 向量嵌入
    embedding VECTOR(1024),
    
    -- 时间信息
    time_value TIMESTAMP WITH TIME ZONE,
    time_source VARCHAR(10),
    
    -- 位置信息
    location_name TEXT,
    
    -- 元数据
    tags JSONB DEFAULT '[]'::jsonb,
    metadata JSONB DEFAULT '{}'::jsonb,
    
    -- 系统字段
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    is_archived BOOLEAN DEFAULT FALSE
);

-- 索引
CREATE INDEX idx_raw_messages_user ON raw_messages(user_id);
CREATE INDEX idx_raw_messages_agent ON raw_messages(agent_id) 
    WHERE agent_id IS NOT NULL;
CREATE INDEX idx_raw_messages_no_agent ON raw_messages(agent_id) 
    WHERE agent_id IS NULL;
CREATE INDEX idx_raw_messages_session ON raw_messages(user_id, session_id);
CREATE INDEX idx_raw_messages_document ON raw_messages(document_id);
CREATE INDEX idx_raw_messages_embedding ON raw_messages 
    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
CREATE INDEX idx_raw_messages_time ON raw_messages(time_value);

COMMENT ON TABLE raw_messages IS '原始消息表：统一存储用户手动输入和Agent对话';
COMMENT ON COLUMN raw_messages.agent_id IS 'Agent ID：NULL=用户手动输入，非NULL=Agent对话提取';
COMMENT ON COLUMN raw_messages.memory_type IS '记忆类型：preference(偏好)/note(笔记)/dialogue(对话)';
COMMENT ON COLUMN raw_messages.document_id IS '文档 ID：长文本分段共享此 ID';
```

### 3.3 summaries 表

```sql
-- 摘要节点表：DAG 结构
CREATE TABLE summaries (
    summary_id VARCHAR(24) PRIMARY KEY,
    user_id VARCHAR(100) NOT NULL,
    agent_id VARCHAR(100),              -- 与 raw_messages 一致
    
    -- 节点类型
    kind VARCHAR(20) NOT NULL CHECK (kind IN ('leaf', 'condensed')),
    depth INTEGER NOT NULL DEFAULT 0,
    
    -- 内容
    content TEXT NOT NULL,
    token_count INTEGER NOT NULL DEFAULT 0,
    
    -- 向量嵌入
    embedding VECTOR(1024),
    
    -- 统计字段
    earliest_at TIMESTAMP WITH TIME ZONE,
    latest_at TIMESTAMP WITH TIME ZONE,
    descendant_count INTEGER NOT NULL DEFAULT 0,
    descendant_token_count INTEGER NOT NULL DEFAULT 0,
    source_message_token_count INTEGER NOT NULL DEFAULT 0,
    
    -- 文档关联
    document_id VARCHAR(24),            -- 长文档摘要关联
    
    -- 元数据
    model VARCHAR(100) DEFAULT 'unknown',
    compression_level VARCHAR(20) DEFAULT 'normal',  -- normal/aggressive/fallback
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 索引
CREATE INDEX idx_summaries_user ON summaries(user_id);
CREATE INDEX idx_summaries_agent ON summaries(agent_id);
CREATE INDEX idx_summaries_embedding ON summaries 
    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
```

### 3.4 summary_messages 表

```sql
-- 摘要-消息关系表
CREATE TABLE summary_messages (
    summary_id VARCHAR(24) NOT NULL REFERENCES summaries(summary_id) ON DELETE CASCADE,
    message_id VARCHAR(24) NOT NULL REFERENCES raw_messages(id) ON DELETE RESTRICT,
    ordinal INTEGER NOT NULL,
    PRIMARY KEY (summary_id, message_id)
);

CREATE INDEX idx_summary_messages_summary ON summary_messages(summary_id, ordinal);
CREATE INDEX idx_summary_messages_message ON summary_messages(message_id);

COMMENT ON TABLE summary_messages IS '摘要-消息关系：leaf 摘要引用的原始消息';
```

### 3.5 summary_parents 表

```sql
-- 摘要-DAG 关系表
-- parent_summary_id 是被压缩的节点，展开时向上遍历
CREATE TABLE summary_parents (
    summary_id VARCHAR(24) NOT NULL REFERENCES summaries(summary_id) ON DELETE CASCADE,
    parent_summary_id VARCHAR(24) NOT NULL REFERENCES summaries(summary_id) ON DELETE RESTRICT,
    ordinal INTEGER NOT NULL,
    PRIMARY KEY (summary_id, parent_summary_id)
);

COMMENT ON TABLE summary_parents IS '摘要-DAG 关系：parent_summary_id 是被压缩的节点';
```

### 3.6 summary_entities 表

```sql
-- 摘要-实体关系表（用于图谱召回）
CREATE TABLE summary_entities (
    summary_id VARCHAR(24) NOT NULL REFERENCES summaries(summary_id) ON DELETE CASCADE,
    entity_id UUID NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    role VARCHAR(50) DEFAULT 'mentioned',
    confidence FLOAT DEFAULT 0.8,
    PRIMARY KEY (summary_id, entity_id)
);

CREATE INDEX idx_summary_entities_entity ON summary_entities(entity_id);
```

### 3.7 context_items 表

```sql
-- 上下文序列表：维护有序消息/摘要序列
CREATE TABLE context_items (
    user_id VARCHAR(100) NOT NULL,
    agent_id VARCHAR(100),              -- NULL 表示用户偏好上下文
    session_id VARCHAR(100) NOT NULL,
    ordinal INTEGER NOT NULL,
    item_type VARCHAR(20) NOT NULL CHECK (item_type IN ('message', 'summary')),
    message_id VARCHAR(24) REFERENCES raw_messages(id) ON DELETE RESTRICT,
    summary_id VARCHAR(24) REFERENCES summaries(summary_id) ON DELETE RESTRICT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    PRIMARY KEY (user_id, session_id, ordinal),
    CHECK (
        (item_type = 'message' AND message_id IS NOT NULL AND summary_id IS NULL) OR
        (item_type = 'summary' AND summary_id IS NOT NULL AND message_id IS NULL)
    )
);

CREATE INDEX idx_context_items_session ON context_items(user_id, session_id, ordinal);
```

### 3.8 entities 表（扩展）

```sql
-- 实体表扩展（已有，补充说明）
-- agent_id 字段已存在：
--   NULL = 用户手动输入的记忆中的实体
--   非NULL = Agent 对话中的实体

COMMENT ON COLUMN entities.agent_id IS 'Agent ID：NULL=用户手动输入，非NULL=Agent对话';
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
│  │              MemoryRecallEngine                              │   │
│  │              （实现 ContextEngine 接口）                      │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                              │                                      │
│         ┌────────────────────┼────────────────────┐                │
│         ↓                    ↓                    ↓                │
│  ┌─────────────┐     ┌─────────────┐     ┌─────────────┐          │
│  │ 写入服务     │     │ 召回服务     │     │ 组装服务     │          │
│  │ IngestSvc   │     │ RecallSvc   │     │ AssembleSvc │          │
│  └─────────────┘     └─────────────┘     └─────────────┘          │
│         │                    │                    │                │
│         ↓                    ↓                    ↓                │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                    底层服务                                  │   │
│  ├─────────────────────────────────────────────────────────────┤   │
│  │                                                              │   │
│  │  【保留服务】                    【新增服务】                  │   │
│  │  ┌─────────────────┐           ┌─────────────────┐          │   │
│  │  │ EntityExtractor │           │ RawMessageStore │          │   │
│  │  │ GraphBuilder    │           │ SummaryStore    │          │   │
│  │  │ VectorIndexer   │           │ DAGManager      │          │   │
│  │  │ HybridRecall    │           │ CompactionEng   │          │   │
│  │  │ QueryParser     │           │ ContextStore    │          │   │
│  │  └─────────────────┘           └─────────────────┘          │   │
│  │                                                              │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                              │                                      │
│                              ↓                                      │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                    数据存储                                  │   │
│  │  PostgreSQL + pgvector                                       │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### 4.2 ContextEngine 接口实现

```python
# services/memory_recall_engine.py

from typing import Dict, Any, List, Optional
from dataclasses import dataclass

@dataclass
class ContextEngineInfo:
    id: str = "memory-recall"
    name: str = "Memory Recall Engine"
    version: str = "3.0.0"
    owns_compaction: bool = True


class MemoryRecallEngine:
    """
    记忆召回引擎
    
    实现 OpenClaw ContextEngine 接口
    """
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.info = ContextEngineInfo()
        
        # 保留服务
        self.entity_extractor = EntityExtractor()
        self.graph_builder = GraphBuilder()
        self.vector_indexer = VectorIndexer()
        self.hybrid_recall = HybridRecallService()
        
        # 新增服务
        self.raw_store = RawMessageStore()
        self.summary_store = SummaryStore()
        self.dag_manager = DAGManager()
        self.compaction_engine = CompactionEngine(config)
        self.context_store = ContextStore()
    
    # ═══════════════════════════════════════════════════════════════
    # ContextEngine 接口实现
    # ═══════════════════════════════════════════════════════════════
    
    async def bootstrap(self, params: Dict) -> Dict:
        """
        初始化会话
        
        流程：
        1. 检查 context_items 是否已存在
        2. 不存在则从 raw_messages 加载历史
        """
        user_id = params["user_id"]
        agent_id = params.get("agent_id")
        session_id = params["session_id"]
        
        # 检查是否已有上下文
        exists = await self.context_store.exists(user_id, session_id)
        
        if not exists:
            # 加载历史消息到 context_items
            await self._load_history_to_context(user_id, agent_id, session_id)
        
        return {"status": "ready"}
    
    async def ingest(self, params: Dict) -> Dict:
        """
        摄入消息
        
        流程：
        1. 存储到 raw_messages
        2. 提取实体，更新图谱
        3. 生成向量嵌入
        4. 追加到 context_items
        5. 检查是否需要压缩
        """
        user_id = params["user_id"]
        agent_id = params.get("agent_id")  # NULL = 用户手动
        session_id = params.get("session_id")
        message = params["message"]
        
        content = self._extract_content(message)
        role = message.get("role", "user")
        
        # 1. 存储原始消息
        memory_type = "dialogue" if agent_id else "preference"
        raw_id = await self.raw_store.store(
            user_id=user_id,
            agent_id=agent_id,
            session_id=session_id,
            memory_type=memory_type,
            role=role,
            content=content
        )
        
        # 2. 提取实体，更新图谱
        entities, relations = await self.entity_extractor.extract(content)
        entity_ids = await self.graph_builder.save_entities(
            entities, user_id, agent_id, raw_id
        )
        await self.graph_builder.save_relations(
            relations, entity_ids, user_id, agent_id
        )
        
        # 3. 生成向量嵌入
        embedding = await self.vector_indexer.embed(content)
        await self.raw_store.update_embedding(raw_id, embedding)
        
        # 4. 追加到 context_items
        await self.context_store.append_message(
            user_id, agent_id, session_id, raw_id
        )
        
        # 5. 检查是否需要压缩
        compaction_triggered = False
        if await self._should_compact(user_id, session_id):
            compaction_triggered = await self._trigger_compact(
                user_id, agent_id, session_id
            )
        
        return {
            "raw_message_id": raw_id,
            "entities_count": len(entities),
            "compaction_triggered": compaction_triggered
        }
    
    async def assemble(self, params: Dict) -> Dict:
        """
        组装上下文
        
        流程：
        1. 从 context_items 获取有序序列
        2. 按 token 预算选择
        3. 保护 fresh tail
        4. 返回 AgentMessage[]
        """
        user_id = params["user_id"]
        agent_id = params.get("agent_id")
        session_id = params["session_id"]
        token_budget = params.get("token_budget", 100000)
        fresh_tail_count = self.config.get("fresh_tail_count", 8)
        
        # 获取上下文序列
        items = await self.context_store.get_context_items(
            user_id, agent_id, session_id
        )
        
        if not items:
            return {"messages": [], "estimated_tokens": 0}
        
        # 分割 evictable 和 fresh tail
        tail_start = max(0, len(items) - fresh_tail_count)
        evictable = items[:tail_start]
        fresh_tail = items[tail_start:]
        
        # 计算 fresh tail token
        tail_tokens = await self._count_tokens(fresh_tail)
        remaining_budget = token_budget - tail_tokens
        
        # 选择 evictable
        selected = []
        if remaining_budget > 0:
            selected = await self._select_within_budget(
                evictable, remaining_budget
            )
        
        # 合并
        final_items = selected + fresh_tail
        
        # 解析为 AgentMessage
        messages = await self._resolve_to_messages(final_items)
        estimated_tokens = await self._count_tokens(final_items)
        
        # 生成系统提示（如有摘要）
        system_prompt = await self._build_system_prompt(final_items)
        
        return {
            "messages": messages,
            "estimated_tokens": estimated_tokens,
            "system_prompt_addition": system_prompt
        }
    
    async def compact(self, params: Dict) -> Dict:
        """
        DAG 压缩
        
        流程：
        1. 选择可压缩的消息块（保护 fresh tail）
        2. 三阶段压缩生成摘要
        3. 存储摘要 + 建立关联
        4. 更新 context_items
        """
        user_id = params["user_id"]
        agent_id = params.get("agent_id")
        session_id = params["session_id"]
        token_budget = params.get("token_budget")
        force = params.get("force", False)
        
        # 执行压缩
        result = await self.compaction_engine.leaf_compact(
            user_id=user_id,
            agent_id=agent_id,
            session_id=session_id,
            token_budget=token_budget,
            force=force
        )
        
        return {
            "action_taken": result.action_taken if result else False,
            "tokens_before": result.tokens_before if result else 0,
            "tokens_after": result.tokens_after if result else 0,
            "summary_id": result.summary_id if result else None
        }
    
    async def afterTurn(self, params: Dict) -> None:
        """回合后处理"""
        # 当前无特殊处理
        pass
    
    async def dispose(self) -> None:
        """清理资源"""
        pass
    
    # ═══════════════════════════════════════════════════════════════
    # 扩展接口（非 ContextEngine 标准）
    # ═══════════════════════════════════════════════════════════════
    
    async def recall(
        self,
        query: str,
        user_id: str,
        agent_id: str = None,
        scope: str = "all",
        limit: int = 20
    ) -> List[Dict]:
        """
        混合召回
        
        Args:
            scope: "all" | "manual_only" | "agent_only"
        """
        return await self.hybrid_recall.recall(
            query=query,
            user_id=user_id,
            agent_id=agent_id,
            scope=scope,
            limit=limit
        )
    
    async def expand(
        self,
        summary_id: str,
        max_tokens: int = 5000
    ) -> List[Dict]:
        """展开摘要查看原始内容"""
        return await self.dag_manager.expand_node(
            summary_id=summary_id,
            max_tokens=max_tokens
        )
```

### 4.3 写入服务（IngestService）

```python
# services/ingest_service.py

class IngestService:
    """消息写入服务"""
    
    async def store_user_memory(
        self,
        user_id: str,
        content: str,
        memory_type: str = "preference"
    ) -> Dict:
        """
        存储用户手动输入的记忆
        
        用于 API: POST /memories
        """
        # 长文本分段处理
        if len(content) > 5000:
            return await self._store_long_document(
                user_id=user_id,
                content=content,
                memory_type=memory_type
            )
        
        # 短文本直接存储
        raw_id = await self.raw_store.store(
            user_id=user_id,
            agent_id=None,  # 用户手动
            memory_type=memory_type,
            role="user",
            content=content
        )
        
        # 提取实体
        entities, relations = await self.entity_extractor.extract(content)
        await self.graph_builder.save_entities(entities, user_id, None, raw_id)
        
        # 生成向量
        embedding = await self.vector_indexer.embed(content)
        await self.raw_store.update_embedding(raw_id, embedding)
        
        return {
            "raw_message_id": raw_id,
            "entities_count": len(entities)
        }
    
    async def _store_long_document(
        self,
        user_id: str,
        content: str,
        memory_type: str
    ) -> Dict:
        """存储长文档（分段 + 可选压缩）"""
        document_id = generate_id("doc")
        chunks = self._split_into_chunks(content, max_chars=5000)
        
        raw_ids = []
        all_entities = []
        
        for chunk in chunks:
            raw_id = await self.raw_store.store(
                user_id=user_id,
                agent_id=None,
                memory_type=memory_type,
                role="user",
                content=chunk,
                document_id=document_id  # 关联同一文档
            )
            raw_ids.append(raw_id)
            
            entities, _ = await self.entity_extractor.extract(chunk)
            all_entities.extend(entities)
        
        # 去重实体
        unique_entities = self._deduplicate_entities(all_entities)
        await self.graph_builder.save_entities(unique_entities, user_id, None)
        
        # 生成整文摘要
        summary_result = await self.compaction_engine.summarize_content(
            content,
            is_condensed=False
        )
        
        if summary_result:
            summary_id = await self.summary_store.create_summary(
                user_id=user_id,
                agent_id=None,
                content=summary_result[0],
                kind="leaf",
                document_id=document_id
            )
            
            # 关联分段
            for idx, raw_id in enumerate(raw_ids):
                await self.summary_store.link_message(summary_id, raw_id, idx)
        
        return {
            "document_id": document_id,
            "raw_message_ids": raw_ids,
            "summary_id": summary_id if summary_result else None,
            "chunk_count": len(chunks)
        }
```

### 4.4 召回服务（RecallService）

```python
# services/recall_service.py

class HybridRecallService:
    """混合召回服务"""
    
    async def recall(
        self,
        query: str,
        user_id: str,
        agent_id: str = None,
        scope: str = "all",
        limit: int = 20
    ) -> List[Dict]:
        """
        混合召回
        
        Args:
            scope: 
              - "all": 用户偏好 + Agent 历史
              - "manual_only": 只查用户手动输入
              - "agent_only": 只查指定 Agent 的对话
        """
        # 获取查询向量
        query_embedding = await self.vector_indexer.embed(query)
        
        # 构建来源过滤
        if scope == "manual_only":
            agent_filter = "agent_id IS NULL"
        elif scope == "agent_only" and agent_id:
            agent_filter = f"agent_id = '{agent_id}'"
        else:  # "all"
            if agent_id:
                agent_filter = f"(agent_id IS NULL OR agent_id = '{agent_id}')"
            else:
                agent_filter = "agent_id IS NULL"
        
        # 并行三路召回
        vector_results, keyword_results, graph_results = await asyncio.gather(
            self._vector_recall(query_embedding, user_id, agent_filter, limit),
            self._keyword_recall(query, user_id, agent_filter, limit),
            self._graph_recall(query, user_id, agent_id, scope, limit)
        )
        
        # 融合结果
        merged = self._merge_results(
            vector_results, keyword_results, graph_results
        )
        
        return merged[:limit]
    
    async def _vector_recall(
        self,
        query_embedding: List[float],
        user_id: str,
        agent_filter: str,
        limit: int
    ) -> List[Dict]:
        """向量召回（同时搜索 raw_messages 和 summaries）"""
        results = []
        
        # 搜索 raw_messages
        raw_results = await db.fetch(f"""
            SELECT id, content, agent_id, memory_type,
                   1 - (embedding <=> $1) AS similarity
            FROM raw_messages
            WHERE user_id = $2 AND {agent_filter}
            ORDER BY embedding <=> $1
            LIMIT {limit}
        """, query_embedding, user_id)
        
        for r in raw_results:
            results.append({
                "type": "raw_message",
                "id": r["id"],
                "content": r["content"],
                "agent_id": r["agent_id"],
                "memory_type": r["memory_type"],
                "similarity": r["similarity"],
                "source": "vector",
                "expandable": False
            })
        
        # 搜索 summaries
        summary_results = await db.fetch(f"""
            SELECT summary_id, content, agent_id, kind, depth,
                   1 - (embedding <=> $1) AS similarity
            FROM summaries
            WHERE user_id = $2 AND {agent_filter}
            ORDER BY embedding <=> $1
            LIMIT {limit}
        """, query_embedding, user_id)
        
        for r in summary_results:
            results.append({
                "type": "summary",
                "id": r["summary_id"],
                "content": r["content"],
                "agent_id": r["agent_id"],
                "kind": r["kind"],
                "depth": r["depth"],
                "similarity": r["similarity"],
                "source": "vector",
                "expandable": True
            })
        
        return results
    
    async def _graph_recall(
        self,
        query: str,
        user_id: str,
        agent_id: str,
        scope: str,
        limit: int
    ) -> List[Dict]:
        """图谱召回"""
        # 提取查询实体
        entities = await self._extract_query_entities(query)
        results = []
        
        for entity_name in entities:
            entity = await db.fetchrow("""
                SELECT id FROM entities 
                WHERE name ILIKE $1 AND user_id = $2
            """, f"%{entity_name}%", user_id)
            
            if not entity:
                continue
            
            # 构建 agent 过滤
            if scope == "manual_only":
                agent_condition = "AND rm.agent_id IS NULL"
            elif scope == "agent_only" and agent_id:
                agent_condition = f"AND rm.agent_id = '{agent_id}'"
            else:
                if agent_id:
                    agent_condition = f"AND (rm.agent_id IS NULL OR rm.agent_id = '{agent_id}')"
                else:
                    agent_condition = "AND rm.agent_id IS NULL"
            
            # 通过 message_entities 找原始消息
            message_results = await db.fetch(f"""
                SELECT DISTINCT rm.id, rm.content, rm.agent_id, rm.memory_type
                FROM raw_messages rm
                JOIN message_entities me ON me.message_id = rm.id
                WHERE me.entity_id = $1 AND rm.user_id = $2 {agent_condition}
                LIMIT 5
            """, entity["id"], user_id)
            
            for r in message_results:
                results.append({
                    "type": "raw_message",
                    "id": r["id"],
                    "content": r["content"],
                    "agent_id": r["agent_id"],
                    "memory_type": r["memory_type"],
                    "entity": entity_name,
                    "source": "graph",
                    "expandable": False
                })
            
            # 通过 summary_entities 找摘要
            summary_results = await db.fetch(f"""
                SELECT s.summary_id, s.content, s.agent_id, s.kind, s.depth
                FROM summaries s
                JOIN summary_entities se ON se.summary_id = s.summary_id
                WHERE se.entity_id = $1 AND s.user_id = $2
                LIMIT 5
            """, entity["id"], user_id)
            
            for r in summary_results:
                results.append({
                    "type": "summary",
                    "id": r["summary_id"],
                    "content": r["content"],
                    "agent_id": r["agent_id"],
                    "kind": r["kind"],
                    "depth": r["depth"],
                    "entity": entity_name,
                    "source": "graph",
                    "expandable": True
                })
        
        return results
```

### 4.5 压缩服务（CompactionEngine）

```python
# services/compaction_engine.py

class CompactionEngine:
    """压缩引擎（三阶段策略）"""
    
    FALLBACK_MAX_CHARS = 512 * 4
    
    async def leaf_compact(
        self,
        user_id: str,
        agent_id: str,
        session_id: str,
        token_budget: int = None,
        force: bool = False
    ) -> Optional[CompactionResult]:
        """
        Leaf 压缩
        """
        # 评估是否需要压缩
        tokens_before = await self._get_context_tokens(user_id, session_id)
        threshold = int(self.config.get("context_threshold", 0.75) * (token_budget or 100000))
        
        if not force and tokens_before <= threshold:
            return None
        
        # 选择可压缩的消息块（保护 fresh tail）
        chunk = await self._select_leaf_chunk(user_id, agent_id, session_id)
        if not chunk["items"]:
            return None
        
        # 三阶段压缩
        source_text = self._format_messages(chunk["messages"])
        summary_result = await self._summarize_with_escalation(source_text)
        
        if not summary_result:
            return None
        
        summary_content, level = summary_result
        
        # 存储摘要
        summary_id = await self._create_summary(
            user_id, agent_id, summary_content, chunk, level
        )
        
        # 提取实体并关联
        await self._extract_and_link_entities(summary_id, summary_content, user_id, agent_id)
        
        # 更新 context_items
        await self._update_context_items(
            user_id, agent_id, session_id, chunk["ordinals"], summary_id
        )
        
        tokens_after = await self._get_context_tokens(user_id, session_id)
        
        return CompactionResult(
            action_taken=True,
            summary_id=summary_id,
            tokens_before=tokens_before,
            tokens_after=tokens_after,
            level=level
        )
    
    async def _summarize_with_escalation(
        self, source_text: str
    ) -> Optional[Tuple[str, str]]:
        """
        三阶段压缩策略
        
        Phase 1: normal - 正常 LLM 压缩
        Phase 2: aggressive - 激进压缩
        Phase 3: fallback - 确定性截断
        """
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
        truncated = source_text[:self.FALLBACK_MAX_CHARS]
        return (f"{truncated}\n[Truncated from {input_tokens} tokens]", "fallback")
    
    async def _select_leaf_chunk(
        self, user_id: str, agent_id: str, session_id: str
    ) -> Dict:
        """选择可压缩的消息块（保护 fresh tail）"""
        fresh_tail_count = self.config.get("fresh_tail_count", 8)
        
        # 获取 context_items
        items = await self.context_store.get_context_items(
            user_id, agent_id, session_id
        )
        
        # 分离消息类型
        message_items = [i for i in items if i["item_type"] == "message"]
        
        if not message_items:
            return {"items": [], "ordinals": [], "messages": [], "total_tokens": 0}
        
        # 计算保护边界
        fresh_tail_ordinal = float('inf')
        if len(message_items) > fresh_tail_count:
            tail_start = len(message_items) - fresh_tail_count
            fresh_tail_ordinal = message_items[tail_start]["ordinal"]
        
        # 选择可压缩的消息块
        chunk = []
        chunk_tokens = 0
        max_chunk_tokens = self.config.get("leaf_chunk_tokens", 20000)
        
        for item in message_items:
            if item["ordinal"] >= fresh_tail_ordinal:
                break
            
            msg = await self.raw_store.get_by_id(item["message_id"])
            if msg:
                chunk.append({
                    "ordinal": item["ordinal"],
                    "message": msg
                })
                chunk_tokens += msg["token_count"]
                
                if chunk_tokens >= max_chunk_tokens:
                    break
        
        return {
            "items": chunk,
            "ordinals": [c["ordinal"] for c in chunk],
            "messages": [c["message"] for c in chunk],
            "total_tokens": chunk_tokens
        }
```

---

## 五、API 接口

### 5.1 接口列表

| 端点 | 方法 | 说明 | 来源 |
|------|------|------|------|
| `/memories` | POST | 用户手动添加记忆 | 保留（重构） |
| `/memories/recall` | POST | 混合召回 | 保留（扩展） |
| `/memories/expand` | POST | 展开摘要 | **新增** |
| `/context/assemble` | POST | 组装上下文 | **新增** |
| `/context/compact` | POST | 触发压缩 | **新增** |
| `/graph/entities` | GET | 查询实体 | 保留 |
| `/graph/relations` | GET | 查询关系 | 保留 |

### 5.2 核心接口定义

#### 用户手动添加记忆

```json
POST /memories

Request:
{
  "content": "我是素食主义者，不喜欢吃肉。我也喜欢喝咖啡，尤其是美式。",
  "user_id": "user_001",
  "memory_type": "preference"  // preference/note
}

Response:
{
  "raw_message_id": "raw_abc123",
  "entities": [
    {"name": "素食主义者", "type": "preference"},
    {"name": "咖啡", "type": "topic"}
  ],
  "summary_id": null  // 短文本不生成摘要
}
```

#### 混合召回

```json
POST /memories/recall

Request:
{
  "query": "我的饮食偏好",
  "user_id": "user_001",
  "agent_id": "agent_001",      // 可选
  "scope": "all",               // all/manual_only/agent_only
  "limit": 10,
  "expand_summaries": false
}

Response:
{
  "results": [
    {
      "type": "raw_message",
      "id": "raw_001",
      "content": "我是素食主义者，不喜欢吃肉",
      "agent_id": null,
      "memory_type": "preference",
      "similarity": 0.92,
      "source": "vector"
    },
    {
      "type": "summary",
      "id": "sum_001",
      "content": "用户偏好汇总：素食主义、咖啡爱好者...",
      "agent_id": null,
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
    "graph_count": 2
  }
}
```

#### 展开摘要

```json
POST /memories/expand

Request:
{
  "summary_id": "sum_001",
  "max_tokens": 5000
}

Response:
{
  "summary": {
    "id": "sum_001",
    "content": "用户偏好汇总..."
  },
  "expanded_items": [
    {
      "type": "raw_message",
      "id": "raw_001",
      "content": "我是素食主义者...",
      "token_count": 50
    },
    {
      "type": "raw_message",
      "id": "raw_002",
      "content": "我喜欢喝咖啡...",
      "token_count": 30
    }
  ],
  "total_tokens": 80
}
```

---

## 六、OpenClaw 插件配置

### 6.1 插件清单

```json
{
  "id": "memory-recall",
  "name": "@openclaw/memory-recall",
  "version": "3.0.0",
  "description": "DAG-based memory recall with hybrid search",
  "slots": ["contextEngine"],
  "configSchema": {
    "type": "object",
    "properties": {
      "freshTailCount": {
        "type": "integer",
        "default": 8,
        "description": "保护最近 N 条消息"
      },
      "contextThreshold": {
        "type": "number",
        "default": 0.75,
        "description": "上下文填充阈值"
      },
      "leafChunkTokens": {
        "type": "integer",
        "default": 20000,
        "description": "单次压缩最大 token"
      }
    }
  }
}
```

### 6.2 插件注册

```python
# plugin/index.py

from openclaw.plugin_sdk import OpenClawPluginApi, ContextEngine
from services.memory_recall_engine import MemoryRecallEngine

def register(api: OpenClawPluginApi):
    """插件注册入口"""
    
    # 获取配置
    config = api.plugin_config or {}
    
    # 创建引擎
    engine = MemoryRecallEngine(config)
    
    # 注册 ContextEngine
    api.registerContextEngine("memory-recall", lambda: engine)
    
    # 可选：注册为默认引擎
    api.registerContextEngine("default", lambda: engine)
```

### 6.3 OpenClaw 配置

```json
// openclaw.json
{
  "contextEngine": "memory-recall",
  "plugins": {
    "entries": {
      "memory-recall": {
        "enabled": true,
        "config": {
          "freshTailCount": 8,
          "contextThreshold": 0.75,
          "leafChunkTokens": 20000
        }
      }
    }
  }
}
```

---

## 七、数据迁移

### 7.1 迁移策略

```
┌─────────────────────────────────────────────────────────────────────┐
│                    数据迁移方案                                      │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  阶段 1: 创建新表                                                   │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  • 创建 raw_messages, summaries, summary_* 表               │   │
│  │  • 创建 context_items 表                                     │   │
│  │  • 扩展 entities 表（添加 agent_id 索引）                    │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  阶段 2: 数据迁移                                                   │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  • memories → raw_messages                                  │   │
│  │    - agent_id = NULL（假设都是用户手动输入）                  │   │
│  │    - memory_type = 根据内容判断                              │   │
│  │  • memory_entities → 保留（兼容过渡期）                       │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  阶段 3: 双写过渡                                                   │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  • 新写入同时写入 memories 和 raw_messages                   │   │
│  │  • 召回优先使用 raw_messages                                 │   │
│  │  • 监控无问题后停止写入 memories                             │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  阶段 4: 清理                                                       │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  • 归档 memories 表                                          │   │
│  │  • 删除 memory_entities 表（改用 summary_entities）          │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### 7.2 迁移脚本

```python
# migrations/migrate_to_v3.py

async def migrate_memories_to_raw_messages():
    """迁移 memories 表数据到 raw_messages"""
    
    # 获取所有 memories
    memories = await db.fetch("""
        SELECT id, content, input_type, user_id, created_at,
               time_value, location_name, tags, embedding
        FROM memories
        WHERE status = 'active'
    """)
    
    for mem in memories:
        # 判断 memory_type
        content = mem["content"]
        if len(content) < 200 and any(kw in content for kw in ["喜欢", "不喜欢", "偏好", "习惯"]):
            memory_type = "preference"
        else:
            memory_type = "note"
        
        # 插入 raw_messages
        await db.execute("""
            INSERT INTO raw_messages (
                id, user_id, agent_id, memory_type, role,
                content, embedding, time_value, location_name,
                tags, created_at
            ) VALUES ($1, $2, NULL, $3, 'user', $4, $5, $6, $7, $8, $9)
        """,
            mem["id"],
            mem["user_id"],
            memory_type,
            content,
            mem["embedding"],
            mem["time_value"],
            mem["location_name"],
            mem["tags"],
            mem["created_at"]
        )
    
    print(f"Migrated {len(memories)} memories to raw_messages")
```

---

## 八、实施计划

### 8.1 总体规划

| 阶段 | 周期 | 目标 | 依赖 |
|------|------|------|------|
| Phase 1 | 1 周 | 数据库迁移 + 基础存储服务 | 无 |
| Phase 2 | 1.5 周 | ContextEngine 实现 + DAG 压缩 | Phase 1 |
| Phase 3 | 1 周 | 混合召回整合 + API 接口 | Phase 1 |
| Phase 4 | 0.5 周 | OpenClaw 插件集成 + 测试 | Phase 2, 3 |

### 8.2 详细任务

#### Phase 1: 数据库迁移（1 周）

| 任务 | 优先级 | 预估时间 |
|------|--------|----------|
| 创建 raw_messages 表 | P0 | 0.5 天 |
| 创建 summaries 表及关系表 | P0 | 0.5 天 |
| 创建 context_items 表 | P0 | 0.5 天 |
| 实现 RawMessageStore | P0 | 1 天 |
| 实现 SummaryStore | P0 | 1 天 |
| 实现 ContextStore | P0 | 1 天 |
| 数据迁移脚本 | P1 | 0.5 天 |
| 单元测试 | P0 | 0.5 天 |

#### Phase 2: ContextEngine 实现（1.5 周）

| 任务 | 优先级 | 预估时间 |
|------|--------|----------|
| 实现 MemoryRecallEngine 框架 | P0 | 1 天 |
| 实现 ingest() 方法 | P0 | 1 天 |
| 实现 assemble() 方法 | P0 | 1 天 |
| 实现 compact() 方法（三阶段） | P0 | 1.5 天 |
| 实现 DAGManager | P0 | 1 天 |
| 实现 Fresh Tail 保护 | P0 | 0.5 天 |
| 集成测试 | P0 | 0.5 天 |

#### Phase 3: 召回整合 + API（1 周）

| 任务 | 优先级 | 预估时间 |
|------|--------|----------|
| 扩展向量召回（搜索 raw_messages + summaries） | P0 | 1 天 |
| 扩展图谱召回（通过 summary_entities） | P0 | 1 天 |
| 实现召回结果融合 | P0 | 0.5 天 |
| 实现 DAG 展开功能 | P0 | 0.5 天 |
| 重构 API 接口 | P0 | 1 天 |
| API 文档 | P1 | 0.5 天 |
| 端到端测试 | P0 | 0.5 天 |

#### Phase 4: 插件集成（0.5 周）

| 任务 | 优先级 | 预估时间 |
|------|--------|----------|
| 创建插件清单 | P0 | 0.5 天 |
| 实现 plugin/index.py | P0 | 0.5 天 |
| OpenClaw 集成测试 | P0 | 1 天 |

### 8.3 里程碑验收标准

| 里程碑 | 验收标准 |
|--------|----------|
| Phase 1 完成 | ✅ 新表创建成功<br>✅ 数据迁移无丢失<br>✅ 单元测试通过 |
| Phase 2 完成 | ✅ ContextEngine 接口实现完整<br>✅ 三阶段压缩正常工作<br>✅ Fresh Tail 保护生效 |
| Phase 3 完成 | ✅ 混合召回能搜索 raw_messages + summaries<br>✅ DAG 展开返回原始消息<br>✅ API 接口正常响应 |
| Phase 4 完成 | ✅ 插件注册成功<br>✅ OpenClaw 集成测试通过 |

---

## 九、版本历史

| 版本 | 日期 | 变更 |
|------|------|------|
| v1.0 | 2026-03-26 | 初始设计 |
| v1.1 | 2026-03-26 | 融入 Lossless-Claw 最佳实践 |
| v2.0 | 2026-03-26 | 重构：融合原始能力与新增能力 |
| v3.0 | 2026-03-26 | **重大重构**：<br>- 统一 DAG 记忆架构（替代记忆点提取）<br>- 基于 agent_id 区分来源<br>- 消息级别存储<br>- OpenClaw 插件集成 |
