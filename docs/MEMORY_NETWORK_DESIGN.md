# 记忆网络构建系统 - 详细设计方案

> 版本：v1.0
> 日期：2026-03-19
> 作者：颓弟 AI Agent

---

## 目录

1. [系统概述](#1-系统概述)
2. [系统架构](#2-系统架构)
3. [数据库设计](#3-数据库设计)
4. [核心服务设计](#4-核心服务设计)
5. [API 接口设计](#5-api-接口设计)
6. [实施步骤](#6-实施步骤)
7. [测试方案](#7-测试方案)
8. [风险和应对](#8-风险和应对)
9. [技术选型](#9-技术选型)

---

## 1. 系统概述

### 1.1 目标

从**孤立记忆**升级到**关联记忆网络**，实现：

- ✅ 记忆自动关联（人物关系、地点关系、事件因果）
- ✅ 网络增强召回（实体扩展、多跳推理）
- ✅ 用户无感输入（快速提取 + 后台构建）

### 1.2 核心价值

| 价值 | 说明 |
|------|------|
| **提升召回准确率** | 从 80% → 95% |
| **自动关联发现** | 无 → 自动关联 |
| **用户感知升级** | 孤立记忆 → 网络化记忆 |

### 1.3 关键指标

| 指标 | 目标 |
|------|------|
| **召回准确率** | > 85% |
| **关联覆盖率** | > 70% |
| **用户确认率** | > 90% |
| **网络构建时间** | < 2s/记忆 |

---

## 2. 系统架构

### 2.1 四层架构

```
┌─────────────────────────────────────────┐
│           用户输入层                      │
│  - 文本输入                               │
│  - 图片上传                               │
│  - 语音转文字                             │
└─────────────────────────────────────────┘
              ↓
┌─────────────────────────────────────────┐
│      存储层（快速提取 <100ms）            │
│  - NER 实体提取                           │
│  - 时间解析                               │
│  - 情感分析                               │
│  - 主题分类                               │
└─────────────────────────────────────────┘
              ↓
┌─────────────────────────────────────────┐
│      后台层（异步构建）                    │
│  - 关系推理引擎                           │
│  - 网络构建服务                           │
│  - 智能确认服务                           │
│  - 网络优化服务                           │
└─────────────────────────────────────────┘
              ↓
┌─────────────────────────────────────────┐
│      召回层（网络增强）                    │
│  - 实体扩展召回                           │
│  - 关联记忆召回                           │
│  - 多跳推理召回                           │
└─────────────────────────────────────────┘
```

### 2.2 数据流

```
用户输入记忆
    ↓
存储层：快速提取实体（<100ms）
    ↓
数据库：存储记忆 + 实体
    ↓
后台层：异步构建网络（不阻塞）
    ↓
    ├─→ 关系推理（LLM + 规则）
    ├─→ 网络更新
    └─→ 智能确认（必要时）
    ↓
召回层：网络增强检索
    ↓
返回结果
```

### 2.3 与现有系统集成

```
现有系统：
  memories 表
  memory_service.py
  recall_service.py
  llm_recall_service.py

扩展后：
  memories 表（不变）
  entities 表（新增）      ← 实体存储
  relations 表（新增）     ← 关系存储
  memory_entities 表（新增）← 关联表
  
  memory_service.py（扩展）→ 添加实体提取
  recall_service.py（扩展）→ 添加网络增强
  
  entity_extraction_service.py（新增）
  relation_inference_service.py（新增）
  network_builder_service.py（新增）
  confirmation_service.py（新增）
  network_recall_service.py（新增）
```

---

## 3. 数据库设计

### 3.1 实体表 (entities)

```sql
CREATE TABLE entities (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    type VARCHAR(20) NOT NULL,  -- person/location/event/topic/emotion
    name VARCHAR(200) NOT NULL,
    aliases TEXT[],              -- 别名列表
    normalized_name VARCHAR(200), -- 标准化名称
    properties JSONB DEFAULT '{}', -- 扩展属性
    
    -- 统计字段
    mention_count INT DEFAULT 1,  -- 提及次数
    last_mentioned_at TIMESTAMP,  -- 最后提及时间
    
    -- 元数据
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    
    -- 索引
    CONSTRAINT unique_entity UNIQUE (type, normalized_name)
);

-- 索引
CREATE INDEX idx_entities_type ON entities(type);
CREATE INDEX idx_entities_name ON entities USING gin(to_tsvector('simple', name));
CREATE INDEX idx_entities_aliases ON entities USING gin(aliases);

-- 注释
COMMENT ON TABLE entities IS '实体表：存储人物、地点、事件等实体';
COMMENT ON COLUMN entities.type IS '实体类型：person/location/event/topic/emotion';
COMMENT ON COLUMN entities.aliases IS '别名列表：如 ["老王", "王明"]';
COMMENT ON COLUMN entities.normalized_name IS '标准化名称：用于去重和匹配';
```

**字段说明**：

| 字段 | 类型 | 说明 | 示例 |
|------|------|------|------|
| `id` | UUID | 主键 | `uuid-xxx` |
| `type` | VARCHAR(20) | 实体类型 | `person` |
| `name` | VARCHAR(200) | 原始名称 | `老王` |
| `aliases` | TEXT[] | 别名列表 | `["王明", "老王"]` |
| `normalized_name` | VARCHAR(200) | 标准化名称 | `王明` |
| `properties` | JSONB | 扩展属性 | `{"phone": "xxx", "relation": "friend"}` |
| `mention_count` | INT | 提及次数 | `5` |

**实体类型**：

| 类型 | 说明 | 示例 |
|------|------|------|
| `person` | 人物 | 张三、老王 |
| `location` | 地点 | 咖啡店、公司 |
| `event` | 事件 | 产品规划会议、野餐 |
| `topic` | 主题 | 机器学习、投资 |
| `emotion` | 情绪 | 开心、焦虑 |

---

### 3.2 关系表 (relations)

```sql
CREATE TABLE relations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    from_entity_id UUID NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    to_entity_id UUID NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    relation_type VARCHAR(50) NOT NULL,  -- friend/colleague/family/at/related_to
    properties JSONB DEFAULT '{}',        -- {confidence: 0.9, source: 'llm'}
    
    -- 权重和状态
    weight FLOAT DEFAULT 1.0,            -- 关系权重（0-1）
    status VARCHAR(20) DEFAULT 'active', -- active/confirmed/ignored
    
    -- 元数据
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    
    -- 唯一约束
    CONSTRAINT unique_relation UNIQUE (from_entity_id, to_entity_id, relation_type)
);

-- 索引
CREATE INDEX idx_relations_from ON relations(from_entity_id);
CREATE INDEX idx_relations_to ON relations(to_entity_id);
CREATE INDEX idx_relations_type ON relations(relation_type);

-- 注释
COMMENT ON TABLE relations IS '关系表：存储实体之间的关系';
COMMENT ON COLUMN relations.relation_type IS '关系类型：friend/colleague/family/at/related_to';
COMMENT ON COLUMN relations.weight IS '关系权重：0-1，越高越重要';
COMMENT ON COLUMN relations.status IS '状态：active(活跃)/confirmed(已确认)/ignored(已忽略)';
```

**关系类型**：

| 类型 | 说明 | 示例 |
|------|------|------|
| `friend` | 朋友 | (张三, 李四, friend) |
| `colleague` | 同事 | (张三, 王经理, colleague) |
| `family` | 家人 | (张三, 张三的妻子, family) |
| `spouse` | 配偶 | (张三, 李四, spouse) |
| `at` | 在某地 | (张三, 咖啡店, at) |
| `located_in` | 位于 | (星巴克, 咖啡店, located_in) |
| `related_to` | 相关 | (野餐, 周末, related_to) |
| `caused_by` | 由...引起 | (加班, 项目紧张, caused_by) |

---

### 3.3 记忆-实体关联表 (memory_entities)

```sql
CREATE TABLE memory_entities (
    memory_id UUID NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
    entity_id UUID NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    role VARCHAR(20) NOT NULL,  -- mentioned/protagonist/location/time
    
    -- 提取信息
    confidence FLOAT DEFAULT 1.0,  -- 提取置信度
    source VARCHAR(20) DEFAULT 'ner',  -- ner/llm/user
    
    -- 上下文
    context TEXT,  -- 实体在记忆中的上下文
    
    PRIMARY KEY (memory_id, entity_id)
);

-- 索引
CREATE INDEX idx_memory_entities_memory ON memory_entities(memory_id);
CREATE INDEX idx_memory_entities_entity ON memory_entities(entity_id);

-- 注释
COMMENT ON TABLE memory_entities IS '记忆-实体关联表';
COMMENT ON COLUMN memory_entities.role IS '角色：mentioned(提及)/protagonist(主角)/location(地点)/time(时间)';
COMMENT ON COLUMN memory_entities.confidence IS '提取置信度：0-1';
COMMENT ON COLUMN memory_entities.source IS '来源：ner(规则提取)/llm(大模型)/user(用户输入)';
```

**角色类型**：

| 角色 | 说明 | 示例 |
|------|------|------|
| `mentioned` | 提及 | "提到张三" |
| `protagonist` | 主角 | "和张三吃饭"，张三是主要参与者 |
| `location` | 地点 | "在咖啡店" |
| `time` | 时间 | "上周" |

---

### 3.4 待确认队列 (pending_confirmations)

```sql
CREATE TABLE pending_confirmations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    type VARCHAR(20) NOT NULL,  -- new_entity/relation_conflict/relation_update
    entity_id UUID REFERENCES entities(id),
    relation_id UUID REFERENCES relations(id),
    
    -- 确认内容
    question TEXT NOT NULL,     -- 问题文本
    options JSONB NOT NULL,     -- 选项列表
    
    -- 状态
    status VARCHAR(20) DEFAULT 'pending',  -- pending/confirmed/ignored/expired
    user_response JSONB,        -- 用户回复
    
    -- 优先级和过期
    priority INT DEFAULT 5,     -- 1-10，越高越优先
    expires_at TIMESTAMP,       -- 过期时间
    
    created_at TIMESTAMP DEFAULT NOW(),
    responded_at TIMESTAMP
);

-- 索引
CREATE INDEX idx_pending_status ON pending_confirmations(status);
CREATE INDEX idx_pending_priority ON pending_confirmations(priority DESC);

-- 注释
COMMENT ON TABLE pending_confirmations IS '待确认队列：存储需要用户确认的内容';
COMMENT ON COLUMN pending_confirmations.type IS '类型：new_entity(新实体)/relation_conflict(关系冲突)/relation_update(关系更新)';
COMMENT ON COLUMN pending_confirmations.priority IS '优先级：1-10，越高越优先';
```

**确认类型**：

| 类型 | 说明 | 示例 |
|------|------|------|
| `new_entity` | 新实体 | "发现新人物'老王'，这是谁？" |
| `relation_conflict` | 关系冲突 | "之前张三是'同事'，现在是'朋友'，更新吗？" |
| `relation_update` | 关系更新 | "老王是你的朋友吗？" |

---

## 4. 核心服务设计

### 4.1 实体提取服务 (EntityExtractionService)

**文件位置**：`apps/api/src/services/entity_extraction_service.py`

```python
"""
实体提取服务

职责：
1. 从文本中提取实体（NER + LLM）
2. 标准化实体名称
3. 链接到已有实体
"""

from typing import List, Dict, Optional
from uuid import UUID
import jieba
import jieba.posseg as pseg


class Entity:
    """实体类"""
    def __init__(
        self,
        name: str,
        type: str,
        aliases: List[str] = None,
        normalized_name: str = None,
        confidence: float = 1.0
    ):
        self.name = name
        self.type = type
        self.aliases = aliases or []
        self.normalized_name = normalized_name or name
        self.confidence = confidence


class EntityExtractionService:
    """实体提取服务"""
    
    # 实体类型映射
    POS_TYPE_MAP = {
        'nr': 'person',      # 人名
        'ns': 'location',    # 地名
        'nt': 'organization',# 组织名
        't': 'time',         # 时间
        'nz': 'other',       # 其他专名
    }
    
    async def extract_entities(
        self,
        content: str,
        extract_types: List[str] = ["person", "location", "time", "topic", "emotion"]
    ) -> Dict[str, List[Entity]]:
        """
        从文本中提取实体
        
        Args:
            content: 文本内容
            extract_types: 要提取的实体类型
            
        Returns:
            {
                "persons": [Entity(...), ...],
                "locations": [Entity(...), ...],
                ...
            }
        """
        results = {f"{t}s": [] for t in extract_types}
        
        # 1. NER 提取
        ner_entities = self._ner_extract(content)
        
        # 2. 规则提取
        rule_entities = self._rule_extract(content)
        
        # 3. LLM 提取（可选，用于复杂场景）
        llm_entities = await self._llm_extract(content, extract_types)
        
        # 4. 合并结果
        all_entities = ner_entities + rule_entities + llm_entities
        all_entities = self._deduplicate(all_entities)
        
        # 5. 分类存储
        for entity in all_entities:
            type_key = f"{entity.type}s"
            if type_key in results:
                results[type_key].append(entity)
        
        return results
    
    def _ner_extract(self, content: str) -> List[Entity]:
        """NER 提取（使用 jieba）"""
        entities = []
        
        words = pseg.cut(content)
        for word, flag in words:
            if flag in self.POS_TYPE_MAP:
                entity_type = self.POS_TYPE_MAP[flag]
                if entity_type in ['person', 'location', 'time']:
                    entities.append(Entity(
                        name=word,
                        type=entity_type,
                        confidence=0.8
                    ))
        
        return entities
    
    def _rule_extract(self, content: str) -> List[Entity]:
        """规则提取"""
        entities = []
        
        # 人物关系关键词
        PERSON_KEYWORDS = {
            "家人": "person",
            "老婆": "person",
            "老公": "person",
            "孩子": "person",
            "朋友": "person",
            "同事": "person",
        }
        
        # 地点关键词
        LOCATION_KEYWORDS = {
            "咖啡店": "location",
            "公司": "location",
            "家里": "location",
            "健身房": "location",
        }
        
        # 检查人物关键词
        for keyword, entity_type in PERSON_KEYWORDS.items():
            if keyword in content:
                entities.append(Entity(
                    name=keyword,
                    type=entity_type,
                    confidence=0.9
                ))
        
        # 检查地点关键词
        for keyword, entity_type in LOCATION_KEYWORDS.items():
            if keyword in content:
                entities.append(Entity(
                    name=keyword,
                    type=entity_type,
                    confidence=0.9
                ))
        
        return entities
    
    async def _llm_extract(
        self,
        content: str,
        extract_types: List[str]
    ) -> List[Entity]:
        """LLM 提取（用于复杂场景）"""
        # TODO: 调用火山引擎 API
        return []
    
    async def normalize_entity(self, entity: Entity) -> Entity:
        """
        标准化实体
        
        - 人物：识别别名（老王 → 王明）
        - 地点：识别层级（星巴克 → 咖啡店）
        - 时间：解析为具体日期
        """
        # TODO: 实现标准化逻辑
        return entity
    
    async def link_entity(
        self,
        entity: Entity
    ) -> Optional[UUID]:
        """
        实体链接：将提取的实体关联到已有实体
        
        策略：
        1. 名称精确匹配
        2. 别名匹配
        3. 语义相似度匹配（> 0.9）
        """
        # TODO: 查询数据库，找到匹配的实体
        return None
    
    def _deduplicate(self, entities: List[Entity]) -> List[Entity]:
        """去重"""
        seen = set()
        result = []
        
        for entity in entities:
            key = (entity.type, entity.name)
            if key not in seen:
                seen.add(key)
                result.append(entity)
        
        return result
```

---

### 4.2 关系推理服务 (RelationInferenceService)

**文件位置**：`apps/api/src/services/relation_inference_service.py`

```python
"""
关系推理服务

职责：
1. 推理实体之间的关系
2. 检测关系冲突
3. 更新关系权重
"""

from typing import List, Optional
from uuid import UUID


class InferredRelation:
    """推理出的关系"""
    def __init__(
        self,
        from_entity: str,
        to_entity: str,
        relation_type: str,
        confidence: float = 0.8,
        source: str = "inference"
    ):
        self.from_entity = from_entity
        self.to_entity = to_entity
        self.relation_type = relation_type
        self.confidence = confidence
        self.source = source


class Conflict:
    """关系冲突"""
    def __init__(
        self,
        existing_relation,
        new_relation,
        conflict_type: str
    ):
        self.existing = existing_relation
        self.new = new_relation
        self.conflict_type = conflict_type


class RelationInferenceService:
    """关系推理服务"""
    
    # 推理规则
    INFERENCE_RULES = {
        # 称谓前缀 → 关系类型
        "老": "friend",
        "小": "colleague",
        
        # 关系关键词 → 关系类型
        "家人": "family",
        "老婆": "spouse",
        "老公": "spouse",
        "孩子": "child",
    }
    
    async def infer_relations(
        self,
        entities: List[str],
        content: str,
        existing_relations: List = None
    ) -> List[InferredRelation]:
        """
        推理实体关系
        
        策略：
        1. 共现分析：同时出现的实体可能有关系
        2. LLM 推理：使用大模型分析关系类型
        3. 规则推理：基于预定义规则
        """
        relations = []
        
        # 1. 规则推理
        rule_relations = self._rule_inference(entities, content)
        relations.extend(rule_relations)
        
        # 2. 共现分析
        co_occurrence_relations = await self._co_occurrence_inference(entities)
        relations.extend(co_occurrence_relations)
        
        # 3. LLM 推理（可选，用于复杂场景）
        llm_relations = await self._llm_inference(entities, content)
        relations.extend(llm_relations)
        
        return relations
    
    def _rule_inference(
        self,
        entities: List[str],
        content: str
    ) -> List[InferredRelation]:
        """规则推理"""
        relations = []
        
        # 检查称谓前缀
        for entity in entities:
            for prefix, relation_type in self.INFERENCE_RULES.items():
                if entity.startswith(prefix):
                    relations.append(InferredRelation(
                        from_entity=entity,
                        to_entity="user",
                        relation_type=relation_type,
                        confidence=0.7,
                        source="rule"
                    ))
        
        return relations
    
    async def _co_occurrence_inference(
        self,
        entities: List[str]
    ) -> List[InferredRelation]:
        """共现分析推理"""
        # TODO: 查询数据库，统计共现次数
        return []
    
    async def _llm_inference(
        self,
        entities: List[str],
        content: str
    ) -> List[InferredRelation]:
        """LLM 推理"""
        # TODO: 调用火山引擎 API
        return []
    
    async def detect_conflicts(
        self,
        new_relation: InferredRelation,
        existing_relations: List
    ) -> Optional[Conflict]:
        """
        检测关系冲突
        
        示例：
        - 已有：(张三, colleague)
        - 新推理：(张三, friend)
        - 冲突：同一人物关系变化
        """
        for existing in existing_relations:
            # 同一实体，不同关系
            if (existing.from_entity == new_relation.from_entity and
                existing.relation_type != new_relation.relation_type):
                return Conflict(
                    existing_relation=existing,
                    new_relation=new_relation,
                    conflict_type="relation_change"
                )
        
        return None
```

---

### 4.3 网络构建服务 (NetworkBuilderService)

**文件位置**：`apps/api/src/services/network_builder_service.py`

```python
"""
网络构建服务

职责：
1. 为记忆构建网络
2. 批量构建网络
3. 网络优化
"""

from typing import List
from uuid import UUID
import asyncio


class NetworkBuilderService:
    """记忆网络构建服务"""
    
    def __init__(self):
        self.entity_extraction = EntityExtractionService()
        self.relation_inference = RelationInferenceService()
    
    async def build_network(self, memory_id: UUID):
        """
        为单个记忆构建网络
        
        流程：
        1. 提取实体
        2. 推理关系
        3. 存储实体和关系
        4. 生成确认任务
        """
        # 1. 获取记忆内容
        memory = await self._get_memory(memory_id)
        
        # 2. 提取实体
        entities = await self.entity_extraction.extract_entities(memory.content)
        
        # 3. 存储实体
        entity_ids = {}
        for entity_type, entity_list in entities.items():
            for entity in entity_list:
                entity_id = await self._upsert_entity(entity)
                entity_ids[entity.name] = entity_id
        
        # 4. 推理关系
        all_entities = [e.name for ents in entities.values() for e in ents]
        relations = await self.relation_inference.infer_relations(
            all_entities,
            memory.content
        )
        
        # 5. 存储关系
        for relation in relations:
            await self._upsert_relation(relation, entity_ids)
        
        # 6. 创建记忆-实体关联
        await self._create_memory_entity_links(memory_id, entities, entity_ids)
        
        # 7. 生成确认任务
        await self._generate_confirmations(entities, relations)
    
    async def batch_build_networks(self, memory_ids: List[UUID]):
        """批量构建网络（后台任务）"""
        tasks = [self.build_network(mid) for mid in memory_ids]
        await asyncio.gather(*tasks)
    
    async def optimize_network(self):
        """
        网络优化
        
        - 删除低权重关系（< 0.3）
        - 合并相似实体
        - 更新实体统计
        """
        # TODO: 实现网络优化逻辑
        pass
    
    async def _get_memory(self, memory_id: UUID):
        """获取记忆"""
        # TODO: 查询数据库
        pass
    
    async def _upsert_entity(self, entity):
        """存储或更新实体"""
        # TODO: 插入数据库
        pass
    
    async def _upsert_relation(self, relation, entity_ids):
        """存储或更新关系"""
        # TODO: 插入数据库
        pass
    
    async def _create_memory_entity_links(self, memory_id, entities, entity_ids):
        """创建记忆-实体关联"""
        # TODO: 插入数据库
        pass
    
    async def _generate_confirmations(self, entities, relations):
        """生成确认任务"""
        # TODO: 调用确认服务
        pass
```

---

### 4.4 智能确认服务 (ConfirmationService)

**文件位置**：`apps/api/src/services/confirmation_service.py`

```python
"""
智能确认服务

职责：
1. 生成确认任务
2. 判断是否需要用户确认
3. 发送确认请求
4. 处理用户回复
"""

from typing import List, Optional
from uuid import UUID


class Confirmation:
    """确认任务"""
    def __init__(
        self,
        type: str,
        question: str,
        options: List[dict],
        entity_id: UUID = None,
        relation_id: UUID = None,
        priority: int = 5
    ):
        self.type = type
        self.question = question
        self.options = options
        self.entity_id = entity_id
        self.relation_id = relation_id
        self.priority = priority


class ConfirmationService:
    """智能确认服务"""
    
    # 确认阈值
    AUTO_CONFIRM_THRESHOLD = 0.9  # 置信度 > 0.9 自动确认
    NEED_CONFIRM_THRESHOLD = 0.7  # 置信度 < 0.7 需要确认
    
    async def generate_confirmations(
        self,
        entity,
        relations: List
    ) -> List[Confirmation]:
        """
        生成确认任务
        
        策略：
        1. 新实体：生成"这是谁？"确认
        2. 新关系：生成"关系确认"
        3. 关系冲突：生成"关系更新"确认
        """
        confirmations = []
        
        # 1. 检查是否需要确认
        for relation in relations:
            if await self.should_ask_user(relation):
                confirmation = Confirmation(
                    type="relation_update",
                    question=f"你提到\"{entity.name}\"，{relation.from_entity}是你的{relation.relation_type}吗？",
                    options=[
                        {"text": f"是的，是{relation.relation_type}", "action": "confirm"},
                        {"text": "不是", "action": "modify"},
                        {"text": "暂时不填", "action": "skip"}
                    ],
                    priority=7
                )
                confirmations.append(confirmation)
        
        return confirmations
    
    async def should_ask_user(self, relation) -> bool:
        """
        判断是否需要用户确认
        
        规则：
        - 置信度 < 0.7 → 需要确认
        - 新实体首次出现 → 需要确认
        - 关系冲突 → 需要确认
        - 置信度 >= 0.9 → 自动确认
        """
        if relation.confidence >= self.AUTO_CONFIRM_THRESHOLD:
            return False
        
        if relation.confidence < self.NEED_CONFIRM_THRESHOLD:
            return True
        
        # TODO: 检查是否是新实体、是否有冲突
        return False
    
    async def send_confirmation(self, confirmation: Confirmation):
        """
        发送确认请求
        
        渠道：
        - 飞书消息卡片
        - 微信推送
        - App 通知
        """
        # TODO: 发送消息卡片
        pass
    
    async def handle_user_response(
        self,
        confirmation_id: UUID,
        response: str
    ):
        """
        处理用户回复
        
        操作：
        - 更新实体/关系状态
        - 更新网络权重
        - 记录用户偏好
        """
        # TODO: 更新数据库
        pass
```

---

### 4.5 网络召回服务 (NetworkRecallService)

**文件位置**：`apps/api/src/services/network_recall_service.py`

```python
"""
网络召回服务

职责：
1. 实体扩展召回
2. 关联记忆召回
3. 多跳推理召回
"""

from typing import List


class NetworkRecallService:
    """网络召回服务"""
    
    async def enhance_recall(
        self,
        query: str,
        base_results: List
    ) -> List:
        """
        网络增强召回
        
        策略：
        1. 实体扩展：根据网络扩展查询实体
        2. 关联召回：召回相关记忆
        3. 多跳推理：基于网络关系推理
        """
        # 1. 提取查询中的实体
        query_entities = await self._extract_query_entities(query)
        
        # 2. 实体扩展
        expanded_entities = await self.expand_entities(query_entities)
        
        # 3. 关联召回
        related_memories = await self.find_related_memories(base_results)
        
        # 4. 合并结果
        enhanced_results = base_results + related_memories
        
        # 5. 去重
        enhanced_results = self._deduplicate(enhanced_results)
        
        return enhanced_results
    
    async def expand_entities(self, entities: List[str]) -> List[str]:
        """
        实体扩展
        
        示例：
        查询："和朋友在一起"
        网络查询：friend-of(user) = [张三, 李四, 老王]
        扩展查询：[朋友, 张三, 李四, 老王]
        """
        expanded = list(entities)
        
        for entity in entities:
            # 查询数据库，找到相关实体
            # TODO: SELECT * FROM relations WHERE from_entity = entity AND relation_type = 'friend'
            pass
        
        return expanded
    
    async def find_related_memories(
        self,
        memories: List,
        max_depth: int = 2
    ) -> List:
        """
        查找关联记忆
        
        策略：
        1. 同实体记忆
        2. 相关实体记忆
        3. 时间相邻记忆
        """
        related = []
        
        for memory in memories:
            # 1. 获取记忆的实体
            entities = await self._get_memory_entities(memory.id)
            
            # 2. 查询同实体的其他记忆
            # TODO: SELECT * FROM memories WHERE id IN (
            #   SELECT memory_id FROM memory_entities WHERE entity_id IN (...)
            # )
            
            # 3. 查询相关实体的记忆
            # TODO: SELECT * FROM memories WHERE id IN (
            #   SELECT memory_id FROM memory_entities WHERE entity_id IN (
            #     SELECT to_entity_id FROM relations WHERE from_entity_id IN (...)
            #   )
            # )
        
        return related
    
    async def _extract_query_entities(self, query: str) -> List[str]:
        """提取查询中的实体"""
        # TODO: 使用 NER 或关键词提取
        return []
    
    async def _get_memory_entities(self, memory_id):
        """获取记忆的实体"""
        # TODO: 查询数据库
        return []
    
    def _deduplicate(self, results: List) -> List:
        """去重"""
        seen = set()
        deduped = []
        
        for result in results:
            if result.id not in seen:
                seen.add(result.id)
                deduped.append(result)
        
        return deduped
```

---

## 5. API 接口设计

### 5.1 实体管理 API

#### 获取实体详情

```http
GET /api/v1/entities/{entity_id}

Response:
{
  "id": "uuid-xxx",
  "type": "person",
  "name": "张三",
  "aliases": ["老张"],
  "normalized_name": "张三",
  "properties": {
    "phone": "xxx",
    "relation": "friend"
  },
  "mention_count": 5,
  "last_mentioned_at": "2026-03-19T10:00:00Z",
  "created_at": "2026-03-01T00:00:00Z"
}
```

#### 搜索实体

```http
GET /api/v1/entities/search?query=张三&type=person

Response:
{
  "code": 200,
  "data": {
    "results": [
      {
        "id": "uuid-xxx",
        "name": "张三",
        "type": "person",
        "mention_count": 5
      }
    ],
    "count": 1
  }
}
```

#### 获取实体的关系

```http
GET /api/v1/entities/{entity_id}/relations

Response:
{
  "code": 200,
  "data": {
    "relations": [
      {
        "id": "uuid-xxx",
        "from_entity": {"id": "xxx", "name": "张三"},
        "to_entity": {"id": "xxx", "name": "咖啡店"},
        "relation_type": "at",
        "weight": 1.0,
        "status": "active"
      }
    ],
    "count": 1
  }
}
```

---

### 5.2 关系管理 API

#### 获取关系详情

```http
GET /api/v1/relations/{relation_id}

Response:
{
  "id": "uuid-xxx",
  "from_entity": {
    "id": "xxx",
    "name": "张三",
    "type": "person"
  },
  "to_entity": {
    "id": "xxx",
    "name": "咖啡店",
    "type": "location"
  },
  "relation_type": "at",
  "weight": 1.0,
  "status": "active",
  "properties": {
    "confidence": 0.9,
    "source": "llm"
  },
  "created_at": "2026-03-19T10:00:00Z"
}
```

#### 创建关系

```http
POST /api/v1/relations

Request:
{
  "from_entity_id": "uuid-xxx",
  "to_entity_id": "uuid-yyy",
  "relation_type": "friend",
  "properties": {
    "confidence": 0.9,
    "source": "user"
  }
}

Response:
{
  "code": 200,
  "message": "success",
  "data": {
    "id": "uuid-zzz",
    "from_entity_id": "uuid-xxx",
    "to_entity_id": "uuid-yyy",
    "relation_type": "friend"
  }
}
```

---

### 5.3 确认管理 API

#### 获取待确认列表

```http
GET /api/v1/confirmations/pending

Response:
{
  "code": 200,
  "data": {
    "confirmations": [
      {
        "id": "uuid-xxx",
        "type": "relation_update",
        "question": "你提到\"老王\"，老王是你的朋友吗？",
        "options": [
          {"text": "是的，是朋友", "action": "confirm"},
          {"text": "是同事", "action": "modify"},
          {"text": "暂时不填", "action": "skip"}
        ],
        "priority": 7,
        "created_at": "2026-03-19T10:00:00Z"
      }
    ],
    "count": 1
  }
}
```

#### 回复确认

```http
POST /api/v1/confirmations/{confirmation_id}/respond

Request:
{
  "action": "confirm",
  "relation_type": "friend"
}

Response:
{
  "code": 200,
  "message": "确认成功",
  "data": {
    "relation": {
      "id": "uuid-xxx",
      "from_entity": "老王",
      "relation_type": "friend",
      "status": "confirmed"
    }
  }
}
```

---

### 5.4 网络可视化 API

#### 获取网络图数据

```http
GET /api/v1/network/graph?entity_id={id}&depth={depth}

Response:
{
  "code": 200,
  "data": {
    "nodes": [
      {"id": "uuid-xxx", "name": "张三", "type": "person", "size": 10},
      {"id": "uuid-yyy", "name": "咖啡店", "type": "location", "size": 5}
    ],
    "edges": [
      {
        "id": "uuid-zzz",
        "from": "uuid-xxx",
        "to": "uuid-yyy",
        "relation_type": "at",
        "weight": 1.0
      }
    ],
    "stats": {
      "node_count": 2,
      "edge_count": 1
    }
  }
}
```

---

## 6. 实施步骤

### Phase 1: 数据库和基础服务（2-3 天）

**任务清单**：

- [ ] 创建数据库表（entities, relations, memory_entities, pending_confirmations）
- [ ] 实现 EntityExtractionService
  - [ ] NER 提取（jieba）
  - [ ] 规则提取
  - [ ] 实体标准化
  - [ ] 实体链接
- [ ] 编写单元测试

**验收标准**：

- [ ] 数据库表创建成功
- [ ] 实体提取准确率 > 80%
- [ ] 实体链接召回率 > 90%

**工作量估算**：

| 任务 | 时间 |
|------|------|
| 数据库设计 | 2 小时 |
| EntityExtractionService | 8 小时 |
| 单元测试 | 4 小时 |
| **总计** | **14 小时** |

---

### Phase 2: 关系推理和网络构建（3-5 天）

**任务清单**：

- [ ] 实现 RelationInferenceService
  - [ ] 规则推理
  - [ ] 共现分析
  - [ ] LLM 推理
- [ ] 实现 NetworkBuilderService
  - [ ] 单记忆构建
  - [ ] 批量构建
  - [ ] 网络优化
- [ ] 后台异步任务
- [ ] 编写单元测试

**验收标准**：

- [ ] 关系推理准确率 > 70%
- [ ] 网络构建时间 < 2s/记忆
- [ ] 支持并发处理

**工作量估算**：

| 任务 | 时间 |
|------|------|
| RelationInferenceService | 8 小时 |
| NetworkBuilderService | 12 小时 |
| 后台任务 | 4 小时 |
| 单元测试 | 6 小时 |
| **总计** | **30 小时** |

---

### Phase 3: 智能确认机制（2-3 天）

**任务清单**：

- [ ] 实现 ConfirmationService
  - [ ] 生成确认任务
  - [ ] 判断是否需要确认
  - [ ] 发送确认请求
  - [ ] 处理用户回复
- [ ] 设计确认卡片 UI
- [ ] 集成飞书消息卡片
- [ ] 编写单元测试

**验收标准**：

- [ ] 确认准确率 > 90%
- [ ] 确认卡片交互流畅
- [ ] 用户反馈处理正确

**工作量估算**：

| 任务 | 时间 |
|------|------|
| ConfirmationService | 6 小时 |
| 飞书卡片集成 | 6 小时 |
| 单元测试 | 4 小时 |
| **总计** | **16 小时** |

---

### Phase 4: 网络召回增强（3-5 天）

**任务清单**：

- [ ] 实现 NetworkRecallService
  - [ ] 实体扩展
  - [ ] 关联召回
  - [ ] 多跳推理
- [ ] 集成到现有召回流程
- [ ] 性能优化
- [ ] 编写单元测试

**验收标准**：

- [ ] 召回准确率提升 > 10%
- [ ] 召回时间 < 2s
- [ ] 关联召回准确率 > 85%

**工作量估算**：

| 任务 | 时间 |
|------|------|
| NetworkRecallService | 12 小时 |
| 集成现有流程 | 4 小时 |
| 性能优化 | 6 小时 |
| 单元测试 | 6 小时 |
| **总计** | **28 小时** |

---

### Phase 5: 测试和优化（2-3 天）

**任务清单**：

- [ ] 端到端测试
- [ ] 性能测试
- [ ] 用户测试
- [ ] Bug 修复
- [ ] 文档完善

**验收标准**：

- [ ] 所有功能正常工作
- [ ] 性能达标
- [ ] 用户满意度 > 80%

**工作量估算**：

| 任务 | 时间 |
|------|------|
| 端到端测试 | 6 小时 |
| 性能测试 | 4 小时 |
| 用户测试 | 4 小时 |
| Bug 修复 | 6 小时 |
| **总计** | **20 小时** |

---

### 总工作量

| 阶段 | 时间 | 工作量 |
|------|------|--------|
| Phase 1 | 2-3 天 | 14 小时 |
| Phase 2 | 3-5 天 | 30 小时 |
| Phase 3 | 2-3 天 | 16 小时 |
| Phase 4 | 3-5 天 | 28 小时 |
| Phase 5 | 2-3 天 | 20 小时 |
| **总计** | **12-19 天** | **108 小时** |

---

## 7. 测试方案

### 7.1 单元测试

#### 实体提取测试

```python
def test_extract_persons():
    """测试人物提取"""
    service = EntityExtractionService()
    result = await service.extract_entities("今天和张三、李四开会")
    
    assert len(result["persons"]) == 2
    assert result["persons"][0].name == "张三"
    assert result["persons"][1].name == "李四"


def test_extract_locations():
    """测试地点提取"""
    service = EntityExtractionService()
    result = await service.extract_entities("在咖啡店和朋友聊天")
    
    assert len(result["locations"]) == 1
    assert result["locations"][0].name == "咖啡店"


def test_entity_normalization():
    """测试实体标准化"""
    service = EntityExtractionService()
    entity = Entity(name="老王", type="person")
    normalized = await service.normalize_entity(entity)
    
    assert normalized.normalized_name == "王明"
```

#### 关系推理测试

```python
def test_infer_relation():
    """测试关系推理"""
    service = RelationInferenceService()
    entities = ["张三", "咖啡店"]
    relations = await service.infer_relations(entities, "和张三在咖啡店吃饭")
    
    assert any(r.relation_type == "at" for r in relations)
    assert any(r.from_entity == "张三" and r.to_entity == "咖啡店" for r in relations)


def test_detect_conflicts():
    """测试冲突检测"""
    service = RelationInferenceService()
    
    existing = Relation(from_entity="张三", relation_type="colleague")
    new = InferredRelation(from_entity="张三", relation_type="friend")
    
    conflict = await service.detect_conflicts(new, [existing])
    
    assert conflict is not None
    assert conflict.conflict_type == "relation_change"
```

#### 网络召回测试

```python
def test_enhance_recall():
    """测试网络增强召回"""
    service = NetworkRecallService()
    base_results = [Memory(id="1", content="和张三吃饭")]
    
    enhanced = await service.enhance_recall("和朋友吃饭", base_results)
    
    assert len(enhanced) >= len(base_results)


def test_expand_entities():
    """测试实体扩展"""
    service = NetworkRecallService()
    
    # 假设网络中已存在：张三是朋友
    expanded = await service.expand_entities(["朋友"])
    
    assert "张三" in expanded
```

---

### 7.2 集成测试

#### 端到端流程测试

```python
def test_end_to_end():
    """端到端流程测试"""
    # 1. 创建记忆
    memory_id = create_memory("今天和老王在咖啡店吃饭")
    
    # 2. 等待网络构建
    time.sleep(2)
    
    # 3. 验证实体
    entities = get_entities(memory_id)
    assert any(e.name == "老王" for e in entities)
    assert any(e.name == "咖啡店" for e in entities)
    
    # 4. 验证关系
    relations = get_relations("老王")
    assert any(r.relation_type == "friend" for r in relations)
    
    # 5. 验证召回
    results = recall("和朋友吃饭")
    assert any(m.id == memory_id for m in results)
```

#### 确认流程测试

```python
def test_confirmation_flow():
    """确认流程测试"""
    # 1. 创建记忆（触发确认）
    memory_id = create_memory("和老王吃饭")
    
    # 2. 获取待确认列表
    confirmations = get_pending_confirmations()
    assert len(confirmations) > 0
    
    # 3. 回复确认
    respond_confirmation(confirmations[0].id, "confirm")
    
    # 4. 验证关系状态
    relation = get_relation(confirmations[0].relation_id)
    assert relation.status == "confirmed"
```

---

### 7.3 性能测试

#### 并发构建测试

```python
def test_concurrent_build():
    """并发构建测试"""
    memories = [f"记忆 {i}" for i in range(100)]
    
    start = time.time()
    await batch_build_networks(memories)
    elapsed = time.time() - start
    
    assert elapsed < 60  # 100条记忆 < 60s
```

#### 召回性能测试

```python
def test_recall_performance():
    """召回性能测试"""
    # 准备数据：1000 条记忆
    for i in range(1000):
        create_memory(f"记忆 {i}")
    
    # 测试召回时间
    start = time.time()
    results = recall("和朋友吃饭")
    elapsed = time.time() - start
    
    assert elapsed < 2  # < 2s
```

#### 内存使用测试

```python
def test_memory_usage():
    """内存使用测试"""
    import psutil
    import os
    
    process = psutil.Process(os.getpid())
    initial_memory = process.memory_info().rss / 1024 / 1024  # MB
    
    # 构建网络
    await build_networks_for_all_memories()
    
    final_memory = process.memory_info().rss / 1024 / 1024
    memory_increase = final_memory - initial_memory
    
    assert memory_increase < 500  # 内存增长 < 500MB
```

---

## 8. 风险和应对

### 8.1 实体提取错误

**风险**：NER 提取错误，导致关系错误

**影响**：高

**应对措施**：
1. **多模型验证**：使用 NER + 规则 + LLM 三种方式，交叉验证
2. **置信度过滤**：置信度 < 0.7 时标记为"待确认"
3. **用户反馈**：提供"修正实体"功能

**示例**：
```
错误提取："老王" → "王"（NER 错误）
应对：
  - 规则匹配："老"前缀 → 可能是人名
  - 用户确认："老王"是一个人名吗？
```

---

### 8.2 关系推理不准确

**风险**：推理的关系不准确，网络质量差

**影响**：高

**应对措施**：
1. **置信度阈值**：只保留置信度 > 0.7 的关系
2. **用户确认**：新关系、冲突关系需要用户确认
3. **权重衰减**：长期不用的关系降低权重
4. **定期清理**：删除低权重关系

**示例**：
```
错误推理：(张三, 咖啡店, friend)  # 实际应该是 at 关系
应对：
  - LLM 验证："张三在咖啡店" → at 关系
  - 规则验证：人物-地点 → at 关系
```

---

### 8.3 用户确认疲劳

**风险**：确认请求过多，用户厌烦

**影响**：中

**应对措施**：
1. **智能筛选**：只对置信度 < 0.7 的新关系请求确认
2. **批量确认**：每周汇总，一次确认
3. **优先级排序**：重要关系优先确认
4. **延迟确认**：非紧急关系延迟到合适时机

**确认频率控制**：
```
每日确认上限：5 条
每周汇总确认：批量确认
置信度 > 0.9：自动确认，不询问
```

---

### 8.4 网络过于复杂

**风险**：网络节点和关系过多，性能下降

**影响**：中

**应对措施**：
1. **权重过滤**：只保留权重 > 0.3 的关系
2. **衰减机制**：长期不用的关系降低权重
3. **定期清理**：删除低权重节点和关系
4. **分层存储**：热点数据缓存，冷数据归档

**清理策略**：
```
每周执行：
  - 删除权重 < 0.3 的关系
  - 删除提及次数 < 2 的实体
  - 更新实体统计
```

---

### 8.5 召回时间过长

**风险**：网络召回增加查询时间，用户体验差

**影响**：高

**应对措施**：
1. **缓存**：缓存热点实体和关系
2. **预计算**：后台预计算关联记忆
3. **限制深度**：限制多跳推理的深度（最多 2 跳）
4. **并行查询**：并行查询多个数据源

**性能优化**：
```
单次召回时间：< 2s
  - 实体扩展：< 100ms
  - 关联召回：< 500ms
  - 结果合并：< 100ms
```

---

### 8.6 数据一致性

**风险**：网络数据和记忆数据不一致

**影响**：中

**应对措施**：
1. **事务处理**：使用数据库事务确保一致性
2. **定期同步**：后台定期检查和修复不一致
3. **版本控制**：记录数据变更历史，支持回滚

**一致性检查**：
```
每日执行：
  - 检查孤立实体（没有关联记忆）
  - 检查孤立关系（实体已删除）
  - 修复数据不一致
```

---

### 8.7 隐私和安全

**风险**：敏感信息泄露（人物关系、地点等）

**影响**：高

**应对措施**：
1. **权限控制**：只有用户本人可以访问自己的网络
2. **敏感词过滤**：自动过滤敏感信息
3. **数据加密**：敏感字段加密存储
4. **审计日志**：记录所有访问和修改操作

**安全措施**：
```
- 用户认证：JWT Token
- 数据加密：AES-256
- 访问日志：记录所有查询
- 敏感词：自动脱敏
```

---

## 9. 技术选型

### 9.1 核心技术栈

| 组件 | 选型 | 版本 | 原因 |
|------|------|------|------|
| **数据库** | PostgreSQL | 15+ | 已有，支持 JSONB、向量检索 |
| **向量检索** | pgvector | 0.5+ | 已有，与 PostgreSQL 集成 |
| **NER** | jieba | 0.42+ | 中文效果好，轻量级 |
| **LLM** | 火山引擎 Doubao | - | 已集成，性价比高 |
| **后端框架** | FastAPI | 0.100+ | 已有，异步支持好 |
| **任务队列** | asyncio | - | Python 内置，轻量级 |

---

### 9.2 可选技术

| 组件 | 选型 | 适用场景 | 说明 |
|------|------|---------|------|
| **图数据库** | Neo4j | 大规模网络（> 10万节点）| 专业图数据库，性能更好 |
| **缓存** | Redis | 热点数据缓存 | 提升查询性能 |
| **消息队列** | Celery | 大量异步任务 | 分布式任务处理 |

---

### 9.3 迁移方案

**从小规模到大规模**：

```
阶段 1（< 1万记忆）：
  - PostgreSQL + pgvector
  - 单机部署
  - 足够应对

阶段 2（1万-10万记忆）：
  - PostgreSQL 分库分表
  - Redis 缓存
  - 可能需要

阶段 3（> 10万记忆）：
  - 迁移到 Neo4j
  - 分布式部署
  - 建议迁移
```

**PostgreSQL → Neo4j 迁移脚本**：

```python
async def migrate_to_neo4j():
    """迁移到 Neo4j"""
    from neo4j import GraphDatabase
    
    driver = GraphDatabase.driver("bolt://localhost:7687")
    
    # 1. 迁移实体
    entities = await fetch_all_entities()
    with driver.session() as session:
        for entity in entities:
            session.run("""
                CREATE (e:Entity {
                    id: $id,
                    type: $type,
                    name: $name,
                    aliases: $aliases
                })
            """, **entity)
    
    # 2. 迁移关系
    relations = await fetch_all_relations()
    with driver.session() as session:
        for relation in relations:
            session.run("""
                MATCH (from:Entity {id: $from_id})
                MATCH (to:Entity {id: $to_id})
                CREATE (from)-[r:RELATION {
                    type: $relation_type,
                    weight: $weight
                }]->(to)
            """, **relation)
```

---

## 附录

### A. 完整建表 SQL

```sql
-- 1. 实体表
CREATE TABLE entities (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    type VARCHAR(20) NOT NULL,
    name VARCHAR(200) NOT NULL,
    aliases TEXT[],
    normalized_name VARCHAR(200),
    properties JSONB DEFAULT '{}',
    mention_count INT DEFAULT 1,
    last_mentioned_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    CONSTRAINT unique_entity UNIQUE (type, normalized_name)
);

-- 2. 关系表
CREATE TABLE relations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    from_entity_id UUID NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    to_entity_id UUID NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    relation_type VARCHAR(50) NOT NULL,
    properties JSONB DEFAULT '{}',
    weight FLOAT DEFAULT 1.0,
    status VARCHAR(20) DEFAULT 'active',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    CONSTRAINT unique_relation UNIQUE (from_entity_id, to_entity_id, relation_type)
);

-- 3. 记忆-实体关联表
CREATE TABLE memory_entities (
    memory_id UUID NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
    entity_id UUID NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    role VARCHAR(20) NOT NULL,
    confidence FLOAT DEFAULT 1.0,
    source VARCHAR(20) DEFAULT 'ner',
    context TEXT,
    PRIMARY KEY (memory_id, entity_id)
);

-- 4. 待确认队列
CREATE TABLE pending_confirmations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    type VARCHAR(20) NOT NULL,
    entity_id UUID REFERENCES entities(id),
    relation_id UUID REFERENCES relations(id),
    question TEXT NOT NULL,
    options JSONB NOT NULL,
    status VARCHAR(20) DEFAULT 'pending',
    user_response JSONB,
    priority INT DEFAULT 5,
    expires_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    responded_at TIMESTAMP
);

-- 索引
CREATE INDEX idx_entities_type ON entities(type);
CREATE INDEX idx_entities_name ON entities USING gin(to_tsvector('simple', name));
CREATE INDEX idx_entities_aliases ON entities USING gin(aliases);
CREATE INDEX idx_relations_from ON relations(from_entity_id);
CREATE INDEX idx_relations_to ON relations(to_entity_id);
CREATE INDEX idx_relations_type ON relations(relation_type);
CREATE INDEX idx_memory_entities_memory ON memory_entities(memory_id);
CREATE INDEX idx_memory_entities_entity ON memory_entities(entity_id);
CREATE INDEX idx_pending_status ON pending_confirmations(status);
CREATE INDEX idx_pending_priority ON pending_confirmations(priority DESC);
```

---

### B. 实施检查清单

#### Phase 1 检查清单

- [ ] 数据库表创建成功
- [ ] entities 表有数据
- [ ] relations 表有数据
- [ ] memory_entities 表有数据
- [ ] EntityExtractionService 测试通过
- [ ] 实体提取准确率 > 80%
- [ ] 实体链接召回率 > 90%

#### Phase 2 检查清单

- [ ] RelationInferenceService 测试通过
- [ ] NetworkBuilderService 测试通过
- [ ] 关系推理准确率 > 70%
- [ ] 网络构建时间 < 2s/记忆
- [ ] 支持并发处理

#### Phase 3 检查清单

- [ ] ConfirmationService 测试通过
- [ ] 飞书卡片集成成功
- [ ] 确认准确率 > 90%
- [ ] 用户反馈处理正确

#### Phase 4 检查清单

- [ ] NetworkRecallService 测试通过
- [ ] 集成到现有召回流程
- [ ] 召回准确率提升 > 10%
- [ ] 召回时间 < 2s
- [ ] 关联召回准确率 > 85%

#### Phase 5 检查清单

- [ ] 所有功能正常工作
- [ ] 性能达标
- [ ] 用户满意度 > 80%
- [ ] 文档完善

---

**文档版本**：v1.0
**最后更新**：2026-03-19
**维护者**：颓弟 AI Agent
