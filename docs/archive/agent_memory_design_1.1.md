# AI Agent 记忆召回服务设计文档（OpenClaw 记忆插件）

> **版本：** v1.1  
> **日期：** 2026-03-26  
> **状态：** 设计完成（已融入 Lossless-Claw 最佳实践，数据库结构完全对齐）  
> **目标：** 构建一个支持 **Lossless（无损）** 的 OpenClaw 记忆插件，兼容原有混合召回能力，同时实现无限历史上下文智能管理。
> 
> **关键更新（基于 Lossless-Claw 源码研究）：**
> - ✅ 数据库结构：独立关系表（`summary_messages`, `summary_parents`, `context_items`）
> - ✅ 三阶段压缩：normal → aggressive → fallback
> - ✅ DAG 展开：正确理解父子关系（parent 是被压缩的节点）
> - ✅ Context 组装：基于 `context_items` 有序序列

---

## 一、项目背景与目标

### 1.1 现状分析

**✅ 已实现 / 保留能力：**
- 向量检索（HNSW 索引，1024 维）
- 关键词检索（PostgreSQL 全文搜索）
- 图谱检索（实体-关系-记忆三层结构）
- 混合召回策略
- Function Calling 自动提取
- 多用户 Schema 隔离
- same_as 别称映射
- 记忆重要性动态计算 + 访问日志
- 批量操作优化
- TTL / 过期 / 归档管理

**🔄 新增 / 强化能力（对标 Lossless-Claw）：**
- Raw Immutable 消息永不丢失 + DAG 总结链路
- 上下文动态组装（Context Assembler）
- Incremental Compaction Pipeline（leaf → condensed）
- Agent 可调用记忆工具（grep / describe / expand）
- Large File 拦截与独立摘要
- Session 精细作用域控制（ignore / stateless patterns）
- OpenClaw ContextEngine 插件集成

**核心指标（更新）：**

| 指标 | 目标值 | 优先级 |
|------|--------|--------|
| 召回延迟（P95） | < 200ms | P0 |
| 缓存命中率 | > 60% | P1 |
| 记忆分类准确率 | > 80% | P1 |
| Context 组装延迟 | < 150ms | P0 |
| Compaction 成功率 | > 95% | P1 |
| Agent 集成时间 | < 1小时 | P2 |

### 1.2 适用场景

**P0**：多轮对话上下文理解、用户偏好记忆  
**P1**：长任务状态跟踪、中断任务恢复、用户反馈学习、Agent 主动记忆交互  
**P2**：知识库构建、用户画像构建

---

## 二、核心设计理念

### 2.1 四层 Lossless 记忆架构（原三层 + Raw 层）

```
┌──────────────────────────────────────────┐
│  Raw Immutable Messages（无损原始层）     │
│  - 每条用户/助手消息完整持久化            │
│  - 永不删除，仅归档                       │
│  - 存储: PostgreSQL（raw_messages 表）   │
│  - 访问: 毫秒级查询                       │
└──────────────────────────────────────────┘
          ↓ Leaf Summarization
┌──────────────────────────────────────────┐
│  Working Memory（工作记忆）               │
│  - 当前对话 fresh tail（最近 N 条消息）   │
│  - TTL: 1-24小时                         │
│  - 存储: 内存缓存 + 数据库               │
│  - 延迟: < 10ms                          │
└──────────────────────────────────────────┘
          ↓ Compaction
┌──────────────────────────────────────────┐
│  Episodic Memory（情景记忆 + Leaf）       │
│  - 具体事件，叶级摘要（depth=0）          │
│  - TTL: 30-90天                          │
│  - 存储: 数据库 + 向量索引               │
│  - 延迟: < 200ms                         │
└──────────────────────────────────────────┘
          ↓ Condensation
┌──────────────────────────────────────────┐
│  Semantic Memory（语义记忆 + Condensed）  │
│  - 知识、偏好、高层摘要（depth>0）        │
│  - TTL: 永久                             │
│  - 存储: 数据库 + 向量/图谱              │
│  - 延迟: < 200ms                         │
└──────────────────────────────────────────┘
```

**DAG 结构：**

每个总结节点记录以下字段，形成可追溯的有向无环图：

```python
{
    "id": "summary_001",
    "source_message_ids": ["msg_1", "msg_2", "msg_3"],  # 来源消息
    "parent_summary_ids": [],                           # 父摘要（condensed 时有值）
    "depth": 0,                                         # 深度（0=leaf, >0=condensed）
    "kind": "leaf",                                     # 节点类型
    "importance_score": 0.8,                            # 重要性评分
    "created_at": "2026-03-26T10:00:00Z"
}
```

**DAG 核心特性：**
- ✅ **完美展开**：通过 `source_message_ids` 可以追溯所有原始消息
- ✅ **Provenance 追踪**：知道每个摘要来自哪些消息
- ✅ **增量压缩**：支持 leaf → condensed 的增量压缩
- ✅ **深度控制**：通过 `depth` 字段控制压缩层级

---

### 2.2 记忆类型判定规则

**规则优先 + LLM 兜底**（保留原逻辑），新增：

```python
def classify_message(content: str, is_raw: bool = False) -> str:
    """记忆类型判定"""
    
    # Raw 消息始终标记
    if is_raw:
        return "raw"
    
    # 规则判断（快速，< 5ms）
    if any(kw in content for kw in ["正在", "当前", "现在"]):
        return "working"
    
    if any(pattern.match(content) for pattern in ["用户(喜欢|偏好)", "系统规则"]):
        return "semantic"
    
    if any(kw in content for kw in ["昨天", "今天", "上周"]):
        return "episodic"
    
    # LLM 兜底（~200ms）
    return await llm_classify(content)
```

**总结节点自动标记：**
- Leaf 节点（depth=0）→ 自动标记为 `episodic`
- Condensed 节点（depth>0）→ 自动标记为 `semantic`

---

### 2.3 记忆重要性计算

在 DAG 节点上叠加 `importance_score`，影响：

1. **Compaction 优先级**：低重要性消息优先压缩
2. **召回排序**：高重要性记忆排序靠前
3. **Pruning 决策**：低重要性节点优先清理

```python
def calculate_dag_importance(node: Dict, current_time: datetime) -> float:
    """DAG 节点重要性计算"""
    
    # 1. 基础重要性（来自用户反馈或自动评分）
    base = node.get("importance_score", 0.5)
    
    # 2. 时间衰减（指数衰减）
    days_old = (current_time - node["created_at"]).days
    decay_rate = 0.01  # 每天衰减 1%
    time_decay = math.exp(-decay_rate * days_old)
    
    # 3. 深度因子（越深层越重要，因为包含更多信息）
    depth_factor = 1 + node["depth"] * 0.1
    
    # 4. 访问频率因子
    access_count = node.get("access_count", 0)
    access_factor = 1 + math.log(1 + access_count) / 10
    
    # 综合重要性
    importance = base * time_decay * depth_factor * access_factor
    
    return min(1.0, max(0.0, importance))
```

---

## 三、数据模型设计

### 3.1 raw_messages 表（新增）

```sql
-- 原始消息表（永不删除）
CREATE TABLE raw_messages (
    id VARCHAR(24) PRIMARY KEY,
    agent_id VARCHAR(100) NOT NULL,
    session_id VARCHAR(100),
    run_id VARCHAR(100),
    
    -- 消息内容
    role VARCHAR(20) NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content TEXT NOT NULL,
    token_count INTEGER DEFAULT 0,
    
    -- 元数据
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    -- 归档标记（仅归档，不删除）
    is_archived BOOLEAN DEFAULT FALSE,
    archived_at TIMESTAMP WITH TIME ZONE
);

-- 索引
CREATE INDEX idx_raw_messages_agent_session 
    ON raw_messages(agent_id, session_id, created_at DESC);

CREATE INDEX idx_raw_messages_agent_run 
    ON raw_messages(agent_id, run_id, created_at DESC);

CREATE INDEX idx_raw_messages_archived 
    ON raw_messages(is_archived, created_at);

-- 注释
COMMENT ON TABLE raw_messages IS '原始消息表：存储所有原始对话消息，永不删除';
COMMENT ON COLUMN raw_messages.role IS '消息角色：user/assistant/system';
COMMENT ON COLUMN raw_messages.token_count IS 'token 数量（用于预算控制）';
COMMENT ON COLUMN raw_messages.is_archived IS '是否归档（归档后不参与常规召回）';
```

---

### 3.2 summaries 表（新增，对标 Lossless-Claw）

> **关键设计决策**：采用独立关系表存储 DAG 关系，而非 JSONB 字段。
> 
> **原因**：
> 1. 更好的查询性能（JOIN vs JSONB 解析）
> 2. 更强的数据完整性约束（外键）
> 3. 支持递归 CTE 查询 DAG 子树
> 4. 与 Lossless-Claw 实现保持一致

```sql
-- summaries 表：存储所有摘要节点（替代在 memories 表中存储）
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
    
    -- 统计字段（Lossless-Claw 最佳实践）
    earliest_at TIMESTAMP WITH TIME ZONE,           -- 最早消息时间
    latest_at TIMESTAMP WITH TIME ZONE,             -- 最新消息时间
    descendant_count INTEGER NOT NULL DEFAULT 0,    -- 后代节点数量
    descendant_token_count INTEGER NOT NULL DEFAULT 0,  -- 后代节点 token 总数
    source_message_token_count INTEGER NOT NULL DEFAULT 0,  -- 源消息 token 总数
    
    -- 元数据
    model VARCHAR(100) DEFAULT 'unknown',           -- 生成摘要的模型
    file_ids JSONB DEFAULT '[]'::jsonb,             -- 关联文件 ID
    
    -- 时间戳
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    -- 原有字段兼容
    importance_score FLOAT DEFAULT 0.5,
    memory_type VARCHAR(20) DEFAULT 'episodic'
);

-- 索引
CREATE INDEX idx_summaries_agent_session 
    ON summaries(agent_id, session_id, created_at DESC);
CREATE INDEX idx_summaries_kind_depth 
    ON summaries(kind, depth);
CREATE INDEX idx_summaries_earliest 
    ON summaries(earliest_at);

-- 向量索引（用于摘要的语义召回）
CREATE INDEX idx_summaries_embedding 
    ON summaries USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

COMMENT ON TABLE summaries IS '摘要节点表：存储 leaf 和 condensed 摘要';
COMMENT ON COLUMN summaries.kind IS '节点类型：leaf（叶级摘要）或 condensed（高层摘要）';
COMMENT ON COLUMN summaries.depth IS 'DAG 深度：0=leaf, >0=condensed';
COMMENT ON COLUMN summaries.descendant_count IS '后代节点数量（condensed 节点的子节点数）';
COMMENT ON COLUMN summaries.descendant_token_count IS '所有后代节点的 token 总数';
COMMENT ON COLUMN summaries.source_message_token_count IS '原始源消息的 token 总数（用于计算压缩比）';
COMMENT ON COLUMN summaries.embedding IS '摘要内容的向量嵌入（用于语义召回）';
```

---

### 3.3 summary_entities 表（新增，摘要-实体关联）

```sql
-- summary_entities 表：存储摘要与实体的关联
-- 用于图谱召回时发现相关摘要
CREATE TABLE summary_entities (
    summary_id VARCHAR(24) NOT NULL REFERENCES summaries(summary_id) ON DELETE CASCADE,
    entity_id UUID NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    
    -- 实体在摘要中的角色
    role VARCHAR(50),  -- 'mentioned', 'primary', 'context'
    confidence FLOAT DEFAULT 0.8,
    
    PRIMARY KEY (summary_id, entity_id)
);

CREATE INDEX idx_summary_entities_summary 
    ON summary_entities(summary_id);
CREATE INDEX idx_summary_entities_entity 
    ON summary_entities(entity_id);

COMMENT ON TABLE summary_entities IS '摘要-实体关联表：用于图谱召回发现相关摘要';
COMMENT ON COLUMN summary_entities.role IS '实体在摘要中的角色：mentioned(提及)/primary(主要)/context(上下文)';
```

---

### 3.4 summary_messages 表（新增，独立关系表）

```sql
-- summary_messages 表：存储 summary 与 raw message 的关系
-- 替代 JSONB 字段 source_message_ids
CREATE TABLE summary_messages (
    summary_id VARCHAR(24) NOT NULL REFERENCES summaries(summary_id) ON DELETE CASCADE,
    message_id VARCHAR(24) NOT NULL REFERENCES raw_messages(id) ON DELETE RESTRICT,
    ordinal INTEGER NOT NULL,                        -- 顺序号（保持消息顺序）
    
    PRIMARY KEY (summary_id, message_id)
);

CREATE INDEX idx_summary_messages_summary 
    ON summary_messages(summary_id, ordinal);
CREATE INDEX idx_summary_messages_message 
    ON summary_messages(message_id);

COMMENT ON TABLE summary_messages IS '摘要-消息关系表：leaf 摘要引用的原始消息';
COMMENT ON COLUMN summary_messages.ordinal IS '消息在摘要中的顺序（用于展开时保持时序）';
```

---

### 3.4 summary_parents 表（新增，独立关系表）

```sql
-- summary_parents 表：存储 summary 之间的父子关系
-- 替代 JSONB 字段 parent_summary_ids
-- 
-- 重要：父子关系语义（来自 Lossless-Claw）
-- - summary_id: condensed 节点（压缩后的节点）
-- - parent_summary_id: 被压缩的节点（物理存储上的"父"）
-- - 展开时向上遍历 parent_summary_id 获取被压缩的内容
CREATE TABLE summary_parents (
    summary_id VARCHAR(24) NOT NULL REFERENCES summaries(summary_id) ON DELETE CASCADE,
    parent_summary_id VARCHAR(24) NOT NULL REFERENCES summaries(summary_id) ON DELETE RESTRICT,
    ordinal INTEGER NOT NULL,                        -- 顺序号
    
    PRIMARY KEY (summary_id, parent_summary_id)
);

CREATE INDEX idx_summary_parents_summary 
    ON summary_parents(summary_id, ordinal);
CREATE INDEX idx_summary_parents_parent 
    ON summary_parents(parent_summary_id);

COMMENT ON TABLE summary_parents IS '摘要-父摘要关系表：condensed 摘要引用的来源摘要';
COMMENT ON COLUMN summary_parents.summary_id IS 'condensed 节点 ID';
COMMENT ON COLUMN summary_parents.parent_summary_id IS '被压缩的节点 ID（展开时向上遍历）';
```

---

### 3.5 context_items 表（新增，有序上下文序列）

```sql
-- context_items 表：维护有序上下文序列
-- 这是 Lossless-Claw 的核心设计：用一张表维护完整的上下文视图
-- 每个 item 要么是 raw message，要么是 summary
CREATE TABLE context_items (
    agent_id VARCHAR(100) NOT NULL,
    session_id VARCHAR(100) NOT NULL,
    ordinal INTEGER NOT NULL,                        -- 顺序号（核心：维护有序序列）
    item_type VARCHAR(20) NOT NULL CHECK (item_type IN ('message', 'summary')),
    message_id VARCHAR(24) REFERENCES raw_messages(id) ON DELETE RESTRICT,
    summary_id VARCHAR(24) REFERENCES summaries(summary_id) ON DELETE RESTRICT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    PRIMARY KEY (agent_id, session_id, ordinal),
    
    -- 约束：message 和 summary 只能有一个
    CHECK (
        (item_type = 'message' AND message_id IS NOT NULL AND summary_id IS NULL) OR
        (item_type = 'summary' AND summary_id IS NOT NULL AND message_id IS NULL)
    )
);

CREATE INDEX idx_context_items_session 
    ON context_items(agent_id, session_id, ordinal);
CREATE INDEX idx_context_items_message 
    ON context_items(message_id) WHERE message_id IS NOT NULL;
CREATE INDEX idx_context_items_summary 
    ON context_items(summary_id) WHERE summary_id IS NOT NULL;

COMMENT ON TABLE context_items IS '上下文序列表：维护有序的消息/摘要序列（Lossless-Claw 核心设计）';
COMMENT ON COLUMN context_items.ordinal IS '顺序号：决定上下文组装顺序';
COMMENT ON COLUMN context_items.item_type IS '类型：message（原始消息）或 summary（摘要）';
```

**context_items 核心操作**：

```sql
-- 1. 追加消息
INSERT INTO context_items (agent_id, session_id, ordinal, item_type, message_id)
SELECT 'agent_001', 'session_001', COALESCE(MAX(ordinal), -1) + 1, 'message', 'msg_001'
FROM context_items WHERE agent_id = 'agent_001' AND session_id = 'session_001';

-- 2. 替换消息范围为摘要（压缩核心操作）
-- a) 删除范围内的 items
DELETE FROM context_items 
WHERE agent_id = 'agent_001' AND session_id = 'session_001' 
  AND ordinal BETWEEN 0 AND 5;

-- b) 插入摘要
INSERT INTO context_items (agent_id, session_id, ordinal, item_type, summary_id)
VALUES ('agent_001', 'session_001', 0, 'summary', 'sum_001');

-- c) 重排序（保持连续性）
-- 使用负数临时 ordinal 避免 unique 约束冲突
UPDATE context_items SET ordinal = -(ROW_NUMBER() OVER (ORDER BY ordinal) - 1)
WHERE agent_id = 'agent_001' AND session_id = 'session_001';
UPDATE context_items SET ordinal = -ordinal - 1
WHERE agent_id = 'agent_001' AND session_id = 'session_001' AND ordinal < 0;

-- 3. 查询完整上下文
SELECT ci.ordinal, ci.item_type, ci.message_id, ci.summary_id,
       COALESCE(m.content, s.content) AS content
FROM context_items ci
LEFT JOIN raw_messages m ON ci.message_id = m.id
LEFT JOIN summaries s ON ci.summary_id = s.summary_id
WHERE ci.agent_id = 'agent_001' AND ci.session_id = 'session_001'
ORDER BY ci.ordinal;
```

---

### 3.3 agent_configs 表（新增 Lossless 配置）

```sql
CREATE TABLE agent_configs (
    agent_id VARCHAR(100) PRIMARY KEY,
    user_id VARCHAR(100) NOT NULL,
    
    -- 原有配置
    memory_scope VARCHAR(20) DEFAULT 'isolated',
    max_working_memory INTEGER DEFAULT 20,
    default_ttl_days INTEGER DEFAULT 30,
    recall_strategy VARCHAR(20) DEFAULT 'hybrid',
    recall_weights JSONB DEFAULT '{"vector": 0.5, "keyword": 0.3, "graph": 0.2}',
    enable_cache BOOLEAN DEFAULT true,
    
    -- Lossless 核心配置（对标 Lossless-Claw CompactionConfig）
    context_threshold FLOAT DEFAULT 0.75,             -- 上下文填充阈值（触发压缩）
    fresh_tail_count INTEGER DEFAULT 8,               -- 保护的消息数（Lossless-Claw 默认 8）
    
    -- Fanout 配置（决定压缩合并的最小节点数）
    leaf_min_fanout INTEGER DEFAULT 8,                -- leaf 压缩最小消息数
    condensed_min_fanout INTEGER DEFAULT 4,           -- condensed 压缩最小摘要数
    condensed_min_fanout_hard INTEGER DEFAULT 2,      -- 硬触发时最小摘要数
    
    -- Token 配置
    leaf_chunk_tokens INTEGER DEFAULT 20000,          -- 单次 leaf 压缩最大 token
    leaf_target_tokens INTEGER DEFAULT 600,           -- leaf 摘要目标 token
    condensed_target_tokens INTEGER DEFAULT 900,      -- condensed 摘要目标 token
    
    -- 深度控制
    incremental_max_depth INTEGER DEFAULT 3,          -- 增量压缩最大深度（-1=无限）
    max_compaction_rounds INTEGER DEFAULT 10,         -- 最大压缩轮数
    
    -- 其他配置
    large_file_token_threshold INTEGER DEFAULT 25000, -- 大文件拦截阈值
    ignore_session_patterns JSONB DEFAULT '[]'::jsonb, -- 忽略的 session 模式
    stateless_session_patterns JSONB DEFAULT '[]'::jsonb, -- 无状态 session 模式
    timezone VARCHAR(50) DEFAULT 'UTC',               -- 时区（用于摘要时间格式化）
    
    -- 模型配置
    summary_model VARCHAR(100),                        -- 摘要模型
    expansion_model VARCHAR(100),                      -- 展开模型
    
    -- 时间戳
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    CONSTRAINT fk_user FOREIGN KEY (user_id) REFERENCES public.users(id)
);

CREATE INDEX IF NOT EXISTS idx_agent_configs_user ON agent_configs(user_id);

COMMENT ON COLUMN agent_configs.context_threshold IS '上下文填充阈值（0-1），超过则触发压缩';
COMMENT ON COLUMN agent_configs.fresh_tail_count IS '保护最近 N 条消息不被压缩（Lossless-Claw 默认 8）';
COMMENT ON COLUMN agent_configs.leaf_min_fanout IS 'leaf 压缩最小消息数，低于此数不压缩';
COMMENT ON COLUMN agent_configs.condensed_min_fanout IS 'condensed 压缩最小摘要数';
COMMENT ON COLUMN agent_configs.leaf_chunk_tokens IS '单次 leaf 压缩最大 token 数（默认 20000）';
COMMENT ON COLUMN agent_configs.leaf_target_tokens IS 'leaf 摘要目标 token 数（默认 600）';
COMMENT ON COLUMN agent_configs.incremental_max_depth IS '增量压缩最大深度，-1 表示无限';
```

---

### 3.4 compaction_batches 表（新增）

```sql
-- 压缩批次表（用于追踪压缩操作）
CREATE TABLE compaction_batches (
    id VARCHAR(24) PRIMARY KEY,
    agent_id VARCHAR(100) NOT NULL,
    
    -- 批次信息
    batch_type VARCHAR(20) NOT NULL CHECK (batch_type IN ('leaf', 'condensed')),
    input_message_ids JSONB NOT NULL,       -- 输入消息 ID 列表
    output_summary_ids JSONB NOT NULL,      -- 输出摘要 ID 列表
    
    -- 统计信息
    input_token_count INTEGER DEFAULT 0,
    output_token_count INTEGER DEFAULT 0,
    compression_ratio FLOAT DEFAULT 0.0,    -- 压缩比
    
    -- 执行信息
    model_used VARCHAR(100),
    duration_ms INTEGER,
    success BOOLEAN DEFAULT true,
    error_message TEXT,
    
    -- 时间戳
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_compaction_batches_agent 
    ON compaction_batches(agent_id, created_at DESC);

CREATE INDEX idx_compaction_batches_type 
    ON compaction_batches(batch_type, created_at DESC);

COMMENT ON TABLE compaction_batches IS '压缩批次表：追踪所有压缩操作';
```

---

## 四、API 接口设计

### 4.1 核心接口列表（扩展）

| 端点 | 方法 | 用途 | 优先级 |
|------|------|------|--------|
| `/agent/memory/store` | POST | 存储消息（自动 raw + 分类 + compaction） | P0 |
| `/agent/memory/recall` | POST | 传统混合召回 | P0 |
| `/agent/memory/assemble` | POST | **新：Context 动态组装** | P0 |
| `/agent/memory/compact` | POST | **新：触发 Incremental Compaction** | P1 |
| `/agent/memory/expand` | POST | **新：展开 DAG 节点** | P1 |
| `/agent/memory/working` | GET/DELETE | 工作记忆管理 | P0 |
| `/agent/memory/tools` | POST | Agent 工具调用入口 | P1 |

---

### 4.2 存储接口（扩展）

```python
POST /agent/memory/store

Request:
{
    "agent_id": "assistant_001",
    "run_id": "run_abc123",
    "session_id": "session_xyz",
    "content": "用户偏好使用中文回复",
    "role": "user",                    # 新增：消息角色
    "auto_compact": true,              # 新增：是否自动压缩
    "memory_type": "semantic"          # 可选
}

Response:
{
    "code": 200,
    "data": {
        "raw_message_id": "raw_abc123",   # 原始消息 ID
        "memory_id": "mem_def456",         # 记忆 ID（如果已压缩）
        "memory_type": "semantic",
        "importance_score": 0.8,
        
        # DAG 信息
        "is_raw": true,
        "source_message_ids": ["raw_abc123"],
        "depth": 0,
        
        # Compaction 信息
        "compaction_triggered": false,
        "compaction_batch_id": null
    }
}
```

---

### 4.3 Context 组装接口（新增）

```python
POST /agent/memory/assemble

Request:
{
    "agent_id": "assistant_001",
    "run_id": "run_abc123",
    "token_budget": 120000,              # token 预算
    "strategy": "auto"                   # auto / fresh_first / summary_first
}

Response:
{
    "code": 200,
    "data": {
        # 组装后的上下文消息
        "context_messages": [
            {
                "role": "system",
                "content": "<summary id=\"summary_001\" kind=\"leaf\" depth=\"0\">\n用户偏好：使用中文回复，简洁风格\n</summary>"
            },
            {
                "role": "user",
                "content": "帮我写一个脚本"
            },
            {
                "role": "assistant",
                "content": "好的，我来帮你..."
            }
        ],
        
        # 统计信息
        "total_tokens": 85432,
        "fresh_tail_count": 10,           # fresh tail 消息数
        "summary_count": 3,                # 使用的摘要数
        
        # 使用的摘要列表
        "used_summaries": [
            {
                "id": "summary_001",
                "kind": "leaf",
                "depth": 0,
                "token_count": 120,
                "source_message_count": 5
            }
        ],
        
        # 性能指标
        "assembly_time_ms": 120,
        "dag_query_time_ms": 30,
        "fresh_tail_time_ms": 10
    }
}
```

---

### 4.4 DAG 展开接口（新增）

```python
POST /agent/memory/expand

Request:
{
    "agent_id": "assistant_001",
    "summary_id": "summary_001",
    "expand_depth": 1,                   # 展开深度（0=展开一层）
    "max_tokens": 5000                   # 最大 token 数
}

Response:
{
    "code": 200,
    "data": {
        # 展开后的消息列表
        "expanded_messages": [
            {
                "id": "msg_1",
                "role": "user",
                "content": "原始消息内容 1",
                "token_count": 50
            },
            {
                "id": "msg_2",
                "role": "assistant",
                "content": "原始消息内容 2",
                "token_count": 80
            }
        ],
        
        # 展开统计
        "total_tokens": 2500,
        "message_count": 5,
        "expansion_time_ms": 50
    }
}
```

---

### 4.5 Compaction 接口（新增）

```python
POST /agent/memory/compact

Request:
{
    "agent_id": "assistant_001",
    "session_id": "session_xyz",
    "compaction_type": "leaf",           # leaf / condensed
    "force": false                       # 是否强制执行
}

Response:
{
    "code": 200,
    "data": {
        "batch_id": "batch_abc123",
        "compaction_type": "leaf",
        
        # 统计信息
        "input_message_count": 10,
        "output_summary_count": 1,
        "input_tokens": 5000,
        "output_tokens": 500,
        "compression_ratio": 0.1,        # 10% 压缩比
        
        # 生成的摘要
        "summaries": [
            {
                "id": "summary_001",
                "content": "用户询问了 Python 脚本编写...",
                "token_count": 500,
                "source_message_ids": ["msg_1", "msg_2", ...]
            }
        ],
        
        # 性能指标
        "compaction_time_ms": 2500,
        "llm_time_ms": 2000
    }
}
```

---

### 4.6 Agent 工具调用接口

```python
POST /agent/memory/tools

Request:
{
    "agent_id": "assistant_001",
    "tool_name": "memory_grep",          # grep / describe / expand
    "query": "关于张三的记忆",
    "options": {
        "limit": 10,
        "min_similarity": 0.5
    }
}

Response:
{
    "code": 200,
    "data": {
        "tool": "memory_grep",
        "results": [
            {
                "memory_id": "mem_001",
                "content": "昨天和张三讨论了项目",
                "similarity": 0.85
            }
        ],
        "execution_time_ms": 150
    }
}
```

---

## 五、服务架构设计

### 5.1 核心服务类

```python
# services/agent/memory_service.py

class AgentMemoryService:
    """OpenClaw Lossless 记忆服务"""
    
    def __init__(self):
        # 复用现有服务
        self.base_memory_service = memory_service
        self.recall_service = get_recall_service()
        self.graph_service = get_graph_recall_service()
        
        # 原有模块
        self.classifier = MemoryClassifier()
        self.importance_calculator = ImportanceCalculator()
        self.cache = MemoryCache()
        
        # 新增 Lossless 模块
        self.raw_store = RawMessageStore()
        self.dag_manager = DAGManager()
        self.compaction_engine = CompactionEngine()
        self.context_assembler = ContextAssembler()
        self.retrieval_tools = RetrievalTools()
    
    async def store(
        self,
        agent_id: str,
        content: str,
        role: str,
        **kwargs
    ) -> Dict[str, Any]:
        """
        存储消息（Lossless 方式）
        
        流程：
        1. 永久存储 raw message（Lossless 核心）
        2. 智能分类 & 重要性计算
        3. 可能触发 leaf compaction
        4. 存入 memories（带 DAG 信息）
        """
        start_time = time.time()
        
        try:
            # 1. 永久存储 raw message
            raw_id = await self.raw_store.store(
                agent_id=agent_id,
                role=role,
                content=content,
                session_id=kwargs.get('session_id'),
                run_id=kwargs.get('run_id')
            )
            
            # 2. 智能分类
            if not kwargs.get('memory_type'):
                kwargs['memory_type'] = await self.classifier.classify(content)
            
            # 3. 计算重要性
            if not kwargs.get('importance_score'):
                kwargs['importance_score'] = await self.importance_calculator.calculate(
                    content=content,
                    memory_type=kwargs['memory_type']
                )
            
            # 4. 可能触发 leaf compaction
            compaction_result = None
            if kwargs.get('auto_compact', True) and self._should_compact(agent_id):
                compaction_result = await self.compaction_engine.leaf_compact(
                    agent_id=agent_id,
                    session_id=kwargs.get('session_id')
                )
            
            # 5. 存入 memories（带 DAG 信息）
            result = await self.base_memory_service.create({
                "content": content,
                "agent_id": agent_id,
                "is_raw": True,
                "source_message_ids": [raw_id],
                "depth": 0,
                "kind": "leaf",
                **kwargs
            })
            
            logger.info(
                f"存储消息成功: agent_id={agent_id}, "
                f"raw_id={raw_id}, "
                f"time={time.time() - start_time:.3f}s"
            )
            
            return {
                "raw_message_id": raw_id,
                "memory_id": result.get("id"),
                "compaction_triggered": compaction_result is not None,
                "compaction_batch_id": compaction_result.get("batch_id") if compaction_result else None
            }
            
        except Exception as e:
            logger.error(f"存储消息失败: {e}")
            raise
    
    async def assemble_context(
        self,
        agent_id: str,
        run_id: str,
        token_budget: int,
        strategy: str = "auto"
    ) -> Dict[str, Any]:
        """
        OpenClaw ContextEngine 核心方法
        
        流程：
        1. 获取 fresh tail（最近 N 条原始消息）
        2. 计算剩余 token 预算
        3. 从 DAG 中选择摘要（智能填充）
        4. 组装上下文（带 provenance 标签）
        """
        start_time = time.time()
        
        try:
            # 1. 获取 fresh tail
            config = await self._get_agent_config(agent_id)
            fresh_tail = await self.raw_store.get_fresh_tail(
                agent_id=agent_id,
                run_id=run_id,
                count=config.get("fresh_tail_count", 32)
            )
            
            # 2. 计算剩余 token 预算
            fresh_tokens = sum(m.get("token_count", 0) for m in fresh_tail)
            remaining_budget = token_budget - fresh_tokens
            
            # 3. 从 DAG 中选择摘要
            summaries = await self.dag_manager.select_summaries_for_budget(
                agent_id=agent_id,
                token_budget=remaining_budget,
                strategy=strategy
            )
            
            # 4. 组装上下文
            context_messages = self.context_assembler.build(
                fresh_tail=fresh_tail,
                summaries=summaries
            )
            
            # 5. 返回结果
            total_tokens = fresh_tokens + sum(s.get("token_count", 0) for s in summaries)
            
            return {
                "context_messages": context_messages,
                "total_tokens": total_tokens,
                "fresh_tail_count": len(fresh_tail),
                "summary_count": len(summaries),
                "used_summaries": summaries,
                "assembly_time_ms": int((time.time() - start_time) * 1000)
            }
            
        except Exception as e:
            logger.error(f"组装上下文失败: {e}")
            raise
    
    def _should_compact(self, agent_id: str) -> bool:
        """判断是否需要压缩"""
        # 检查最近的消息数量
        # 如果超过阈值，触发压缩
        return True  # 简化逻辑
```

---

### 5.2 RawMessageStore

```python
# services/agent/raw_message_store.py

class RawMessageStore:
    """原始消息存储"""
    
    async def store(
        self,
        agent_id: str,
        role: str,
        content: str,
        **kwargs
    ) -> str:
        """存储原始消息"""
        # 计算 token 数量
        token_count = self._count_tokens(content)
        
        # 生成 ID
        raw_id = generate_id("raw")
        
        # 存储到数据库
        await db.execute("""
            INSERT INTO raw_messages 
            (id, agent_id, session_id, run_id, role, content, token_count)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
        """, 
            raw_id, 
            agent_id, 
            kwargs.get('session_id'),
            kwargs.get('run_id'),
            role, 
            content, 
            token_count
        )
        
        return raw_id
    
    async def get_fresh_tail(
        self,
        agent_id: str,
        run_id: str,
        count: int = 32
    ) -> List[Dict[str, Any]]:
        """获取 fresh tail（最近 N 条消息）"""
        messages = await db.fetch("""
            SELECT id, role, content, token_count, created_at
            FROM raw_messages
            WHERE agent_id = $1 AND run_id = $2
            ORDER BY created_at DESC
            LIMIT $3
        """, agent_id, run_id, count)
        
        # 按时间正序返回
        return list(reversed([dict(m) for m in messages]))
    
    def _count_tokens(self, content: str) -> int:
        """计算 token 数量"""
        # 简化：按字符数估算
        return len(content) // 2
```

---

### 5.3 DAGManager（对标 Lossless-Claw SummaryStore）

> **关键理解**：DAG 父子关系的语义
> 
> 在 `summary_parents` 表中：
> - `summary_id`: condensed 节点（压缩后的结果）
> - `parent_summary_id`: 被压缩的节点（展开时需要向上遍历）
> 
> **注意**：这里的 "parent" 是物理存储上的概念，不是逻辑上的父子。
> 展开时，从 condensed 节点出发，向上遍历 `parent_summary_id` 获取被压缩的内容。

```python
# services/agent/dag_manager.py

from dataclasses import dataclass
from typing import List, Dict, Any, Optional
from datetime import datetime

@dataclass
class SummaryRecord:
    """摘要记录"""
    summary_id: str
    agent_id: str
    session_id: str
    kind: str  # 'leaf' | 'condensed'
    depth: int
    content: str
    token_count: int
    earliest_at: Optional[datetime]
    latest_at: Optional[datetime]
    descendant_count: int
    descendant_token_count: int
    source_message_token_count: int
    model: str
    created_at: datetime

@dataclass
class SummarySubtreeNode(SummaryRecord):
    """DAG 子树节点（用于展开）"""
    depth_from_root: int
    parent_summary_id: Optional[str]  # 被压缩的节点 ID
    path: str
    child_count: int

class DAGManager:
    """DAG 管理器（对标 Lossless-Claw SummaryStore）"""
    
    # ── Summary CRUD ─────────────────────────────────────────────
    
    async def insert_summary(self, input: Dict[str, Any]) -> SummaryRecord:
        """插入摘要节点"""
        summary_id = input.get("summary_id") or generate_id("sum")
        
        await db.execute("""
            INSERT INTO summaries (
                summary_id, agent_id, session_id, kind, depth,
                content, token_count, earliest_at, latest_at,
                descendant_count, descendant_token_count,
                source_message_token_count, model
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
        """,
            summary_id,
            input["agent_id"],
            input.get("session_id"),
            input["kind"],
            input.get("depth", 0),
            input["content"],
            input["token_count"],
            input.get("earliest_at"),
            input.get("latest_at"),
            input.get("descendant_count", 0),
            input.get("descendant_token_count", 0),
            input.get("source_message_token_count", 0),
            input.get("model", "unknown")
        )
        
        return await self.get_summary(summary_id)
    
    async def get_summary(self, summary_id: str) -> Optional[SummaryRecord]:
        """获取摘要记录"""
        row = await db.fetchrow("""
            SELECT * FROM summaries WHERE summary_id = $1
        """, summary_id)
        
        if not row:
            return None
        
        return SummaryRecord(
            summary_id=row["summary_id"],
            agent_id=row["agent_id"],
            session_id=row["session_id"],
            kind=row["kind"],
            depth=row["depth"],
            content=row["content"],
            token_count=row["token_count"],
            earliest_at=row["earliest_at"],
            latest_at=row["latest_at"],
            descendant_count=row["descendant_count"],
            descendant_token_count=row["descendant_token_count"],
            source_message_token_count=row["source_message_token_count"],
            model=row["model"],
            created_at=row["created_at"]
        )
    
    # ── 关系链接（关键方法）─────────────────────────────────────
    
    async def link_summary_to_messages(
        self, 
        summary_id: str, 
        message_ids: List[str]
    ) -> None:
        """
        链接 leaf 摘要到原始消息
        
        在 summary_messages 表中建立关系：
        - summary_id: leaf 摘要
        - message_id: 被压缩的原始消息
        """
        if not message_ids:
            return
        
        for idx, msg_id in enumerate(message_ids):
            await db.execute("""
                INSERT INTO summary_messages (summary_id, message_id, ordinal)
                VALUES ($1, $2, $3)
                ON CONFLICT (summary_id, message_id) DO NOTHING
            """, summary_id, msg_id, idx)
    
    async def link_summary_to_parents(
        self, 
        summary_id: str, 
        parent_summary_ids: List[str]
    ) -> None:
        """
        链接 condensed 摘要到父摘要
        
        在 summary_parents 表中建立关系：
        - summary_id: condensed 节点（压缩结果）
        - parent_summary_id: 被压缩的节点（展开时向上遍历）
        
        **重要**：这里的 "parent" 是被压缩的节点，不是逻辑父节点！
        展开时需要从 summary_id 向上遍历 parent_summary_id。
        """
        if not parent_summary_ids:
            return
        
        for idx, parent_id in enumerate(parent_summary_ids):
            await db.execute("""
                INSERT INTO summary_parents (summary_id, parent_summary_id, ordinal)
                VALUES ($1, $2, $3)
                ON CONFLICT (summary_id, parent_summary_id) DO NOTHING
            """, summary_id, parent_id, idx)
    
    # ── 关系查询（核心展开方法）─────────────────────────────────
    
    async def get_summary_messages(self, summary_id: str) -> List[str]:
        """
        获取 leaf 摘要关联的原始消息 ID
        
        用于展开 leaf 节点，获取被压缩的原始消息。
        """
        rows = await db.fetch("""
            SELECT message_id FROM summary_messages
            WHERE summary_id = $1
            ORDER BY ordinal
        """, summary_id)
        
        return [row["message_id"] for row in rows]
    
    async def get_summary_parents(self, summary_id: str) -> List[SummaryRecord]:
        """
        获取 condensed 摘要的父摘要（被压缩的节点）
        
        **关键理解**：
        - 返回的是被这个 condensed 节点压缩的所有摘要
        - 展开时需要向上遍历这些 "父" 节点
        - 这与传统的树结构父子关系是相反的！
        
        对应 Lossless-Claw 的注释：
        > getSummaryParents(summaryId) returns the source summaries compacted
        > into `summaryId`. Expansion should use this direction for replay.
        """
        rows = await db.fetch("""
            SELECT s.* FROM summaries s
            JOIN summary_parents sp ON sp.parent_summary_id = s.summary_id
            WHERE sp.summary_id = ?
            ORDER BY sp.ordinal
        """, summary_id)
        
        return [self._row_to_record(row) for row in rows]
    
    async def get_summary_children(self, parent_summary_id: str) -> List[SummaryRecord]:
        """
        获取引用某个摘要的所有 condensed 节点
        
        返回所有 "压缩了" 这个摘要的 condensed 节点。
        这是从子节点向父节点的反向查询。
        """
        rows = await db.fetch("""
            SELECT s.* FROM summaries s
            JOIN summary_parents sp ON sp.summary_id = s.summary_id
            WHERE sp.parent_summary_id = ?
            ORDER BY sp.ordinal
        """, parent_summary_id)
        
        return [self._row_to_record(row) for row in rows]
    
    # ── DAG 子树查询（递归 CTE）──────────────────────────────────
    
    async def get_summary_subtree(
        self, 
        summary_id: str
    ) -> List[SummarySubtreeNode]:
        """
        获取摘要的完整子树（用于展开）
        
        使用递归 CTE 从 summary_id 向上遍历所有被压缩的节点。
        
        遍历方向：
        summary_id → parent_summary_id → parent_summary_id → ...
        
        这会返回所有被这个 condensed 节点压缩的内容。
        """
        rows = await db.fetch("""
            WITH RECURSIVE subtree(summary_id, parent_summary_id, depth_from_root, path) AS (
                -- 起点：指定的摘要
                SELECT $1, NULL, 0, ''
                
                UNION ALL
                
                -- 递归：向上遍历父节点
                SELECT
                    sp.summary_id,
                    sp.parent_summary_id,
                    subtree.depth_from_root + 1,
                    CASE
                        WHEN subtree.path = '' THEN printf('%04d', sp.ordinal)
                        ELSE subtree.path || '.' || printf('%04d', sp.ordinal)
                    END
                FROM summary_parents sp
                JOIN subtree ON sp.parent_summary_id = subtree.summary_id
            )
            SELECT
                s.*,
                subtree.depth_from_root,
                subtree.parent_summary_id,
                subtree.path,
                (SELECT COUNT(*) FROM summary_parents sp2
                 WHERE sp2.parent_summary_id = s.summary_id) AS child_count
            FROM subtree
            JOIN summaries s ON s.summary_id = subtree.summary_id
            ORDER BY subtree.depth_from_root ASC, subtree.path ASC, s.created_at ASC
        """, summary_id)
        
        # 去重（DAG 可能有重复节点）
        seen = set()
        result = []
        for row in rows:
            if row["summary_id"] in seen:
                continue
            seen.add(row["summary_id"])
            
            record = self._row_to_record(row)
            result.append(SummarySubtreeNode(
                **record.__dict__,
                depth_from_root=row["depth_from_root"],
                parent_summary_id=row["parent_summary_id"],
                path=row["path"],
                child_count=row["child_count"]
            ))
        
        return result
    
    # ── 展开方法 ─────────────────────────────────────────────────
    
    async def expand_node(
        self,
        summary_id: str,
        expand_depth: int = 1,
        max_tokens: int = 5000
    ) -> List[Dict[str, Any]]:
        """
        展开 DAG 节点
        
        流程：
        1. 获取摘要信息
        2. 如果是 leaf，直接返回关联的原始消息
        3. 如果是 condensed，向上遍历父节点
        4. 按 token 限制返回
        """
        summary = await self.get_summary(summary_id)
        if not summary:
            return []
        
        result = []
        total_tokens = 0
        
        if summary.kind == "leaf":
            # Leaf 节点：返回原始消息
            message_ids = await self.get_summary_messages(summary_id)
            
            for msg_id in message_ids:
                if total_tokens >= max_tokens:
                    break
                
                msg = await db.fetchrow("""
                    SELECT id, role, content, token_count
                    FROM raw_messages WHERE id = $1
                """, msg_id)
                
                if msg:
                    tokens = msg["token_count"] or len(msg["content"]) // 4
                    if total_tokens + tokens <= max_tokens:
                        result.append({
                            "id": msg["id"],
                            "role": msg["role"],
                            "content": msg["content"],
                            "token_count": tokens,
                            "source": "raw_message"
                        })
                        total_tokens += tokens
        
        else:
            # Condensed 节点：向上遍历父节点
            subtree = await self.get_summary_subtree(summary_id)
            
            for node in subtree:
                if total_tokens >= max_tokens:
                    break
                
                if node.depth_from_root > expand_depth:
                    continue
                
                tokens = node.token_count
                if total_tokens + tokens <= max_tokens:
                    result.append({
                        "id": node.summary_id,
                        "kind": node.kind,
                        "depth": node.depth,
                        "content": node.content,
                        "token_count": tokens,
                        "source": "summary"
                    })
                    total_tokens += tokens
        
        return result
    
    def _row_to_record(self, row: Dict) -> SummaryRecord:
        """将数据库行转换为记录对象"""
        return SummaryRecord(
            summary_id=row["summary_id"],
            agent_id=row["agent_id"],
            session_id=row["session_id"],
            kind=row["kind"],
            depth=row["depth"],
            content=row["content"],
            token_count=row["token_count"],
            earliest_at=row["earliest_at"],
            latest_at=row["latest_at"],
            descendant_count=row["descendant_count"],
            descendant_token_count=row["descendant_token_count"],
            source_message_token_count=row["source_message_token_count"],
            model=row["model"],
            created_at=row["created_at"]
        )
```

**DAG 展开流程图**：

```
┌─────────────────────────────────────────────────────────────────────┐
│                        DAG 展开逻辑                                  │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  假设有以下 DAG 结构：                                               │
│                                                                     │
│       [condensed_2, depth=2]                                        │
│              │                                                      │
│              ├── [condensed_1, depth=1]                             │
│              │         │                                            │
│              │         ├── [leaf_1] ── msg_1, msg_2, msg_3          │
│              │         └── [leaf_2] ── msg_4, msg_5                 │
│              │                                                      │
│              └── [condensed_1b, depth=1]                            │
│                        │                                            │
│                        └── [leaf_3] ── msg_6, msg_7                 │
│                                                                     │
│  展开流程：                                                          │
│                                                                     │
│  1. 用户请求展开 condensed_2                                        │
│     │                                                               │
│     ↓                                                               │
│  2. 查询 summary_parents 表                                         │
│     WHERE summary_id = 'condensed_2'                                │
│     → 返回 parent_summary_ids: [condensed_1, condensed_1b]         │
│     │                                                               │
│     ↓                                                               │
│  3. 递归向上遍历                                                    │
│     condensed_1 → parent: [leaf_1, leaf_2]                         │
│     condensed_1b → parent: [leaf_3]                                │
│     leaf_1 → messages: [msg_1, msg_2, msg_3]                       │
│     leaf_2 → messages: [msg_4, msg_5]                              │
│     leaf_3 → messages: [msg_6, msg_7]                              │
│     │                                                               │
│     ↓                                                               │
│  4. 按 token 预算返回结果                                           │
│     - 按时序排列                                                    │
│     - 截断到 max_tokens                                             │
│                                                                     │
│  关键理解：                                                          │
│  - summary_parents 表存储的是 "被压缩" 关系                         │
│  - parent_summary_id 是被压缩的节点                                 │
│  - 展开时向上遍历 parent_summary_id                                 │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```
        
        for summary in summaries:
            summary_tokens = summary["token_count"]
            
            if total_tokens + summary_tokens <= token_budget:
                selected.append(dict(summary))
                total_tokens += summary_tokens
        
        return selected
    
    async def expand_node(
        self,
        summary_id: str,
        expand_depth: int = 1,
        max_tokens: int = 5000
    ) -> List[Dict[str, Any]]:
        """展开 DAG 节点"""
        # 获取摘要信息
        summary = await db.fetchrow(
            "SELECT * FROM memories WHERE id = $1",
            summary_id
        )
        
        if not summary:
            return []
        
        # 获取源消息
        source_ids = json.loads(summary["source_message_ids"])
        
        messages = await db.fetch("""
            SELECT id, role, content, token_count
            FROM raw_messages
            WHERE id = ANY($1)
            ORDER BY created_at ASC
        """, source_ids)
        
        # 按 token 限制返回
        result = []
        total_tokens = 0
        
        for msg in messages:
            if total_tokens + msg["token_count"] <= max_tokens:
                result.append(dict(msg))
                total_tokens += msg["token_count"]
        
        return result
```

---

### 5.4 CompactionEngine（对标 Lossless-Claw）

> **核心设计**：三阶段压缩策略（normal → aggressive → fallback）
> 
> **来源**：Lossless-Claw `src/compaction.ts` `summarizeWithEscalation` 方法

```python
# services/agent/compaction_engine.py

from enum import Enum
from dataclasses import dataclass
from typing import List, Dict, Any, Optional, Callable

class CompactionLevel(Enum):
    """压缩级别（三阶段）"""
    NORMAL = "normal"           # 正常压缩
    AGGRESSIVE = "aggressive"   # 激进压缩
    FALLBACK = "fallback"       # 确定性截断

@dataclass
class CompactionConfig:
    """压缩配置（对标 Lossless-Claw CompactionConfig）"""
    context_threshold: float = 0.75         # 触发压缩的阈值
    fresh_tail_count: int = 8               # 保护的消息数
    leaf_min_fanout: int = 8                # leaf 压缩最小消息数
    condensed_min_fanout: int = 4           # condensed 压缩最小摘要数
    condensed_min_fanout_hard: int = 2      # 硬触发时最小摘要数
    incremental_max_depth: int = 3          # 增量压缩最大深度
    leaf_chunk_tokens: int = 20000          # 单次 leaf 压缩最大 token
    leaf_target_tokens: int = 600           # leaf 摘要目标 token
    condensed_target_tokens: int = 900      # condensed 摘要目标 token
    max_rounds: int = 10                    # 最大压缩轮数
    timezone: str = "UTC"                   # 时区

@dataclass
class CompactionResult:
    """压缩结果"""
    action_taken: bool
    tokens_before: int
    tokens_after: int
    created_summary_id: Optional[str] = None
    condensed: bool = False
    level: Optional[CompactionLevel] = None

class CompactionEngine:
    """压缩引擎（对标 Lossless-Claw CompactionEngine）"""
    
    FALLBACK_MAX_CHARS = 512 * 4  # 512 tokens * 4 chars
    
    def __init__(self, config: CompactionConfig):
        self.config = config
        self.llm_client = get_llm_client()
        self.summary_store = SummaryStore()
        self.context_store = ContextStore()
    
    # ── 三阶段压缩核心方法 ─────────────────────────────────────────
    
    async def summarize_with_escalation(
        self,
        source_text: str,
        previous_summary: Optional[str] = None,
        is_condensed: bool = False,
        depth: int = 0
    ) -> Optional[tuple[str, CompactionLevel]]:
        """
        三阶段压缩策略（Lossless-Claw 核心设计）
        
        阶段 1: normal - 正常 LLM 压缩
        阶段 2: aggressive - 激进 LLM 压缩（更强提示）
        阶段 3: fallback - 确定性截断（不依赖 LLM）
        
        Returns:
            (summary_content, level) 或 None（认证失败时）
        """
        source_text = source_text.strip()
        if not source_text:
            return ("[Truncated from 0 tokens]", CompactionLevel.FALLBACK)
        
        input_tokens = max(1, self._estimate_tokens(source_text))
        
        # ── 阶段 1: Normal 压缩 ─────────────────────────────────────
        try:
            normal_summary = await self._call_llm(
                source_text,
                aggressive=False,
                previous_summary=previous_summary,
                is_condensed=is_condensed,
                depth=depth
            )
        except LLMAuthError:
            # 认证失败，不写入截断产物
            return None
        
        if not normal_summary or not normal_summary.strip():
            # 空输出，回退到确定性截断
            return self._build_deterministic_fallback(source_text, input_tokens)
        
        summary_text = normal_summary.strip()
        level = CompactionLevel.NORMAL
        
        # 检查压缩效果
        if self._estimate_tokens(summary_text) >= input_tokens:
            # ── 阶段 2: Aggressive 压缩 ─────────────────────────────
            try:
                aggressive_summary = await self._call_llm(
                    source_text,
                    aggressive=True,
                    previous_summary=previous_summary,
                    is_condensed=is_condensed,
                    depth=depth
                )
            except LLMAuthError:
                return None
            
            if not aggressive_summary or not aggressive_summary.strip():
                return self._build_deterministic_fallback(source_text, input_tokens)
            
            summary_text = aggressive_summary.strip()
            level = CompactionLevel.AGGRESSIVE
            
            # 再次检查
            if self._estimate_tokens(summary_text) >= input_tokens:
                # ── 阶段 3: Fallback 确定性截断 ─────────────────────
                return self._build_deterministic_fallback(source_text, input_tokens)
        
        return (summary_text, level)
    
    def _build_deterministic_fallback(
        self, 
        source_text: str, 
        input_tokens: int
    ) -> tuple[str, CompactionLevel]:
        """
        确定性截断（不依赖 LLM）
        
        当 LLM 压缩失败或效果不佳时，使用简单的字符截断
        """
        truncated = (
            source_text[:self.FALLBACK_MAX_CHARS] 
            if len(source_text) > self.FALLBACK_MAX_CHARS 
            else source_text
        )
        return (
            f"{truncated}\n[Truncated from {input_tokens} tokens]",
            CompactionLevel.FALLBACK
        )
    
    # ── Leaf 压缩流程 ─────────────────────────────────────────────
    
    async def leaf_compact(
        self,
        agent_id: str,
        session_id: str,
        token_budget: int,
        force: bool = False,
        previous_summary_content: Optional[str] = None
    ) -> CompactionResult:
        """
        Leaf 压缩（depth=0）
        
        流程：
        1. 评估是否需要压缩
        2. 选择最老的未压缩消息块（保护 fresh tail）
        3. 三阶段压缩生成摘要
        4. 创建 leaf 节点，更新 context_items
        5. 可选：增量 condensed 压缩
        """
        tokens_before = await self._get_context_token_count(agent_id, session_id)
        threshold = int(self.config.context_threshold * token_budget)
        
        # 评估 leaf trigger
        leaf_trigger = await self._evaluate_leaf_trigger(agent_id, session_id)
        
        if not force and tokens_before <= threshold and not leaf_trigger.should_compact:
            return CompactionResult(
                action_taken=False,
                tokens_before=tokens_before,
                tokens_after=tokens_before
            )
        
        # 选择最老的未压缩消息块
        leaf_chunk = await self._select_oldest_leaf_chunk(agent_id, session_id)
        if not leaf_chunk.items:
            return CompactionResult(
                action_taken=False,
                tokens_before=tokens_before,
                tokens_after=tokens_before
            )
        
        # 解析 prior summary context
        prior_context = (
            previous_summary_content or 
            await self._resolve_prior_leaf_summary_context(
                agent_id, session_id, leaf_chunk.items
            )
        )
        
        # 执行 leaf pass
        leaf_result = await self._leaf_pass(
            agent_id, session_id, leaf_chunk.items, prior_context
        )
        if not leaf_result:
            return CompactionResult(
                action_taken=False,
                tokens_before=tokens_before,
                tokens_after=tokens_before
            )
        
        tokens_after_leaf = await self._get_context_token_count(agent_id, session_id)
        
        # 增量 condensed 压缩
        tokens_after = tokens_after_leaf
        condensed = False
        created_summary_id = leaf_result.summary_id
        level = leaf_result.level
        
        if self.config.incremental_max_depth > 0:
            for target_depth in range(self.config.incremental_max_depth):
                fanout = self._get_fanout_for_depth(target_depth, hard_trigger=False)
                chunk = await self._select_oldest_chunk_at_depth(
                    agent_id, session_id, target_depth
                )
                
                if len(chunk.items) < fanout:
                    break
                
                condense_result = await self._condensed_pass(
                    agent_id, session_id, chunk.items, target_depth
                )
                if not condense_result:
                    break
                
                tokens_after = await self._get_context_token_count(agent_id, session_id)
                condensed = True
                created_summary_id = condense_result.summary_id
                level = condense_result.level
                
                if tokens_after >= tokens_after_leaf:
                    break
        
        return CompactionResult(
            action_taken=True,
            tokens_before=tokens_before,
            tokens_after=tokens_after,
            created_summary_id=created_summary_id,
            condensed=condensed,
            level=level
        )
    
    # ── Condensed 压缩流程 ─────────────────────────────────────────
    
    async def condensed_pass(
        self,
        agent_id: str,
        session_id: str,
        summary_items: List[ContextItem],
        target_depth: int
    ) -> Optional[tuple[str, CompactionLevel]]:
        """
        Condensed 压缩（depth > 0）
        
        将多个同深度摘要压缩为一个更高层摘要
        """
        # 获取摘要记录
        summary_records = []
        for item in summary_items:
            if item.summary_id:
                rec = await self.summary_store.get_summary(item.summary_id)
                if rec:
                    summary_records.append(rec)
        
        if not summary_records:
            return None
        
        # 格式化输入
        concatenated = self._format_summaries_for_condensation(summary_records)
        
        # 三阶段压缩
        result = await self.summarize_with_escalation(
            concatenated,
            is_condensed=True,
            depth=target_depth + 1
        )
        
        if not result:
            return None
        
        summary_content, level = result
        
        # 创建 condensed 节点
        summary_id = generate_id("sum")
        token_count = self._estimate_tokens(summary_content)
        
        # 计算统计字段
        earliest_at = min(r.earliest_at or r.created_at for r in summary_records)
        latest_at = max(r.latest_at or r.created_at for r in summary_records)
        descendant_count = sum(r.descendant_count + 1 for r in summary_records)
        descendant_token_count = sum(
            r.token_count + r.descendant_token_count for r in summary_records
        )
        source_message_token_count = sum(
            r.source_message_token_count for r in summary_records
        )
        
        # 存储 condensed 摘要
        await self.summary_store.insert_summary({
            "summary_id": summary_id,
            "agent_id": agent_id,
            "session_id": session_id,
            "kind": "condensed",
            "depth": target_depth + 1,
            "content": summary_content,
            "token_count": token_count,
            "earliest_at": earliest_at,
            "latest_at": latest_at,
            "descendant_count": descendant_count,
            "descendant_token_count": descendant_token_count,
            "source_message_token_count": source_message_token_count
        })
        
        # 关联父摘要（关键：parent_summary_id 是被压缩的节点）
        parent_ids = [r.summary_id for r in summary_records]
        await self.summary_store.link_summary_to_parents(summary_id, parent_ids)
        
        # 更新 context_items
        ordinals = [item.ordinal for item in summary_items]
        await self.context_store.replace_context_range_with_summary(
            agent_id, session_id,
            start_ordinal=min(ordinals),
            end_ordinal=max(ordinals),
            summary_id=summary_id
        )
        
        return (summary_id, level)
    
    # ── Fresh Tail 保护机制 ─────────────────────────────────────────
    
    async def _select_oldest_leaf_chunk(
        self, 
        agent_id: str, 
        session_id: str
    ) -> LeafChunkSelection:
        """
        选择最老的未压缩消息块（保护 fresh tail）
        
        关键逻辑：
        1. 获取 context_items 中的所有消息
        2. 计算保护边界（最后 N 条消息）
        3. 选择保护边界外的连续消息块
        4. 限制单次压缩的 token 数
        """
        context_items = await self.context_store.get_context_items(
            agent_id, session_id
        )
        
        # 计算保护边界
        message_items = [
            item for item in context_items 
            if item.item_type == "message" and item.message_id
        ]
        
        fresh_tail_ordinal = float('inf')
        if self.config.fresh_tail_count > 0 and message_items:
            tail_start_idx = max(0, len(message_items) - self.config.fresh_tail_count)
            fresh_tail_ordinal = message_items[tail_start_idx].ordinal
        
        # 选择可压缩的消息块
        chunk = []
        chunk_tokens = 0
        started = False
        
        for item in context_items:
            # 超过保护边界，停止
            if item.ordinal >= fresh_tail_ordinal:
                break
            
            # 跳过摘要（只压缩原始消息）
            if item.item_type != "message" or not item.message_id:
                if started:
                    break
                continue
            
            started = True
            msg = await self.raw_store.get_message(item.message_id)
            if not msg:
                continue
            
            msg_tokens = msg.token_count or self._estimate_tokens(msg.content)
            
            # 检查 token 限制
            if chunk and chunk_tokens + msg_tokens > self.config.leaf_chunk_tokens:
                break
            
            chunk.append(item)
            chunk_tokens += msg_tokens
            
            if chunk_tokens >= self.config.leaf_chunk_tokens:
                break
        
        return LeafChunkSelection(items=chunk, tokens=chunk_tokens)
    
    # ── 辅助方法 ─────────────────────────────────────────────────
    
    def _estimate_tokens(self, text: str) -> int:
        """估算 token 数（~4 chars per token）"""
        return max(1, len(text) // 4)
    
    def _get_fanout_for_depth(self, depth: int, hard_trigger: bool) -> int:
        """获取指定深度的最小 fanout"""
        if hard_trigger:
            return self.config.condensed_min_fanout_hard
        if depth == 0:
            return self.config.leaf_min_fanout
        return self.config.condensed_min_fanout
```

**三阶段压缩流程图**：

```
┌─────────────────────────────────────────────────────────────┐
│                    三阶段压缩策略                            │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  输入: source_text (原始消息/摘要内容)                       │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ 阶段 1: Normal 压缩                                   │   │
│  │ - 调用 LLM 生成摘要                                   │   │
│  │ - 使用正常提示词                                       │   │
│  │ - 检查: output_tokens < input_tokens?                │   │
│  └─────────────────────────────────────────────────────┘   │
│                        │                                    │
│              ┌────────┴────────┐                           │
│              ↓ 是              ↓ 否                        │
│         返回结果         进入阶段 2                          │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ 阶段 2: Aggressive 压缩                               │   │
│  │ - 调用 LLM 生成摘要                                   │   │
│  │ - 使用更强压缩提示词                                   │   │
│  │ - 检查: output_tokens < input_tokens?                │   │
│  └─────────────────────────────────────────────────────┘   │
│                        │                                    │
│              ┌────────┴────────┐                           │
│              ↓ 是              ↓ 否                        │
│         返回结果         进入阶段 3                          │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ 阶段 3: Fallback 确定性截断                            │   │
│  │ - 不依赖 LLM                                          │   │
│  │ - 字符截断（最大 512 tokens）                          │   │
│  │ - 添加 "[Truncated from N tokens]" 标记               │   │
│  └─────────────────────────────────────────────────────┘   │
│                        │                                    │
│                        ↓                                    │
│                   返回结果                                   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

### 5.5 ContextAssembler（对标 Lossless-Claw）

> **核心设计**：基于 `context_items` 表的有序序列组装
> 
> **来源**：Lossless-Claw `src/assembler.ts`

```python
# services/agent/context_assembler.py

from dataclasses import dataclass
from typing import List, Dict, Any, Optional
from datetime import datetime

@dataclass
class AssembleResult:
    """组装结果"""
    messages: List[Dict[str, Any]]      # 有序消息列表
    estimated_tokens: int               # 估算 token 数
    system_prompt_addition: Optional[str]  # 动态系统提示
    stats: Dict[str, int]               # 统计信息

class ContextAssembler:
    """
    上下文组装器（对标 Lossless-Claw ContextAssembler）
    
    核心功能：
    1. 从 context_items 表获取有序序列
    2. 解析每个 item（message 或 summary）
    3. 保护 fresh tail
    4. 按 token 预算选择
    5. 生成动态系统提示（LCM Recall 指引）
    """
    
    def __init__(self, timezone: str = "UTC"):
        self.timezone = timezone
        self.raw_store = RawMessageStore()
        self.summary_store = SummaryStore()
        self.context_store = ContextStore()
    
    async def assemble(
        self,
        agent_id: str,
        session_id: str,
        token_budget: int,
        fresh_tail_count: int = 8
    ) -> AssembleResult:
        """
        组装上下文
        
        流程：
        1. 获取 context_items 有序序列
        2. 解析每个 item 为 AgentMessage
        3. 分割 evictable prefix 和 protected fresh tail
        4. 按 token 预算选择
        5. 生成动态系统提示
        """
        # Step 1: 获取有序 context items
        context_items = await self.context_store.get_context_items(
            agent_id, session_id
        )
        
        if not context_items:
            return AssembleResult(
                messages=[],
                estimated_tokens=0,
                system_prompt_addition=None,
                stats={"raw_message_count": 0, "summary_count": 0, "total_items": 0}
            )
        
        # Step 2: 解析每个 item
        resolved_items = await self._resolve_items(context_items)
        
        # 统计
        raw_message_count = sum(1 for item in resolved_items if item.is_message)
        summary_count = sum(1 for item in resolved_items if not item.is_message)
        summary_signals = [
            item.summary_signal for item in resolved_items 
            if item.summary_signal
        ]
        
        # Step 3: 分割 evictable 和 fresh tail
        tail_start = max(0, len(resolved_items) - fresh_tail_count)
        fresh_tail = resolved_items[tail_start:]
        evictable = resolved_items[:tail_start]
        
        # Step 4: 按 token 预算选择
        # 计算新鲜尾部 token
        tail_tokens = sum(item.tokens for item in fresh_tail)
        
        # 填充剩余预算
        remaining_budget = max(0, token_budget - tail_tokens)
        evictable_total = sum(item.tokens for item in evictable)
        
        selected = []
        if evictable_total <= remaining_budget:
            # 全部放得下
            selected = evictable
        else:
            # 从最新开始保留，丢弃最老的
            kept = []
            accum = 0
            for i in range(len(evictable) - 1, -1, -1):
                item = evictable[i]
                if accum + item.tokens <= remaining_budget:
                    kept.append(item)
                    accum += item.tokens
                else:
                    break
            selected = list(reversed(kept))
        
        # 追加 fresh tail
        selected.extend(fresh_tail)
        
        # 计算 token
        estimated_tokens = sum(item.tokens for item in selected)
        
        # Step 5: 生成动态系统提示
        system_prompt_addition = self._build_system_prompt_addition(summary_signals)
        
        return AssembleResult(
            messages=[item.message for item in selected],
            estimated_tokens=estimated_tokens,
            system_prompt_addition=system_prompt_addition,
            stats={
                "raw_message_count": raw_message_count,
                "summary_count": summary_count,
                "total_items": len(resolved_items)
            }
        )
    
    async def _resolve_items(
        self, 
        context_items: List[ContextItem]
    ) -> List[ResolvedItem]:
        """解析 context items 为 resolved items"""
        resolved = []
        
        for item in context_items:
            if item.item_type == "message" and item.message_id:
                result = await self._resolve_message_item(item)
                if result:
                    resolved.append(result)
            elif item.item_type == "summary" and item.summary_id:
                result = await self._resolve_summary_item(item)
                if result:
                    resolved.append(result)
        
        return resolved
    
    async def _resolve_message_item(
        self, 
        item: ContextItem
    ) -> Optional[ResolvedItem]:
        """解析消息 item"""
        msg = await self.raw_store.get_message(item.message_id)
        if not msg:
            return None
        
        tokens = self._estimate_tokens(msg.content)
        
        return ResolvedItem(
            ordinal=item.ordinal,
            message={
                "role": msg.role,
                "content": msg.content
            },
            tokens=tokens,
            is_message=True
        )
    
    async def _resolve_summary_item(
        self, 
        item: ContextItem
    ) -> Optional[ResolvedItem]:
        """解析摘要 item"""
        summary = await self.summary_store.get_summary(item.summary_id)
        if not summary:
            return None
        
        # 格式化摘要为 XML
        content = await self._format_summary_content(summary)
        tokens = self._estimate_tokens(content)
        
        return ResolvedItem(
            ordinal=item.ordinal,
            message={
                "role": "user",  # 摘要作为 user message
                "content": content
            },
            tokens=tokens,
            is_message=False,
            summary_signal={
                "kind": summary.kind,
                "depth": summary.depth,
                "descendant_count": summary.descendant_count
            }
        )
    
    async def _format_summary_content(
        self, 
        summary: SummaryRecord
    ) -> str:
        """
        格式化摘要为 XML（对标 Lossless-Claw formatSummaryContent）
        
        输出格式：
        <summary id="sum_xxx" kind="leaf" depth="0" descendant_count="0" earliest_at="..." latest_at="...">
          <parents>
            <summary_ref id="sum_yyy" />
          </parents>
          <content>
            摘要内容...
          </content>
        </summary>
        """
        attributes = [
            f'id="{summary.summary_id}"',
            f'kind="{summary.kind}"',
            f'depth="{summary.depth}"',
            f'descendant_count="{summary.descendant_count}"'
        ]
        
        if summary.earliest_at:
            attributes.append(
                f'earliest_at="{self._format_date(summary.earliest_at)}"'
            )
        if summary.latest_at:
            attributes.append(
                f'latest_at="{self._format_date(summary.latest_at)}"'
            )
        
        lines = [f"<summary {' '.join(attributes)}>"]
        
        # Condensed 节点包含父引用
        if summary.kind == "condensed":
            parents = await self.summary_store.get_summary_parents(summary.summary_id)
            if parents:
                lines.append("  <parents>")
                for parent in parents:
                    lines.append(f'    <summary_ref id="{parent.summary_id}" />')
                lines.append("  </parents>")
        
        lines.append("  <content>")
        lines.append(summary.content)
        lines.append("  </content>")
        lines.append("</summary>")
        
        return "\n".join(lines)
    
    def _build_system_prompt_addition(
        self, 
        summary_signals: List[Dict]
    ) -> Optional[str]:
        """
        构建动态系统提示（LCM Recall 指引）
        
        对标 Lossless-Claw buildSystemPromptAddition
        """
        if not summary_signals:
            return None
        
        max_depth = max(s["depth"] for s in summary_signals)
        condensed_count = sum(1 for s in summary_signals if s["kind"] == "condensed")
        heavily_compacted = max_depth >= 2 or condensed_count >= 2
        
        sections = [
            "## LCM Recall",
            "",
            "Summaries above are compressed context — maps to details, not the details themselves.",
            "",
            "**Recall priority:** Use LCM tools first for compacted conversation history.",
            "",
            "**Tool escalation:**",
            "1. `lcm_grep` — search by regex or full-text",
            "2. `lcm_describe` — inspect a specific summary",
            "3. `lcm_expand_query` — deep recall with DAG expansion",
        ]
        
        if heavily_compacted:
            sections.extend([
                "",
                "⚠ **Deeply compacted context — expand before asserting specifics.**",
                "",
                "**Do not guess** exact commands, SHAs, file paths, timestamps, or config values from condensed summaries.",
            ])
        else:
            sections.extend([
                "",
                "**For precision questions** (exact commands, SHAs, paths): expand before answering.",
            ])
        
        return "\n".join(sections)
    
    def _estimate_tokens(self, text: str) -> int:
        """估算 token 数（~4 chars per token）"""
        return max(1, len(text) // 4)
    
    def _format_date(self, date: datetime) -> str:
        """格式化日期用于 XML 属性"""
        try:
            import pytz
            tz = pytz.timezone(self.timezone)
            localized = date.astimezone(tz)
            return localized.strftime("%Y-%m-%dT%H:%M:%S")
        except:
            return date.isoformat()
```

**Context 组装流程图**：

```
┌─────────────────────────────────────────────────────────────────────┐
│                    Context 组装流程                                  │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  输入: agent_id, session_id, token_budget, fresh_tail_count        │
│                                                                     │
│  Step 1: 获取 context_items 有序序列                                 │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │ SELECT * FROM context_items                                  │   │
│  │ WHERE agent_id = ? AND session_id = ?                        │   │
│  │ ORDER BY ordinal                                              │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                        │                                            │
│                        ↓                                            │
│  Step 2: 解析每个 item                                              │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │ item_type = 'message' → 查询 raw_messages 表                 │   │
│  │ item_type = 'summary' → 查询 summaries 表                    │   │
│  │                                                              │   │
│  │ 格式化 summary 为 XML：                                       │   │
│  │ <summary id="sum_xxx" kind="leaf" depth="0" ...>            │   │
│  │   <content>摘要内容</content>                                 │   │
│  │ </summary>                                                   │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                        │                                            │
│                        ↓                                            │
│  Step 3: 分割 evictable 和 fresh tail                               │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │ ┌──────────────┬──────────────────────────────────────────┐ │   │
│  │ │  evictable   │          fresh tail (protected)           │ │   │
│  │ │  (可丢弃)     │          (最后 N 条，不可丢弃)              │ │   │
│  │ └──────────────┴──────────────────────────────────────────┘ │   │
│  │                      ↑                                       │   │
│  │              tail_start = len - fresh_tail_count            │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                        │                                            │
│                        ↓                                            │
│  Step 4: 按 token 预算选择                                          │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │ 1. 计算 fresh tail 的 token 占用                             │   │
│  │ 2. 剩余预算 = token_budget - tail_tokens                     │   │
│  │ 3. 从 evictable 末端开始保留（保留最新的）                     │   │
│  │ 4. 直到预算用完                                              │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                        │                                            │
│                        ↓                                            │
│  Step 5: 生成动态系统提示                                           │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │ 如果有 summary：                                              │   │
│  │ - 添加 LCM Recall 指引                                        │   │
│  │ - 深度压缩时添加警告                                          │   │
│  │ - 提示使用 lcm_grep/lcm_expand_query 工具                    │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                        │                                            │
│                        ↓                                            │
│  输出: AssembleResult                                               │
│  - messages: 有序消息列表                                           │
│  - estimated_tokens: token 数                                       │
│  - system_prompt_addition: 动态系统提示                             │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 六、混合召回与图谱整合设计

> **核心问题**：如何将现有的混合召回（向量+关键词+图谱）与 DAG 压缩/展开机制整合？

### 6.1 整合架构

```
┌─────────────────────────────────────────────────────────────────────┐
│                        混合召回架构（扩展）                           │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                      召回请求                                 │   │
│  │            query: "张三的项目进展"                            │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                              │                                      │
│                              ↓                                      │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                   并行三路召回                                │   │
│  ├─────────────────────────────────────────────────────────────┤   │
│  │                                                              │   │
│  │  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐        │   │
│  │  │ 向量召回      │ │ 关键词召回    │ │ 图谱召回      │        │   │
│  │  │ (HNSW)       │ │ (FTS)        │ │ (Graph)      │        │   │
│  │  └──────────────┘ └──────────────┘ └──────────────┘        │   │
│  │        │                │                │                  │   │
│  │        ↓                ↓                ↓                  │   │
│  │  ┌──────────────────────────────────────────────────┐      │   │
│  │  │ 同时搜索：                                         │      │   │
│  │  │ 1. raw_messages 表（原始消息）                      │      │   │
│  │  │ 2. summaries 表（摘要节点）★新增★                  │      │   │
│  │  │ 3. memories 表（传统记忆）                          │      │   │
│  │  └──────────────────────────────────────────────────┘      │   │
│  │                                                              │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                              │                                      │
│                              ↓                                      │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                    结果融合与排序                             │   │
│  ├─────────────────────────────────────────────────────────────┤   │
│  │  来源类型：                                                   │   │
│  │  - raw_message: 原始消息（最新鲜，优先级高）                    │   │
│  │  - summary: 压缩摘要（信息密度高，可展开）                      │   │
│  │  - memory: 传统记忆（兼容旧数据）                              │   │
│  │                                                              │   │
│  │  排序因子：                                                   │   │
│  │  - 相似度得分                                                 │   │
│  │  - 时间相关性                                                 │   │
│  │  - 来源类型权重                                               │   │
│  │  - 重要性评分                                                 │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                              │                                      │
│                              ↓                                      │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                    返回结果                                   │   │
│  │  [                                                           │   │
│  │    { type: "raw_message", id: "msg_001", ... },              │   │
│  │    { type: "summary", id: "sum_001", expandable: true },     │   │
│  │    { type: "summary", id: "sum_002", expandable: true },     │   │
│  │    ...                                                       │   │
│  │  ]                                                           │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

### 6.2 三路召回整合实现

#### 6.2.1 向量召回（扩展）

```python
# services/agent/hybrid_recall_service.py

class HybridRecallService:
    """混合召回服务（扩展支持摘要）"""
    
    def __init__(self):
        self.embedding_service = get_embedding_service()
        self.vector_store = VectorStore()
    
    async def vector_recall(
        self,
        query: str,
        agent_id: str,
        limit: int = 20,
        include_summaries: bool = True
    ) -> List[Dict[str, Any]]:
        """
        向量召回（同时搜索原始消息和摘要）
        
        对比原实现：
        - 原：只搜索 memories 表
        - 新：同时搜索 raw_messages, summaries, memories 三张表
        """
        # 1. 获取查询向量
        query_embedding = await self.embedding_service.embed(query)
        
        results = []
        
        # 2. 搜索原始消息（如果有 embedding）
        raw_results = await self.vector_store.search(
            table="raw_messages",
            embedding=query_embedding,
            filters={"agent_id": agent_id},
            limit=limit // 3
        )
        for r in raw_results:
            results.append({
                "type": "raw_message",
                "id": r["id"],
                "content": r["content"],
                "similarity": r["similarity"],
                "created_at": r["created_at"],
                "source": "vector"
            })
        
        # 3. 搜索摘要节点（★新增★）
        if include_summaries:
            summary_results = await self.vector_store.search(
                table="summaries",
                embedding=query_embedding,
                filters={"agent_id": agent_id},
                limit=limit // 3
            )
            for r in summary_results:
                results.append({
                    "type": "summary",
                    "id": r["summary_id"],
                    "content": r["content"],
                    "kind": r["kind"],
                    "depth": r["depth"],
                    "similarity": r["similarity"],
                    "created_at": r["created_at"],
                    "expandable": True,  # 可展开
                    "source": "vector"
                })
        
        # 4. 搜索传统记忆（兼容）
        memory_results = await self.vector_store.search(
            table="memories",
            embedding=query_embedding,
            filters={"agent_id": agent_id},
            limit=limit // 3
        )
        for r in memory_results:
            results.append({
                "type": "memory",
                "id": r["id"],
                "content": r["content"],
                "similarity": r["similarity"],
                "created_at": r["created_at"],
                "source": "vector"
            })
        
        # 5. 统一排序
        results.sort(key=lambda x: x["similarity"], reverse=True)
        
        return results[:limit]
```

#### 6.2.2 图谱召回（扩展）

```python
async def graph_recall(
    self,
    query: str,
    agent_id: str,
    limit: int = 20,
    include_summaries: bool = True
) -> List[Dict[str, Any]]:
    """
    图谱召回（扩展支持摘要实体）
    
    流程：
    1. 从 query 提取实体
    2. 查询 entities 表找到相关实体
    3. 通过 memory_entities 和 summary_entities 双路召回
    """
    # 1. 提取查询实体
    query_entities = await self._extract_query_entities(query)
    
    results = []
    
    for entity_name in query_entities:
        # 2. 查找实体
        entity = await db.fetchrow("""
            SELECT id, name, type FROM entities 
            WHERE name ILIKE $1 AND user_id = (
                SELECT user_id FROM agent_configs WHERE agent_id = $2
            )
        """, f"%{entity_name}%", agent_id)
        
        if not entity:
            continue
        
        # 3. 通过 memory_entities 召回（原逻辑）
        memory_results = await db.fetch("""
            SELECT m.id, m.content, m.created_at, me.confidence
            FROM memories m
            JOIN memory_entities me ON me.memory_id = m.id
            WHERE me.entity_id = $1 AND m.agent_id = $2
            ORDER BY me.confidence DESC, m.created_at DESC
            LIMIT $3
        """, entity["id"], agent_id, limit // 2)
        
        for r in memory_results:
            results.append({
                "type": "memory",
                "id": r["id"],
                "content": r["content"],
                "entity": entity["name"],
                "confidence": r["confidence"],
                "source": "graph"
            })
        
        # 4. 通过 summary_entities 召回（★新增★）
        if include_summaries:
            summary_results = await db.fetch("""
                SELECT s.summary_id, s.content, s.kind, s.depth,
                       s.earliest_at, se.confidence
                FROM summaries s
                JOIN summary_entities se ON se.summary_id = s.summary_id
                WHERE se.entity_id = $1 AND s.agent_id = $2
                ORDER BY se.confidence DESC, s.earliest_at DESC
                LIMIT $3
            """, entity["id"], agent_id, limit // 2)
            
            for r in summary_results:
                results.append({
                    "type": "summary",
                    "id": r["summary_id"],
                    "content": r["content"],
                    "kind": r["kind"],
                    "depth": r["depth"],
                    "entity": entity["name"],
                    "confidence": r["confidence"],
                    "expandable": True,
                    "source": "graph"
                })
    
    return results
```

---

### 6.3 压缩时的实体提取

> **关键设计**：压缩时需要提取摘要中的实体，建立 summary_entities 关联

```python
# services/agent/compaction_engine.py

async def leaf_pass(
    self,
    agent_id: str,
    session_id: str,
    message_items: List[ContextItem],
    previous_summary_content: Optional[str] = None
) -> Optional[LeafPassResult]:
    """
    Leaf 压缩（扩展：同时提取实体）
    """
    # ... 原有压缩逻辑 ...
    
    # 创建 leaf 摘要
    summary_id = generate_id("sum")
    
    # ★新增：提取摘要中的实体★
    entities = await self._extract_summary_entities(
        summary_content, 
        agent_id
    )
    
    # 存储 summary
    await self.summary_store.insert_summary({
        "summary_id": summary_id,
        "agent_id": agent_id,
        "content": summary_content,
        "embedding": await self.embedding_service.embed(summary_content),
        # ... 其他字段 ...
    })
    
    # ★新增：建立实体关联★
    for entity_info in entities:
        # 获取或创建实体
        entity = await self._get_or_create_entity(
            agent_id, 
            entity_info["name"], 
            entity_info["type"]
        )
        
        # 建立关联
        await db.execute("""
            INSERT INTO summary_entities (summary_id, entity_id, role, confidence)
            VALUES ($1, $2, $3, $4)
        """, summary_id, entity["id"], entity_info["role"], entity_info["confidence"])
    
    return LeafPassResult(summary_id=summary_id, ...)

async def _extract_summary_entities(
    self, 
    content: str, 
    agent_id: str
) -> List[Dict[str, Any]]:
    """
    从摘要中提取实体
    
    复用现有的实体提取逻辑（Function Calling）
    """
    # 复用 extract_memories_tool 的实体提取部分
    result = await self.llm_client.function_call(
        model=self.config.summary_model,
        tools=[EXTRACT_ENTITIES_TOOL],
        messages=[{
            "role": "user",
            "content": f"提取以下摘要中的关键实体：\n\n{content}"
        }]
    )
    
    entities = []
    for entity in result.get("entities", []):
        entities.append({
            "name": entity["name"],
            "type": entity["type"],
            "role": entity.get("role", "mentioned"),
            "confidence": entity.get("confidence", 0.8)
        })
    
    return entities
```

---

### 6.4 召回结果融合

```python
class HybridRecallService:
    
    async def recall(
        self,
        query: str,
        agent_id: str,
        strategy: str = "hybrid",
        weights: Dict[str, float] = None,
        limit: int = 20
    ) -> Dict[str, Any]:
        """
        混合召回（向量+关键词+图谱）
        
        扩展：支持摘要节点的召回和展开
        """
        weights = weights or {"vector": 0.5, "keyword": 0.3, "graph": 0.2}
        
        # 并行三路召回
        vector_results, keyword_results, graph_results = await asyncio.gather(
            self.vector_recall(query, agent_id, limit),
            self.keyword_recall(query, agent_id, limit),
            self.graph_recall(query, agent_id, limit)
        )
        
        # 融合结果
        merged = self._merge_results(
            vector_results, 
            keyword_results, 
            graph_results,
            weights
        )
        
        # 按综合得分排序
        merged.sort(key=lambda x: x["combined_score"], reverse=True)
        
        # 返回结果（区分可展开的摘要）
        return {
            "results": merged[:limit],
            "expandable_summaries": [
                r for r in merged 
                if r["type"] == "summary"
            ][:5],  # 最多返回5个可展开摘要
            "stats": {
                "vector_count": len(vector_results),
                "keyword_count": len(keyword_results),
                "graph_count": len(graph_results),
                "summary_count": sum(1 for r in merged if r["type"] == "summary")
            }
        }
    
    def _merge_results(
        self,
        vector_results: List,
        keyword_results: List,
        graph_results: List,
        weights: Dict[str, float]
    ) -> List[Dict]:
        """
        融合三路召回结果
        
        考虑因素：
        1. 来源权重（向量/关键词/图谱）
        2. 类型权重（raw_message > summary > memory）
        3. 时间衰减
        """
        score_map = {}  # id -> result with score
        
        # 类型权重
        type_weights = {
            "raw_message": 1.0,  # 原始消息最高
            "summary": 0.85,     # 摘要次高
            "memory": 0.7        # 传统记忆最低
        }
        
        # 向量结果
        for r in vector_results:
            rid = r["id"]
            if rid not in score_map:
                score_map[rid] = r
                score_map[rid]["combined_score"] = 0
            
            score_map[rid]["combined_score"] += (
                r["similarity"] * weights["vector"] * type_weights[r["type"]]
            )
        
        # 关键词结果
        for r in keyword_results:
            rid = r["id"]
            if rid not in score_map:
                score_map[rid] = r
                score_map[rid]["combined_score"] = 0
            
            score_map[rid]["combined_score"] += (
                r.get("match_score", 0.5) * weights["keyword"] * type_weights[r["type"]]
            )
        
        # 图谱结果
        for r in graph_results:
            rid = r["id"]
            if rid not in score_map:
                score_map[rid] = r
                score_map[rid]["combined_score"] = 0
            
            score_map[rid]["combined_score"] += (
                r.get("confidence", 0.5) * weights["graph"] * type_weights[r["type"]]
            )
        
        return list(score_map.values())
```

---

### 6.5 召回后展开

> **用户场景**：召回结果包含摘要，用户想要查看详细内容

```python
async def recall_with_expansion(
    self,
    query: str,
    agent_id: str,
    expand_summaries: bool = True,
    max_expansion_tokens: int = 5000
) -> Dict[str, Any]:
    """
    召回 + 展开
    
    流程：
    1. 执行混合召回
    2. 对召回结果中的摘要，执行 DAG 展开
    3. 合并返回
    """
    # 1. 混合召回
    recall_result = await self.recall(query, agent_id)
    
    if not expand_summaries:
        return recall_result
    
    # 2. 展开摘要
    expanded_results = []
    total_expansion_tokens = 0
    
    for result in recall_result["results"]:
        if result["type"] == "summary":
            # 展开摘要
            if total_expansion_tokens >= max_expansion_tokens:
                break
            
            expanded = await self.dag_manager.expand_node(
                summary_id=result["id"],
                max_tokens=max_expansion_tokens - total_expansion_tokens
            )
            
            total_expansion_tokens += sum(
                item.get("token_count", 0) for item in expanded
            )
            
            result["expanded"] = expanded
            result["expansion_token_count"] = sum(
                item.get("token_count", 0) for item in expanded
            )
        
        expanded_results.append(result)
    
    recall_result["results"] = expanded_results
    recall_result["expansion_stats"] = {
        "total_tokens": total_expansion_tokens,
        "expanded_count": sum(1 for r in expanded_results if r.get("expanded"))
    }
    
    return recall_result
```

---

### 6.6 整合流程图

```
┌─────────────────────────────────────────────────────────────────────┐
│                  混合召回 + DAG 整合流程                             │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  用户查询: "张三的项目进展"                                          │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │ Step 1: 并行三路召回                                         │   │
│  │                                                              │   │
│  │  向量召回 ──────────────────────────────────────────────────┐│   │
│  │  │ 搜索: raw_messages.embedding ~ query_embedding          ││   │
│  │  │ 搜索: summaries.embedding ~ query_embedding ★新增★      ││   │
│  │  │ 搜索: memories.embedding ~ query_embedding              ││   │
│  │  └────────────────────────────────────────────────────────┘│   │
│  │                                                              │   │
│  │  关键词召回 ────────────────────────────────────────────────┐│   │
│  │  │ 搜索: raw_messages.content @@ to_tsquery()              ││   │
│  │  │ 搜索: summaries.content @@ to_tsquery() ★新增★          ││   │
│  │  │ 搜索: memories.content @@ to_tsquery()                  ││   │
│  │  └────────────────────────────────────────────────────────┘│   │
│  │                                                              │   │
│  │  图谱召回 ──────────────────────────────────────────────────┐│   │
│  │  │ 提取实体: "张三"                                         ││   │
│  │  │ 通过 memory_entities 找相关记忆                          ││   │
│  │  │ 通过 summary_entities 找相关摘要 ★新增★                  ││   │
│  │  │ 通过 relations 找关联实体                                 ││   │
│  │  └────────────────────────────────────────────────────────┘│   │
│  └─────────────────────────────────────────────────────────────┘   │
│                              │                                      │
│                              ↓                                      │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │ Step 2: 结果融合                                             │   │
│  │                                                              │   │
│  │  去重 + 加权计算综合得分                                      │   │
│  │  - 来源权重: vector(0.5) + keyword(0.3) + graph(0.2)        │   │
│  │  - 类型权重: raw_message(1.0) > summary(0.85) > memory(0.7) │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                              │                                      │
│                              ↓                                      │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │ Step 3: 返回结果                                             │   │
│  │                                                              │   │
│  │  [                                                          │   │
│  │    { type: "raw_message", id: "msg_001", content: "..." },  │   │
│  │    { type: "summary", id: "sum_001", content: "...",        │   │
│  │      expandable: true, kind: "leaf", depth: 0 },            │   │
│  │    { type: "summary", id: "sum_002", content: "...",        │   │
│  │      expandable: true, kind: "condensed", depth: 1 },       │   │
│  │    ...                                                      │   │
│  │  ]                                                          │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                              │                                      │
│                              ↓                                      │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │ Step 4: 可选展开                                             │   │
│  │                                                              │   │
│  │  用户选择展开 sum_001:                                        │   │
│  │  → DAG 向上遍历获取原始消息                                   │   │
│  │  → 返回 msg_1, msg_2, msg_3, ...                            │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 七、性能优化方案

### 6.1 多级缓存架构

```
┌──────────────────────────────────────┐
│  L1 Cache: 工作记忆（内存）           │
│  - TTL: 1小时                        │
│  - 容量: 20条/session                 │
│  - 延迟: < 10ms                      │
│  - 命中率目标: > 90%                 │
└──────────────────────────────────────┘
          ↓ Miss
┌──────────────────────────────────────┐
│  L2 Cache: 召回结果（内存）           │
│  - TTL: 5分钟                        │
│  - 容量: 1000条                      │
│  - 延迟: < 5ms                       │
│  - 命中率目标: > 60%                 │
└──────────────────────────────────────┘
          ↓ Miss
┌──────────────────────────────────────┐
│  L3 Cache: DAG 预计算（Redis）        │
│  - TTL: 10分钟                       │
│  - 存储: 热门 session 的 DAG 结构     │
│  - 延迟: < 50ms                      │
│  - 命中率目标: > 40%                 │
└──────────────────────────────────────┘
          ↓ Miss
┌──────────────────────────────────────┐
│  Database: PostgreSQL + pgvector     │
│  - 延迟: 50-200ms                    │
└──────────────────────────────────────┘
```

### 6.2 批量操作优化

```python
async def batch_compact(agent_id: str, session_id: str):
    """批量压缩优化"""
    
    # 1. 批量获取消息
    messages = await db.fetch("""
        SELECT id, role, content, token_count
        FROM raw_messages
        WHERE agent_id = $1 AND session_id = $2
        ORDER BY created_at ASC
        LIMIT 50
    """, agent_id, session_id)
    
    # 2. 批量生成摘要（1次 LLM 调用）
    summaries = await llm_client.batch_summarize(messages)
    
    # 3. 批量存储（事务）
    async with db.transaction() as conn:
        for summary in summaries:
            await conn.execute("""
                INSERT INTO memories (...)
                VALUES (...)
            """, ...)
```

### 6.3 DAG 查询优化

```sql
-- 预计算 DAG 路径物化视图
CREATE MATERIALIZED VIEW dag_paths AS
WITH RECURSIVE dag_path AS (
    -- 起点：所有 leaf 节点
    SELECT 
        id, 
        ARRAY[id] as path, 
        0 as depth
    FROM memories 
    WHERE kind = 'leaf' AND is_summary = true
    
    UNION ALL
    
    -- 递归：向上查找父节点
    SELECT 
        m.id, 
        dp.path || m.id, 
        dp.depth + 1
    FROM memories m
    JOIN dag_path dp ON m.id = ANY(dp.parent_summary_ids)
    WHERE dp.depth < 10  -- 防止无限循环
)
SELECT * FROM dag_path;

-- 创建索引
CREATE INDEX idx_dag_paths_id ON dag_paths(id);
CREATE INDEX idx_dag_paths_depth ON dag_paths(depth);

-- 每小时刷新
-- REFRESH MATERIALIZED VIEW dag_paths;
```

### 6.4 大文件拦截

```python
async def store_with_large_file_check(
    agent_id: str,
    content: str,
    **kwargs
):
    """大文件拦截处理"""
    
    config = await get_agent_config(agent_id)
    threshold = config.get("large_file_token_threshold", 25000)
    
    # 检查 token 数量
    token_count = count_tokens(content)
    
    if token_count > threshold:
        # 大文件处理：
        # 1. 存储到独立位置
        # 2. 生成摘要
        # 3. 仅返回摘要引用
        
        summary = await generate_file_summary(content)
        
        return {
            "is_large_file": True,
            "original_token_count": token_count,
            "summary": summary,
            "message": f"文件过大（{token_count} tokens），已生成摘要"
        }
    
    # 正常存储
    return await normal_store(agent_id, content, **kwargs)
```

---

## 八、实施计划（调整后）

### Phase 1: 基础 Lossless 适配（1-1.5 周）

**Day 1-2: 数据库迁移**
- [ ] 编写迁移脚本 016_add_lossless_fields.sql
- [ ] 创建 raw_messages 表
- [ ] 添加 DAG 字段（is_raw, source_message_ids, parent_summary_ids）
- [ ] 创建索引和约束
- [ ] 编写迁移测试

**Day 3-4: RawStore 实现**
- [ ] 实现 RawMessageStore 类
- [ ] 实现 store_raw() 方法
- [ ] 实现 get_fresh_tail() 方法
- [ ] 实现 token 计数
- [ ] 单元测试

**Day 5-6: DAGManager 实现**
- [ ] 实现 DAGManager 类
- [ ] 实现 create_leaf_node() 方法
- [ ] 实现 create_condensed_node() 方法
- [ ] 实现 select_summaries_for_budget() 方法
- [ ] 实现 expand_node() 方法
- [ ] DAG 一致性检查

**Day 7-8: ContextAssembler 实现**
- [ ] 实现 ContextAssembler 类
- [ ] 实现 build() 方法（XML-tagged 输出）
- [ ] 实现 provenance 标签
- [ ] 集成测试

**Day 9-10: OpenClaw 插件集成**
- [ ] 编写 openclaw.plugin.json
- [ ] 注册 ContextEngine slot
- [ ] 实现插件生命周期钩子
- [ ] 端到端测试

**验收标准：**
- ✅ 所有原始消息永不丢失
- ✅ Context 组装延迟 < 150ms
- ✅ DAG 结构完整可追溯
- ✅ OpenClaw 插件正常加载

---

### Phase 2: Compaction & Tools（1 周）

**Day 1-3: CompactionEngine 实现**
- [ ] 实现 CompactionEngine 类
- [ ] 实现 leaf_compact() 方法
- [ ] 实现 condensation() 方法
- [ ] 实现 summary 生成
- [ ] 压缩策略配置

**Day 4-5: Retrieval Tools 实现**
- [ ] 实现 memory_grep() 工具
- [ ] 实现 memory_describe() 工具
- [ ] 实现 memory_expand_query() 工具
- [ ] Agent 工具接口

**Day 6-7: Large File & Session Patterns**
- [ ] 实现 Large File 拦截
- [ ] 实现 ignore_session_patterns
- [ ] 实现 stateless_session_patterns
- [ ] 集成测试

**验收标准：**
- ✅ Compaction 成功率 > 95%
- ✅ 压缩比 < 0.2（80% 压缩）
- ✅ Agent 工具可正常调用

---

### Phase 3: 高级特性 & 优化（1-2 周）

**Week 1: 重要性计算与监控**
- [ ] 重要性计算与 DAG 深度整合
- [ ] 实现 DAG pruning 机制
- [ ] 实现 integrity check 任务
- [ ] Prometheus 监控指标
- [ ] 告警规则配置

**Week 2: 性能优化与压测**
- [ ] DAG 查询优化
- [ ] 缓存策略优化
- [ ] 完整性能压测（长对话场景）
- [ ] 压力测试（>10k 轮对话）
- [ ] 性能报告

**验收标准：**
- ✅ 召回 P95 < 200ms
- ✅ DAG 深度可控（< 5）
- ✅ 系统稳定运行（无内存泄漏）

---

## 九、测试方案

### 8.1 单元测试

```python
# tests/test_dag_manager.py

@pytest.mark.asyncio
async def test_create_leaf_node():
    """测试创建 leaf 节点"""
    dag = DAGManager()
    
    result = await dag.create_leaf_node(
        agent_id="test_agent",
        source_message_ids=["msg_1", "msg_2"],
        summary_content="测试摘要"
    )
    
    assert result["kind"] == "leaf"
    assert result["depth"] == 0
    assert len(result["source_message_ids"]) == 2

@pytest.mark.asyncio
async def test_create_condensed_node():
    """测试创建 condensed 节点"""
    dag = DAGManager()
    
    result = await dag.create_condensed_node(
        agent_id="test_agent",
        parent_summary_ids=["summary_1", "summary_2"],
        summary_content="高层摘要",
        depth=1
    )
    
    assert result["kind"] == "condensed"
    assert result["depth"] == 1

@pytest.mark.asyncio
async def test_expand_node():
    """测试展开 DAG 节点"""
    dag = DAGManager()
    
    messages = await dag.expand_node(
        summary_id="summary_001",
        expand_depth=1,
        max_tokens=5000
    )
    
    assert len(messages) > 0
    assert all("content" in m for m in messages)
```

### 8.2 集成测试

```python
# tests/test_context_assembly.py

@pytest.mark.asyncio
async def test_assemble_context():
    """测试上下文组装"""
    service = AgentMemoryService()
    
    # 1. 存储多条消息
    for i in range(10):
        await service.store(
            agent_id="test_agent",
            role="user" if i % 2 == 0 else "assistant",
            content=f"测试消息 {i}"
        )
    
    # 2. 触发压缩
    await service.compaction_engine.leaf_compact(
        agent_id="test_agent",
        session_id="test_session"
    )
    
    # 3. 组装上下文
    result = await service.assemble_context(
        agent_id="test_agent",
        run_id="test_run",
        token_budget=10000
    )
    
    assert result["total_tokens"] <= 10000
    assert result["assembly_time_ms"] < 150
```

### 8.3 性能测试

```python
@pytest.mark.asyncio
async def test_context_assembly_latency():
    """测试上下文组装延迟（P95 < 150ms）"""
    service = AgentMemoryService()
    
    # 准备大量消息
    for i in range(100):
        await service.store(
            agent_id="perf_test",
            role="user",
            content=f"性能测试消息 {i}" * 100
        )
    
    # 测试组装延迟
    latencies = []
    for _ in range(100):
        start = time.time()
        await service.assemble_context(
            agent_id="perf_test",
            run_id="perf_run",
            token_budget=50000
        )
        latencies.append((time.time() - start) * 1000)
    
    p95 = sorted(latencies)[95]
    assert p95 < 150, f"P95 latency {p95}ms > 150ms"
```

---

## 十、监控与运维

### 9.1 Prometheus 监控指标

```python
# metrics.py

from prometheus_client import Counter, Histogram, Gauge

# DAG 深度
dag_depth_avg = Gauge(
    'dag_depth_avg',
    'Average DAG depth',
    ['agent_id']
)

# Compaction 性能
compaction_duration_seconds = Histogram(
    'compaction_duration_seconds',
    'Compaction duration',
    ['agent_id', 'batch_type'],
    buckets=[1, 2, 5, 10, 30, 60]
)

# Context 组装延迟
context_assembly_duration_seconds = Histogram(
    'context_assembly_duration_seconds',
    'Context assembly duration',
    ['agent_id'],
    buckets=[0.05, 0.1, 0.15, 0.2, 0.5, 1.0]
)

# 展开操作
expansion_token_usage = Counter(
    'expansion_token_usage_total',
    'Total tokens used in expansion',
    ['agent_id']
)

# 原始消息数量
raw_message_count = Gauge(
    'raw_message_count_total',
    'Total raw messages',
    ['agent_id']
)

# DAG 节点数量
dag_node_count = Gauge(
    'dag_node_count_total',
    'Total DAG nodes',
    ['agent_id', 'kind']
)
```

### 9.2 告警规则

```yaml
# prometheus/alerts.yml

groups:
  - name: lossless_memory_alerts
    rules:
      - alert: DAGDepthTooDeep
        expr: dag_depth_avg > 5
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "DAG 深度过深，需要 condensation"
          description: "Agent {{ $labels.agent_id }} 的 DAG 平均深度为 {{ $value }}"
      
      - alert: CompactionFailure
        expr: rate(compaction_errors_total[5m]) > 0.01
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "Compaction 失败率过高"
          description: "失败率 {{ $value }}/s"
      
      - alert: ContextAssemblySlow
        expr: histogram_quantile(0.95, context_assembly_duration_seconds) > 0.2
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Context 组装延迟过高"
          description: "P95 延迟 {{ $value }}s > 0.2s"
      
      - alert: RawMessageGrowthTooFast
        expr: rate(raw_message_count_total[1h]) > 10000
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "原始消息增长过快"
          description: "每小时增长 {{ $value }} 条"
```

### 9.3 定时清理任务

```python
# scripts/cleanup_dag.py

async def cleanup_dag():
    """DAG 清理任务"""
    
    # 1. 归档低重要性节点
    low_importance = await db.fetch("""
        UPDATE memories
        SET status = 'archived'
        WHERE is_summary = true
          AND importance_score < 0.2
          AND created_at < NOW() - INTERVAL '90 days'
          AND status = 'active'
        RETURNING id
    """)
    
    # 2. 深度超过阈值的 condensation
    deep_nodes = await db.fetch("""
        SELECT id, depth, parent_summary_ids
        FROM memories
        WHERE is_summary = true
          AND depth > 5
          AND kind = 'condensed'
    """)
    
    # 3. 执行额外 condensation
    for node in deep_nodes:
        await compaction_engine.condense_node(node["id"])
    
    # 4. 清理孤立的 raw messages
    orphaned = await db.fetch("""
        UPDATE raw_messages
        SET is_archived = true, archived_at = NOW()
        WHERE is_archived = false
          AND created_at < NOW() - INTERVAL '1 year'
          AND NOT EXISTS (
              SELECT 1 FROM memories m
              WHERE m.source_message_ids::jsonb @> to_jsonb(raw_messages.id)
          )
        RETURNING id
    """)
    
    print(f"清理完成: 低重要性 {len(low_importance)} 条, "
          f"深度超限 {len(deep_nodes)} 条, "
          f"孤立消息 {len(orphaned)} 条")
```

---

## 十一、风险评估

### 10.1 技术风险

| 风险 | 影响 | 概率 | 缓解措施 |
|------|------|------|----------|
| DAG 膨胀 | 高 | 中 | depth 限制 + importance-based pruning + 定期 condensation |
| 数据一致性 | 高 | 低 | integrity check 任务 + 事务保证 |
| Compaction 失败 | 中 | 低 | 重试机制 + 降级策略 + 告警 |
| 性能下降 | 中 | 中 | 缓存优化 + DAG 查询优化 + 监控 |

### 10.2 业务风险

| 风险 | 影响 | 概率 | 缓解措施 |
|------|------|------|----------|
| 记忆数据泄漏 | 高 | 低 | 权限控制 + 数据加密 + 审计日志 |
| 记忆丢失 | 高 | 极低 | Raw 消息永不删除 + 多副本 + 定期备份 |
| 存储成本过高 | 中 | 中 | TTL 管理 + importance 清理 + 压缩策略 |
| Agent 滥用 | 中 | 低 | 限流 + 配额管理 + 监控告警 |

---

## 十二、附录

### A. openclaw.plugin.json

```json
{
  "name": "memory-recall-plugin",
  "version": "1.1.0",
  "description": "Lossless Memory Recall Plugin for OpenClaw",
  "slots": [
    {
      "name": "contextEngine",
      "type": "context",
      "priority": 100,
      "methods": {
        "ingest": "/agent/memory/store",
        "assemble": "/agent/memory/assemble",
        "compact": "/agent/memory/compact"
      }
    }
  ],
  "config": {
    "fresh_tail_count": 32,
    "context_threshold": 0.75,
    "incremental_max_depth": 3
  }
}
```

### B. 与 Lossless-Claw 对比

> **更新说明**：v1.1 设计已完全融入 Lossless-Claw 最佳实践，数据库结构保持一致。

| 维度 | Lossless-Claw | Memory Recall v1.1 | 说明 |
|------|---------------|-------------------|------|
| **存储引擎** | SQLite | PostgreSQL | v1.1 使用生产级数据库 |
| **DAG 关系存储** | ✅ 独立关系表 | ✅ 独立关系表 | **已对齐** |
| **context_items 表** | ✅ 有序序列 | ✅ 有序序列 | **已对齐** |
| **统计字段** | ✅ earliest/latest/descendant | ✅ 完全一致 | **已对齐** |
| **三阶段压缩** | ✅ normal→aggressive→fallback | ✅ 完全一致 | **已对齐** |
| **Fresh Tail 保护** | ✅ 默认 8 条 | ✅ 可配置 | **已对齐** |
| **向量索引** | ❌ | ✅ HNSW | v1.1 扩展能力 |
| **图谱检索** | ❌ | ✅ 实体-关系 | v1.1 扩展能力 |
| **混合召回** | ❌ | ✅ 向量+关键词+图谱 | v1.1 扩展能力 |
| **重要性计算** | ❌ | ✅ 动态计算 | v1.1 扩展能力 |
| **TTL/归档** | ❌ | ✅ 灵活配置 | v1.1 扩展能力 |
| **Session 控制** | ❌ | ✅ ignore/stateless | v1.1 扩展能力 |

**核心继承（已对齐）：**
1. ✅ 独立关系表（`summary_messages`, `summary_parents`, `context_items`）
2. ✅ 三阶段压缩策略（normal → aggressive → fallback）
3. ✅ DAG 统计字段（earliest_at, latest_at, descendant_count, etc.）
4. ✅ Fresh Tail 保护机制
5. ✅ XML 格式化摘要输出

**核心扩展（v1.1 新增）：**
1. ✅ PostgreSQL 生产级存储
2. ✅ HNSW 向量索引 + 混合召回
3. ✅ 实体-关系图谱
4. ✅ 动态重要性计算
5. ✅ TTL/归档管理

### C. 参考资料

1. **Lossless-Claw 源码分析**：
   - `src/db/migration.ts` - 数据库 Schema 定义
   - `src/store/summary-store.ts` - DAG 存储实现
   - `src/compaction.ts` - 压缩引擎（三阶段策略）
   - `src/assembler.ts` - Context 组装器

2. **理论参考**：
   - [认知心理学记忆理论](https://en.wikipedia.org/wiki/Memory)
   - [PostgreSQL 向量索引优化](https://www.postgresql.org/docs/current/indexes-types.html)

---

**文档版本历史：**

| 版本 | 日期 | 变更说明 |
|------|------|----------|
| v1.0 | 2026-03-26 | 初始版本（三层记忆模型） |
| v1.1 | 2026-03-26 | 融入 Lossless-Claw 最佳实践：<br>- **数据库结构完全对齐**（独立关系表、context_items、统计字段）<br>- **三阶段压缩策略**（normal→aggressive→fallback）<br>- **DAG 展开逻辑修正**（正确理解父子关系）<br>- **Context 组装流程**（基于 context_items 表）<br>- 详细代码示例与流程图<br>- 完整实施计划与监控方案 |
