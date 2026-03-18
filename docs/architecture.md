# Memory Recall - 架构设计

> **文档说明**：本文档介绍 memory_recall 的系统架构、模块划分、数据流和技术栈选型。

---

## 系统架构图

```
┌─────────────────────────────────────────────────────────────────┐
│                        Memory Recall 系统                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │   文本输入   │  │   图片输入   │  │   语音输入   │          │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘          │
│         │                 │                 │                   │
│         └─────────────────┼─────────────────┘                   │
│                           │                                     │
│                           ▼                                     │
│         ┌─────────────────────────────────┐                    │
│         │        输入处理层               │                    │
│         ├─────────────────────────────────┤                    │
│         │ • 文本预处理（分词、清洗）      │                    │
│         │ • 图片预处理（OCR、EXIF、识别）│                    │
│         │ • 语音预处理（ASR 转文本）      │                    │
│         └─────────────┬───────────────────┘                    │
│                       │                                        │
│                       ▼                                        │
│         ┌─────────────────────────────────┐                    │
│         │        LLM 服务层               │                    │
│         ├─────────────────────────────────┤                    │
│         │ • 结构化信息提取                │                    │
│         │ • 智能询问判断                  │                    │
│         │ • 查询解析                      │                    │
│         │ • 召回排序                      │                    │
│         └─────────────┬───────────────────┘                    │
│                       │                                        │
│         ┌─────────────┴───────────────────┐                    │
│         │                                 │                    │
│         ▼                                 ▼                    │
│  ┌──────────────┐                ┌──────────────┐              │
│  │   记忆管理   │                │   召回服务   │              │
│  ├──────────────┤                ├──────────────┤              │
│  │ • 记忆存储   │                │ • 检索策略   │              │
│  │ • 索引更新   │                │ • 排序算法   │              │
│  │ • 人物管理   │                │ • 结果融合   │              │
│  │ • 人脸识别   │                │ • 主动推送   │              │
│  └──────┬───────┘                └──────┬───────┘              │
│         │                               │                      │
│         └───────────┬───────────────────┘                      │
│                     │                                          │
│                     ▼                                          │
│         ┌─────────────────────────────────┐                    │
│         │         存储层                  │                    │
│         ├─────────────────────────────────┤                    │
│         │ • PostgreSQL（关系型数据）      │                    │
│         │ • pgvector（向量索引）          │                    │
│         │ • 文件存储（附件、图片）        │                    │
│         └─────────────────────────────────┘                    │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 模块划分

### 1. 输入处理模块

**职责**：处理不同类型的输入，提取原始信息

```
输入处理模块
├── text_processor.py      # 文本处理
│   ├── TextPreprocessor   # 文本预处理（清洗、分词）
│   └── TextExtractor      # 文本信息提取
├── image_processor.py     # 图片处理
│   ├── EXIFExtractor      # EXIF 信息提取
│   ├── OCRProcessor       # OCR 文字识别
│   ├── SceneRecognizer    # 场景识别
│   └── FaceDetector       # 人脸检测与识别
└── audio_processor.py     # 语音处理（Phase 2）
    ├── ASRProcessor       # 语音转文本
    └── AudioFeatureExtractor # 音频特征提取
```

**核心类设计**：

```python
from abc import ABC, abstractmethod
from typing import Dict, Any
from dataclasses import dataclass

@dataclass
class ProcessedInput:
    """处理后的输入数据"""
    content: str                      # 主要内容
    metadata: Dict[str, Any]          # 元数据
    extracted_info: Dict[str, Any]    # 提取的信息
    attachments: list                 # 附件列表

class InputProcessor(ABC):
    """输入处理器基类"""
    
    @abstractmethod
    def process(self, raw_input: Any) -> ProcessedInput:
        """处理原始输入"""
        pass

class TextProcessor(InputProcessor):
    """文本处理器"""
    
    def process(self, raw_input: str) -> ProcessedInput:
        # 1. 文本清洗
        cleaned_text = self._clean_text(raw_input)
        
        # 2. 提取关键信息
        extracted_info = self._extract_info(cleaned_text)
        
        return ProcessedInput(
            content=cleaned_text,
            metadata={"source": "text", "length": len(cleaned_text)},
            extracted_info=extracted_info,
            attachments=[]
        )

class ImageProcessor(InputProcessor):
    """图片处理器"""
    
    def __init__(self, ocr_engine, scene_recognizer, face_detector):
        self.ocr_engine = ocr_engine
        self.scene_recognizer = scene_recognizer
        self.face_detector = face_detector
    
    def process(self, image_path: str) -> ProcessedInput:
        # 1. 提取 EXIF
        exif = self._extract_exif(image_path)
        
        # 2. OCR 识别
        ocr_result = self.ocr_engine.recognize(image_path)
        
        # 3. 场景识别
        scene = self.scene_recognizer.recognize(image_path)
        
        # 4. 人脸检测
        faces = self.face_detector.detect(image_path)
        
        # 5. 构建描述文本
        content = self._build_description(exif, ocr_result, scene, faces)
        
        return ProcessedInput(
            content=content,
            metadata={"source": "image", "exif": exif},
            extracted_info={
                "ocr": ocr_result,
                "scene": scene,
                "faces": faces
            },
            attachments=[image_path]
        )
```

### 2. 记忆管理模块

**职责**：记忆的存储、索引更新、人物管理

```
记忆管理模块
├── memory_store.py        # 记忆存储
│   ├── MemoryStore        # 记忆 CRUD 操作
│   └── MemoryValidator    # 记忆验证
├── index_manager.py       # 索引管理
│   ├── TimeIndex          # 时间索引
│   ├── LocationIndex      # 位置索引
│   ├── PeopleIndex        # 人物索引
│   └── TagsIndex          # 标签索引
├── person_manager.py      # 人物管理
│   ├── PersonProfile      # 人物档案
│   └── PersonMatcher      # 人物匹配
└── face_manager.py        # 人脸管理
    ├── FaceFeatureStore   # 人脸特征存储
    └── FaceRecognizer     # 人脸识别
```

**核心类设计**：

```python
from typing import List, Optional
from datetime import datetime
import uuid

class MemoryStore:
    """记忆存储"""
    
    def __init__(self, db_connection):
        self.db = db_connection
    
    def create(self, memory_data: dict) -> str:
        """创建记忆"""
        memory_id = f"mem_{uuid.uuid4().hex[:12]}"
        memory_data['id'] = memory_id
        memory_data['created_at'] = datetime.utcnow().isoformat()
        
        # 插入数据库
        self.db.insert_memory(memory_data)
        
        # 更新索引
        self._update_indexes(memory_data)
        
        return memory_id
    
    def get(self, memory_id: str) -> Optional[dict]:
        """获取记忆"""
        return self.db.get_memory(memory_id)
    
    def update(self, memory_id: str, updates: dict) -> bool:
        """更新记忆"""
        # 更新数据库
        success = self.db.update_memory(memory_id, updates)
        
        # 重新索引
        if success:
            memory = self.get(memory_id)
            self._rebuild_index(memory)
        
        return success
    
    def delete(self, memory_id: str) -> bool:
        """删除记忆"""
        # 获取记忆（用于删除索引）
        memory = self.get(memory_id)
        
        # 删除数据库记录
        success = self.db.delete_memory(memory_id)
        
        # 删除索引
        if success and memory:
            self._remove_from_indexes(memory)
        
        return success

class IndexManager:
    """索引管理器"""
    
    def __init__(self, db_connection):
        self.db = db_connection
        self.time_index = TimeIndex(db_connection)
        self.location_index = LocationIndex(db_connection)
        self.people_index = PeopleIndex(db_connection)
        self.tags_index = TagsIndex(db_connection)
    
    def update_all(self, memory: dict):
        """更新所有索引"""
        self.time_index.update(memory)
        self.location_index.update(memory)
        self.people_index.update(memory)
        self.tags_index.update(memory)
    
    def query_by_time(self, start: datetime, end: datetime) -> List[str]:
        """时间范围查询"""
        return self.time_index.query(start, end)
    
    def query_by_location(self, location: str) -> List[str]:
        """位置查询"""
        return self.location_index.query(location)
    
    def query_by_person(self, person_name: str) -> List[str]:
        """人物查询"""
        return self.people_index.query(person_name)
    
    def query_by_tags(self, tags: List[str]) -> List[str]:
        """标签查询"""
        return self.tags_index.query(tags)
```

### 3. 召回服务模块

**职责**：处理召回请求、检索策略、排序算法

```
召回服务模块
├── recall_service.py      # 召回服务
│   ├── RecallService      # 召回服务主类
│   ├── QueryParser        # 查询解析
│   └── ResultMerger       # 结果融合
├── retrieval_strategy.py  # 检索策略
│   ├── ExactFilter        # 精确过滤
│   ├── SemanticSearch     # 语义搜索
│   └── HybridRetrieval    # 混合检索
└── ranking.py             # 排序算法
    ├── MultiFactorRanking # 多因子排序
    ├── TimeDecay          # 时间衰减
    └── MMR                # 最大边际相关性
```

**核心类设计**：

```python
from typing import List, Dict
from dataclasses import dataclass

@dataclass
class RecallRequest:
    """召回请求"""
    query: str                         # 查询文本
    time_range: Optional[tuple]        # 时间范围
    location: Optional[str]            # 位置
    people: Optional[List[str]]        # 人物
    tags: Optional[List[str]]          # 标签
    top_k: int = 10                    # 返回数量

@dataclass
class RecallResult:
    """召回结果"""
    memory_id: str
    memory: dict
    score: float
    matched_fields: List[str]

class RecallService:
    """召回服务"""
    
    def __init__(self, memory_store, index_manager, llm_service, embedding_service):
        self.memory_store = memory_store
        self.index_manager = index_manager
        self.llm_service = llm_service
        self.embedding_service = embedding_service
    
    def recall(self, request: RecallRequest) -> List[RecallResult]:
        """执行召回"""
        # 1. 解析查询
        parsed_query = self._parse_query(request.query)
        
        # 2. 多索引检索
        candidate_ids = self._retrieve_candidates(request, parsed_query)
        
        # 3. 加载记忆数据
        memories = [self.memory_store.get(mid) for mid in candidate_ids]
        memories = [m for m in memories if m is not None]
        
        # 4. 语义相似度计算
        query_embedding = self.embedding_service.embed(request.query)
        memory_embeddings = [self._get_memory_embedding(m) for m in memories]
        
        # 5. 多因子排序
        ranked_results = self._rank(memories, query_embedding, memory_embeddings)
        
        # 6. 返回 Top-K
        return ranked_results[:request.top_k]
    
    def _parse_query(self, query: str) -> dict:
        """使用 LLM 解析查询"""
        prompt = self._build_parse_prompt(query)
        return self.llm_service.extract(prompt)
    
    def _retrieve_candidates(self, request: RecallRequest, parsed_query: dict) -> set:
        """多索引检索候选"""
        candidate_sets = []
        
        # 时间索引
        if request.time_range:
            ids = self.index_manager.query_by_time(*request.time_range)
            candidate_sets.append(set(ids))
        
        # 位置索引
        if request.location:
            ids = self.index_manager.query_by_location(request.location)
            candidate_sets.append(set(ids))
        
        # 人物索引
        if request.people:
            ids = self.index_manager.query_by_person(request.people[0])
            candidate_sets.append(set(ids))
        
        # 标签索引
        if request.tags:
            ids = self.index_manager.query_by_tags(request.tags)
            candidate_sets.append(set(ids))
        
        # 融合候选集（取并集）
        if candidate_sets:
            return set.union(*candidate_sets)
        else:
            # 无明确条件时，返回最近记忆
            return set(self.index_manager.time_index.get_recent(100))
    
    def _rank(self, memories: List[dict], query_embedding: List[float], 
              memory_embeddings: List[List[float]]) -> List[RecallResult]:
        """多因子排序"""
        results = []
        
        for i, memory in enumerate(memories):
            # 计算各项得分
            time_score = self._calculate_time_score(memory)
            semantic_score = self._calculate_semantic_score(query_embedding, memory_embeddings[i])
            access_score = self._calculate_access_score(memory)
            
            # 加权求和
            total_score = (
                0.3 * time_score +
                0.3 * semantic_score +
                0.1 * access_score
            )
            
            results.append(RecallResult(
                memory_id=memory['id'],
                memory=memory,
                score=total_score,
                matched_fields=[]
            ))
        
        # 按分数排序
        results.sort(key=lambda x: x.score, reverse=True)
        
        return results
```

### 4. LLM 服务模块

**职责**：与大模型交互，处理结构化提取、查询解析、智能询问

```
LLM 服务模块
├── llm_service.py         # LLM 服务
│   ├── LLMService         # LLM 调用封装
│   ├── StructuredExtractor # 结构化提取
│   └── QueryParser        # 查询解析
└── prompts/               # Prompt 模板
    ├── extract_memory.txt # 记忆提取
    ├── parse_query.txt    # 查询解析
    └── judge_inquiry.txt  # 询问判断
```

**核心类设计**：

```python
import json
from typing import Dict, Any

class LLMService:
    """LLM 服务"""
    
    def __init__(self, api_key: str, model: str = "gpt-4"):
        self.api_key = api_key
        self.model = model
    
    def extract(self, prompt: str) -> Dict[str, Any]:
        """调用 LLM 提取结构化信息"""
        # 调用 OpenAI API
        response = self._call_api(prompt)
        
        # 解析 JSON
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            return self._parse_unstructured(response)
    
    def extract_memory(self, content: str, metadata: dict = None) -> dict:
        """提取记忆结构化信息"""
        prompt = self._build_extract_prompt(content, metadata)
        return self.extract(prompt)
    
    def parse_query(self, query: str) -> dict:
        """解析用户查询"""
        prompt = self._build_parse_prompt(query)
        return self.extract(prompt)
    
    def judge_inquiry(self, field_name: str, field_value: Any, context: str) -> bool:
        """判断是否需要询问"""
        prompt = self._build_inquiry_prompt(field_name, field_value, context)
        result = self.extract(prompt)
        return result.get('need_inquiry', False)
```

---

## 数据流设计

### 1. 记忆写入流程

```
用户输入（文本/图片/语音）
    ↓
输入处理模块
    ├─ 文本：清洗、分词
    ├─ 图片：OCR、EXIF、场景识别、人脸检测
    └─ 语音：ASR 转文本
    ↓
LLM 服务模块
    ├─ 结构化信息提取
    └─ 智能询问判断
    ↓
[需要询问？]
    ├─ 是 → 返回询问问题 → 用户确认 → 继续流程
    └─ 否 → 继续
    ↓
记忆管理模块
    ├─ 存储到数据库
    ├─ 更新索引
    └─ 更新人物档案
    ↓
[有图片且有人脸？]
    └─ 是 → 人脸识别 → 关联人物档案
    ↓
返回记忆 ID
```

### 2. 记忆召回流程

```
用户查询（"上周和老同学在咖啡店聊了什么"）
    ↓
召回服务模块
    ├─ 查询解析（提取时间、人物、位置）
    └─ 构建召回请求
    ↓
多索引检索
    ├─ 时间索引：上周的时间范围
    ├─ 人物索引：老同学
    └─ 位置索引：咖啡店
    ↓
结果融合
    ├─ 取交集（精确匹配）
    └─ 取并集（宽松匹配）
    ↓
加载记忆数据
    ↓
语义相似度计算
    ↓
多因子排序
    ├─ 时间相关性（0.3）
    ├─ 关键词匹配度（0.3）
    ├─ 语义相似度（0.3）
    └─ 访问频率（0.1）
    ↓
返回 Top-K 结果
```

---

## 技术栈选型

> **详细技术选型请查看**：[tech-stack.md](./tech-stack.md)

### Phase 1（MVP）- 已确认

| 组件 | 技术选择 | 原因 |
|------|---------|------|
| **编程语言** | Python 3.10+ | 丰富的 AI 生态 |
| **数据库** | PostgreSQL 14+ + pgvector | 关系型 + 向量支持，统一存储 |
| **LLM** | doubao-seed-2-0-pro-260215（火山引擎） | 性价比高，支持多模态 |
| **Embedding** | doubao-embedding-vision-251215（火山引擎） | 性价比高，支持多模态，1024 维向量 |
| **人脸识别** | face_recognition（本地） | 免费隐私，离线可用，128 维特征向量 |
| **OCR** | PaddleOCR | 中文识别准确 |
| **Web 框架** | FastAPI | 高性能、异步 |
| **任务队列** | Celery | 异步任务处理 |

**火山引擎统一方案优势**：
- LLM 和 Embedding 使用同一平台，统一 API 管理
- 简化认证和计费流程
- 月成本约 ¥0.8（LLM）+ ¥0.7（Embedding）

**人脸识别本地方案优势**：
- 完全免费，无需 API 调用费
- 隐私保护，数据不出本地
- 离线可用

### Phase 2（生产）

| 组件 | 技术选择 | 原因 |
|------|---------|------|
| **向量数据库** | Qdrant（可选） | 专业向量数据库（如需更高性能） |
| **缓存** | Redis | 高性能缓存 |
| **消息队列** | RabbitMQ | 可靠消息传递 |
| **容器化** | Docker + K8s | 易于部署和扩展 |
| **监控** | Prometheus + Grafana | 全方位监控 |
| **日志** | ELK Stack | 集中式日志管理 |

---

## 部署架构

### 单机部署（MVP）

```
┌─────────────────────────────────────────┐
│            单机部署架构                  │
├─────────────────────────────────────────┤
│                                         │
│  ┌─────────────┐      ┌──────────────┐ │
│  │   FastAPI   │──────│ PostgreSQL   │ │
│  │   (Web)     │      │ + pgvector   │ │
│  └─────────────┘      └──────────────┘ │
│         │                              │
│         │                              │
│  ┌─────────────┐                       │
│  │   Celery    │                       │
│  │  (Worker)   │                       │
│  └─────────────┘                       │
│         │                              │
│         │                              │
│  ┌─────────────┐      ┌──────────────┐ │
│  │   Redis     │──────│  文件存储    │ │
│  │  (Queue)    │      │  (本地磁盘)  │ │
│  └─────────────┘      └──────────────┘ │
│                                         │
└─────────────────────────────────────────┘
```

### 分布式部署（生产）

```
┌──────────────────────────────────────────────────────────────┐
│                   分布式部署架构                              │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌─────────────┐   ┌─────────────┐   ┌─────────────┐        │
│  │   Nginx     │   │   Nginx     │   │   Nginx     │        │
│  │  (LB)       │   │  (LB)       │   │  (LB)       │        │
│  └──────┬──────┘   └──────┬──────┘   └──────┬──────┘        │
│         │                 │                 │                │
│         └─────────────────┼─────────────────┘                │
│                           │                                  │
│                           ▼                                  │
│         ┌─────────────────────────────────┐                 │
│         │      API Gateway (Kong)         │                 │
│         └─────────────┬───────────────────┘                 │
│                       │                                     │
│         ┌─────────────┼─────────────┐                       │
│         │             │             │                       │
│         ▼             ▼             ▼                       │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐                  │
│  │ FastAPI  │  │ FastAPI  │  │ FastAPI  │                  │
│  │ Pod 1    │  │ Pod 2    │  │ Pod 3    │                  │
│  └──────────┘  └──────────┘  └──────────┘                  │
│         │             │             │                       │
│         └─────────────┼─────────────┘                       │
│                       │                                     │
│         ┌─────────────┼─────────────┐                       │
│         │             │             │                       │
│         ▼             ▼             ▼                       │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐                  │
│  │ Celery   │  │ Celery   │  │ Celery   │                  │
│  │ Worker 1 │  │ Worker 2 │  │ Worker 3 │                  │
│  └──────────┘  └──────────┘  └──────────┘                  │
│                                                              │
│  ┌──────────────────────────────────────────────┐           │
│  │              数据层                           │           │
│  ├──────────────────────────────────────────────┤           │
│  │                                              │           │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  │           │
│  │  │PostgreSQL│  │ Qdrant   │  │  Redis   │  │           │
│  │  │ Cluster  │  │ Cluster  │  │ Cluster  │  │           │
│  │  └──────────┘  └──────────┘  └──────────┘  │           │
│  │                                              │           │
│  │  ┌──────────┐  ┌──────────┐                 │           │
│  │  │RabbitMQ  │  │   S3     │                 │           │
│  │  │ Cluster  │  │ Storage  │                 │           │
│  │  └──────────┘  └──────────┘                 │           │
│  │                                              │           │
│  └──────────────────────────────────────────────┘           │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

---

## 扩展性设计

### 水平扩展

- **API 服务**：无状态，可水平扩展
- **Worker**：可增加 worker 数量
- **数据库**：PostgreSQL 支持读写分离
- **向量库**：Qdrant 支持分片

### 插件化设计

```
plugins/
├── input_processors/      # 输入处理器插件
│   ├── text.py
│   ├── image.py
│   └── audio.py
├── extractors/            # 信息提取器插件
│   ├── time_extractor.py
│   ├── location_extractor.py
│   └── people_extractor.py
└── recall_strategies/     # 召回策略插件
    ├── exact_match.py
    ├── semantic_search.py
    └── hybrid.py
```

---

*文档版本：v0.1*  
*最后更新：2026-03-19*  
*维护者：颓弟*
