"""
Relations Endpoints

GET  /v1/memories/{id}/relations - Get memory relations
POST /v1/memories/{id}/relations - Create relation
GET  /v1/memories/{id}/history   - Get version chain
"""

from fastapi import APIRouter, HTTPException, Depends
from datetime import datetime
import uuid

from ...models.api import MemoryRelationCreate, MemoryRelationResponse
from ..auth import get_current_user, require_permission

router = APIRouter(tags=["Relations"])


@router.get(
    "/memories/{memory_id}/relations",
    response_model=list[MemoryRelationResponse],
    summary="Get Memory Relations",
    description="Get all relations for a memory",
)
async def get_relations(
    memory_id: str,
    current_user: dict = Depends(get_current_user),
):
    from src.database import db

    user_id = current_user["user_id"]

    rows = await db.fetch(
        """
        SELECT * FROM memory_relations
        WHERE user_id = $1 AND (source_memory_id = $2 OR target_memory_id = $2)
        ORDER BY created_at DESC
        """,
        user_id,
        memory_id,
    )

    return [
        MemoryRelationResponse(
            id=row["id"],
            source_memory_id=row["source_memory_id"],
            target_memory_id=row["target_memory_id"],
            relation_type=row["relation_type"],
            confidence=row["confidence"],
            detected_by=row["detected_by"],
            created_at=row["created_at"],
        )
        for row in rows
    ]


@router.post(
    "/memories/{memory_id}/relations",
    response_model=MemoryRelationResponse,
    summary="Create Relation",
    description="Create a relation between memories",
)
async def create_relation(
    memory_id: str,
    request: MemoryRelationCreate,
    current_user: dict = Depends(require_permission("write")),
):
    from src.database import db

    user_id = current_user["user_id"]

    if memory_id != request.source_memory_id:
        raise HTTPException(400, "memory_id must match source_memory_id")

    relation_id = str(uuid.uuid4())
    now = datetime.utcnow()

    await db.execute(
        """
        INSERT INTO memory_relations (id, user_id, source_memory_id, target_memory_id, relation_type, confidence, detected_by, created_at)
        VALUES ($1, $2, $3, $4, $5, $6, 'manual', $7)
        """,
        relation_id,
        user_id,
        request.source_memory_id,
        request.target_memory_id,
        request.relation_type,
        request.confidence,
        now,
    )

    return MemoryRelationResponse(
        id=relation_id,
        source_memory_id=request.source_memory_id,
        target_memory_id=request.target_memory_id,
        relation_type=request.relation_type,
        confidence=request.confidence,
        detected_by="manual",
        created_at=now,
    )


@router.get(
    "/memories/{memory_id}/history",
    summary="Get Memory History",
    description="Get version chain for a memory",
)
async def get_history(
    memory_id: str,
    current_user: dict = Depends(get_current_user),
):
    from src.database import db

    user_id = current_user["user_id"]

    rows = await db.fetch(
        """
        WITH RECURSIVE history AS (
            SELECT id, content, created_at, container_id, 0 as depth
            FROM raw_messages WHERE id = $1 AND user_id = $2
            
            UNION ALL
            
            SELECT r.id, r.content, r.created_at, r.container_id, h.depth + 1
            FROM raw_messages r
            JOIN memory_relations mr ON mr.target_memory_id = r.id
            JOIN history h ON h.id = mr.source_memory_id
            WHERE mr.relation_type = 'supersedes' AND mr.user_id = $2
        )
        SELECT * FROM history ORDER BY depth
        """,
        memory_id,
        user_id,
    )

    return {
        "memory_id": memory_id,
        "history": [
            {
                "id": row["id"],
                "content": row["content"][:100] + "..."
                if len(row["content"] or "") > 100
                else row["content"],
                "created_at": row["created_at"],
                "depth": row["depth"],
            }
            for row in rows
        ],
        "total_versions": len(rows),
    }
