import uuid
import json
from typing import Optional, List, Dict, Any
from datetime import datetime

from src.database import db
from src.models.lossless import RawMessage, MemoryType


class RawMessageStore:
    def generate_id(self) -> str:
        return f"raw_{uuid.uuid4().hex[:16]}"

    def estimate_tokens(self, text: str) -> int:
        return max(1, len(text) // 4)

    async def store(
        self,
        user_id: str,
        content: str,
        memory_type: MemoryType = "preference",
        agent_id: Optional[str] = None,
        session_id: Optional[str] = None,
        document_id: Optional[str] = None,
        role: str = "user",
        time_value: Optional[datetime] = None,
        location_name: Optional[str] = None,
        location_address: Optional[str] = None,
        location_latitude: Optional[float] = None,
        location_longitude: Optional[float] = None,
        people: Optional[List[Dict]] = None,
        emotion: Optional[Dict] = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict] = None,
        source_type: str = "manual",
        input_type: str = "text",
        importance_score: float = 0.5,
    ) -> str:
        raw_id = self.generate_id()
        token_count = self.estimate_tokens(content)

        await db.execute(
            """
            INSERT INTO raw_messages (
                id, user_id, agent_id, memory_type, session_id, document_id,
                role, content, token_count, time_value, 
                location_name, location_address, location_latitude, location_longitude,
                people, emotion, tags, metadata, source_type, input_type, importance_score
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19, $20, $21)
        """,
            raw_id,
            user_id,
            agent_id,
            memory_type,
            session_id,
            document_id,
            role,
            content,
            token_count,
            time_value,
            location_name,
            location_address,
            location_latitude,
            location_longitude,
            json.dumps(people or []),
            json.dumps(emotion or {}),
            json.dumps(tags or []),
            json.dumps(metadata or {}),
            source_type,
            input_type,
            importance_score,
        )

        return raw_id

    async def get_by_id(self, raw_id: str) -> Optional[RawMessage]:
        row = await db.fetchrow("SELECT * FROM raw_messages WHERE id = $1", raw_id)

        if not row:
            return None

        return self._row_to_model(row)

    async def get_by_session(
        self, user_id: str, session_id: str, limit: int = 100
    ) -> List[RawMessage]:
        rows = await db.fetch(
            """
            SELECT * FROM raw_messages
            WHERE user_id = $1 AND session_id = $2
            ORDER BY created_at ASC
            LIMIT $3
        """,
            user_id,
            session_id,
            limit,
        )

        return [self._row_to_model(row) for row in rows]

    async def get_by_document(self, document_id: str, user_id: str) -> List[RawMessage]:
        rows = await db.fetch(
            """
            SELECT * FROM raw_messages
            WHERE document_id = $1 AND user_id = $2
            ORDER BY created_at ASC
        """,
            document_id,
            user_id,
        )

        return [self._row_to_model(row) for row in rows]

    async def update_embedding(self, raw_id: str, embedding: List[float]) -> None:
        embedding_str = "[" + ",".join(map(str, embedding)) + "]"

        await db.execute(
            """
            UPDATE raw_messages SET embedding = $1 WHERE id = $2
        """,
            embedding_str,
            raw_id,
        )

    async def get_fresh_tail(
        self, user_id: str, session_id: str, count: int = 8
    ) -> List[RawMessage]:
        rows = await db.fetch(
            """
            SELECT rm.* FROM raw_messages rm
            JOIN context_items ci ON ci.message_id = rm.id
            WHERE ci.user_id = $1 AND ci.session_id = $2
              AND ci.item_type = 'message'
            ORDER BY ci.ordinal DESC
            LIMIT $3
        """,
            user_id,
            session_id,
            count,
        )

        return [self._row_to_model(row) for row in reversed(rows)]

    async def get_by_agent(
        self, user_id: str, agent_id: str, limit: int = 100
    ) -> List[RawMessage]:
        rows = await db.fetch(
            """
            SELECT * FROM raw_messages
            WHERE user_id = $1 AND agent_id = $2
            ORDER BY created_at DESC
            LIMIT $3
        """,
            user_id,
            agent_id,
            limit,
        )

        return [self._row_to_model(row) for row in rows]

    async def get_user_preferences(
        self, user_id: str, limit: int = 100
    ) -> List[RawMessage]:
        rows = await db.fetch(
            """
            SELECT * FROM raw_messages
            WHERE user_id = $1 AND agent_id IS NULL
            ORDER BY created_at DESC
            LIMIT $2
        """,
            user_id,
            limit,
        )

        return [self._row_to_model(row) for row in rows]

    async def delete(self, raw_id: str) -> bool:
        result = await db.execute("DELETE FROM raw_messages WHERE id = $1", raw_id)
        return result == "DELETE 1"

    async def archive(self, raw_id: str) -> bool:
        result = await db.execute(
            """
            UPDATE raw_messages 
            SET is_archived = TRUE 
            WHERE id = $1
        """,
            raw_id,
        )
        return result == "UPDATE 1"

    def _row_to_model(self, row: Dict[str, Any]) -> RawMessage:
        tags = row.get("tags", [])
        if isinstance(tags, str):
            tags = json.loads(tags)

        metadata = row.get("metadata", {})
        if isinstance(metadata, str):
            metadata = json.loads(metadata)

        people = row.get("people", [])
        if isinstance(people, str):
            people = json.loads(people)

        emotion = row.get("emotion", {})
        if isinstance(emotion, str):
            emotion = json.loads(emotion)

        embedding = row.get("embedding")
        if embedding and isinstance(embedding, str):
            embedding = json.loads(embedding)

        return RawMessage(
            id=row["id"],
            user_id=row["user_id"],
            agent_id=row["agent_id"],
            memory_type=row["memory_type"],
            session_id=row["session_id"],
            document_id=row["document_id"],
            role=row["role"],
            content=row["content"],
            token_count=row["token_count"],
            embedding=embedding,
            time_value=row["time_value"],
            time_source=row["time_source"],
            location_name=row["location_name"],
            location_address=row.get("location_address"),
            location_latitude=row.get("location_latitude"),
            location_longitude=row.get("location_longitude"),
            people=people,
            emotion=emotion,
            tags=tags,
            metadata=metadata,
            source_type=row.get("source_type", "manual"),
            input_type=row.get("input_type", "text"),
            importance_score=row.get("importance_score", 0.5),
            created_at=row["created_at"],
            is_archived=row["is_archived"],
        )


raw_message_store = RawMessageStore()
