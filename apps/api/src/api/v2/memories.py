from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any

from src.services.core.memory_store import memory_store
from src.services.core.profile_service import profile_service
from src.services.core.relation_service import relation_service
from src.services.core.document_store import document_store

router = APIRouter(prefix="/v1", tags=["Memories"])


class CreateMemoryRequest(BaseModel):
    content: str = Field(..., description="Memory content", examples=["我喜欢喝咖啡"])
    container_tag: str = Field(
        ..., description="Container tag for isolation", examples=["user_001"]
    )
    is_static: bool = Field(
        False,
        description="Whether this is a permanent trait (name, preference) vs recent activity",
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Additional metadata"
    )


class MemoryResponse(BaseModel):
    id: str = Field(..., description="Memory ID", examples=["mem_abc123"])
    content: str = Field(..., description="Memory content")
    container_tag: str = Field(..., description="Container tag")
    is_static: bool = Field(..., description="Is static memory")
    created_at: Optional[str] = Field(None, description="Creation timestamp")


class SearchRequest(BaseModel):
    query: str = Field(..., description="Search query", examples=["饮食偏好"])
    container_tag: str = Field(..., description="Container tag to search in")
    limit: int = Field(10, ge=1, le=100, description="Max results")
    threshold: float = Field(
        0.6, ge=0.0, le=1.0, description="Similarity threshold (0-1)"
    )


class UpdateMemoryRequest(BaseModel):
    content: str = Field(
        ..., description="New memory content", examples=["我现在在 Supermemory 工作"]
    )


class CreateDocumentRequest(BaseModel):
    content: str = Field(..., description="Document content")
    container_tag: str = Field(..., description="Container tag for isolation")
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Additional metadata"
    )


@router.post(
    "/memories",
    summary="Create a new memory",
    description="Store a new memory with automatic entity extraction and relation detection. Use is_static=true for permanent traits.",
    responses={
        200: {
            "description": "Memory created successfully",
            "content": {
                "application/json": {
                    "example": {
                        "id": "mem_abc123",
                        "content": "我喜欢喝咖啡",
                        "container_tag": "user_001",
                        "is_static": True,
                        "created_at": "2024-01-15T10:30:00",
                    }
                }
            },
        }
    },
)
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


@router.get(
    "/memories",
    summary="List memories",
    description="List all memories for a container, ordered by creation date (newest first).",
    responses={
        200: {
            "description": "List of memories",
            "content": {
                "application/json": {
                    "example": {
                        "memories": [
                            {
                                "id": "mem_abc123",
                                "content": "我喜欢喝咖啡",
                                "is_static": True,
                                "created_at": "2024-01-15T10:30:00",
                            }
                        ],
                        "count": 1,
                    }
                }
            },
        }
    },
)
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


@router.get(
    "/memories/{memory_id}",
    summary="Get memory by ID",
    description="Retrieve a single memory with full details including metadata.",
    responses={
        200: {"description": "Memory details"},
        404: {"description": "Memory not found"},
    },
)
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


@router.post(
    "/memories/{memory_id}/forget",
    summary="Soft delete a memory",
    description="Mark a memory as forgotten (soft delete). It can be restored later.",
    responses={
        200: {"description": "Memory forgotten"},
        404: {"description": "Memory not found"},
    },
)
async def forget_memory(memory_id: str):
    memory = await memory_store.get_by_id(memory_id)
    if not memory:
        raise HTTPException(status_code=404, detail="Memory not found")

    success = await memory_store.forget(memory_id)
    if success:
        await profile_service.invalidate_cache(memory.container_tag)

    return {"id": memory_id, "forgotten": success}


@router.post(
    "/memories/{memory_id}/restore",
    summary="Restore a forgotten memory",
    description="Restore a previously forgotten memory.",
    responses={
        200: {"description": "Memory restored"},
        404: {"description": "Memory not found"},
    },
)
async def restore_memory(memory_id: str):
    memory = await memory_store.get_by_id(memory_id)
    if not memory:
        raise HTTPException(status_code=404, detail="Memory not found")

    success = await memory_store.restore(memory_id)
    if success:
        await profile_service.invalidate_cache(memory.container_tag)

    return {"id": memory_id, "restored": success}


@router.post(
    "/memories/{memory_id}/update",
    summary="Create a new version of a memory",
    description="Create an updated version of a memory. The old memory will be marked as is_latest=false and an 'updates' relation will be created.",
    responses={
        200: {"description": "New version created"},
        404: {"description": "Memory not found"},
    },
)
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


@router.get(
    "/memories/{memory_id}/history",
    summary="Get memory version history",
    description="Get the version history of a memory, showing all previous versions linked by 'updates' relations.",
    responses={
        200: {"description": "Version history"},
        404: {"description": "Memory not found"},
    },
)
async def get_memory_history(memory_id: str):
    memory = await memory_store.get_by_id(memory_id)
    if not memory:
        raise HTTPException(status_code=404, detail="Memory not found")

    history = await relation_service.get_version_history(memory_id)

    return {"memory_id": memory_id, "history": history}


@router.get(
    "/profile",
    summary="Get user profile",
    description="Get the aggregated user profile with static (permanent traits) and dynamic (recent activities) memories. Optionally search within the profile.",
    responses={
        200: {
            "description": "User profile",
            "content": {
                "application/json": {
                    "example": {
                        "profile": {
                            "static": ["John Doe", "喜欢喝咖啡"],
                            "dynamic": ["最近在做一个认证迁移项目"],
                        },
                        "searchResults": [],
                    }
                }
            },
        }
    },
)
async def get_profile(
    container_tag: str = Query(..., description="Container tag"),
    query: Optional[str] = Query(
        None, description="Optional search query to find relevant memories"
    ),
    max_static: int = Query(10, ge=1, le=50, description="Max static facts to return"),
    max_dynamic: int = Query(
        10, ge=1, le=50, description="Max dynamic facts to return"
    ),
):
    profile = await profile_service.get_profile(
        container_tag=container_tag,
        query=query,
        max_static=max_static,
        max_dynamic=max_dynamic,
    )

    return profile


@router.post(
    "/search",
    summary="Search memories",
    description="Semantic search across memories using vector similarity. Returns memories ranked by relevance.",
    responses={
        200: {
            "description": "Search results",
            "content": {
                "application/json": {
                    "example": {
                        "query": "饮食偏好",
                        "results": [
                            {
                                "id": "mem_abc123",
                                "content": "我喜欢喝咖啡",
                                "similarity": 0.92,
                            }
                        ],
                        "count": 1,
                    }
                }
            },
        }
    },
)
async def search_memories(request: SearchRequest):
    results = await memory_store.search(
        query=request.query,
        container_tag=request.container_tag,
        limit=request.limit,
        threshold=request.threshold,
    )

    return {"query": request.query, "results": results, "count": len(results)}


@router.post(
    "/documents",
    summary="Create a new document",
    description="Store a document for later processing or reference.",
    responses={200: {"description": "Document created"}},
)
async def create_document(request: CreateDocumentRequest):
    document = await document_store.create(
        content=request.content,
        container_tag=request.container_tag,
        metadata=request.metadata,
    )

    return {
        "id": document.id,
        "content": document.content,
        "container_tag": document.container_tag,
        "status": document.status,
        "created_at": document.created_at.isoformat() if document.created_at else None,
    }


@router.get(
    "/documents",
    summary="List documents",
    description="List all documents for a container with pagination support.",
    responses={200: {"description": "List of documents"}},
)
async def list_documents(
    container_tag: str = Query(..., description="Container tag"),
    limit: int = Query(20, ge=1, le=100, description="Max results"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
):
    documents = await document_store.get_by_container(
        container_tag=container_tag,
        limit=limit,
        offset=offset,
    )

    total = await document_store.count(container_tag)

    return {
        "documents": [
            {
                "id": d.id,
                "content": d.content[:500] + "..."
                if len(d.content) > 500
                else d.content,
                "status": d.status,
                "created_at": d.created_at.isoformat() if d.created_at else None,
            }
            for d in documents
        ],
        "count": len(documents),
        "total": total,
        "offset": offset,
    }


@router.get(
    "/documents/{document_id}",
    summary="Get document by ID",
    description="Retrieve a single document with full content.",
    responses={
        200: {"description": "Document details"},
        404: {"description": "Document not found"},
    },
)
async def get_document(document_id: str):
    document = await document_store.get_by_id(document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    return {
        "id": document.id,
        "content": document.content,
        "container_tag": document.container_tag,
        "metadata": document.metadata,
        "status": document.status,
        "created_at": document.created_at.isoformat() if document.created_at else None,
    }


@router.delete(
    "/documents/{document_id}",
    summary="Delete a document",
    description="Permanently delete a document.",
    responses={
        200: {"description": "Document deleted"},
        404: {"description": "Document not found"},
    },
)
async def delete_document(document_id: str):
    document = await document_store.get_by_id(document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    success = await document_store.delete(document_id)

    return {"id": document_id, "deleted": success}
