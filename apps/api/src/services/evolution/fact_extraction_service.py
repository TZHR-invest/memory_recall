"""
Fact Extraction Service

Extracts entity-centric facts from memory content.
Stores as subject-predicate-object triples.
"""

from typing import List, Dict, Any, Optional
from dataclasses import dataclass
import uuid
import re


@dataclass
class ExtractedFact:
    entity_name: str
    entity_type: str
    attribute: str
    value: str
    confidence: float
    is_static: bool


class FactExtractionService:
    """Entity-centric fact extraction from memory content"""

    STATIC_PATTERNS = [
        (r"我(的)?名字叫(.+)", "user", "name", True),
        (r"我是(.+?)工程师", "user", "profession", True),
        (r"我在(.+?)工作", "user", "workplace", True),
        (r"我的生日是(.+)", "user", "birthday", True),
        (r"我住在(.+)", "user", "location", True),
        (r"我来自(.+)", "user", "hometown", True),
        (r"我(的)?(手机|电话)号码是(.+)", "user", "phone", True),
        (r"我(的)?邮箱是(.+)", "user", "email", True),
    ]

    PREFERENCE_PATTERNS = [
        (r"我喜欢(.+)", "user", "likes", False),
        (r"我不喜欢(.+)", "user", "dislikes", False),
        (r"我讨厌(.+)", "user", "dislikes", False),
        (r"我爱吃(.+)", "user", "favorite_food", False),
        (r"我爱喝(.+)", "user", "favorite_drink", False),
        (r"我喜欢听(.+)", "user", "favorite_music", False),
        (r"我喜欢看(.+)", "user", "favorite_content", False),
    ]

    DYNAMIC_PATTERNS = [
        (r"今天(.+)", "event", "today", False),
        (r"明天(.+)", "event", "tomorrow", False),
        (r"昨天(.+)", "event", "yesterday", False),
        (r"下周(.+)", "event", "next_week", False),
    ]

    async def extract_facts(
        self,
        content: str,
        memory_id: Optional[str] = None,
    ) -> List[ExtractedFact]:
        """Extract facts from memory content"""
        facts = []

        for pattern, entity_type, attribute, is_static in self.STATIC_PATTERNS:
            matches = re.findall(pattern, content)
            for match in matches:
                value = match[-1] if isinstance(match, tuple) else match
                facts.append(
                    ExtractedFact(
                        entity_name="user",
                        entity_type=entity_type,
                        attribute=attribute,
                        value=value.strip(),
                        confidence=0.9,
                        is_static=is_static,
                    )
                )

        for pattern, entity_type, attribute, is_static in self.PREFERENCE_PATTERNS:
            matches = re.findall(pattern, content)
            for match in matches:
                value = match[-1] if isinstance(match, tuple) else match
                facts.append(
                    ExtractedFact(
                        entity_name="user",
                        entity_type=entity_type,
                        attribute=attribute,
                        value=value.strip(),
                        confidence=0.8,
                        is_static=is_static,
                    )
                )

        for pattern, entity_type, attribute, is_static in self.DYNAMIC_PATTERNS:
            matches = re.findall(pattern, content)
            for match in matches:
                value = match[-1] if isinstance(match, tuple) else match
                facts.append(
                    ExtractedFact(
                        entity_name="event",
                        entity_type=entity_type,
                        attribute=attribute,
                        value=value.strip(),
                        confidence=0.7,
                        is_static=is_static,
                    )
                )

        return facts

    async def store_facts(
        self,
        user_id: str,
        memory_id: str,
        facts: List[ExtractedFact],
    ) -> List[str]:
        """Store extracted facts in database"""
        from src.database import db

        fact_ids = []

        async with db.user_context(user_id):
            for fact in facts:
                fact_id = str(uuid.uuid4())

                await db.execute(
                    """
                    INSERT INTO facts (
                        id, user_id, memory_id, entity_name, entity_type,
                        attribute, value, confidence, is_static, created_at
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, NOW())
                    """,
                    fact_id,
                    user_id,
                    memory_id,
                    fact.entity_name,
                    fact.entity_type,
                    fact.attribute,
                    fact.value,
                    fact.confidence,
                    fact.is_static,
                )

                fact_ids.append(fact_id)

        return fact_ids

    async def get_user_facts(
        self,
        user_id: str,
        entity_name: Optional[str] = None,
        is_static: Optional[bool] = None,
    ) -> List[Dict[str, Any]]:
        """Get facts for a user, optionally filtered"""
        from src.database import db

        async with db.user_context(user_id):
            query = "SELECT * FROM facts WHERE user_id = $1"
            params: List[Any] = [user_id]

            if entity_name:
                query += f" AND entity_name = ${len(params) + 1}"
                params.append(entity_name)

            if is_static is not None:
                query += f" AND is_static = ${len(params) + 1}"
                params.append(is_static)

            rows = await db.fetch(query, *params)

        return [dict(row) for row in rows]

    async def get_facts_by_memory(
        self,
        memory_id: str,
        user_id: str,
    ) -> List[Dict[str, Any]]:
        """Get all facts extracted from a specific memory"""
        from src.database import db

        async with db.user_context(user_id):
            rows = await db.fetch(
                "SELECT * FROM facts WHERE memory_id = $1",
                memory_id,
            )

        return [dict(row) for row in rows]

    def classify_fact_type(self, content: str) -> str:
        """Classify if content represents a fact, preference, or event"""
        content_lower = content.lower()

        if any(kw in content_lower for kw in ["喜欢", "爱", "讨厌", "偏好"]):
            return "preference"
        elif any(
            kw in content_lower for kw in ["今天", "明天", "昨天", "下周", "上周"]
        ):
            return "event"
        else:
            return "fact"


fact_extraction_service = FactExtractionService()
