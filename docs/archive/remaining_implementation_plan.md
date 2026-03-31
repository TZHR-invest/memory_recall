# Memory Recall v3.0 剩余实施计划

> **版本：** v3.0 补充
> **日期：** 2026-03-27
> **状态：** 待审核
> **前置：** Phase 1-4 核心功能已完成

---

## 一、当前进度总结

### 已完成功能

| 模块 | 状态 | 文件 |
|-----|------|-----|
| 数据库表（6个） | ✅ | `migrations/015_create_lossless_tables.sql` |
| RawMessageStore | ✅ | `src/services/lossless/raw_message_store.py` |
| SummaryStore | ✅ | `src/services/lossless/summary_store.py` |
| ContextStore | ✅ | `src/services/lossless/context_store.py` |
| CompactionEngine | ✅ | `src/services/lossless/compaction_engine.py` |
| MemoryRecallEngine | ✅ | `src/services/lossless/memory_recall_engine.py` |
| LosslessRecallService | ✅ | `src/services/lossless/lossless_recall_service.py` |
| DAGExpandService | ✅ | `src/services/lossless/dag_expand_service.py` |
| UnifiedMemoryService | ✅ | `src/services/unified_memory_service.py` |
| OpenClaw 插件清单 | ✅ | `src/openclaw_plugin/openclaw.plugin.json` |
| API: POST /memories | ✅ | `src/routes/memories.py`（使用 raw_messages） |
| API: POST /files/upload | ✅ | `src/routes/files.py`（使用 raw_messages） |

### 待完成功能

| 功能 | 优先级 | 影响范围 |
|-----|--------|---------|
| 实体提取集成 | P0 | 图谱召回失效 |
| 召回返回片段 | P0 | 长文本召回不可用 |
| 暴露 expand API | P1 | 摘要无法展开 |
| 暴露 assemble API | P1 | Agent 无法组装上下文 |
| 暴露 compact API | P1 | 无法手动触发压缩 |
| message_entities 关联 | P2 | 图谱召回精度下降 |
| 长文档自动压缩 | P2 | 长文档无摘要 |

---

## 二、实施计划

### Phase 5: 核心功能补全（预计 3 天）

| 任务 | 优先级 | 预估时间 | 依赖 |
|-----|--------|---------|------|
| 实体提取集成 | P0 | 0.5 天 | 无 |
| 召回返回片段 | P0 | 0.5 天 | 无 |
| 暴露 expand API | P1 | 0.5 天 | 无 |
| 暴露 assemble API | P1 | 0.5 天 | 无 |
| 暴露 compact API | P1 | 0.5 天 | 无 |
| 单元测试 | P0 | 0.5 天 | 上述完成 |

### Phase 6: 增强功能（预计 1 天）

| 任务 | 优先级 | 预估时间 | 依赖 |
|-----|--------|---------|------|
| message_entities 关联 | P2 | 0.5 天 | Phase 5 |
| 长文档自动压缩 | P2 | 0.3 天 | Phase 5 |
| 端到端测试 | P2 | 0.2 天 | Phase 5 |

---

## 三、详细实施步骤

### 3.0 长文档判定标准

#### 存储策略

```python
MAX_TOKENS_PER_MESSAGE = 1000  # 约 4000 中文字符

async def store(self, content, ...):
    tokens = self.estimate_tokens(content)
    
    if tokens <= MAX_TOKENS_PER_MESSAGE:
        # 整体存储
        raw_id = await self.raw_store.store(content=content, ...)
    else:
        # 按段落分段（双换行分隔）
        paragraphs = content.split('\n\n')
        chunks = self._merge_paragraphs(paragraphs, MAX_TOKENS_PER_MESSAGE)
        
        document_id = generate_document_id()
        for chunk in chunks:
            await self.raw_store.store(
                content=chunk,
                document_id=document_id,
            )
```

#### 判定标准表

| 维度 | 阈值 | 说明 |
|-----|-----|-----|
| **Token 数** | > 1000 tokens | 超过则分段存储 |
| **字符数** | ~4000 字符 | 参考（token 为主） |
| **分段方式** | 按段落（\n\n） | 尊重自然边界 |

#### 不同场景判定结果

| 场景 | Token 数 | 判定结果 | 处理方式 |
|-----|---------|---------|---------|
| 用户输入偏好 | ~50 | ❌ 短文本 | 整体存储 |
| 日记/笔记 | ~200 | ❌ 短文本 | 整体存储 |
| 文章 | ~1500 | ✅ 长文档 | 按段落分段 |
| 文件上传 | ~3000 | ✅ 长文档 | 按段落分段 |
| Agent 单条对话 | ~100 | ❌ 短文本 | 整体存储 |

---

### 3.1 实体提取集成（P0）

#### 目标

将实体提取集成到 `UnifiedMemoryService`，采用**差异化策略**：

| 来源 | 长文档判定 | 提取时机 | 存储位置 | 原因 |
|-----|----------|---------|---------|-----|
| 用户短输入（≤ 1000 tokens） | ❌ | 存储时立即提取 | `entities` + `memory_entities` | 量少、重要、值得成本 |
| 用户长输入（> 1000 tokens） | ✅ | 压缩后提取 | `entities` + `summary_entities` | 已生成摘要、复用 |
| 文件上传 | ✅ | 压缩后提取 | `entities` + `summary_entities` | 天然是长文档 |
| Agent 对话 | ❌ | 压缩后提取 | `entities` + `summary_entities` | 量大、高频、成本控制 |

#### 成本对比

| 场景 | LLM 调用次数（提取实体） |
|-----|------------------------|
| 用户短输入 10 条（≤ 1000 tokens） | 10 次（立即提取，每条一次） |
| 用户长输入 1 条（> 1000 tokens） | 1 次（压缩后对摘要提取） |
| Agent 对话 100 条 | 1 次（压缩后对摘要提取） |
| 文件上传 1 个 | 1 次（压缩后对摘要提取） |

#### 当前问题

```python
# 当前 unified_memory_service.py
async def store(self, ...):
    raw_id = await self.raw_store.store(...)
    embedding = self.embedding_client.embed(content)
    # ❌ 缺少实体提取！
    return {"raw_message_id": raw_id}
```

#### 设计要求

```python
# 用户手动输入：存储时立即提取
async def store_user_memory(self, ...):
    raw_id = await self.raw_store.store(...)
    
    # 立即提取实体（仅用户手动输入）
    entities, relations = await self.entity_extractor.extract(content)
    await self.graph_builder.save_entities(entities, user_id, agent_id=None, raw_id)
    
    embedding = await self.vector_indexer.embed(content)
    await self.raw_store.update_embedding(raw_id, embedding)
    
    return {
        "raw_message_id": raw_id,
        "entities": entities,
        "entities_count": len(entities)
    }

# Agent 对话：存储时不提取，压缩时提取
async def store_agent_message(self, ...):
    raw_id = await self.raw_store.store(...)
    
    # 不提取实体，等待压缩时处理
    embedding = await self.vector_indexer.embed(content)
    await self.raw_store.update_embedding(raw_id, embedding)
    
    return {
        "raw_message_id": raw_id,
        "entities_count": 0  # Agent 消息暂不提取
    }

# 压缩时：对摘要提取实体
async def compact(self, ...):
    # 生成摘要
    summary = await self._summarize(messages)
    summary_id = await self.summary_store.create_summary(content=summary)
    
    # 对摘要提取实体
    entities = await self.entity_extractor.extract(summary)
    for entity in entities:
        entity_id = await self.graph_builder._upsert_entity(...)
        await self.summary_store.link_entity(summary_id, entity_id)
    
    return {"summary_id": summary_id, "entities_count": len(entities)}
```

#### 实施步骤

**Step 1**: 修改 `UnifiedMemoryService.__init__`

```python
# 文件：src/services/unified_memory_service.py
# 位置：__init__ 方法

# 添加导入
from src.services.memory_extraction_service import MemoryExtractionService
from src.services.graph_builder_service import GraphBuilderService

# 修改 __init__
def __init__(self, ...):
    # 现有初始化
    self.raw_store = raw_store or RawMessageStore()
    ...
    
    # 新增：实体提取服务
    self.entity_extractor = MemoryExtractionService()
    self.graph_builder = GraphBuilderService()
```

**Step 2**: 添加实体提取方法（仅用于用户手动输入）

```python
# 文件：src/services/unified_memory_service.py
# 新增方法

async def _extract_and_store_entities_for_user(
    self,
    content: str,
    user_id: str,
    memory_id: str,
) -> Dict[str, Any]:
    """
    提取并存储实体（仅用于用户手动输入）
    
    Returns:
        {"entities": [...], "relations": [...], "entities_count": N}
    """
    try:
        extraction_result = await self.entity_extractor.extract_memories(content)
        
        if not extraction_result or not extraction_result.get("success"):
            return {"entities": [], "relations": [], "entities_count": 0}
        
        memories = extraction_result.get("memories", [])
        all_entities = []
        all_relations = []
        
        for memory in memories:
            entities = memory.get("entities", [])
            relations = memory.get("relations", [])
            all_entities.extend(entities)
            all_relations.extend(relations)
        
        # 去重
        unique_entities = self._deduplicate_entities(all_entities)
        unique_relations = self._deduplicate_relations(all_relations)
        
        # 存储实体
        entity_ids = {}
        for entity in unique_entities:
            entity_name = entity.get("name")
            entity_type = entity.get("type", "unknown")
            confidence = entity.get("confidence", 0.8)
            
            if entity_name == "我":
                continue
            
            entity_id = await self.graph_builder._upsert_entity(
                name=entity_name,
                entity_type=entity_type,
                user_id=user_id,
                agent_id=None,  # 用户手动输入，agent_id = NULL
                confidence=confidence,
            )
            
            if entity_id:
                entity_ids[entity_name] = entity_id
                # 创建 message_entities 关联
                await self._link_message_entity(memory_id, entity_id)
        
        # 存储关系
        for relation in unique_relations:
            source = relation.get("source")
            target = relation.get("target")
            relation_type = relation.get("relation_type")
            confidence = relation.get("confidence", 0.8)
            
            if target == "我":
                continue
            
            await self.graph_builder._upsert_relation(
                from_entity=source,
                to_entity=target,
                relation_type=relation_type,
                confidence=confidence,
                user_id=user_id,
            )
        
        return {
            "entities": unique_entities,
            "relations": unique_relations,
            "entities_count": len(unique_entities),
        }
    
    except Exception as e:
        logger.warning(f"Entity extraction failed: {e}")
        return {"entities": [], "relations": [], "entities_count": 0}
```

**Step 3**: 修改 `store` 方法（差异化处理）

```python
# 文件：src/services/unified_memory_service.py
# 修改 store 方法

async def store(
    self,
    user_id: str,
    content: str,
    source: str = "manual",  # manual | agent | file
    agent_id: Optional[str] = None,
    session_id: Optional[str] = None,
    memory_type: str = "preference",
    metadata: Optional[Dict] = None,
    enable_graph: bool = True,
) -> Dict[str, Any]:
    actual_agent_id = None if source == "manual" else agent_id
    actual_memory_type = "dialogue" if source == "agent" else memory_type
    
    # 判定是否为长文档
    is_long = self._is_long_document(content, source, metadata or {})
    
    # 长文档：分段存储
    if is_long and source in ("manual", "file"):
        return await self._store_as_long_document(
            user_id=user_id,
            content=content,
            memory_type=actual_memory_type,
            source=source,
            metadata=metadata,
            enable_graph=enable_graph,
        )
    
    # 短文本：直接存储
    raw_id = await self.raw_store.store(
        user_id=user_id,
        content=content,
        memory_type=actual_memory_type,
        agent_id=actual_agent_id,
        session_id=session_id,
        ...
    )
    
    # 差异化实体提取策略
    entities_result = {"entities": [], "entities_count": 0}
    
    if enable_graph:
        if source == "manual" and not is_long:
            # 用户短输入：立即提取实体
            entities_result = await self._extract_and_store_entities_for_user(
                content=content,
                user_id=user_id,
                memory_id=raw_id,
            )
        # 其他场景（长文档、Agent 对话）：不提取，等待压缩时处理
    
    # 生成向量
    embedding = self.embedding_client.embed(content)
    if embedding:
        await self.raw_store.update_embedding(raw_id, embedding)
    
    return {
        "raw_message_id": raw_id,
        "memory_type": actual_memory_type,
        "agent_id": actual_agent_id,
        "source": source,
        "is_long_document": is_long,
        "has_embedding": embedding is not None,
        "entities": entities_result.get("entities", []),
        "entities_count": entities_result.get("entities_count", 0),
    }

def _is_long_document(self, content: str, source: str, metadata: Dict) -> bool:
    """判定是否为长文档"""
    # 1. Token 数估算（主标准）
    token_count = self.estimate_tokens(content)
    if token_count > 1000:
        return True
    
    # 2. 字符数（辅助标准）
    if len(content) > 5000:
        return True
    
    # 3. 来源判断（文件上传）
    if source == "file":
        return True
    
    # 4. 显式标记
    if metadata.get("is_document"):
        return True
    
    return False

async def _store_as_long_document(
    self,
    user_id: str,
    content: str,
    memory_type: str,
    source: str,
    metadata: Optional[Dict],
    enable_graph: bool,
) -> Dict[str, Any]:
    """存储长文档（分段 + 压缩后提取实体）"""
    document_id = generate_document_id()
    chunks = split_into_chunks(content, max_chars=5000)
    
    chunk_ids = []
    for i, chunk_content in enumerate(chunks):
        raw_id = await self.raw_store.store(
            user_id=user_id,
            content=chunk_content,
            memory_type=memory_type,
            document_id=document_id,
            ...
        )
        chunk_ids.append(raw_id)
        
        # 生成分段向量
        embedding = self.embedding_client.embed(chunk_content)
        if embedding:
            await self.raw_store.update_embedding(raw_id, embedding)
    
    # 注意：不立即提取实体，等待压缩时处理
    return {
        "document_id": document_id,
        "chunk_count": len(chunks),
        "chunk_ids": chunk_ids,
        "memory_type": memory_type,
        "source": source,
        "is_long_document": True,
        "entities": [],  # 压缩后提取
        "entities_count": 0,
    }
```

**Step 4**: 修改 `CompactionEngine` 压缩时提取实体

```python
# 文件：src/services/lossless/compaction_engine.py
# 修改 leaf_compact 方法

async def leaf_compact(
    self,
    user_id: str,
    agent_id: Optional[str],
    session_id: str,
    summarize_fn: Callable[[str, bool], str],
    entity_extractor: Optional[Any] = None,  # 新增参数
    ...
) -> Optional[CompactionResult]:
    # ... 现有压缩逻辑 ...
    
    # 生成摘要
    summary_content, level = await self._summarize_with_escalation(
        source_text, summarize_fn
    )
    
    # 创建摘要
    summary_id = await self._create_summary(
        user_id=user_id,
        agent_id=agent_id,
        content=summary_content,
        ...
    )
    
    # 新增：对摘要提取实体（Agent 对话场景）
    if entity_extractor and agent_id:
        entities = await self._extract_entities_for_summary(
            summary_content=summary_content,
            summary_id=summary_id,
            user_id=user_id,
            agent_id=agent_id,
            entity_extractor=entity_extractor,
        )
    
    return CompactionResult(...)

async def _extract_entities_for_summary(
    self,
    summary_content: str,
    summary_id: str,
    user_id: str,
    agent_id: str,
    entity_extractor: Any,
) -> List[Dict]:
    """对摘要提取实体"""
    try:
        result = await entity_extractor.extract_memories(summary_content)
        if not result or not result.get("success"):
            return []
        
        memories = result.get("memories", [])
        all_entities = []
        
        for memory in memories:
            entities = memory.get("entities", [])
            all_entities.extend(entities)
        
        # 去重并存储
        unique_entities = self._deduplicate_entities(all_entities)
        
        for entity in unique_entities:
            entity_name = entity.get("name")
            entity_type = entity.get("type", "unknown")
            
            if entity_name == "我":
                continue
            
            # 存储实体（agent_id 标记来源）
            entity_id = await self.summary_store.graph_builder._upsert_entity(
                name=entity_name,
                entity_type=entity_type,
                user_id=user_id,
                agent_id=agent_id,  # Agent 对话中的实体
                confidence=entity.get("confidence", 0.8),
            )
            
            if entity_id:
                # 关联到摘要
                await self.summary_store.link_entity(
                    summary_id=summary_id,
                    entity_id=entity_id,
                    role="mentioned",
                )
        
        return unique_entities
    
    except Exception as e:
        logger.warning(f"Entity extraction for summary failed: {e}")
        return []
```

**Step 5**: 修改 `MemoryRecallEngine.compact` 传入提取器

```python
# 文件：src/services/lossless/memory_recall_engine.py
# 修改 compact 方法

async def compact(self, params: Dict) -> Dict:
    user_id = params["user_id"]
    agent_id = params.get("agent_id")
    session_id = params["session_id"]
    summarize_fn = params.get("summarize_fn")
    
    if not summarize_fn:
        return {"action_taken": False, ...}
    
    result = await self.compaction_engine.leaf_compact(
        user_id=user_id,
        agent_id=agent_id,
        session_id=session_id,
        summarize_fn=summarize_fn,
        entity_extractor=self.entity_extractor,  # 新增
        ...
    )
    
    return {...}
```

**Step 6**: 添加辅助方法

```python
# 文件：src/services/unified_memory_service.py

def _deduplicate_entities(self, entities: List[Dict]) -> List[Dict]:
    """去重实体"""
    seen = set()
    unique = []
    for e in entities:
        key = (e.get("name"), e.get("type"))
        if key not in seen:
            seen.add(key)
            unique.append(e)
    return unique

def _deduplicate_relations(self, relations: List[Dict]) -> List[Dict]:
    """去重关系"""
    seen = set()
    unique = []
    for r in relations:
        key = (r.get("source"), r.get("target"), r.get("relation_type"))
        if key not in seen:
            seen.add(key)
            unique.append(r)
    return unique

async def _link_message_entity(self, message_id: str, entity_id: str):
    """创建消息-实体关联"""
    await db.execute("""
        INSERT INTO memory_entities (memory_id, entity_id)
        VALUES ($1, $2)
        ON CONFLICT DO NOTHING
    """, message_id, entity_id)
```

**Step 7**: 更新 API 返回

```python
# 文件：src/routes/memories.py

return {
    "code": 200,
    "message": "success",
    "data": {
        "id": result["raw_message_id"],
        "content": memory.content,
        "memory_type": result["memory_type"],
        "source": result["source"],
        "entities": result.get("entities", []),  # 用户输入有值，Agent 对话为空
        "entities_count": result.get("entities_count", 0),
        "created_at": ...,
    },
}
```

```python
# 文件：tests/test_entity_integration.py

@pytest.mark.asyncio
async def test_user_short_input_extracts_entities_immediately():
    """用户短输入：立即提取实体"""
    service = UnifiedMemoryService()
    user_id = "test_user_short"
    
    result = await service.store(
        user_id=user_id,
        content="今天在星巴克遇到了老同学张三",  # ~50 tokens
        source="manual",
        enable_graph=True,
    )
    
    assert result["raw_message_id"].startswith("raw_")
    assert result["is_long_document"] == False
    assert result["entities_count"] >= 1  # 立即提取
    entity_names = [e["name"] for e in result["entities"]]
    assert "星巴克" in entity_names or "张三" in entity_names

@pytest.mark.asyncio
async def test_user_long_input_no_immediate_extraction():
    """用户长输入（文章）：不立即提取实体"""
    service = UnifiedMemoryService()
    user_id = "test_user_long"
    
    long_content = "这是一篇很长的文章..." * 500  # > 1000 tokens
    result = await service.store(
        user_id=user_id,
        content=long_content,
        source="manual",
        enable_graph=True,
    )
    
    assert result["is_long_document"] == True
    assert result["chunk_count"] >= 1
    assert result["entities_count"] == 0  # 不立即提取，等待压缩

@pytest.mark.asyncio
async def test_file_upload_no_immediate_extraction():
    """文件上传：不立即提取实体"""
    service = UnifiedMemoryService()
    user_id = "test_file_upload"
    
    result = await service.store_file(
        user_id=user_id,
        content=b"文件内容...",
        file_name="article.txt",
        metadata={"enable_graph": True},
    )
    
    assert result["status"] == "created"
    assert result["chunk_count"] >= 1
    # 实体在压缩后提取

@pytest.mark.asyncio
async def test_agent_message_no_immediate_extraction():
    """Agent 对话：不立即提取实体"""
    service = UnifiedMemoryService()
    user_id = "test_agent_entity"
    
    result = await service.store(
        user_id=user_id,
        content="用户询问今天天气",
        source="agent",
        agent_id="agent_001",
        session_id="session_001",
        enable_graph=True,
    )
    
    assert result["raw_message_id"].startswith("raw_")
    assert result["is_long_document"] == False
    assert result["entities_count"] == 0  # Agent 对话不立即提取

@pytest.mark.asyncio
async def test_compact_extracts_entities_for_summary():
    """压缩时：对摘要提取实体（长文档/Agent 场景）"""
    engine = MemoryRecallEngine()
    
    # 存储 Agent 消息
    await engine.ingest({
        "user_id": user_id,
        "agent_id": "agent_001",
        "session_id": "session_001",
        "message": {"content": "用户说他在星巴克工作"},
    })
    
    # 触发压缩
    def mock_summarize(text, aggressive=False):
        return "用户提到在星巴克工作"
    
    result = await engine.compact({
        "user_id": user_id,
        "agent_id": "agent_001",
        "session_id": "session_001",
        "summarize_fn": mock_summarize,
        "force": True,
    })
    
    # 验证摘要关联了实体
    if result["summary_id"]:
        entities = await db.fetch("""
            SELECT e.name FROM summary_entities se
            JOIN entities e ON e.id = se.entity_id
            WHERE se.summary_id = $1
        """, result["summary_id"])
        
        entity_names = [e["name"] for e in entities]
        assert "星巴克" in entity_names
```

#### 验收标准

- [ ] 用户短输入（≤ 1000 tokens）：`store()` 返回 entities（立即提取）
- [ ] 用户长输入（> 1000 tokens）：`store()` 返回 `is_long_document=true`，按段落分段
- [ ] 文件上传：自动判定为长文档，按段落分段
- [ ] Agent 对话：不立即提取实体
- [ ] 压缩时：摘要关联 `summary_entities` 表数据
- [ ] 实体存储到 `entities` 表，`agent_id` 正确标记来源
- [ ] 测试通过

---

### 3.2 召回返回片段（P0）

#### 目标

召回时返回匹配片段（snippets）而非完整内容，避免长文本召回结果过长。

#### 当前问题

```python
# 当前召回返回
{
    "type": "raw_message",
    "content": "完整的 5000 字符内容...",  # 太长
    "similarity": 0.85
}
```

#### 设计要求

```python
# 设计要求
{
    "type": "raw_message",
    "content": "完整的 5000 字符内容...",  # 保留完整内容（可选）
    "snippet": "...关键里程碑包括：第一阶段完成原型...",  # 新增：匹配片段
    "snippet_highlight": "<em>里程碑</em>包括：第一阶段...",  # 新增：高亮片段
    "similarity": 0.85,
    "expandable": True  # 可展开获取完整内容
}
```

#### 实施步骤

**Step 1**: 添加片段提取方法

```python
# 文件：src/services/lossless/lossless_recall_service.py
# 新增方法

def _extract_snippet(
    self,
    content: str,
    query: str,
    max_chars: int = 300,
    context_chars: int = 100,
) -> Dict[str, str]:
    """
    从内容中提取匹配片段
    
    Args:
        content: 完整内容
        query: 查询文本
        max_chars: 片段最大长度
        context_chars: 匹配位置前后上下文长度
    
    Returns:
        {"snippet": "...", "snippet_highlight": "..."}
    """
    import re
    
    # 提取查询关键词
    keywords = self._extract_keywords(query)
    if not keywords:
        # 无关键词，返回开头
        snippet = content[:max_chars]
        if len(content) > max_chars:
            snippet += "..."
        return {"snippet": snippet, "snippet_highlight": snippet}
    
    # 查找第一个匹配关键词的位置
    content_lower = content.lower()
    match_pos = -1
    matched_keyword = None
    
    for keyword in keywords:
        pos = content_lower.find(keyword.lower())
        if pos != -1:
            if match_pos == -1 or pos < match_pos:
                match_pos = pos
                matched_keyword = keyword
    
    if match_pos == -1:
        # 无匹配，返回开头
        snippet = content[:max_chars]
        if len(content) > max_chars:
            snippet += "..."
        return {"snippet": snippet, "snippet_highlight": snippet}
    
    # 计算片段范围
    start = max(0, match_pos - context_chars)
    end = min(len(content), match_pos + len(matched_keyword) + context_chars)
    
    # 调整到句子边界
    if start > 0:
        # 向前找句子边界
        for i in range(start, max(0, start - 50), -1):
            if content[i] in "。！？\n":
                start = i + 1
                break
    
    if end < len(content):
        # 向后找句子边界
        for i in range(end, min(len(content), end + 50)):
            if content[i] in "。！？\n":
                end = i + 1
                break
    
    # 提取片段
    snippet = content[start:end]
    
    if start > 0:
        snippet = "..." + snippet
    if end < len(content):
        snippet = snippet + "..."
    
    # 生成高亮片段
    snippet_highlight = snippet
    for keyword in keywords:
        # 高亮关键词（不区分大小写）
        pattern = re.compile(re.escape(keyword), re.IGNORECASE)
        snippet_highlight = pattern.sub(f"<em>{keyword}</em>", snippet_highlight)
    
    return {
        "snippet": snippet[:max_chars],
        "snippet_highlight": snippet_highlight[:max_chars + 50],  # 高亮版本允许稍长
    }
```

**Step 2**: 修改召回方法添加片段

```python
# 文件：src/services/lossless/lossless_recall_service.py
# 修改 _vector_recall 方法

async def _vector_recall(...):
    # ... 现有查询逻辑 ...
    
    for r in raw_results:
        content = r["content"]
        
        # 提取片段
        snippet_data = self._extract_snippet(content, query)
        
        results.append({
            "type": "raw_message",
            "id": r["id"],
            "content": content,  # 保留完整内容
            "snippet": snippet_data["snippet"],  # 新增
            "snippet_highlight": snippet_data["snippet_highlight"],  # 新增
            "agent_id": r["agent_id"],
            "memory_type": r["memory_type"],
            "similarity": float(r["similarity"]) if r["similarity"] else 0.0,
            "source": "vector",
            "expandable": len(content) > 500,  # 长文本可展开
            "created_at": r["created_at"].isoformat() if r["created_at"] else None,
        })
    
    return results
```

**Step 3**: 同样修改 `_keyword_recall` 和 `_graph_recall`

```python
# 在每个召回方法中添加片段提取
snippet_data = self._extract_snippet(content, query)
result["snippet"] = snippet_data["snippet"]
result["snippet_highlight"] = snippet_data["snippet_highlight"]
```

**Step 4**: 添加参数控制返回格式

```python
# 文件：src/services/unified_memory_service.py
# 修改 recall 方法

async def recall(
    self,
    query: str,
    user_id: str,
    scope: str = "all",
    agent_id: Optional[str] = None,
    limit: int = 20,
    min_similarity: float = 0.3,
    return_snippet: bool = True,  # 新增：是否返回片段
    return_full_content: bool = False,  # 新增：是否返回完整内容
) -> List[Dict[str, Any]]:
    results = await self.recall_service.hybrid_recall(...)
    
    # 根据参数处理返回格式
    if not return_full_content:
        for r in results:
            if "snippet" in r:
                r["content"] = None  # 不返回完整内容
    
    return results
```

**Step 5**: 创建测试

```python
# 文件：tests/test_recall_snippet.py

@pytest.mark.asyncio
async def test_recall_returns_snippet():
    service = UnifiedMemoryService()
    
    # 存储长文本
    long_content = "这是一段很长的文本..." * 100
    await service.store(user_id="test", content=long_content)
    
    # 召回
    results = await service.recall(
        query="长文本",
        user_id="test",
        return_snippet=True,
    )
    
    assert len(results) >= 1
    assert "snippet" in results[0]
    assert len(results[0]["snippet"]) < 500  # 片段比完整内容短
```

#### 验收标准

- [ ] 召回结果包含 `snippet` 字段
- [ ] 召回结果包含 `snippet_highlight` 字段（关键词高亮）
- [ ] 片段长度控制在 300 字符内
- [ ] 长文本标记为 `expandable: true`
- [ ] 测试通过

---

### 3.3 暴露 expand API（P1）

#### 目标

暴露 `/memories/expand` API，允许展开摘要获取原始消息。

#### API 设计

```json
POST /memories/expand

Request:
{
  "summary_id": "sum_001",
  "user_id": "user_001",
  "max_tokens": 5000  // 可选，限制展开内容长度
}

Response:
{
  "code": 200,
  "data": {
    "summary": {
      "id": "sum_001",
      "content": "用户偏好汇总..."
    },
    "messages": [
      {
        "id": "raw_001",
        "content": "我是素食主义者...",
        "token_count": 50,
        "created_at": "2026-03-26T10:00:00"
      },
      {
        "id": "raw_002",
        "content": "我喜欢喝咖啡...",
        "token_count": 30,
        "created_at": "2026-03-26T11:00:00"
      }
    ],
    "total_messages": 2,
    "total_tokens": 80
  }
}
```

#### 实施步骤

**Step 1**: 创建请求模型

```python
# 文件：src/routes/memories.py
# 新增请求模型

class ExpandRequest(BaseModel):
    """展开摘要请求"""
    summary_id: str = Field(..., description="摘要 ID")
    user_id: str = Field(..., description="用户 ID")
    max_tokens: int = Field(5000, ge=100, le=50000, description="最大 token 数")
```

**Step 2**: 创建 API 端点

```python
# 文件：src/routes/memories.py
# 新增端点

@router.post(
    "/expand",
    response_model=dict,
    summary="展开摘要",
    description="展开摘要获取原始消息列表",
)
async def expand_summary(request: ExpandRequest):
    """
    展开摘要
    
    - **summary_id**: 摘要 ID（必填）
    - **user_id**: 用户 ID（必填）
    - **max_tokens**: 最大 token 数（默认 5000）
    """
    db.set_current_user(request.user_id)
    
    try:
        from src.services.lossless.dag_expand_service import dag_expand_service
        
        result = await dag_expand_service.expand_to_messages(
            summary_id=request.summary_id,
            max_tokens=request.max_tokens,
        )
        
        if "error" in result:
            raise HTTPException(status_code=404, detail=result["error"])
        
        return {
            "code": 200,
            "message": "success",
            "data": result,
        }
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"展开失败：{str(e)}")
```

**Step 3**: 创建测试

```python
# 文件：tests/test_expand_api.py

@pytest.mark.asyncio
async def test_expand_summary():
    # 创建摘要
    ...
    
    # 调用 API
    response = await client.post("/memories/expand", json={
        "summary_id": "sum_xxx",
        "user_id": "test_user",
        "max_tokens": 5000,
    })
    
    assert response.status_code == 200
    data = response.json()
    assert "messages" in data["data"]
```

#### 验收标准

- [ ] API 端点可访问
- [ ] 返回原始消息列表
- [ ] 限制 max_tokens 生效
- [ ] 测试通过

---

### 3.4 暴露 assemble API（P1）

#### 目标

暴露 `/context/assemble` API，允许 Agent 组装上下文。

#### API 设计

```json
POST /context/assemble

Request:
{
  "user_id": "user_001",
  "agent_id": "agent_001",  // 可选
  "session_id": "session_001",
  "token_budget": 100000
}

Response:
{
  "code": 200,
  "data": {
    "messages": [
      {"role": "user", "content": "..."},
      {"role": "assistant", "content": "..."},
      {"role": "system", "content": "[历史摘要]\n..."}
    ],
    "estimated_tokens": 5000,
    "system_prompt_addition": "[历史上下文摘要]\n..."
  }
}
```

#### 实施步骤

**Step 1**: 创建路由文件

```python
# 文件：src/routes/context.py（新建）

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, List

from ..database import db
from ..services.lossless.memory_recall_engine import memory_recall_engine

router = APIRouter(prefix="/context", tags=["上下文管理"])


class AssembleRequest(BaseModel):
    """组装上下文请求"""
    user_id: str = Field(..., description="用户 ID")
    agent_id: Optional[str] = Field(None, description="Agent ID")
    session_id: str = Field(..., description="会话 ID")
    token_budget: int = Field(100000, ge=1000, le=500000, description="Token 预算")


@router.post(
    "/assemble",
    response_model=dict,
    summary="组装上下文",
    description="组装上下文给 Agent 使用",
)
async def assemble_context(request: AssembleRequest):
    """
    组装上下文
    
    返回消息列表，包含：
    - 原始消息（fresh tail）
    - 历史摘要
    - 系统提示
    """
    db.set_current_user(request.user_id)
    
    try:
        result = await memory_recall_engine.assemble({
            "user_id": request.user_id,
            "agent_id": request.agent_id,
            "session_id": request.session_id,
            "token_budget": request.token_budget,
        })
        
        return {
            "code": 200,
            "message": "success",
            "data": result,
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"组装失败：{str(e)}")
```

**Step 2**: 注册路由

```python
# 文件：src/main.py
# 添加导入和注册

from src.routes.context import router as context_router

app.include_router(context_router)
```

#### 验收标准

- [ ] API 端点可访问
- [ ] 返回消息列表
- [ ] 返回 token 估算
- [ ] 测试通过

---

### 3.5 暴露 compact API（P1）

#### 目标

暴露 `/context/compact` API，允许手动触发压缩。

#### API 设计

```json
POST /context/compact

Request:
{
  "user_id": "user_001",
  "agent_id": "agent_001",  // 可选
  "session_id": "session_001",
  "token_budget": 100000,
  "force": false
}

Response:
{
  "code": 200,
  "data": {
    "action_taken": true,
    "tokens_before": 80000,
    "tokens_after": 20000,
    "summary_id": "sum_new",
    "level": "normal"
  }
}
```

#### 实施步骤

**Step 1**: 添加端点到 context.py

```python
# 文件：src/routes/context.py
# 新增端点

class CompactRequest(BaseModel):
    """压缩请求"""
    user_id: str = Field(..., description="用户 ID")
    agent_id: Optional[str] = Field(None, description="Agent ID")
    session_id: str = Field(..., description="会话 ID")
    token_budget: int = Field(100000, ge=1000, le=500000, description="Token 预算")
    force: bool = Field(False, description="强制压缩")


@router.post(
    "/compact",
    response_model=dict,
    summary="触发压缩",
    description="手动触发 DAG 压缩",
)
async def compact_context(request: CompactRequest):
    """
    触发压缩
    
    - **force**: 是否强制压缩（忽略阈值检查）
    """
    db.set_current_user(request.user_id)
    
    try:
        # 注意：compact 需要 summarize_fn，这里需要配置 LLM
        from src.llm.client import get_llm_client
        
        llm_client = get_llm_client()
        
        def summarize_fn(text: str, aggressive: bool = False) -> str:
            # 调用 LLM 生成摘要
            prompt = f"请总结以下内容（{'详细' if not aggressive else '简略'}）：\n\n{text}"
            return llm_client.chat(prompt)
        
        result = await memory_recall_engine.compact({
            "user_id": request.user_id,
            "agent_id": request.agent_id,
            "session_id": request.session_id,
            "token_budget": request.token_budget,
            "force": request.force,
            "summarize_fn": summarize_fn,
        })
        
        return {
            "code": 200,
            "message": "success",
            "data": result,
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"压缩失败：{str(e)}")
```

#### 验收标准

- [ ] API 端点可访问
- [ ] 返回压缩结果
- [ ] force 参数生效
- [ ] 测试通过

---

## 四、测试计划

### 单元测试

```bash
# 实体提取测试
tests/test_entity_integration.py

# 召回片段测试
tests/test_recall_snippet.py

# API 测试
tests/test_expand_api.py
tests/test_context_api.py
```

### 集成测试

```python
# tests/test_v3_integration.py

async def test_full_workflow():
    """完整工作流测试"""
    
    # 1. 存储记忆（含实体提取）
    result = await unified_memory_service.store(
        user_id="test",
        content="今天在星巴克遇到了老同学张三",
        enable_graph=True,
    )
    assert result["entities_count"] >= 1
    
    # 2. 召回（返回片段）
    results = await unified_memory_service.recall(
        query="张三",
        user_id="test",
        return_snippet=True,
    )
    assert len(results) >= 1
    assert "snippet" in results[0]
    
    # 3. 组装上下文
    context = await memory_recall_engine.assemble({
        "user_id": "test",
        "session_id": "session_001",
    })
    assert "messages" in context
    
    # 4. 触发压缩
    compact_result = await memory_recall_engine.compact({
        "user_id": "test",
        "session_id": "session_001",
        "force": True,
        "summarize_fn": mock_summarize,
    })
    
    # 5. 展开摘要
    if compact_result["summary_id"]:
        expanded = await dag_expand_service.expand_to_messages(
            compact_result["summary_id"]
        )
        assert len(expanded["messages"]) >= 1
```

---

## 五、验收标准

### Phase 5 完成标准

- [ ] `POST /memories` 返回 entities
- [ ] `POST /memories/recall` 返回 snippet
- [ ] `POST /memories/expand` 可访问
- [ ] `POST /context/assemble` 可访问
- [ ] `POST /context/compact` 可访问
- [ ] 所有单元测试通过
- [ ] 集成测试通过

### Phase 6 完成标准

- [ ] `memory_entities` 表有数据
- [ ] 图谱召回能找到 raw_messages
- [ ] 长文档上传自动生成摘要

---

## 六、风险与缓解

| 风险 | 影响 | 缓解措施 |
|-----|-----|---------|
| 实体提取 LLM 调用失败 | 功能降级 | 捕获异常，返回空实体 |
| 片段提取性能影响 | 召回延迟 | 异步处理，缓存结果 |
| 压缩 LLM 调用成本 | 成本增加 | 提供手动触发，默认关闭 |

---

## 七、时间估算

| 阶段 | 任务 | 预估时间 |
|-----|-----|---------|
| Phase 5 | 实体提取集成 | 0.5 天 |
| | 召回返回片段 | 0.5 天 |
| | 暴露 expand API | 0.5 天 |
| | 暴露 assemble API | 0.5 天 |
| | 暴露 compact API | 0.5 天 |
| | 单元测试 | 0.5 天 |
| Phase 6 | message_entities 关联 | 0.5 天 |
| | 长文档自动压缩 | 0.3 天 |
| | 端到端测试 | 0.2 天 |
| **总计** | | **4 天** |
