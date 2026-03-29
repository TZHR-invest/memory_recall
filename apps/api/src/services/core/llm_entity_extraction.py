"""
LLM-based entity extraction service.
"""

from typing import List, Dict, Any, Optional
from dataclasses import dataclass

from src.llm.client import get_llm_client


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


ENTITY_EXTRACTION_PROMPT = """Extract entities and facts from the following text.

Text: {text}

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
    def __init__(self):
        self.llm_client = None
        try:
            self.llm_client = get_llm_client()
        except Exception:
            pass

    async def extract(self, text: str) -> ExtractedFact:
        if not self.llm_client:
            return ExtractedFact(
                content=text,
                entities={},
                is_static=False,
                confidence=0.5,
            )

        try:
            prompt = ENTITY_EXTRACTION_PROMPT.format(text=text)
            result = self.llm_client.extract_json(prompt, temperature=0.3)

            if result:
                return ExtractedFact(
                    content=text,
                    entities=result.get("entities", {}),
                    is_static=result.get("is_static", False),
                    confidence=result.get("confidence", 0.5),
                )

            return ExtractedFact(
                content=text,
                entities={},
                is_static=False,
                confidence=0.5,
            )
        except Exception:
            return ExtractedFact(
                content=text,
                entities={},
                is_static=False,
                confidence=0.5,
            )

    async def extract_entities_only(self, text: str) -> Dict[str, List[str]]:
        result = await self.extract(text)
        return result.entities

    async def batch_extract(self, texts: List[str]) -> List[ExtractedFact]:
        results = []
        for text in texts:
            result = await self.extract(text)
            results.append(result)
        return results

    async def detect_contradiction(
        self,
        new_content: str,
        existing_content: str,
    ) -> tuple[bool, float, str]:
        if not self.llm_client:
            return (False, 0.0, "")

        prompt = f"""Analyze if these two statements contradict each other.

Statement 1 (new): {new_content}
Statement 2 (existing): {existing_content}

Return JSON:
{{
  "is_contradiction": true,
  "confidence": 0.9,
  "reason": "brief explanation"
}}"""

        try:
            result = self.llm_client.extract_json(prompt, temperature=0.3)
            if result:
                return (
                    result.get("is_contradiction", False),
                    result.get("confidence", 0.0),
                    result.get("reason", ""),
                )
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

        prompt = f"""Analyze if these two statements are about the same topic.

Statement 1: {content1}
Statement 2: {content2}

Return JSON:
{{
  "is_same_topic": true,
  "similarity": 0.8,
  "topic": "the common topic"
}}"""

        try:
            result = self.llm_client.extract_json(prompt, temperature=0.3)
            if result:
                return (
                    result.get("is_same_topic", False),
                    result.get("similarity", 0.0),
                    result.get("topic"),
                )
            return (False, 0.0, None)
        except Exception:
            return (False, 0.0, None)


llm_entity_extractor = LLMEntityExtractor()
