# Memory Recall - 召回机制

> **文档说明**：本文档详细说明记忆召回的触发方式、查询解析、检索策略、排序算法和结果呈现。

---

## 召回触发方式

### 1. 主动搜索

**定义**：用户主动发起查询请求

**触发方式**：
- 用户输入查询文本
- 用户指定时间范围
- 用户指定人物/位置/标签

**示例**：
```
用户查询："上周和老同学在咖啡店聊了什么"
    ↓
查询解析
    ├─ 时间范围：上周
    ├─ 人物：老同学
    └─ 位置：咖啡店
    ↓
多索引检索
    ↓
返回结果
```

### 2. 被动推送

**定义**：系统基于上下文主动推送相关记忆

**触发条件**：

| 触发场景 | 推送策略 | 示例 |
|---------|---------|------|
| **关键词触发** | 检测到关键词，推送相关记忆 | 提到"咖啡店"时推送在咖啡店的记忆 |
| **人物触发** | 提到人物，推送相关记忆 | 提到"张三"时推送与张三相关的记忆 |
| **位置触发** | 检测位置信息，推送相关记忆 | 在咖啡店时推送在咖啡店的记忆 |
| **时间触发** | 特定时间点，推送相关记忆 | 每年生日推送生日相关记忆 |

**实现方式**：

```python
class PassiveRecallService:
    """被动召回服务"""
    
    def __init__(self, memory_store, index_manager, llm_service):
        self.memory_store = memory_store
        self.index_manager = index_manager
        self.llm_service = llm_service
    
    def on_context_change(self, context: dict) -> list:
        """上下文变化时触发召回"""
        # 提取关键词
        keywords = self._extract_keywords(context)
        
        # 检索相关记忆
        memory_ids = set()
        for keyword in keywords:
            ids = self.index_manager.query_by_keyword(keyword)
            memory_ids.update(ids)
        
        # 加载记忆
        memories = [self.memory_store.get(mid) for mid in memory_ids]
        
        # 相关性评分
        scored_memories = self._score_relevance(memories, context)
        
        # 返回 Top-K
        return sorted(scored_memories, key=lambda x: x['score'], reverse=True)[:5]
    
    def _extract_keywords(self, context: dict) -> list:
        """从上下文提取关键词"""
        keywords = []
        
        # 人物
        if context.get('people'):
            keywords.extend(context['people'])
        
        # 位置
        if context.get('location'):
            keywords.append(context['location'])
        
        # 文本关键词
        if context.get('text'):
            extracted = self.llm_service.extract_keywords(context['text'])
            keywords.extend(extracted)
        
        return keywords
```

### 3. 定期回顾

**定义**：系统定期推送重要记忆

**推送策略**：

| 周期 | 推送内容 | 示例 |
|------|---------|------|
| **每日回顾** | 昨天的重要记忆 | "昨天你完成了项目文档" |
| **每周回顾** | 本周的重要事件 | "本周你参加了 3 次会议" |
| **每月回顾** | 本月的重要时刻 | "这个月你认识了很多新朋友" |
| **年度回顾** | 年度精彩瞬间 | "今年最开心的事..." |
| **纪念日提醒** | 特殊日期的相关记忆 | "去年的今天，你在咖啡店遇到了老同学" |

**实现方式**：

```python
from datetime import datetime, timedelta
from typing import List

class PeriodicRecallService:
    """定期回顾服务"""
    
    def __init__(self, memory_store, index_manager):
        self.memory_store = memory_store
        self.index_manager = index_manager
    
    def daily_recall(self) -> List[dict]:
        """每日回顾：昨天的重要记忆"""
        yesterday = datetime.now() - timedelta(days=1)
        start = yesterday.replace(hour=0, minute=0, second=0)
        end = yesterday.replace(hour=23, minute=59, second=59)
        
        # 获取昨天的记忆
        memories = self.memory_store.query_by_time(start, end)
        
        # 筛选重要记忆
        important_memories = [m for m in memories if m.get('importance_score', 0) > 0.7]
        
        return important_memories[:10]
    
    def anniversary_recall(self, date: datetime) -> List[dict]:
        """纪念日回顾：往年同一天的记忆"""
        memories = []
        
        # 查询过去 5 年的同一天
        for year in range(1, 6):
            target_date = date.replace(year=date.year - year)
            start = target_date.replace(hour=0, minute=0, second=0)
            end = target_date.replace(hour=23, minute=59, second=59)
            
            year_memories = self.memory_store.query_by_time(start, end)
            memories.extend(year_memories)
        
        return memories[:10]
```

---

## 查询解析

### 1. 查询解析流程

```
用户查询："上周和老同学在咖啡店聊了什么"
    ↓
LLM 查询解析
    ├─ 提取时间范围：上周
    ├─ 提取人物：老同学
    ├─ 提取位置：咖啡店
    ├─ 提取关键词：聊
    └─ 提取意图：查询事件内容
    ↓
生成结构化查询
    ↓
传递给召回服务
```

### 2. 查询解析 Prompt

```markdown
# 查询解析

你是一个查询解析助手。请从用户查询中提取结构化信息。

## 用户查询
{query}

## 解析规则

### 1. 时间范围（time_range）
- 识别时间表述
- 转换为具体的开始和结束时间
- 支持的时间表述：
  - 相对时间：今天、昨天、上周、上个月
  - 具体日期：2026-03-19、3 月 19 日
  - 时间范围：最近一周、过去三天
  - 特殊日期：生日、纪念日

### 2. 人物（people）
- 识别人物名称或称呼
- 判断是否为已知人物
- 支持的表述：
  - 人名：张三、李四
  - 称呼：老同学、同事、朋友
  - 关系：大学同学、前同事

### 3. 位置（location）
- 识别位置信息
- 支持的表述：
  - 具体位置：星巴克（国贸店）
  - 泛指位置：咖啡店、办公室
  - 城市地点：北京、上海

### 4. 关键词（keywords）
- 提取查询中的关键词
- 用于全文搜索

### 5. 查询意图（intent）
- 识别用户意图
- 支持的意图：
  - query_content：查询内容
  - query_summary：查询摘要
  - query_people：查询人物
  - query_location：查询位置

## 输出格式

```json
{
  "time_range": {
    "start": "2026-03-12T00:00:00+08:00",
    "end": "2026-03-19T23:59:59+08:00",
    "original_text": "上周"
  },
  "people": ["老同学"],
  "location": "咖啡店",
  "keywords": ["聊"],
  "intent": "query_content",
  "filters": {
    "tags": [],
    "emotion": null
  }
}
```

## 示例

### 示例 1
查询："上周和老同学在咖啡店聊了什么"

输出：
```json
{
  "time_range": {
    "start": "2026-03-12T00:00:00+08:00",
    "end": "2026-03-19T23:59:59+08:00",
    "original_text": "上周"
  },
  "people": ["老同学"],
  "location": "咖啡店",
  "keywords": ["聊"],
  "intent": "query_content",
  "filters": {}
}
```

### 示例 2
查询："最近在哪些地方见过张三"

输出：
```json
{
  "time_range": {
    "start": "2026-03-01T00:00:00+08:00",
    "end": "2026-03-19T23:59:59+08:00",
    "original_text": "最近"
  },
  "people": ["张三"],
  "location": null,
  "keywords": [],
  "intent": "query_location",
  "filters": {}
}
```

### 示例 3
查询："去年最开心的事"

输出：
```json
{
  "time_range": {
    "start": "2025-01-01T00:00:00+08:00",
    "end": "2025-12-31T23:59:59+08:00",
    "original_text": "去年"
  },
  "people": [],
  "location": null,
  "keywords": [],
  "intent": "query_content",
  "filters": {
    "emotion": "开心"
  }
}
```
```

### 3. 实现代码

```python
from datetime import datetime, timedelta
import json

class QueryParser:
    """查询解析器"""
    
    def __init__(self, llm_service):
        self.llm = llm_service
    
    def parse(self, query: str) -> dict:
        """解析查询"""
        prompt = self._build_parse_prompt(query)
        result = self.llm.extract(prompt)
        
        # 处理时间范围
        if result.get('time_range'):
            result['time_range'] = self._process_time_range(result['time_range'])
        
        return result
    
    def _build_parse_prompt(self, query: str) -> str:
        """构建解析 Prompt"""
        return f"""
你是一个查询解析助手。请从用户查询中提取结构化信息。

## 用户查询
{query}

## 输出格式
```json
{{
  "time_range": {{"start": "...", "end": "...", "original_text": "..."}},
  "people": ["..."],
  "location": "...",
  "keywords": ["..."],
  "intent": "query_content"
}}
```

请只输出 JSON，不要其他内容。
"""
    
    def _process_time_range(self, time_range: dict) -> dict:
        """处理时间范围"""
        now = datetime.now()
        original_text = time_range.get('original_text', '')
        
        if not time_range.get('start'):
            # 根据原始文本推断时间范围
            if '今天' in original_text:
                time_range['start'] = now.replace(hour=0, minute=0, second=0).isoformat()
                time_range['end'] = now.replace(hour=23, minute=59, second=59).isoformat()
            elif '昨天' in original_text:
                yesterday = now - timedelta(days=1)
                time_range['start'] = yesterday.replace(hour=0, minute=0, second=0).isoformat()
                time_range['end'] = yesterday.replace(hour=23, minute=59, second=59).isoformat()
            elif '上周' in original_text:
                week_start = now - timedelta(days=now.weekday() + 7)
                time_range['start'] = week_start.replace(hour=0, minute=0, second=0).isoformat()
                time_range['end'] = (week_start + timedelta(days=6)).replace(hour=23, minute=59, second=59).isoformat()
        
        return time_range
```

---

## 检索策略

### 1. 精确过滤

**适用场景**：明确的时间、位置、人物条件

**实现方式**：

```python
class ExactFilter:
    """精确过滤"""
    
    def __init__(self, memory_store):
        self.memory_store = memory_store
    
    def filter_by_time(self, start: datetime, end: datetime) -> List[str]:
        """按时间范围过滤"""
        return self.memory_store.query_ids("""
            SELECT id FROM memories
            WHERE time_value >= %s AND time_value <= %s
            AND status = 'active'
        """, (start, end))
    
    def filter_by_location(self, location: str) -> List[str]:
        """按位置过滤"""
        return self.memory_store.query_ids("""
            SELECT id FROM memories
            WHERE to_tsvector('simple', location_name) @@ to_tsquery('simple', %s)
            AND status = 'active'
        """, (location,))
    
    def filter_by_person(self, person_name: str) -> List[str]:
        """按人物过滤"""
        return self.memory_store.query_ids("""
            SELECT id FROM memories
            WHERE people @> %s::jsonb
            AND status = 'active'
        """, (json.dumps([{"name": person_name}]),))
    
    def filter_by_tags(self, tags: List[str]) -> List[str]:
        """按标签过滤"""
        return self.memory_store.query_ids("""
            SELECT id FROM memories
            WHERE tags ?| %s
            AND status = 'active'
        """, (tags,))
```

### 2. 语义搜索

**适用场景**：模糊查询、概念搜索

**实现方式**：

```python
import numpy as np
from typing import List, Tuple

class SemanticSearch:
    """语义搜索"""
    
    def __init__(self, memory_store, embedding_service):
        self.memory_store = memory_store
        self.embedding_service = embedding_service
    
    def search(self, query: str, top_k: int = 10) -> List[Tuple[str, float]]:
        """语义搜索"""
        # 生成查询向量
        query_embedding = self.embedding_service.embed(query)
        
        # 向量相似度搜索
        results = self.memory_store.query("""
            SELECT id, 1 - (embedding <=> %s::vector) as similarity
            FROM memories
            WHERE status = 'active' AND embedding IS NOT NULL
            ORDER BY embedding <=> %s::vector
            LIMIT %s
        """, (query_embedding, query_embedding, top_k * 2))
        
        return [(row['id'], row['similarity']) for row in results]
    
    def search_by_embedding(self, query_embedding: List[float], top_k: int = 10) -> List[Tuple[str, float]]:
        """通过向量搜索"""
        results = self.memory_store.query("""
            SELECT id, 1 - (embedding <=> %s::vector) as similarity
            FROM memories
            WHERE status = 'active' AND embedding IS NOT NULL
            ORDER BY embedding <=> %s::vector
            LIMIT %s
        """, (query_embedding, query_embedding, top_k))
        
        return [(row['id'], row['similarity']) for row in results]
```

### 3. 混合检索

**适用场景**：复杂查询，多条件组合

**实现方式**：

```python
class HybridRetrieval:
    """混合检索"""
    
    def __init__(self, memory_store, index_manager, embedding_service):
        self.memory_store = memory_store
        self.index_manager = index_manager
        self.embedding_service = embedding_service
        self.exact_filter = ExactFilter(memory_store)
        self.semantic_search = SemanticSearch(memory_store, embedding_service)
    
    def retrieve(self, parsed_query: dict, top_k: int = 20) -> List[str]:
        """混合检索"""
        candidate_sets = []
        
        # 1. 精确过滤
        if parsed_query.get('time_range'):
            ids = self.exact_filter.filter_by_time(
                parsed_query['time_range']['start'],
                parsed_query['time_range']['end']
            )
            candidate_sets.append(set(ids))
        
        if parsed_query.get('location'):
            ids = self.exact_filter.filter_by_location(parsed_query['location'])
            candidate_sets.append(set(ids))
        
        if parsed_query.get('people'):
            for person in parsed_query['people']:
                ids = self.exact_filter.filter_by_person(person)
                candidate_sets.append(set(ids))
        
        if parsed_query.get('keywords'):
            # 全文搜索
            ids = self._fulltext_search(parsed_query['keywords'])
            candidate_sets.append(set(ids))
        
        # 2. 融合候选集
        if candidate_sets:
            # 取交集（精确匹配）
            candidates = set.intersection(*candidate_sets)
            
            # 如果交集为空，取并集（宽松匹配）
            if not candidates:
                candidates = set.union(*candidate_sets)
        else:
            candidates = set()
        
        # 3. 语义搜索（补充）
        if parsed_query.get('keywords') or len(candidates) < top_k:
            semantic_results = self.semantic_search.search(
                ' '.join(parsed_query.get('keywords', []) + [parsed_query.get('location', '')]),
                top_k=50
            )
            semantic_ids = [id for id, _ in semantic_results]
            candidates.update(semantic_ids)
        
        return list(candidates)[:top_k]
    
    def _fulltext_search(self, keywords: List[str]) -> List[str]:
        """全文搜索"""
        query = ' | '.join(keywords)
        return self.memory_store.query_ids("""
            SELECT id FROM memories
            WHERE to_tsvector('simple', content) @@ to_tsquery('simple', %s)
            AND status = 'active'
            LIMIT 100
        """, (query,))
```

---

## 排序算法

### 1. 多因子排序

**公式**：

```
score = w1 × 时间相关性
      + w2 × 关键词匹配度
      + w3 × 语义相似度
      + w4 × 访问频率
```

**权重配置**：

| 因子 | 权重 | 说明 |
|------|------|------|
| 时间相关性 | 0.3 | 近期记忆优先 |
| 关键词匹配度 | 0.3 | 精确匹配优先 |
| 语义相似度 | 0.3 | 语义相关优先 |
| 访问频率 | 0.1 | 常访问优先 |

**实现方式**：

```python
from datetime import datetime, timedelta
import math

class MultiFactorRanking:
    """多因子排序"""
    
    def __init__(self, weights: dict = None):
        self.weights = weights or {
            'time_relevance': 0.3,
            'keyword_match': 0.3,
            'semantic_similarity': 0.3,
            'access_frequency': 0.1
        }
    
    def rank(self, memories: List[dict], query_context: dict) -> List[dict]:
        """排序"""
        scored_memories = []
        
        for memory in memories:
            # 计算各项得分
            time_score = self._calculate_time_score(memory, query_context)
            keyword_score = self._calculate_keyword_score(memory, query_context)
            semantic_score = self._calculate_semantic_score(memory, query_context)
            access_score = self._calculate_access_score(memory)
            
            # 加权求和
            total_score = (
                self.weights['time_relevance'] * time_score +
                self.weights['keyword_match'] * keyword_score +
                self.weights['semantic_similarity'] * semantic_score +
                self.weights['access_frequency'] * access_score
            )
            
            scored_memories.append({
                'memory': memory,
                'score': total_score,
                'scores': {
                    'time': time_score,
                    'keyword': keyword_score,
                    'semantic': semantic_score,
                    'access': access_score
                }
            })
        
        # 按分数排序
        scored_memories.sort(key=lambda x: x['score'], reverse=True)
        
        return scored_memories
    
    def _calculate_time_score(self, memory: dict, query_context: dict) -> float:
        """计算时间相关性得分"""
        if not memory.get('time') or not memory['time'].get('value'):
            return 0.5
        
        memory_time = datetime.fromisoformat(memory['time']['value'].replace('Z', '+00:00'))
        now = datetime.now(memory_time.tzinfo)
        
        # 时间衰减：越近的记忆得分越高
        days_ago = (now - memory_time).days
        decay_rate = 0.1
        
        score = math.exp(-decay_rate * days_ago)
        return min(score, 1.0)
    
    def _calculate_keyword_score(self, memory: dict, query_context: dict) -> float:
        """计算关键词匹配度得分"""
        keywords = query_context.get('keywords', [])
        if not keywords:
            return 0.5
        
        content = memory.get('content', '')
        matches = sum(1 for kw in keywords if kw.lower() in content.lower())
        
        return matches / len(keywords) if keywords else 0
    
    def _calculate_semantic_score(self, memory: dict, query_context: dict) -> float:
        """计算语义相似度得分"""
        # 如果有预计算的相似度，直接使用
        if 'semantic_score' in memory:
            return memory['semantic_score']
        
        # 否则返回默认值
        return 0.5
    
    def _calculate_access_score(self, memory: dict) -> float:
        """计算访问频率得分"""
        access_count = memory.get('access_count', 0)
        
        # 对数归一化
        score = math.log(1 + access_count) / math.log(1 + 100)
        return min(score, 1.0)
```

### 2. 时间衰减

**公式**：

```
time_score = exp(-decay_rate × days_ago)
```

**参数说明**：
- `decay_rate`：衰减率，默认 0.1
- `days_ago`：距离现在的天数

**示例**：

| 天数 | 衰减率 0.1 | 衰减率 0.05 |
|------|-----------|------------|
| 1 天 | 0.905 | 0.951 |
| 7 天 | 0.497 | 0.705 |
| 30 天 | 0.050 | 0.223 |
| 90 天 | 0.000 | 0.011 |

### 3. MMR（最大边际相关性）

**目的**：在保证相关性的同时，增加结果多样性

**公式**：

```
MMR = λ × Sim(q, d) - (1 - λ) × max(Sim(d, d'))
```

**参数说明**：
- `λ`：平衡参数（0-1），默认 0.7
- `Sim(q, d)`：查询与文档的相似度
- `Sim(d, d')`：文档与已选文档的最大相似度

**实现方式**：

```python
class MMR:
    """最大边际相关性"""
    
    def __init__(self, lambda_param: float = 0.7):
        self.lambda_param = lambda_param
    
    def diversify(self, candidates: List[dict], query_embedding: List[float], 
                  top_k: int = 10) -> List[dict]:
        """多样化排序"""
        selected = []
        remaining = candidates.copy()
        
        while len(selected) < top_k and remaining:
            max_mmr = -float('inf')
            best_candidate = None
            best_idx = -1
            
            for idx, candidate in enumerate(remaining):
                # 计算与查询的相似度
                relevance = self._cosine_similarity(
                    query_embedding, 
                    candidate['embedding']
                )
                
                # 计算与已选文档的最大相似度
                if selected:
                    max_sim = max(
                        self._cosine_similarity(candidate['embedding'], s['embedding'])
                        for s in selected
                    )
                else:
                    max_sim = 0
                
                # 计算 MMR
                mmr = self.lambda_param * relevance - (1 - self.lambda_param) * max_sim
                
                if mmr > max_mmr:
                    max_mmr = mmr
                    best_candidate = candidate
                    best_idx = idx
            
            if best_candidate:
                selected.append(best_candidate)
                remaining.pop(best_idx)
        
        return selected
    
    def _cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """计算余弦相似度"""
        import numpy as np
        vec1 = np.array(vec1)
        vec2 = np.array(vec2)
        return np.dot(vec1, vec2) / (np.linalg.norm(vec1) * np.linalg.norm(vec2))
```

---

## 结果呈现

### 1. 结果格式

```json
{
  "query": "上周和老同学在咖啡店聊了什么",
  "total": 5,
  "results": [
    {
      "id": "mem_abc123",
      "content": "今天在咖啡店遇到老同学，聊了很久关于创业的想法",
      "time": {
        "value": "2026-03-15T14:30:00+08:00",
        "display": "3月15日 周五 14:30"
      },
      "location": {
        "name": "星巴克（国贸店）",
        "display": "星巴克（国贸店）"
      },
      "people": [
        {
          "name": "张三",
          "display": "张三（老同学）"
        }
      ],
      "tags": ["社交", "创业", "聊天"],
      "score": 0.92,
      "matched_fields": ["时间", "人物", "位置"],
      "highlights": [
        "在<span class='highlight'>咖啡店</span>遇到<span class='highlight'>老同学</span>",
        "聊了很久关于<span class='highlight'>创业</span>的想法"
      ]
    }
  ],
  "summary": "找到 5 条相关记忆，主要涉及创业话题",
  "suggestions": [
    "查看更多关于创业的记忆",
    "查看与张三相关的其他记忆"
  ]
}
```

### 2. 高亮显示

**实现方式**：

```python
class ResultHighlighter:
    """结果高亮"""
    
    def highlight(self, content: str, keywords: List[str], tag: str = 'span') -> str:
        """高亮关键词"""
        highlighted = content
        
        for keyword in keywords:
            # 忽略大小写替换
            import re
            pattern = re.compile(re.escape(keyword), re.IGNORECASE)
            replacement = f'<{tag} class="highlight">{keyword}</{tag}>'
            highlighted = pattern.sub(replacement, highlighted)
        
        return highlighted
    
    def extract_highlights(self, content: str, keywords: List[str], 
                          context_length: int = 50) -> List[str]:
        """提取高亮片段"""
        highlights = []
        
        for keyword in keywords:
            # 查找关键词位置
            idx = content.lower().find(keyword.lower())
            if idx != -1:
                # 提取上下文
                start = max(0, idx - context_length)
                end = min(len(content), idx + len(keyword) + context_length)
                snippet = content[start:end]
                
                # 高亮
                highlighted = self.highlight(snippet, [keyword])
                highlights.append(highlighted)
        
        return highlights[:3]  # 最多返回 3 个片段
```

### 3. 结果摘要

**实现方式**：

```python
class ResultSummarizer:
    """结果摘要"""
    
    def __init__(self, llm_service):
        self.llm = llm_service
    
    def summarize(self, query: str, results: List[dict]) -> str:
        """生成结果摘要"""
        # 构建摘要内容
        contents = [r['content'] for r in results[:5]]
        
        prompt = f"""
根据以下记忆内容，生成一个简洁的摘要（50 字以内）：

查询：{query}

记忆内容：
{chr(10).join(f'{i+1}. {c}' for i, c in enumerate(contents))}

摘要：
"""
        
        summary = self.llm.generate(prompt)
        return summary.strip()
    
    def generate_suggestions(self, query: str, results: List[dict]) -> List[str]:
        """生成后续建议"""
        suggestions = []
        
        # 提取主题
        tags = set()
        for r in results:
            tags.update(r.get('tags', []))
        
        if tags:
            top_tag = list(tags)[:1]
            suggestions.append(f"查看更多关于{'、'.join(top_tag)}的记忆")
        
        # 提取人物
        people = set()
        for r in results:
            for p in r.get('people', []):
                if p.get('name'):
                    people.add(p['name'])
        
        if people:
            person = list(people)[0]
            suggestions.append(f"查看与{person}相关的其他记忆")
        
        return suggestions[:3]
```

---

*文档版本：v0.1*  
*最后更新：2026-03-19*  
*维护者：颓弟*
