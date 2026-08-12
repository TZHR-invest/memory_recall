from fastapi import APIRouter, HTTPException, Query, Depends, BackgroundTasks
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any

from src.services.core.memory_store import memory_store
from src.services.core.profile_service import profile_service
from src.services.core.relation_service import relation_service
from src.services.core.document_store import document_store
from src.database import db
from src.api.auth import (
    require_permission,
    check_rate_limit,
    verify_container_ownership,
)

router = APIRouter(tags=["Memories"])


class CreateMemoryRequest(BaseModel):
    content: str = Field(..., description="Memory content", examples=["我喜欢喝咖啡"])
    container_tag: Optional[str] = Field(
        None,
        description="Container tag (optional, defaults to your API key's container)",
    )
    is_static: bool = Field(
        False,
        description="Whether this is a permanent trait (name, preference) vs recent activity",
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Additional metadata"
    )
    entity_context: Optional[str] = Field(
        None,
        description="Per-container context to guide entity extraction (max 1500 chars). Persists for subsequent extractions in this container.",
        examples=["设计探索对话，关注用户的UI偏好和品牌需求"],
    )
    skip_extraction: bool = Field(
        False,
        description="Skip LLM entity extraction (faster for large documents)",
    )
    async_process: bool = Field(
        False,
        description="Process entity extraction and relation creation in background (faster response, returns status='processing')",
    )


class MemoryResponse(BaseModel):
    id: str = Field(..., description="Memory ID", examples=["mem_abc123"])
    content: str = Field(..., description="Memory content")
    container_tag: str = Field(..., description="Container tag")
    is_static: bool = Field(..., description="Is static memory")
    created_at: Optional[str] = Field(None, description="Creation timestamp")


class SearchRequest(BaseModel):
    query: str = Field(..., description="Search query", examples=["饮食偏好"])
    container_tag: Optional[str] = Field(
        None,
        description="Container tag (optional, defaults to your API key's container)",
    )
    limit: int = Field(10, ge=1, le=100, description="Max results")
    threshold: float = Field(
        0.3, ge=0.0, le=1.0, description="Similarity threshold (0-1)"
    )


class UpdateMemoryRequest(BaseModel):
    content: str = Field(
        ..., description="New memory content", examples=["我现在在 Supermemory 工作"]
    )


class CreateDocumentRequest(BaseModel):
    content: str = Field(..., description="Document content")
    container_tag: Optional[str] = Field(
        None,
        description="Container tag (optional, defaults to your API key's container)",
    )
    title: Optional[str] = Field(None, description="Document title")
    source: Optional[str] = Field(None, description="Document source (e.g., file path)")
    doc_type: str = Field("text", description="Document type")
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Additional metadata"
    )


class ChunkSearchRequest(BaseModel):
    query: str = Field(
        ..., description="Search query for document chunks", examples=["how to deploy"]
    )
    container_tag: Optional[str] = Field(
        None,
        description="Container tag (optional, defaults to your API key's container)",
    )
    limit: int = Field(10, ge=1, le=100, description="Max results")
    threshold: float = Field(
        0.5, ge=0.0, le=1.0, description="Similarity threshold (0-1)"
    )
    doc_types: Optional[List[str]] = Field(
        None, description="Filter by document types (e.g., ['markdown', 'code'])"
    )


class ChunkSearchResult(BaseModel):
    id: str = Field(..., description="Chunk ID")
    content: str = Field(..., description="Chunk content (truncated to 500 chars)")
    document_id: str = Field(..., description="Parent document ID")
    document_title: Optional[str] = Field(None, description="Document title")
    document_type: Optional[str] = Field(None, description="Document type")
    position: Optional[int] = Field(None, description="Chunk position in document")
    similarity: float = Field(..., description="Similarity score (0-1)")


class HybridSearchRequest(BaseModel):
    query: str = Field(
        ..., description="Search query", examples=["deployment instructions"]
    )
    container_tag: Optional[str] = Field(
        None,
        description="Container tag (optional, defaults to your API key's container)",
    )
    limit: int = Field(10, ge=1, le=100, description="Max results")
    threshold: float = Field(
        0.5, ge=0.0, le=1.0, description="Similarity threshold (0-1)"
    )
    sources: Optional[List[str]] = Field(
        None, description="Filter by source types: ['memory'], ['chunk'], or both"
    )


class HybridSearchResult(BaseModel):
    id: str = Field(..., description="Memory or Chunk ID")
    content: str = Field(..., description="Content (truncated for display)")
    source: str = Field(..., description="Source type: 'memory' or 'chunk'")
    similarity: float = Field(..., description="Similarity score (0-1)")
    document_title: Optional[str] = Field(
        None, description="Document title (for chunks)"
    )
    document_type: Optional[str] = Field(None, description="Document type (for chunks)")


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
async def create_memory(
    request: CreateMemoryRequest,
    background_tasks: BackgroundTasks,
    current_user: Dict = Depends(require_permission("write")),
    _: Dict = Depends(check_rate_limit),
):
    container_tag = request.container_tag or current_user["container_tag"]

    verify_container_ownership(container_tag, current_user["key_id"])

    # 自动分类：type=preference 时强制为永久特征
    is_static = request.is_static
    if not is_static and request.metadata.get("type") == "preference":
        is_static = True

    # 写入分类标记（审计用，不改 is_static）：行为规则 vs 临时记录（配置/一次性事件）
    # 与 context_inject_service.TRANSIENT_STATIC_MARKERS 共用同一套标记，防读/写漂移
    if is_static:
        import re
        from src.services.core.context_inject_service import (
            TRANSIENT_STATIC_MARKERS,
        )

        request.metadata["_classification"] = (
            "config_record"
            if any(
                re.search(m, request.content) for m in TRANSIENT_STATIC_MARKERS
            )
            else "behavior_rule"
        )

    entity_context = request.entity_context

    if entity_context:
        await profile_service.set_entity_context(
            container_tag=container_tag,
            entity_context=entity_context,
        )
    else:
        entity_context = await profile_service.get_entity_context(container_tag)

    memory = await memory_store.create(
        content=request.content,
        container_tag=container_tag,
        is_static=is_static,
        metadata=request.metadata,
        entity_context=entity_context,
        extract_entities=not request.skip_extraction,
        async_process=request.async_process,
        generate_embedding=not request.async_process,
    )

    # 异步模式：后台处理实体提取和关系创建
    if request.async_process:
        background_tasks.add_task(memory_store.process_embedding_async, memory.id)
    else:
        await profile_service.invalidate_cache(container_tag)

    # 确定 status
    status = "done"
    if request.async_process:
        status = memory.metadata.get("_status", "processing")

    return {
        "id": memory.id,
        "content": memory.content,
        "container_tag": memory.container_tag,
        "is_static": memory.is_static,
        "created_at": memory.created_at.isoformat() if memory.created_at else None,
        "status": status,
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
    container_tag: Optional[str] = Query(None, description="Container tag (optional)"),
    limit: int = Query(20, ge=1, le=100, description="Max results"),
    current_user: Dict = Depends(require_permission("read")),
    _: Dict = Depends(check_rate_limit),
):
    container_tag = container_tag or current_user["container_tag"]
    verify_container_ownership(container_tag, current_user["key_id"])

    # 先查总数（不受 limit 影响）
    total = await db.fetchval(
        "SELECT COUNT(*) FROM memories WHERE container_tag = $1 AND is_latest = TRUE AND is_forgotten = FALSE",
        container_tag,
    )

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
        "total": total,
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
async def get_memory(
    memory_id: str,
    current_user: Dict = Depends(require_permission("read")),
    _: Dict = Depends(check_rate_limit),
):
    memory = await memory_store.get_by_id(memory_id, include_forgotten=True)
    if not memory:
        raise HTTPException(status_code=404, detail="Memory not found")

    verify_container_ownership(memory.container_tag, current_user["key_id"])

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
async def forget_memory(
    memory_id: str,
    current_user: Dict = Depends(require_permission("write")),
    _: Dict = Depends(check_rate_limit),
):
    memory = await memory_store.get_by_id(memory_id, include_forgotten=True)
    if not memory:
        raise HTTPException(status_code=404, detail="Memory not found")

    verify_container_ownership(memory.container_tag, current_user["key_id"])

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
async def restore_memory(
    memory_id: str,
    current_user: Dict = Depends(require_permission("write")),
    _: Dict = Depends(check_rate_limit),
):
    memory = await memory_store.get_by_id(memory_id, include_forgotten=True)
    if not memory:
        raise HTTPException(status_code=404, detail="Memory not found")

    verify_container_ownership(memory.container_tag, current_user["key_id"])

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
async def update_memory(
    memory_id: str,
    request: UpdateMemoryRequest,
    current_user: Dict = Depends(require_permission("write")),
    _: Dict = Depends(check_rate_limit),
):
    old_memory = await memory_store.get_by_id(memory_id)
    if not old_memory:
        raise HTTPException(status_code=404, detail="Memory not found")

    verify_container_ownership(old_memory.container_tag, current_user["key_id"])

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
async def get_memory_history(
    memory_id: str,
    current_user: Dict = Depends(require_permission("read")),
    _: Dict = Depends(check_rate_limit),
):
    memory = await memory_store.get_by_id(memory_id, include_forgotten=True)
    if not memory:
        raise HTTPException(status_code=404, detail="Memory not found")

    verify_container_ownership(memory.container_tag, current_user["key_id"])

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
    current_user: Dict = Depends(require_permission("read")),
    _: Dict = Depends(check_rate_limit),
):
    verify_container_ownership(container_tag, current_user["key_id"])

    profile = await profile_service.get_profile(
        container_tag=container_tag,
        query=query,
        max_static=max_static,
        max_dynamic=max_dynamic,
    )

    return profile


class EntityContextResponse(BaseModel):
    container_tag: str = Field(..., description="Container tag")
    entity_context: Optional[str] = Field(None, description="Current entity context")
    source: str = Field(
        "stored", description="Source of entity context: 'stored' or 'default'"
    )


class SetEntityContextRequest(BaseModel):
    entity_context: str = Field(
        ...,
        description="Entity context to set (max 1500 chars)",
        examples=["设计探索对话，关注用户的UI偏好和品牌需求"],
    )


@router.get(
    "/profile/entity-context",
    summary="Get entity context",
    description="Get the current entity context for a container. Returns the stored context or indicates default is being used.",
    response_model=EntityContextResponse,
)
async def get_entity_context(
    container_tag: str = Query(..., description="Container tag"),
    current_user: Dict = Depends(require_permission("read")),
    _: Dict = Depends(check_rate_limit),
):
    verify_container_ownership(container_tag, current_user["key_id"])

    stored_context = await profile_service.get_entity_context(container_tag)

    if stored_context:
        return EntityContextResponse(
            container_tag=container_tag,
            entity_context=stored_context,
            source="stored",
        )

    from src.services.core.llm_entity_extraction import get_default_entity_context
    from src.services.core.chinese_prompts import detect_language

    default_context = get_default_entity_context("english")

    return EntityContextResponse(
        container_tag=container_tag,
        entity_context=default_context,
        source="default",
    )


@router.put(
    "/profile/entity-context",
    summary="Set entity context",
    description="Set the entity context for a container. This context will be used to guide memory extraction for all subsequent memories in this container.",
    response_model=EntityContextResponse,
)
async def set_entity_context(
    request: SetEntityContextRequest,
    container_tag: str = Query(..., description="Container tag"),
    current_user: Dict = Depends(require_permission("write")),
    _: Dict = Depends(check_rate_limit),
):
    verify_container_ownership(container_tag, current_user["key_id"])

    await profile_service.set_entity_context(
        container_tag=container_tag,
        entity_context=request.entity_context,
    )

    await profile_service.invalidate_cache(container_tag)

    return EntityContextResponse(
        container_tag=container_tag,
        entity_context=request.entity_context,
        source="stored",
    )


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
async def search_memories(
    request: SearchRequest,
    current_user: Dict = Depends(require_permission("read")),
    _: Dict = Depends(check_rate_limit),
):
    container_tag = request.container_tag or current_user["container_tag"]
    verify_container_ownership(container_tag, current_user["key_id"])

    results = await memory_store.search(
        query=request.query,
        container_tag=container_tag,
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
async def create_document(
    request: CreateDocumentRequest,
    background_tasks: BackgroundTasks,
    current_user: Dict = Depends(require_permission("write")),
    _: Dict = Depends(check_rate_limit),
):
    container_tag = request.container_tag or current_user["container_tag"]
    verify_container_ownership(container_tag, current_user["key_id"])

    document, is_duplicate = await document_store.create(
        content=request.content,
        container_tag=container_tag,
        title=request.title,
        source=request.source,
        doc_type=request.doc_type,
        metadata=request.metadata,
        async_process=True,
    )

    # 后台异步处理：chunking → embedding → entity extraction
    background_tasks.add_task(document_store.process_document_async, document.id)

    return {
        "id": document.id,
        "title": document.title,
        "source": document.source,
        "container_tag": document.container_tag,
        "token_count": document.token_count,
        "chunk_count": document.chunk_count,
        "status": document.status,
        "is_duplicate": is_duplicate,
        "created_at": document.created_at.isoformat() if document.created_at else None,
    }


class UpdateDocumentRequest(BaseModel):
    content: str = Field(..., description="Updated document content")
    title: Optional[str] = Field(None, description="Updated document title")
    metadata: Optional[Dict[str, Any]] = Field(
        None, description="Updated metadata (partial update)"
    )


@router.put(
    "/documents/{document_id}",
    summary="Update a document",
    description="Update document content with incremental chunk updates.",
    responses={
        200: {"description": "Document updated"},
        404: {"description": "Not found"},
    },
)
async def update_document(
    document_id: str,
    request: UpdateDocumentRequest,
    current_user: Dict = Depends(require_permission("write")),
    _: Dict = Depends(check_rate_limit),
):
    document, unchanged = await document_store.update(
        document_id=document_id,
        content=request.content,
        title=request.title,
        metadata=request.metadata,
    )

    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    return {
        "id": document.id,
        "title": document.title,
        "container_tag": document.container_tag,
        "token_count": document.token_count,
        "chunk_count": document.chunk_count,
        "content_hash": document.content_hash,
        "unchanged": unchanged,
        "updated_at": document.updated_at.isoformat() if document.updated_at else None,
    }


@router.get(
    "/documents",
    summary="List documents",
    description="List all documents for a container with pagination support.",
    responses={200: {"description": "List of documents"}},
)
async def list_documents(
    container_tag: Optional[str] = Query(None, description="Container tag (optional)"),
    limit: int = Query(20, ge=1, le=100, description="Max results"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    current_user: Dict = Depends(require_permission("read")),
    _: Dict = Depends(check_rate_limit),
):
    container_tag = container_tag or current_user["container_tag"]
    verify_container_ownership(container_tag, current_user["key_id"])

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
                "title": d.title,
                "source": d.source,
                "doc_type": d.doc_type,
                "token_count": d.token_count,
                "chunk_count": d.chunk_count,
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
async def get_document(
    document_id: str,
    current_user: Dict = Depends(require_permission("read")),
    _: Dict = Depends(check_rate_limit),
):
    document = await document_store.get_by_id(document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    verify_container_ownership(document.container_tag, current_user["key_id"])

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
async def delete_document(
    document_id: str,
    current_user: Dict = Depends(require_permission("delete")),
    _: Dict = Depends(check_rate_limit),
):
    document = await document_store.get_by_id(document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    verify_container_ownership(document.container_tag, current_user["key_id"])

    success = await document_store.delete(document_id)

    return {"id": document_id, "deleted": success}


@router.post(
    "/documents/search",
    summary="Search document chunks",
    description="Semantic search across document chunks with similarity scoring.",
    responses={
        200: {
            "description": "Search results",
            "content": {
                "application/json": {
                    "example": {
                        "query": "how to deploy",
                        "results": [
                            {
                                "id": "chunk_abc123",
                                "content": "## Deployment\nRun `bun run build` to build...",
                                "document_id": "doc_xyz",
                                "document_title": "README.md",
                                "document_type": "markdown",
                                "position": 5,
                                "similarity": 0.85,
                            }
                        ],
                        "count": 1,
                    }
                }
            },
        }
    },
)
async def search_chunks(
    request: ChunkSearchRequest,
    current_user: Dict = Depends(require_permission("read")),
    _: Dict = Depends(check_rate_limit),
):
    from src.embedding.client import get_embedding_client

    container_tag = request.container_tag or current_user["container_tag"]
    verify_container_ownership(container_tag, current_user["key_id"])

    embedding_client = get_embedding_client()
    query_embedding = await embedding_client.embed(request.query)

    if query_embedding is None:
        return {"query": request.query, "results": [], "count": 0}

    results = await document_store.search_chunks(
        query_embedding=query_embedding,
        container_tag=container_tag,
        limit=request.limit,
        threshold=request.threshold,
    )

    formatted_results = []
    for r in results:
        if not isinstance(r, dict):
            continue
        chunk = r.get("chunk")
        if chunk is None:
            continue

        content = getattr(chunk, "content", "") or ""
        if len(content) > 500:
            content = content[:500] + "..."

        metadata = getattr(chunk, "metadata", None) or {}
        doc_type = metadata.get("doc_type") if isinstance(metadata, dict) else None

        formatted_results.append(
            {
                "id": getattr(chunk, "id", ""),
                "content": content,
                "document_id": r.get("document_id", ""),
                "document_title": r.get("title"),
                "document_type": doc_type,
                "position": getattr(chunk, "position", None),
                "similarity": r.get("similarity", 0.0),
            }
        )

    if request.doc_types:
        formatted_results = [
            r for r in formatted_results if r.get("document_type") in request.doc_types
        ]

    return {
        "query": request.query,
        "results": formatted_results,
        "count": len(formatted_results),
    }


@router.post(
    "/search/hybrid",
    summary="Hybrid search across memories and documents",
    description="Search both memories and document chunks in a single query, returning combined results sorted by similarity.",
    responses={
        200: {
            "description": "Hybrid search results",
            "content": {
                "application/json": {
                    "example": {
                        "query": "deployment preferences",
                        "results": [
                            {
                                "id": "mem_abc123",
                                "content": "I prefer Docker for deployments",
                                "source": "memory",
                                "similarity": 0.92,
                            },
                            {
                                "id": "chunk_xyz",
                                "content": "## Deployment Guide\nUse Docker Compose...",
                                "source": "chunk",
                                "similarity": 0.85,
                                "document_title": "README.md",
                            },
                        ],
                        "count": 2,
                    }
                }
            },
        }
    },
)
async def hybrid_search(
    request: HybridSearchRequest,
    current_user: Dict = Depends(require_permission("read")),
    _: Dict = Depends(check_rate_limit),
):
    from src.embedding.client import get_embedding_client

    container_tag = request.container_tag or current_user["container_tag"]
    verify_container_ownership(container_tag, current_user["key_id"])

    sources = request.sources or ["memory", "chunk"]
    search_memories = "memory" in sources
    search_chunks_flag = "chunk" in sources

    memory_results = []
    chunk_results = []

    if search_memories:
        memory_results = await memory_store.search(
            query=request.query,
            container_tag=container_tag,
            limit=request.limit,
            threshold=request.threshold,
        )

    if search_chunks_flag:
        embedding_client = get_embedding_client()
        query_embedding = await embedding_client.embed(request.query)

        if query_embedding is not None:
            chunk_raw = await document_store.search_chunks(
                query_embedding=query_embedding,
                container_tag=container_tag,
                limit=request.limit,
                threshold=request.threshold,
            )

            chunk_results = []
            for r in chunk_raw:
                if not isinstance(r, dict):
                    continue
                chunk = r.get("chunk")
                if chunk is None:
                    continue
                content = getattr(chunk, "content", "") or ""
                truncated = content[:500] + ("..." if len(content) > 500 else "")

                metadata = getattr(chunk, "metadata", None) or {}
                doc_type = (
                    metadata.get("doc_type") if isinstance(metadata, dict) else None
                )

                chunk_results.append(
                    {
                        "id": getattr(chunk, "id", ""),
                        "content": truncated,
                        "source": "chunk",
                        "similarity": r.get("similarity", 0.0),
                        "document_title": r.get("title"),
                        "document_type": doc_type,
                    }
                )

    memory_formatted = [
        {
            "id": m.get("id", ""),
            "content": m.get("content", ""),
            "source": "memory",
            "similarity": m.get("similarity", 0.0),
        }
        for m in memory_results
    ]

    combined = memory_formatted + chunk_results
    combined.sort(key=lambda x: x.get("similarity", 0), reverse=True)
    combined = combined[: request.limit]

    return {"query": request.query, "results": combined, "count": len(combined)}


class ExtractMemoryRequest(BaseModel):
    summary: str = Field(..., description="Session summary to extract memories from")
    language: str = Field("zh_CN", description="Language for extraction (zh_CN or en_US)")


class ExtractedMemory(BaseModel):
    content: str = Field(..., description="Extracted memory content")
    type: str = Field(..., description="Memory type (preference, constraint, learned-pattern)")
    reason: str = Field(..., description="Why this is worth saving")


class ExtractMemoryResponse(BaseModel):
    memories: List[ExtractedMemory] = Field(..., description="Extracted memories")
    has_worthwhile: bool = Field(..., description="Whether any worthwhile memories found")


@router.post(
    "/extract-memory",
    summary="Extract worthwhile memories from session summary",
    description="Use LLM to extract memories worth saving from a session summary",
)
async def extract_memory_from_summary(
    request: ExtractMemoryRequest,
    container_tag: str = Depends(require_permission("read")),
) -> ExtractMemoryResponse:
    """使用 LLM 从会话摘要中提取值得保存的记忆"""
    from src.llm.client import get_llm_client
    import json

    if request.language == "zh_CN":
        system_prompt = """你是一个记忆提取专家。你的任务是从会话摘要中提取值得长期保存的记忆。

**保存标准**（必须同时满足）：
1. 跨会话有效：这个信息在未来的对话中仍然有用
2. 非临时状态：不是"正在做什么"，而是"应该怎么做"
3. 非代码细节：代码实现在代码库中，不需要记忆

**值得保存的例子**：
- 用户偏好："用户偏好使用中文回复"
- 项目约束："测试不能跳过"
- 学到的模式："语义去重阈值 0.85 最合适"
- 技术决策："使用 PostgreSQL 而不是 MySQL"

**不值得保存的例子**：
- 临时任务："实现登录功能"（完成后就没意义）
- 当前状态："正在编辑 auth.ts"（下次不同）
- 代码细节："函数签名是..."（在代码中）
- 已完成工作："已创建 3 个文件"（历史记录）

请分析摘要，返回 JSON 格式：
```json
{
  "memories": [
    {
      "content": "提取的记忆内容（简洁，一句话）",
      "type": "preference|constraint|learned-pattern",
      "reason": "为什么值得保存（一句话）"
    }
  ]
}
```

如果没有值得保存的内容，返回：`{"memories": []}`"""

    else:
        system_prompt = """You are a memory extraction expert. Your task is to extract memories worth long-term preservation from a session summary.

**Save Criteria** (must meet all):
1. Cross-session validity: This information will still be useful in future conversations
2. Non-temporary state: Not "what is being done", but "how things should be done"
3. Non-code details: Code implementation is in the codebase, no need to memorize

**Worth saving examples**:
- User preference: "User prefers Chinese responses"
- Project constraint: "Tests cannot be skipped"
- Learned pattern: "Semantic dedup threshold 0.85 works best"
- Technical decision: "Use PostgreSQL instead of MySQL"

**Not worth saving examples**:
- Temporary task: "Implement login function" (meaningless after completion)
- Current state: "Editing auth.ts" (different next time)
- Code details: "Function signature is..." (in code)
- Completed work: "Created 3 files" (history)

Analyze the summary and return JSON format:
```json
{
  "memories": [
    {
      "content": "Extracted memory content (concise, one sentence)",
      "type": "preference|constraint|learned-pattern",
      "reason": "Why worth saving (one sentence)"
    }
  ]
}
```

If nothing worth saving, return: `{"memories": []}`"""

    try:
        llm = get_llm_client()
        result = await llm.aextract_json(
            prompt=f"{system_prompt}\n\n会话摘要：\n{request.summary}",
            temperature=0.3,
            max_tokens=1000
        )

        if not result or "memories" not in result:
            return ExtractMemoryResponse(memories=[], has_worthwhile=False)

        memories = [
            ExtractedMemory(
                content=m.get("content", ""),
                type=m.get("type", "learned-pattern"),
                reason=m.get("reason", "")
            )
            for m in result.get("memories", [])
            if m.get("content")
        ]

        return ExtractMemoryResponse(
            memories=memories,
            has_worthwhile=len(memories) > 0
        )

    except Exception as e:
        return ExtractMemoryResponse(memories=[], has_worthwhile=False)
