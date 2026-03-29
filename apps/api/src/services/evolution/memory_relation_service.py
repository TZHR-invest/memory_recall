"""
Memory Relation Service

Detects and manages relationships between memories.
Supports contradiction detection, relationship classification, and version tracking.
"""

from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime
import uuid
import json
import logging

logger = logging.getLogger(__name__)


@dataclass
class MemoryRelation:
    """Memory relation data model"""

    id: str
    user_id: str
    source_memory_id: str
    target_memory_id: str
    relation_type: str  # updates, extends, derives, supersedes, related_to
    confidence: float
    detected_by: str  # manual, llm, fusion
    status: str  # active, inactive
    created_at: Optional[datetime] = None


@dataclass
class ContradictionResult:
    """Result of contradiction detection"""

    has_contradiction: bool
    conflicting_memory_id: Optional[str] = None
    conflicting_content: Optional[str] = None
    explanation: Optional[str] = None
    confidence: float = 0.0


class MemoryRelationService:
    """Service for detecting and managing memory relationships"""

    RELATION_TYPES = ["updates", "extends", "derives", "supersedes", "related_to"]
    CONTRADICTION_THRESHOLD = 0.7

    async def detect_contradiction(
        self,
        memory_id: str,
        user_id: str,
        content: Optional[str] = None,
    ) -> ContradictionResult:
        """
        Detect if a memory contradicts existing memories.

        Args:
            memory_id: The ID of the memory to check
            user_id: User ID for schema isolation
            content: Optional content (if not provided, will fetch from DB)

        Returns:
            ContradictionResult with details about any conflicts
        """
        from src.database import db
        from src.llm.client import get_llm_client

        if content is None:
            async with db.user_context(user_id):
                row = await db.fetchrow(
                    "SELECT content FROM raw_messages WHERE id = $1 AND user_id = $2",
                    memory_id,
                    user_id,
                )
                if not row:
                    return ContradictionResult(has_contradiction=False)
                content = row["content"]

        async with db.user_context(user_id):
            mem_row = await db.fetchrow(
                "SELECT embedding, content FROM raw_messages WHERE id = $1",
                memory_id,
            )

            if not mem_row or not mem_row["embedding"]:
                return ContradictionResult(has_contradiction=False)

            embedding_str = (
                "[" + ",".join(map(str, mem_row["embedding"])) + "]"
                if isinstance(mem_row["embedding"], list)
                else str(mem_row["embedding"])
            )

            similar_rows = await db.fetch(
                """
                SELECT id, content, embedding <=> $1::vector as distance
                FROM raw_messages
                WHERE user_id = $2
                  AND id != $3
                  AND is_expired = FALSE
                  AND embedding <=> $1::vector < 0.3
                ORDER BY distance
                LIMIT 5
                """,
                embedding_str,
                user_id,
                memory_id,
            )

        if not similar_rows:
            return ContradictionResult(has_contradiction=False)

        try:
            llm_client = get_llm_client()

            for similar in similar_rows:
                prompt = f"""分析以下两条记忆是否存在矛盾：

记忆1（新记忆）: {content}

记忆2（已有记忆）: {similar["content"]}

请判断这两条记忆是否存在语义上的矛盾或冲突。例如：
- "我喜欢吃苹果" 和 "我讨厌吃苹果" 是矛盾
- "我住在北京" 和 "我现在住在上海" 可能是更新关系而非矛盾
- "我是工程师" 和 "我是医生" 是矛盾

请以 JSON 格式返回：
{{
    "has_contradiction": true/false,
    "explanation": "解释原因",
    "confidence": 0.0-1.0
}}"""

                result = llm_client.extract_json(prompt, temperature=0.1)

                if result and result.get("has_contradiction", False):
                    confidence = result.get("confidence", 0.5)
                    if confidence >= self.CONTRADICTION_THRESHOLD:
                        return ContradictionResult(
                            has_contradiction=True,
                            conflicting_memory_id=similar["id"],
                            conflicting_content=similar["content"],
                            explanation=result.get("explanation"),
                            confidence=confidence,
                        )

        except Exception as e:
            logger.error(f"Contradiction detection failed: {e}")

        return ContradictionResult(has_contradiction=False)

    async def classify_relationship(
        self,
        source_id: str,
        target_id: str,
        user_id: str,
    ) -> Tuple[str, float]:
        """
        Classify the relationship type between two memories.

        Args:
            source_id: Source memory ID
            target_id: Target memory ID
            user_id: User ID for schema isolation

        Returns:
            Tuple of (relation_type, confidence)
        """
        from src.database import db
        from src.llm.client import get_llm_client

        async with db.user_context(user_id):
            rows = await db.fetch(
                """
                SELECT id, content, created_at 
                FROM raw_messages 
                WHERE id = ANY($1) AND user_id = $2
                """,
                [source_id, target_id],
                user_id,
            )

        if len(rows) < 2:
            return ("related_to", 0.5)

        memories = {row["id"]: row for row in rows}
        source = memories.get(source_id)
        target = memories.get(target_id)

        if not source or not target:
            return ("related_to", 0.5)

        try:
            llm_client = get_llm_client()

            prompt = f"""分析以下两条记忆之间的关系类型：

记忆A（较早）: {target["content"]}
时间: {target["created_at"]}

记忆B（较新）: {source["content"]}
时间: {source["created_at"]}

请判断记忆B相对于记忆A的关系类型：
- "updates": 记忆B更新了记忆A中的信息（如地址变更、状态改变）
- "extends": 记忆B扩展了记忆A的内容（添加了更多细节）
- "derives": 记忆B从记忆A衍生出来（如基于A做出的决定）
- "supersedes": 记忆B完全取代了记忆A（A已过时）
- "related_to": 记忆A和B相关但没有直接的演化关系

请以 JSON 格式返回：
{{
    "relation_type": "updates|extends|derives|supersedes|related_to",
    "confidence": 0.0-1.0,
    "explanation": "简短解释"
}}"""

            result = llm_client.extract_json(prompt, temperature=0.1)

            if result:
                relation_type = result.get("relation_type", "related_to")
                if relation_type not in self.RELATION_TYPES:
                    relation_type = "related_to"
                confidence = result.get("confidence", 0.5)
                return (relation_type, confidence)

        except Exception as e:
            logger.error(f"Relationship classification failed: {e}")

        return ("related_to", 0.5)

    async def create_relation(
        self,
        source_id: str,
        target_id: str,
        relation_type: str,
        user_id: str,
        confidence: float = 0.8,
        detected_by: str = "manual",
    ) -> str:
        """
        Create a relation record between two memories.

        Args:
            source_id: Source memory ID
            target_id: Target memory ID
            relation_type: Type of relation (updates, extends, derives, supersedes, related_to)
            user_id: User ID for schema isolation
            confidence: Confidence score (0.0-1.0)
            detected_by: Detection method (manual, llm, fusion)

        Returns:
            The created relation ID
        """
        from src.database import db

        if relation_type not in self.RELATION_TYPES:
            raise ValueError(
                f"Invalid relation_type: {relation_type}. Must be one of {self.RELATION_TYPES}"
            )

        relation_id = str(uuid.uuid4())

        async with db.user_context(user_id):
            await db.execute(
                """
                INSERT INTO memory_relations (
                    id, user_id, source_memory_id, target_memory_id,
                    relation_type, confidence, detected_by, status, created_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, 'active', NOW())
                """,
                relation_id,
                user_id,
                source_id,
                target_id,
                relation_type,
                confidence,
                detected_by,
            )

        logger.info(
            f"Created relation {relation_id}: {source_id} -> {target_id} ({relation_type})"
        )
        return relation_id

    async def get_memory_history(
        self,
        memory_id: str,
        user_id: str,
    ) -> List[Dict[str, Any]]:
        """
        Get the version chain (history) of a memory.

        Args:
            memory_id: The memory ID to get history for
            user_id: User ID for schema isolation

        Returns:
            List of memory versions in chronological order
        """
        from src.database import db

        async with db.user_context(user_id):
            rows = await db.fetch(
                """
                WITH RECURSIVE memory_chain AS (
                    -- Base case: start with the given memory
                    SELECT 
                        rm.id,
                        rm.content,
                        rm.created_at,
                        rm.is_expired,
                        0 as depth,
                        ARRAY[rm.id] as path
                    FROM raw_messages rm
                    WHERE rm.id = $1
                    
                    UNION ALL
                    
                    -- Recursive case: find related memories
                    SELECT 
                        rm.id,
                        rm.content,
                        rm.created_at,
                        rm.is_expired,
                        mc.depth + 1,
                        mc.path || rm.id
                    FROM raw_messages rm
                    JOIN memory_relations mr ON (
                        (mr.source_memory_id = rm.id AND mr.target_memory_id = mc.id)
                        OR (mr.target_memory_id = rm.id AND mr.source_memory_id = mc.id)
                    )
                    JOIN memory_chain mc ON mc.id = CASE
                        WHEN mr.source_memory_id = rm.id THEN mr.target_memory_id
                        ELSE mr.source_memory_id
                    END
                    WHERE rm.id != ALL(mc.path)
                      AND mr.relation_type IN ('updates', 'supersedes', 'derives')
                )
                SELECT DISTINCT id, content, created_at, is_expired, depth
                FROM memory_chain
                ORDER BY created_at ASC
                """,
                memory_id,
            )

        history = []
        for row in rows:
            history.append(
                {
                    "id": row["id"],
                    "content": row["content"],
                    "created_at": row["created_at"],
                    "is_expired": row["is_expired"],
                    "depth": row["depth"],
                }
            )

        return history

    async def mark_superseded(
        self,
        old_id: str,
        new_id: str,
        user_id: str,
        confidence: float = 0.9,
    ) -> Dict[str, Any]:
        """
        Mark an old memory as superseded by a new one.

        Args:
            old_id: The memory ID to mark as superseded
            new_id: The new memory ID that supersedes the old one
            user_id: User ID for schema isolation
            confidence: Confidence score for the relation

        Returns:
            Dict with operation result
        """
        from src.database import db

        async with db.user_context(user_id):
            relation_id = await self.create_relation(
                source_id=new_id,
                target_id=old_id,
                relation_type="supersedes",
                user_id=user_id,
                confidence=confidence,
                detected_by="manual",
            )

            await db.execute(
                """
                UPDATE raw_messages 
                SET is_latest = FALSE
                WHERE id = $1 AND user_id = $2
                """,
                old_id,
                user_id,
            )

            await db.execute(
                """
                UPDATE raw_messages 
                SET is_latest = TRUE
                WHERE id = $1 AND user_id = $2
                """,
                new_id,
                user_id,
            )

        logger.info(f"Marked {old_id} as superseded by {new_id}")

        return {
            "success": True,
            "relation_id": relation_id,
            "old_memory_id": old_id,
            "new_memory_id": new_id,
        }

    async def get_related_memories(
        self,
        memory_id: str,
        user_id: str,
        relation_types: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get all memories related to a given memory.

        Args:
            memory_id: The memory ID to find relations for
            user_id: User ID for schema isolation
            relation_types: Optional filter for relation types

        Returns:
            List of related memories with relation details
        """
        from src.database import db

        if relation_types is None:
            relation_types = self.RELATION_TYPES

        async with db.user_context(user_id):
            rows = await db.fetch(
                """
                SELECT 
                    mr.id as relation_id,
                    mr.source_memory_id,
                    mr.target_memory_id,
                    mr.relation_type,
                    mr.confidence,
                    mr.detected_by,
                    mr.created_at as relation_created_at,
                    CASE 
                        WHEN mr.source_memory_id = $1 THEN rm_target.content
                        ELSE rm_source.content
                    END as related_content,
                    CASE 
                        WHEN mr.source_memory_id = $1 THEN rm_target.created_at
                        ELSE rm_source.created_at
                    END as related_created_at
                FROM memory_relations mr
                LEFT JOIN raw_messages rm_source ON rm_source.id = mr.source_memory_id
                LEFT JOIN raw_messages rm_target ON rm_target.id = mr.target_memory_id
                WHERE (mr.source_memory_id = $1 OR mr.target_memory_id = $1)
                  AND mr.user_id = $2
                  AND mr.relation_type = ANY($3)
                  AND mr.status = 'active'
                ORDER BY mr.created_at DESC
                """,
                memory_id,
                user_id,
                relation_types,
            )

        related = []
        for row in rows:
            related_memory_id = (
                row["target_memory_id"]
                if row["source_memory_id"] == memory_id
                else row["source_memory_id"]
            )
            related.append(
                {
                    "relation_id": row["relation_id"],
                    "related_memory_id": related_memory_id,
                    "related_content": row["related_content"],
                    "related_created_at": row["related_created_at"],
                    "relation_type": row["relation_type"],
                    "confidence": row["confidence"],
                    "detected_by": row["detected_by"],
                    "is_outgoing": row["source_memory_id"] == memory_id,
                }
            )

        return related

    async def delete_relation(
        self,
        relation_id: str,
        user_id: str,
    ) -> bool:
        """
        Delete a relation (mark as inactive).

        Args:
            relation_id: The relation ID to delete
            user_id: User ID for schema isolation

        Returns:
            True if deleted successfully
        """
        from src.database import db

        async with db.user_context(user_id):
            result = await db.execute(
                """
                UPDATE memory_relations 
                SET status = 'inactive'
                WHERE id = $1 AND user_id = $2
                """,
                relation_id,
                user_id,
            )

        return result == "UPDATE 1"


# Singleton instance
memory_relation_service = MemoryRelationService()
