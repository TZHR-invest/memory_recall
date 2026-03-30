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


DEFAULT_TIMEOUT = 5.0

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

ENGLISH_ENTITY_EXTRACTION_PROMPT = """Extract entities and facts from the following text.

Text: {text}
{context_section}

Extract:
1. Entities with their types (person, location, organization, time, preference, contact, activity)
2. Whether this is a static fact (permanent trait like name, preference) or dynamic fact (recent activity)
3. Confidence score (0.0-1.0)

Return JSON format:
{{
  "entities": {{
    "location": ["Beijing"],
    "organization": ["Google"],
    "person": ["John"],
    "time": ["tomorrow"],
    "preference": ["likes coffee"],
    "contact": ["email@example.com"],
    "activity": ["working on project"]
  }},
  "is_static": true,
  "confidence": 0.9,
  "key_facts": ["User works at Google", "User lives in Beijing"]
}}

Only include non-empty entity types. Be concise and accurate."""


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
            context_section = f"\nEntity Context: {entity_context}\nPlease adjust extraction focus based on the context above."

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


llm_entity_extractor = LLMEntityExtractor()
