"""
Memory Management Endpoints

POST   /v1/memories              - Create memory
GET    /v1/memories              - List memories
GET    /v1/memories/{id}         - Get memory
PATCH  /v1/memories/{id}         - Update metadata
DELETE /v1/memories/{id}         - Delete memory
POST   /v1/memories/{id}/forget  - Mark as forgotten
"""

from fastapi import APIRouter, HTTPException, Depends, Query
from typing import Optional
from datetime import datetime

from ...models.api import (
    MemoryCreate,
    MemoryUpdate,
    MemoryResponse,
    MemoryListResponse,
)
from ..auth import get_current_user, require_permission, check_rate_limit

router = APIRouter(prefix="/memories", tags=["Memories"])


def _row_to_response(row: dict) -> MemoryResponse:
    return MemoryResponse(
        id=row["id"],
        content=row["content"],
        memory_type=row.get("memory_type", "preference"),
        memory_behavior=row.get("memory_behavior", "episode"),
        memory_lifespan=row.get("memory_lifespan", "long_term"),
        event_date=row.get("event_date"),
        created_at=row.get("created_at"),
        updated_at=row.get("updated_at"),
        expiration_date=row.get("expiration_date"),
        is_latest=row.get("is_latest", True),
        is_expired=row.get("is_expired", False),
        tags=row.get("tags", []),
        importance_score=row.get("importance_score", 0.5),
        access_count=row.get("access_count", 0),
        container_id=row.get("container_id"),
        token_count=row.get("token_count", 0),
        chunk_count=row.get("chunk_count", 0),
    )


@router.post(
    "",
    response_model=MemoryResponse,
    summary="Create Memory",
    description="Create a new memory",
)
async def create_memory(
    request: MemoryCreate,
    current_user: dict = Depends(require_permission("write")),
    _: dict = Depends(check_rate_limit),
):
    """
    Create a new memory

    - **content**: Memory content (required)
    - **memory_type**: preference, note, or dialogue
    - **memory_behavior**: fact, preference, or episode
    - **memory_lifespan**: temporary, short_term, long_term, or permanent
    """
    from src.services.unified_memory_service import unified_memory_service
    from src.database import db

    user_id = current_user["user_id"]
    db.set_current_user(user_id)

    try:
        result = await unified_memory_service.store(
            user_id=user_id,
            content=request.content,
            source="manual",
            memory_type=request.memory_type,
            metadata={
                "memory_behavior": request.memory_behavior,
                "memory_lifespan": request.memory_lifespan,
                "event_date": request.event_date.isoformat()
                if request.event_date
                else None,
                "location_name": request.location_name,
                "tags": request.tags,
                "container_id": request.container_id,
            },
        )

        memory_data = await unified_memory_service.get_memory_by_id(
            result["raw_message_id"]
        )

        if not memory_data:
            raise HTTPException(
                status_code=500, detail="Failed to fetch created memory"
            )

        return _row_to_response(memory_data)

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "",
    response_model=MemoryListResponse,
    summary="List Memories",
    description="List memories with pagination",
)
async def list_memories(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    memory_type: Optional[str] = Query(None),
    container_id: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user),
):
    """
    List memories with pagination

    - **limit**: Items per page (1-100)
    - **offset**: Pagination offset
    - **memory_type**: Filter by type
    - **container_id**: Filter by container
    """
    from src.services.unified_memory_service import unified_memory_service
    from src.database import db

    user_id = current_user["user_id"]
    db.set_current_user(user_id)

    memories = await unified_memory_service.get_user_memories(
        user_id, limit + offset + 1
    )

    if memory_type:
        memories = [m for m in memories if m.get("memory_type") == memory_type]
    if container_id:
        memories = [m for m in memories if m.get("container_id") == container_id]

    total = len(memories)
    memories = memories[offset : offset + limit]

    return MemoryListResponse(
        memories=[_row_to_response(m) for m in memories],
        total=total,
        has_more=offset + limit < total,
    )


@router.get(
    "/{memory_id}",
    response_model=MemoryResponse,
    summary="Get Memory",
    description="Get a single memory by ID",
)
async def get_memory(
    memory_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Get a single memory by ID"""
    from src.services.unified_memory_service import unified_memory_service
    from src.database import db

    user_id = current_user["user_id"]
    db.set_current_user(user_id)

    memory = await unified_memory_service.get_memory_by_id(memory_id)

    if not memory:
        raise HTTPException(status_code=404, detail="Memory not found")

    await db.execute(
        """
        UPDATE raw_messages 
        SET access_count = access_count + 1, last_accessed_at = NOW()
        WHERE id = $1
        """,
        memory_id,
    )

    return _row_to_response(memory)


@router.patch(
    "/{memory_id}",
    response_model=MemoryResponse,
    summary="Update Memory",
    description="Update memory metadata",
)
async def update_memory(
    memory_id: str,
    request: MemoryUpdate,
    current_user: dict = Depends(require_permission("write")),
):
    """Update memory metadata"""
    from src.database import db

    user_id = current_user["user_id"]
    db.set_current_user(user_id)

    updates = []
    params = []
    idx = 1

    if request.tags is not None:
        updates.append(f"tags = ${idx}")
        params.append(request.tags)
        idx += 1

    if request.importance_score is not None:
        updates.append(f"importance_score = ${idx}")
        params.append(request.importance_score)
        idx += 1

    if request.memory_lifespan is not None:
        updates.append(f"memory_lifespan = ${idx}")
        params.append(request.memory_lifespan)
        idx += 1

    if request.expiration_date is not None:
        updates.append(f"expiration_date = ${idx}")
        params.append(request.expiration_date)
        idx += 1

    if not updates:
        raise HTTPException(status_code=400, detail="No updates provided")

    params.append(memory_id)

    result = await db.execute(
        f"UPDATE raw_messages SET {', '.join(updates)} WHERE id = ${idx}",
        *params,
    )

    if result == 0:
        raise HTTPException(status_code=404, detail="Memory not found")

    row = await db.fetchrow("SELECT * FROM raw_messages WHERE id = $1", memory_id)
    return _row_to_response(dict(row))


@router.delete(
    "/{memory_id}",
    summary="Delete Memory",
    description="Soft delete a memory",
)
async def delete_memory(
    memory_id: str,
    current_user: dict = Depends(require_permission("delete")),
):
    """Soft delete a memory"""
    from src.services.unified_memory_service import unified_memory_service
    from src.database import db

    user_id = current_user["user_id"]
    db.set_current_user(user_id)

    success = await unified_memory_service.delete_memory(memory_id)

    if not success:
        raise HTTPException(status_code=404, detail="Memory not found")

    return {"success": True, "message": f"Memory {memory_id} deleted"}


@router.post(
    "/{memory_id}/forget",
    summary="Forget Memory",
    description="Mark a memory as forgotten (expired)",
)
async def forget_memory(
    memory_id: str,
    current_user: dict = Depends(require_permission("write")),
):
    """Mark a memory as forgotten"""
    from src.database import db

    user_id = current_user["user_id"]
    db.set_current_user(user_id)

    result = await db.execute(
        """
        UPDATE raw_messages 
        SET is_expired = TRUE, expiration_date = NOW()
        WHERE id = $1
        """,
        memory_id,
    )

    if result == 0:
        raise HTTPException(status_code=404, detail="Memory not found")

    return {"success": True, "message": f"Memory {memory_id} marked as forgotten"}
