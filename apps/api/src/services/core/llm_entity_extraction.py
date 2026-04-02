"""
LLM-based entity extraction service with Chinese optimization.

Supports:
- Language detection (Chinese/English) with appropriate prompts
- ASMR 6-dimension entity extraction
- Chinese-specific entity types
- Entity context parameter for extraction guidance
"""

import asyncio
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

from src.llm.client import get_llm_client
from src.services.core.chinese_prompts import (
    get_chinese_extraction_prompt,
    get_chinese_contradiction_prompt,
    get_chinese_topic_similarity_prompt,
    get_chinese_relation_detection_prompt,
    detect_language,
)
from src.services.core.asmr_entity_types import detect_is_static
from src.services.graph_tools import RELATION_TYPES, ENTITY_TYPES


@dataclass
class ExtractedEntity:
    text: str
    type: str
    confidence: float = 0.9


@dataclass
class ExtractedFact:
    content: str
    entities: Dict[str, List[str]]
    is_static: bool
    confidence: float
    asmr_dimension: Optional[str] = None
    entity_context: Optional[str] = None


DEFAULT_TIMEOUT = 30.0

# =============================================================================
# Default Entity Context Constants (Supermemory-style extraction guidance)
# =============================================================================

DEFAULT_ENTITY_CONTEXT_CN = """记忆提取规则：
记住：永久性个人事实 — 饮食偏好、工作地点、技能、长期项目、明确要求
不记：临时任务、一次性请求、助手行为、对话填充词
规则：
- 只有明确表达偏好才记录（"我喜欢..."、"我偏好..."）
- 不确定时不创建记忆，宁缺毋滥"""

DEFAULT_ENTITY_CONTEXT_EN = """REMEMBER: lasting personal facts — dietary restrictions, preferences, personal details, workplace, location, tools, ongoing projects, routines, explicit "remember this" requests.
DO NOT REMEMBER: temporary intents, one-time tasks, assistant actions (searching, writing files, generating code), assistant suggestions, implementation details, in-progress task status.
RULES:
- Only store preferences explicitly stated ("I like...", "I prefer...", "I always...")
- When in doubt, do NOT create a memory. Less is more."""


def get_default_entity_context(language: str = "english") -> str:
    """
    Get the default entity context based on language.

    Args:
        language: "chinese" or "english" (default)

    Returns:
        Default entity context string for memory extraction guidance.
    """
    if language == "chinese":
        return DEFAULT_ENTITY_CONTEXT_CN
    return DEFAULT_ENTITY_CONTEXT_EN


# 无意义实体黑名单
MEANINGLESS_ENTITIES = {
    # 代词
    "我",
    "你",
    "他",
    "她",
    "它",
    "我们",
    "你们",
    "他们",
    "自己",
    "大家",
    # 模糊时间
    "目前",
    "平时",
    "最近",
    "现在",
    "当前",
    "近期",
    "将来",
    "过去",
    # 数量词
    "一个",
    "几个",
    "一些",
    "很多",
    "少量",
    "多个",
    "各种",
    "所有",
    # 副词/连词
    "就",
    "也",
    "都",
    "还",
    "又",
    "才",
    "只",
    "最",
    "很",
    "非常",
    # 常见误识别
    "博客",
    "微信",
    "微博",
    "网站",
    "app",
    "APP",
}

# 不需要的实体类型
SKIP_ENTITY_TYPES = {"time", "number", "activity"}

ENGLISH_ENTITY_EXTRACTION_PROMPT = """You are an entity extraction expert. Extract entities from text and return JSON.

Text: {text}
{context_section}

【Extraction Examples】

"I work at Google" → {{"organization": ["Google"]}}
"I joined Meta last year" → {{"organization": ["Meta"]}}
"I live in Beijing" → {{"location": ["Beijing"]}}
"I live in San Francisco" → {{"location": ["San Francisco"]}}
"Meeting with John tomorrow" → {{"person": ["John"]}}
"I like coffee" → {{"preference": ["like coffee"]}}
"I don't eat spicy food" → {{"preference": ["don't eat spicy food"]}}
"I'm a vegetarian" → {{"preference": ["vegetarian"]}}
"I prefer dark mode" → {{"preference": ["prefer dark mode"]}}

【Boundary Rules】

1. organization (company/school):
   - Extract name only: "Google" not "work at Google" or "joined Google"
   - Rule: "work at X/joined X/at X" → X is organization

2. location (place):
   - Rule: "live in X/from X" → X is location

3. preference (preference):
   - Extract complete phrase: "like coffee" not "like"
   - Extract complete phrase: "don't eat spicy food" not "don't"

【Entity Types】
- organization: companies, schools (Google, Meta, Stanford, MIT)
- location: cities, regions (Beijing, San Francisco, Manhattan)
- person: names (John, Sarah, Mike)
- preference: preferences (like coffee, vegetarian, prefer dark mode)
- skill: skills (Python, React, machine learning)
- contact: contact info (phone, email, WeChat)
- occupation: jobs (engineer, product manager, designer)

【Don't Extract】
Pronouns (I, you, he), vague time (recently, currently)

【Return Format】
{{
  "entities": {{"organization": ["Google"], "person": ["John"]}},
  "is_static": true,
  "confidence": 0.9
}}"""


ENGLISH_BATCH_RELATION_PROMPT = """Analyze the relationship between a new memory and candidate memories.

New Memory: {new_content}

Candidate Memories:
{candidates_section}

Relation Types:
1. updates: New information contradicts/replaces old knowledge
   - Markers: "now", "changed", "switched to", "no longer", "already"
   - Example: "I now work at Google" updates "I work at Meta"

2. extends: Enriches/supplements existing information, same topic
   - Markers: "also", "additionally", "furthermore", "besides"
   - Example: "I like basketball" extends "I like sports"

3. derives: Infers new knowledge from existing memory
   - Markers: "so", "therefore", "can infer", "thus"
   - Example: "So I drink coffee often" derives from "I work long hours"

4. null: No significant relation, skip

Return JSON format:
{{
  "relations": [
    {{"id": "memory_id_1", "type": "updates", "confidence": 0.9}},
    {{"id": "memory_id_2", "type": "extends", "confidence": 0.8}},
    {{"id": "memory_id_3", "type": "derives", "confidence": 0.7}},
    {{"id": "memory_id_4", "type": null}}
  ]
}}

Note:
- Only return memories with clear relations
- Return type: null for no relation
- Confidence range: 0.0-1.0
- Use derives for causal relationships or inferences, not for supplementary information"""


@dataclass
class BatchRelationResult:
    memory_id: str
    relation_type: Optional[str]
    confidence: float


def get_batch_relation_prompt(
    new_content: str,
    candidates: List[Dict[str, Any]],
    language: str = "english",
) -> str:
    candidates_section = "\n".join(
        f"{i + 1}. [ID: {c['id']}] {c['content'][:200]}"
        for i, c in enumerate(candidates)
    )

    if language == "chinese":
        from src.services.core.chinese_prompts import get_chinese_batch_relation_prompt

        return get_chinese_batch_relation_prompt(new_content, candidates)

    return ENGLISH_BATCH_RELATION_PROMPT.format(
        new_content=new_content,
        candidates_section=candidates_section,
    )


class LLMEntityExtractor:
    def __init__(self, timeout: float = DEFAULT_TIMEOUT):
        self.llm_client = None
        self.timeout = timeout
        try:
            self.llm_client = get_llm_client()
        except Exception:
            pass

    async def extract(
        self,
        text: str,
        entity_context: Optional[str] = None,
    ) -> ExtractedFact:
        if not self.llm_client:
            return self._fallback_extraction(text, entity_context)

        language = detect_language(text)

        try:
            prompt = self._get_prompt(text, language, entity_context)

            result = await asyncio.wait_for(
                asyncio.to_thread(
                    self.llm_client.extract_json,
                    prompt,
                    0.3,
                ),
                timeout=self.timeout,
            )

            if result:
                entities = result.get("entities", {})
                entities = self._filter_entities(entities)

                llm_is_static = result.get("is_static", False)
                chinese_is_static = (
                    detect_is_static(text) if language == "chinese" else None
                )

                final_is_static = (
                    chinese_is_static
                    if chinese_is_static is not None
                    else llm_is_static
                )

                asmr_dimension = self._detect_primary_asmr_dimension(entities)

                return ExtractedFact(
                    content=text,
                    entities=entities,
                    is_static=final_is_static,
                    confidence=result.get("confidence", 0.5),
                    asmr_dimension=asmr_dimension,
                    entity_context=entity_context,
                )

            return self._fallback_extraction(text, entity_context)

        except asyncio.TimeoutError:
            return self._fallback_extraction(text, entity_context)
        except Exception:
            return self._fallback_extraction(text, entity_context)

    def _get_prompt(
        self,
        text: str,
        language: str,
        entity_context: Optional[str] = None,
    ) -> str:
        if language == "chinese":
            return get_chinese_extraction_prompt(text, entity_context)

        context_section = ""
        if entity_context:
            context_section = f"""
<extraction_guidance>
{entity_context}
</extraction_guidance>
"""

        return ENGLISH_ENTITY_EXTRACTION_PROMPT.format(
            text=text,
            context_section=context_section,
        )

    def _filter_entities(self, entities: Dict[str, List[str]]) -> Dict[str, List[str]]:
        """过滤无意义的实体"""
        filtered = {}

        for entity_type, values in entities.items():
            if entity_type in SKIP_ENTITY_TYPES:
                continue

            clean_values = []
            for value in values:
                if not value or len(value) < 2:
                    continue
                if value in MEANINGLESS_ENTITIES:
                    continue
                if value.lower() in MEANINGLESS_ENTITIES:
                    continue
                clean_values.append(value)

            if clean_values:
                filtered[entity_type] = clean_values

        return filtered

    def _fallback_extraction(
        self,
        text: str,
        entity_context: Optional[str] = None,
    ) -> ExtractedFact:
        from src.services.core.entity_extraction import entity_extractor

        entities = entity_extractor.extract_to_metadata(text)
        entities = self._filter_entities(entities)

        is_static = (
            detect_is_static(text) if detect_language(text) == "chinese" else False
        )
        asmr_dimension = self._detect_primary_asmr_dimension(entities)

        return ExtractedFact(
            content=text,
            entities=entities,
            is_static=is_static,
            confidence=0.5,
            asmr_dimension=asmr_dimension,
            entity_context=entity_context,
        )

    def _detect_primary_asmr_dimension(
        self, entities: Dict[str, List[str]]
    ) -> Optional[str]:
        from src.services.core.entity_extraction import map_generic_to_asmr

        dimension_counts: Dict[str, int] = {}

        for entity_type in entities.keys():
            dimension = map_generic_to_asmr(entity_type)
            dimension_counts[dimension] = dimension_counts.get(dimension, 0) + 1

        if not dimension_counts:
            return None

        return max(dimension_counts.keys(), key=lambda d: dimension_counts[d])

    async def extract_with_relations(
        self,
        text: str,
        entity_context: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        提取实体和关系（用于 Entity Graph 构建）

        借鉴 graph_builder_service.parse_relation_from_text() 的 Prompt 架构

        Args:
            text: 待提取的文本内容
            entity_context: 实体提取指导上下文（可选）

        Returns:
            包含实体和关系的字典：
            {
                "entities": [{"name": "实体名", "type": "person/location/organization/event"}],
                "relations": [{"from": "实体1", "to": "实体2", "type": "关系类型", "confidence": 0.9}],
                "confidence": 0.8
            }
        """
        if not self.llm_client:
            return self._fallback_extract_with_relations(text, entity_context)

        language = detect_language(text)

        try:
            prompt = self._get_prompt_with_relations(text, language, entity_context)

            result = await asyncio.wait_for(
                asyncio.to_thread(
                    self.llm_client.extract_json,
                    prompt,
                    0.3,
                ),
                timeout=self.timeout,
            )

            if result:
                entities = result.get("entities", [])
                entities = self._filter_entities_with_types(entities)

                relations = result.get("relations", [])
                relations = self._filter_relations(relations)

                return {
                    "entities": entities,
                    "relations": relations,
                    "confidence": result.get("confidence", 0.5),
                }

            return self._fallback_extract_with_relations(text, entity_context)

        except asyncio.TimeoutError:
            return self._fallback_extract_with_relations(text, entity_context)
        except Exception:
            return self._fallback_extract_with_relations(text, entity_context)

    def _get_prompt_with_relations(
        self,
        text: str,
        language: str,
        entity_context: Optional[str] = None,
    ) -> str:
        """
        增强的 Prompt，包含关系抽取

        借鉴 graph_builder_service 的 Prompt 架构
        """
        if language == "chinese":
            relation_types_list = "\n".join(
                f"- {en}: {cn}" for en, cn in list(RELATION_TYPES.items())[:15]
            )

            context_section = ""
            if entity_context:
                context_section = f"""
<提取指导>
{entity_context}
</提取指导>
"""

            return f"""从以下文本中提取实体和关系：

文本: {text}
{context_section}

返回 JSON 格式：
{{
  "entities": [
    {{"name": "实体名", "type": "person/location/organization/event"}}
  ],
  "relations": [
    {{"from": "实体1", "to": "实体2", "type": "关系类型", "confidence": 0.9}}
  ]
}}

【实体类型】
- person: 人物
- location: 地点  
- organization: 组织/公司
- event: 事件
- preference: 偏好
- skill: 技能
- occupation: 职业

【关系类型】（优先使用预定义类型）
{relation_types_list}

【示例】
文本: "我在字节跳动工作，同事张三也在那"
输出:
{{
  "entities": [
    {{"name": "字节跳动", "type": "organization"}},
    {{"name": "张三", "type": "person"}}
  ],
  "relations": [
    {{"from": "我", "to": "字节跳动", "type": "works_at", "confidence": 0.9}},
    {{"from": "张三", "to": "字节跳动", "type": "works_at", "confidence": 0.9}},
    {{"from": "我", "to": "张三", "type": "colleague", "confidence": 0.85}}
  ]
}}

【注意】
1. 只提取明确表达的关系，不要推断
2. 每个关系必须包含 confidence 字段（0.0-1.0）
3. 如果预定义类型不适用，可以创建新类型
4. 实体名称要准确，避免代词（我、你、他等）"""

        else:
            relation_types_list = "\n".join(
                f"- {en}: {cn}" for en, cn in list(RELATION_TYPES.items())[:15]
            )

            context_section = ""
            if entity_context:
                context_section = f"""
<extraction_guidance>
{entity_context}
</extraction_guidance>
"""

            return f"""Extract entities and relations from the following text:

Text: {text}
{context_section}

Return JSON format:
{{
  "entities": [
    {{"name": "entity_name", "type": "person/location/organization/event"}}
  ],
  "relations": [
    {{"from": "entity1", "to": "entity2", "type": "relation_type", "confidence": 0.9}}
  ]
}}

【Entity Types】
- person: Person name
- location: Place
- organization: Company/Organization
- event: Event
- preference: Preference
- skill: Skill
- occupation: Job title

【Relation Types】 (use predefined types when applicable)
{relation_types_list}

【Example】
Text: "I work at Google with my colleague John"
Output:
{{
  "entities": [
    {{"name": "Google", "type": "organization"}},
    {{"name": "John", "type": "person"}}
  ],
  "relations": [
    {{"from": "I", "to": "Google", "type": "works_at", "confidence": 0.9}},
    {{"from": "John", "to": "Google", "type": "works_at", "confidence": 0.9}},
    {{"from": "I", "to": "John", "type": "colleague", "confidence": 0.85}}
  ]
}}

【Note】
1. Only extract explicitly stated relations, do not infer
2. Each relation must have confidence field (0.0-1.0)
3. Create new relation type if predefined ones don't fit
4. Avoid pronouns (I, you, he, etc.) as entity names"""

    def _filter_entities_with_types(
        self, entities: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """过滤无意义或类型不明确的实体"""
        filtered = []

        for entity in entities:
            name = entity.get("name", "")
            entity_type = entity.get("type", "")

            if not name or len(name) < 2:
                continue

            if name in MEANINGLESS_ENTITIES or name.lower() in MEANINGLESS_ENTITIES:
                continue

            if entity_type in SKIP_ENTITY_TYPES:
                continue

            filtered.append(entity)

        return filtered

    def _filter_relations(
        self, relations: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """过滤无效或低置信度的关系"""
        filtered = []

        for relation in relations:
            from_entity = relation.get("from", "")
            to_entity = relation.get("to", "")
            relation_type = relation.get("type", "")
            confidence = relation.get("confidence", 0.5)

            if not all([from_entity, to_entity, relation_type]):
                continue

            if confidence < 0.3:
                continue

            relation["confidence"] = max(0.0, min(1.0, float(confidence)))

            filtered.append(relation)

        return filtered

    def _fallback_extract_with_relations(
        self,
        text: str,
        entity_context: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        降级提取：当 LLM 不可用时，使用现有实体提取方法

        返回实体和空关系列表
        """
        from src.services.core.entity_extraction import entity_extractor

        entities_dict = entity_extractor.extract_to_metadata(text)
        entities_dict = self._filter_entities(entities_dict)

        entities_list = []
        for entity_type, names in entities_dict.items():
            for name in names:
                entities_list.append(
                    {
                        "name": name,
                        "type": entity_type,
                    }
                )

        return {
            "entities": entities_list,
            "relations": [],
            "confidence": 0.3,
        }

    async def extract_entities_only(
        self,
        text: str,
        entity_context: Optional[str] = None,
    ) -> Dict[str, List[str]]:
        result = await self.extract(text, entity_context)
        return result.entities

    async def batch_extract(
        self,
        texts: List[str],
        entity_context: Optional[str] = None,
    ) -> List[ExtractedFact]:
        results = []
        for text in texts:
            result = await self.extract(text, entity_context)
            results.append(result)
        return results

    async def detect_contradiction(
        self,
        new_content: str,
        existing_content: str,
    ) -> tuple[bool, float, str]:
        if not self.llm_client:
            return (False, 0.0, "")

        language = detect_language(new_content + existing_content)

        try:
            if language == "chinese":
                prompt = get_chinese_contradiction_prompt(new_content, existing_content)
            else:
                prompt = f"""Analyze if these two statements contradict each other.

Statement 1 (new): {new_content}
Statement 2 (existing): {existing_content}

Return JSON:
{{
  "is_contradiction": true,
  "confidence": 0.9,
  "reason": "brief explanation"
}}"""

            result = await asyncio.wait_for(
                asyncio.to_thread(
                    self.llm_client.extract_json,
                    prompt,
                    0.3,
                ),
                timeout=self.timeout,
            )

            if result:
                return (
                    result.get("is_contradiction", False),
                    result.get("confidence", 0.0),
                    result.get("reason", ""),
                )
            return (False, 0.0, "")
        except asyncio.TimeoutError:
            return (False, 0.0, "")
        except Exception:
            return (False, 0.0, "")

    async def detect_topic_similarity(
        self,
        content1: str,
        content2: str,
    ) -> tuple[bool, float, Optional[str]]:
        if not self.llm_client:
            return (False, 0.0, None)

        language = detect_language(content1 + content2)

        try:
            if language == "chinese":
                prompt = get_chinese_topic_similarity_prompt(content1, content2)
            else:
                prompt = f"""Analyze if these two statements are about the same topic.

Statement 1: {content1}
Statement 2: {content2}

Return JSON:
{{
  "is_same_topic": true,
  "similarity": 0.8,
  "topic": "the common topic"
}}"""

            result = await asyncio.wait_for(
                asyncio.to_thread(
                    self.llm_client.extract_json,
                    prompt,
                    0.3,
                ),
                timeout=self.timeout,
            )

            if result:
                return (
                    result.get("is_same_topic", False),
                    result.get("similarity", 0.0),
                    result.get("topic"),
                )
            return (False, 0.0, None)
        except asyncio.TimeoutError:
            return (False, 0.0, None)
        except Exception:
            return (False, 0.0, None)

    async def detect_relation(
        self,
        new_content: str,
        existing_content: str,
    ) -> tuple[Optional[str], float, str]:
        if not self.llm_client:
            return (None, 0.0, "")

        language = detect_language(new_content + existing_content)

        try:
            if language == "chinese":
                prompt = get_chinese_relation_detection_prompt(
                    new_content, existing_content
                )
            else:
                prompt = f"""Analyze the relationship between new memory and existing memory.

New memory: {new_content}
Existing memory: {existing_content}

Relation types:
1. updates: New information replaces old knowledge
2. extends: Enriches/supplements existing information
3. derives: Inferred new knowledge from patterns

Return JSON:
{{
  "relation_type": "updates",
  "confidence": 0.9,
  "reason": "brief explanation"
}}"""

            result = await asyncio.wait_for(
                asyncio.to_thread(
                    self.llm_client.extract_json,
                    prompt,
                    0.3,
                ),
                timeout=self.timeout,
            )

            if result:
                return (
                    result.get("relation_type"),
                    result.get("confidence", 0.0),
                    result.get("reason", ""),
                )
            return (None, 0.0, "")
        except asyncio.TimeoutError:
            return (None, 0.0, "")
        except Exception:
            return (None, 0.0, "")

    async def detect_relations_batch(
        self,
        new_content: str,
        candidates: List[Dict[str, Any]],
        language: Optional[str] = None,
    ) -> List[BatchRelationResult]:
        """
        Detect relations between a new memory and multiple candidates in a single LLM call.

        Args:
            new_content: The new memory content
            candidates: List of candidate memories with 'id' and 'content' keys
            language: Language hint ('chinese' or 'english'), auto-detected if None

        Returns:
            List of BatchRelationResult with memory_id, relation_type, and confidence
        """
        if not self.llm_client or not candidates:
            return []

        # Auto-detect language if not provided
        if language is None:
            language = detect_language(new_content)

        try:
            # Generate batch prompt
            prompt = get_batch_relation_prompt(new_content, candidates, language)

            result = await asyncio.wait_for(
                asyncio.to_thread(
                    self.llm_client.extract_json,
                    prompt,
                    0.3,
                ),
                timeout=self.timeout,
            )

            if result and "relations" in result:
                return self._parse_batch_relations(result["relations"])

            # Fallback to rule-based detection if no valid response
            return self._fallback_batch_detection(new_content, candidates)

        except asyncio.TimeoutError:
            # Fallback to rule-based detection on timeout
            return self._fallback_batch_detection(new_content, candidates)
        except Exception:
            # Fallback to rule-based detection on any error
            return self._fallback_batch_detection(new_content, candidates)

    def _parse_batch_relations(
        self, relations_data: List[Dict[str, Any]]
    ) -> List[BatchRelationResult]:
        """Parse batch LLM response into BatchRelationResult objects."""
        results = []
        for item in relations_data:
            memory_id = item.get("id", "")
            relation_type = item.get("type")
            confidence = item.get("confidence", 0.5)

            # Only include valid relation types
            if relation_type in ("updates", "extends", "derives"):
                results.append(
                    BatchRelationResult(
                        memory_id=memory_id,
                        relation_type=relation_type,
                        confidence=float(confidence),
                    )
                )
            # Skip null relations (no significant relation)

        return results

    def _fallback_batch_detection(
        self,
        new_content: str,
        candidates: List[Dict[str, Any]],
    ) -> List[BatchRelationResult]:
        """Fallback to rule-based detection when LLM fails."""
        from src.services.core.chinese_entity_types import (
            has_update_marker,
            has_extend_marker,
            has_derive_marker,
        )

        results = []

        for candidate in candidates:
            memory_id = candidate.get("id", "")
            existing_content = candidate.get("content", "")

            # Rule-based detection using markers
            relation_type = None
            confidence = 0.5

            if has_update_marker(new_content):
                relation_type = "updates"
                confidence = 0.7
            elif has_extend_marker(new_content):
                relation_type = "extends"
                confidence = 0.6
            elif has_derive_marker(new_content):
                relation_type = "derives"
                confidence = 0.6

            if relation_type:
                results.append(
                    BatchRelationResult(
                        memory_id=memory_id,
                        relation_type=relation_type,
                        confidence=confidence,
                    )
                )

        return results


llm_entity_extractor = LLMEntityExtractor()

# 使用配置项覆盖默认 timeout
try:
    from src.config import settings

    llm_entity_extractor.timeout = settings.LLM_EXTRACTION_TIMEOUT
except Exception:
    pass
