"""
Relation service for memory relationships (updates/extends/derives).
"""

from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime
from dataclasses import dataclass
from enum import Enum
import re
import logging

from src.database import db
from src.config import settings
from src.services.core.llm_entity_extraction import llm_entity_extractor
try:
    from src.services.jieba_service import extract_keywords as _jieba_extract_keywords
except ImportError:
    # jieba not available, use simple regex fallback
    import re as _re
    def _jieba_extract_keywords(text: str, min_length: int = 2):
        """Fallback: split by punctuation/whitespace, filter short tokens"""
        tokens = _re.split(r'[，。！？、；：\s,.;!?]+', text)
        return [t for t in tokens if len(t) >= min_length and not t.isdigit()]
from src.embedding.client import get_embedding_client

logger = logging.getLogger(__name__)


class RelationType(Enum):
    UPDATES = "updates"
    EXTENDS = "extends"
    DERIVES = "derives"


@dataclass
class MemoryRelation:
    id: str
    from_memory_id: str
    to_memory_id: str
    relation_type: str
    confidence: float
    created_at: datetime


CONTRADICTION_PATTERNS = [
    (r"现在(.+?)(工作|住|在)", r"以前(.+?)(工作|住|在)"),
    (r"目前在(.+?)", r"之前在(.+?)"),
    (r"目前是(.+?)", r"之前是(.+?)"),
    (r"(不喜欢|不爱)(.+)", r"(喜欢|爱)\1"),
    (r"(喜欢|爱)(.+)", r"(不喜欢|不爱)\1"),
    (r"现在(.+?)是(.+)", r"(.+?)是(.+)"),
    (r"(\d+)(岁|年|月|天)", r"(\d+)\1"),
]

TOPIC_KEYWORDS = {
    "饮食": ["吃", "喝", "食物", "餐", "口味", "喜欢", "不喜欢", "素食", "肉"],
    "工作": ["工作", "公司", "职业", "职位", "项目", "同事", "老板", "上班"],
    "居住": ["住", "城市", "地区", "地址", "搬家", "房子"],
    "爱好": ["喜欢", "爱好", "兴趣", "运动", "游戏", "电影", "音乐", "书"],
    "社交": ["朋友", "家人", "同事", "见面", "聚会", "社交"],
    "健康": ["健康", "运动", "锻炼", "医生", "医院", "生病"],
}


class RelationService:
    def __init__(self):
        self.contradiction_patterns = CONTRADICTION_PATTERNS
        self.topic_keywords = TOPIC_KEYWORDS
        self.embedding_client = get_embedding_client()

    async def create(
        self,
        from_memory_id: str,
        to_memory_id: str,
        relation_type: str,
        confidence: float = 0.8,
    ) -> MemoryRelation:
        if relation_type not in [r.value for r in RelationType]:
            raise ValueError(f"Invalid relation type: {relation_type}")

        row = await db.fetchrow(
            """
            INSERT INTO memory_relations (from_memory_id, to_memory_id, relation_type, confidence)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (from_memory_id, to_memory_id, relation_type) DO NOTHING
            RETURNING *
            """,
            from_memory_id,
            to_memory_id,
            relation_type,
            confidence,
        )

        if row is None:
            existing = await self.get_by_pair(from_memory_id, to_memory_id, relation_type)
            if existing:
                return existing
            raise RuntimeError("Failed to create or find memory relation")

        if relation_type == RelationType.DERIVES.value:
            await self._mark_as_inference(from_memory_id)

        return self._row_to_relation(row)

    async def get_by_pair(
        self,
        from_memory_id: str,
        to_memory_id: str,
        relation_type: str,
    ) -> Optional[MemoryRelation]:
        row = await db.fetchrow(
            """
            SELECT * FROM memory_relations
            WHERE from_memory_id = $1 AND to_memory_id = $2 AND relation_type = $3
            """,
            from_memory_id,
            to_memory_id,
            relation_type,
        )
        return self._row_to_relation(row) if row else None

    async def get_by_memory(self, memory_id: str) -> List[MemoryRelation]:
        rows = await db.fetch(
            """
            SELECT * FROM memory_relations
            WHERE from_memory_id = $1 OR to_memory_id = $1
            ORDER BY created_at DESC
            """,
            memory_id,
        )
        return [self._row_to_relation(row) for row in rows]

    async def get_version_history(self, memory_id: str) -> List[Dict[str, Any]]:
        visited = set()
        history = []

        async def traverse(mid: str, depth: int = 0):
            if mid in visited or depth > 10:
                return
            visited.add(mid)

            relations = await db.fetch(
                """
                SELECT r.*, m.content, m.created_at, m.is_latest
                FROM memory_relations r
                JOIN memories m ON r.to_memory_id = m.id
                WHERE r.from_memory_id = $1 AND r.relation_type = 'updates'
                """,
                mid,
            )

            for row in relations:
                history.append(
                    {
                        "id": row["to_memory_id"],
                        "content": row["content"],
                        "created_at": row["created_at"].isoformat()
                        if row["created_at"]
                        else None,
                        "is_latest": row["is_latest"],
                        "depth": depth,
                    }
                )
                await traverse(row["to_memory_id"], depth + 1)

        await traverse(memory_id)
        return sorted(history, key=lambda x: x["created_at"], reverse=True)

    async def get_related_memories(
        self,
        memory_id: str,
        relation_types: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        types = relation_types or [r.value for r in RelationType]
        placeholders = ",".join(f"'{t}'" for t in types)

        rows = await db.fetch(
            f"""
            SELECT r.relation_type, r.confidence, m.id, m.content, m.created_at
            FROM memory_relations r
            JOIN memories m ON (
                CASE 
                    WHEN r.from_memory_id = $1 THEN r.to_memory_id
                    ELSE r.from_memory_id
                END = m.id
            )
            WHERE (r.from_memory_id = $1 OR r.to_memory_id = $1)
            AND r.relation_type IN ({placeholders})
            AND m.is_forgotten = FALSE
            ORDER BY r.created_at DESC
            """,
            memory_id,
        )

        return [
            {
                "id": row["id"],
                "content": row["content"],
                "relation_type": row["relation_type"],
                "confidence": row["confidence"],
                "created_at": row["created_at"].isoformat()
                if row["created_at"]
                else None,
            }
            for row in rows
        ]

    async def delete(self, relation_id: str) -> bool:
        result = await db.execute(
            "DELETE FROM memory_relations WHERE id = $1",
            relation_id,
        )
        return result == "DELETE 1"

    async def detect_contradiction(
        self,
        new_content: str,
        existing_content: str,
    ) -> Tuple[bool, float]:
        score = 0.0

        for pattern_new, pattern_old in self.contradiction_patterns:
            new_match = re.search(pattern_new, new_content)
            old_match = re.search(pattern_old, existing_content)

            if new_match and old_match:
                new_value = new_match.group(1) if new_match.groups() else ""
                old_value = old_match.group(1) if old_match.groups() else ""

                if new_value and old_value and new_value != old_value:
                    score += 0.3

        time_indicators = ["现在", "目前", "现在", "最近", "已经"]
        has_time_new = any(ind in new_content for ind in time_indicators)
        has_time_old = any(
            ind in existing_content for ind in ["以前", "之前", "过去", "原来"]
        )

        if has_time_new and has_time_old:
            score += 0.2

        update_keywords = ["换了", "改了", "变成", "不再", "现在", "已经"]
        if any(kw in new_content for kw in update_keywords):
            score += 0.2

        return (score >= 0.5, min(score, 1.0))

    async def detect_topic_similarity(
        self,
        content1: str,
        content2: str,
    ) -> Tuple[bool, float, Optional[str]]:
        content1_topics = set()
        content2_topics = set()

        for topic, keywords in self.topic_keywords.items():
            if any(kw in content1 for kw in keywords):
                content1_topics.add(topic)
            if any(kw in content2 for kw in keywords):
                content2_topics.add(topic)

        common_topics = content1_topics & content2_topics

        if common_topics:
            return (True, 0.7, list(common_topics)[0])

        return (False, 0.0, None)

    async def _get_semantic_similar_memories(
        self,
        content: str,
        container_tag: str,
        exclude_id: str,
        limit: int = 20,
        threshold: float = 0.4,
    ) -> List[Dict[str, Any]]:
        if not self.embedding_client:
            return []

        query_embedding = await self.embedding_client.embed(content)
        if not query_embedding:
            return []

        embedding_str = "[" + ",".join(map(str, query_embedding)) + "]"

        rows = await db.fetch(
            """
            SELECT id, content, is_static,
                   1 - (embedding <=> $1::vector) as similarity
            FROM memories
            WHERE container_tag = $2
            AND id != $3
            AND is_latest = TRUE
            AND is_forgotten = FALSE
            AND 1 - (embedding <=> $1::vector) > $4
            ORDER BY similarity DESC
            LIMIT $5
            """,
            embedding_str,
            container_tag,
            exclude_id,
            threshold,
            limit,
        )
        return [dict(r) for r in rows]

    async def auto_create_relations(
        self,
        new_memory_id: str,
        new_content: str,
        container_tag: str,
        is_static: bool = False,
        use_llm: Optional[bool] = None,
        similarity_threshold: float = 0.4,
        max_candidates: Optional[int] = None,
    ) -> List[MemoryRelation]:
        relations = []

        if max_candidates is None:
            max_candidates = settings.BATCH_DETECTION_MAX_CANDIDATES

        if use_llm is None:
            use_llm = settings.USE_BATCH_RELATION_DETECTION

        rows = await self._get_semantic_similar_memories(
            content=new_content,
            container_tag=container_tag,
            exclude_id=new_memory_id,
            limit=max_candidates,
            threshold=similarity_threshold,
        )

        if not rows:
            return relations

        if settings.USE_BATCH_RELATION_DETECTION and use_llm:
            logger.debug(f"Using batch relation detection for {len(rows)} candidates")
            batch_results = await llm_entity_extractor.detect_relations_batch(
                new_content=new_content,
                candidates=[{"id": r["id"], "content": r["content"]} for r in rows],
            )

            for result in batch_results:
                if result.relation_type is None:
                    continue

                relation = await self.create(
                    from_memory_id=new_memory_id,
                    to_memory_id=result.memory_id,
                    relation_type=result.relation_type,
                    confidence=result.confidence,
                )
                relations.append(relation)

                if result.relation_type == RelationType.UPDATES.value:
                    await self._mark_not_latest(result.memory_id)

            logger.debug(f"Batch detection created {len(relations)} relations")
            return relations

        logger.debug(f"Using serial relation detection for {len(rows)} candidates")
        for row in rows:
            existing_id = row["id"]
            existing_content = row["content"]
            existing_is_static = row["is_static"]

            if use_llm:
                try:
                    (
                        is_contradiction,
                        contradiction_score,
                        reason,
                    ) = await llm_entity_extractor.detect_contradiction(
                        new_content, existing_content
                    )
                except Exception:
                    is_contradiction, contradiction_score = await self.detect_contradiction(
                        new_content, existing_content
                    )
                    reason = ""
            else:
                is_contradiction, contradiction_score = await self.detect_contradiction(
                    new_content, existing_content
                )
                reason = ""

            if is_contradiction:
                relation = await self.create(
                    from_memory_id=new_memory_id,
                    to_memory_id=existing_id,
                    relation_type=RelationType.UPDATES.value,
                    confidence=contradiction_score,
                )
                relations.append(relation)

                await self._mark_not_latest(existing_id)
                continue

            if use_llm:
                try:
                    (
                        is_similar,
                        similarity_score,
                        topic,
                    ) = await llm_entity_extractor.detect_topic_similarity(
                        new_content, existing_content
                    )
                except Exception:
                    (
                        is_similar,
                        similarity_score,
                        topic,
                    ) = await self.detect_topic_similarity(new_content, existing_content)
            else:
                (
                    is_similar,
                    similarity_score,
                    topic,
                ) = await self.detect_topic_similarity(new_content, existing_content)

            if is_similar and existing_is_static == is_static:
                relation = await self.create(
                    from_memory_id=new_memory_id,
                    to_memory_id=existing_id,
                    relation_type=RelationType.EXTENDS.value,
                    confidence=similarity_score,
                )
                relations.append(relation)

        return relations

    async def _mark_not_latest(self, memory_id: str) -> None:
        await db.execute(
            """
            UPDATE memories 
            SET is_latest = FALSE, valid_until = NOW(), updated_at = NOW()
            WHERE id = $1
            """,
            memory_id,
        )

    async def _mark_as_inference(self, memory_id: str) -> None:
        await db.execute(
            """
            UPDATE memories 
            SET is_inference = TRUE, updated_at = NOW()
            WHERE id = $1
            """,
            memory_id,
        )

    async def create_derived_memory(
        self,
        inferred_content: str,
        source_memory_ids: List[str],
        container_tag: str,
        confidence: float = 0.7,
        is_static: bool = False,
    ) -> Tuple[str, List[MemoryRelation]]:
        from src.services.core.memory_store import memory_store

        inferred_memory = await memory_store.create(
            content=inferred_content,
            container_tag=container_tag,
            is_static=is_static,
            is_inference=True,
            auto_relations=False,
        )

        relations = []
        for source_id in source_memory_ids:
            relation = await self.create(
                from_memory_id=inferred_memory.id,
                to_memory_id=source_id,
                relation_type=RelationType.DERIVES.value,
                confidence=confidence,
            )
            relations.append(relation)

        return (inferred_memory.id, relations)

    async def get_full_history(self, memory_id: str) -> Dict[str, Any]:
        memory = await db.fetchrow(
            "SELECT * FROM memories WHERE id = $1",
            memory_id,
        )

        if not memory:
            return {}

        updates = await self.get_version_history(memory_id)

        extends = await db.fetch(
            """
            SELECT m.id, m.content, m.created_at, r.confidence
            FROM memory_relations r
            JOIN memories m ON r.to_memory_id = m.id
            WHERE r.from_memory_id = $1 AND r.relation_type = 'extends'
            ORDER BY r.created_at DESC
            """,
            memory_id,
        )

        derives = await db.fetch(
            """
            SELECT m.id, m.content, m.created_at, r.confidence
            FROM memory_relations r
            JOIN memories m ON r.to_memory_id = m.id
            WHERE r.from_memory_id = $1 AND r.relation_type = 'derives'
            ORDER BY r.created_at DESC
            """,
            memory_id,
        )

        return {
            "memory": {
                "id": memory["id"],
                "content": memory["content"],
                "is_latest": memory["is_latest"],
                "created_at": memory["created_at"].isoformat()
                if memory["created_at"]
                else None,
            },
            "updates_history": updates,
            "extends_related": [dict(r) for r in extends],
            "derives_related": [dict(r) for r in derives],
        }

    def _row_to_relation(self, row: Dict) -> MemoryRelation:
        return MemoryRelation(
            id=str(row["id"]),
            from_memory_id=row["from_memory_id"],
            to_memory_id=row["to_memory_id"],
            relation_type=row["relation_type"],
            confidence=row["confidence"],
            created_at=row["created_at"],
        )


relation_service = RelationService()
