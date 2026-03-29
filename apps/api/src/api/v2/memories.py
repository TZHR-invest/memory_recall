from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any

from src.services.core.memory_store import memory_store
from src.services.core.profile_service import profile_service
from src.services.core.relation_service import relation_service

router = APIRouter(prefix="/v1", tags=["Memories"])


class CreateMemoryRequest(BaseModel):
    content: str = Field(..., description="Memory content")
    container_tag: str = Field(..., description="Container tag for isolation")
    is_static: bool = Field(False, description="Whether this is a permanent trait")
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Additional metadata"
    )


class SearchRequest(BaseModel):
    query: str = Field(..., description="Search query")
    container_tag: str = Field(..., description="Container tag to search in")
    limit: int = Field(10, ge=1, le=100, description="Max results")
    threshold: float = Field(0.6, ge=0.0, le=1.0, description="Similarity threshold")


class UpdateMemoryRequest(BaseModel):
    content: str = Field(..., description="New memory content")


@router.post("/memories")
async def create_memory(request: CreateMemoryRequest):
    memory = await memory_store.create(
        content=request.content,
        container_tag=request.container_tag,
        is_static=request.is_static,
        metadata=request.metadata,
    )

    await profile_service.invalidate_cache(request.container_tag)

    return {
        "id": memory.id,
        "content": memory.content,
        "container_tag": memory.container_tag,
        "is_static": memory.is_static,
        "created_at": memory.created_at.isoformat() if memory.created_at else None,
    }


@router.get("/memories")
async def list_memories(
    container_tag: str = Query(..., description="Container tag"),
    limit: int = Query(20, ge=1, le=100, description="Max results"),
):
    memories = await memory_store.get_by_container(
        container_tag=container_tag,
        limit=limit,
    )

    return {
        "memories": [
            {
                "id": m.id,
                "content": m.content,
                "is_static": m.is_static,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
            for m in memories
        ],
        "count": len(memories),
    }


@router.get("/memories/{memory_id}")
async def get_memory(memory_id: str):
    memory = await memory_store.get_by_id(memory_id)
    if not memory:
        raise HTTPException(status_code=404, detail="Memory not found")

    return {
        "id": memory.id,
        "content": memory.content,
        "container_tag": memory.container_tag,
        "is_static": memory.is_static,
        "is_latest": memory.is_latest,
        "metadata": memory.metadata,
        "created_at": memory.created_at.isoformat() if memory.created_at else None,
        "is_forgotten": memory.is_forgotten,
    }


@router.post("/memories/{memory_id}/forget")
async def forget_memory(memory_id: str):
    memory = await memory_store.get_by_id(memory_id)
    if not memory:
        raise HTTPException(status_code=404, detail="Memory not found")

    success = await memory_store.forget(memory_id)
    if success:
        await profile_service.invalidate_cache(memory.container_tag)

    return {"id": memory_id, "forgotten": success}


@router.post("/memories/{memory_id}/restore")
async def restore_memory(memory_id: str):
    memory = await memory_store.get_by_id(memory_id)
    if not memory:
        raise HTTPException(status_code=404, detail="Memory not found")

    success = await memory_store.restore(memory_id)
    if success:
        await profile_service.invalidate_cache(memory.container_tag)

    return {"id": memory_id, "restored": success}


@router.post("/memories/{memory_id}/update")
async def update_memory(memory_id: str, request: UpdateMemoryRequest):
    old_memory = await memory_store.get_by_id(memory_id)
    if not old_memory:
        raise HTTPException(status_code=404, detail="Memory not found")

    new_memory = await memory_store.create_update_version(
        memory_id=memory_id,
        new_content=request.content,
    )

    if new_memory:
        await profile_service.invalidate_cache(old_memory.container_tag)

    return {
        "id": new_memory.id,
        "content": new_memory.content,
        "old_id": memory_id,
        "relation": "updates",
    }


@router.get("/memories/{memory_id}/history")
async def get_memory_history(memory_id: str):
    memory = await memory_store.get_by_id(memory_id)
    if not memory:
        raise HTTPException(status_code=404, detail="Memory not found")

    history = await relation_service.get_version_history(memory_id)

    return {"memory_id": memory_id, "history": history}


@router.get("/profile")
async def get_profile(
    container_tag: str = Query(..., description="Container tag"),
    query: Optional[str] = Query(None, description="Optional search query"),
    max_static: int = Query(10, ge=1, le=50, description="Max static facts"),
    max_dynamic: int = Query(10, ge=1, le=50, description="Max dynamic facts"),
):
    profile = await profile_service.get_profile(
        container_tag=container_tag,
        query=query,
        max_static=max_static,
        max_dynamic=max_dynamic,
    )

    return profile


@router.post("/search")
async def search_memories(request: SearchRequest):
    results = await memory_store.search(
        query=request.query,
        container_tag=request.container_tag,
        limit=request.limit,
        threshold=request.threshold,
    )

    return {"query": request.query, "results": results, "count": len(results)}
