"""
Recall Trace Debug API.

Read-only debugging endpoints for the recall pipeline:
- GET  /debug/traces        list recent traces (summary only)
- GET  /debug/traces/{id}   full trace detail
- POST /debug/traces/run    trigger a real recall and return {result, trace}

All endpoints reuse the standard API key auth and container ownership checks.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from src.api.auth import (
    check_rate_limit,
    require_permission,
    verify_container_ownership,
)
from src.api.context_inject import ContextInjectRequest
from src.services.core.context_inject_service import context_inject_service
from src.services.core.recall_trace_service import recall_trace_service
from src.services.core.recall_embedding_service import recall_embedding_service

router = APIRouter(prefix="/debug", tags=["Debug"])


@router.get(
    "/traces",
    summary="List recent recall traces",
    description="List recall traces for a container (matches container_tag, user_tag or project_tag).",
)
async def list_traces(
    container_tag: Optional[str] = Query(None, description="Container tag (optional)"),
    limit: int = Query(20, ge=1, le=100, description="Max results"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    current_user: dict = Depends(require_permission("read")),
    _: dict = Depends(check_rate_limit),
):
    container_tag_was_given = container_tag is not None
    container_tag = container_tag or current_user["container_tag"]
    verify_container_ownership(container_tag, current_user["key_id"])

    # 未指定容器时聚合 key 名下所有容器（含 project 作用域），避免遗漏
    include_children = not container_tag_was_given

    traces = await recall_trace_service.list_traces_for_container(
        container_tag=container_tag,
        limit=limit,
        offset=offset,
        include_children=include_children,
    )
    total = await recall_trace_service.count_for_container(
        container_tag, include_children=include_children
    )

    return {"traces": traces, "count": len(traces), "total": total}


@router.get(
    "/traces/{trace_id}",
    summary="Get a recall trace detail",
    description="Get full recall trace detail including per-channel recall data.",
)
async def get_trace(
    trace_id: str,
    current_user: dict = Depends(require_permission("read")),
    _: dict = Depends(check_rate_limit),
):
    trace = await recall_trace_service.get_trace(trace_id)
    if not trace:
        raise HTTPException(status_code=404, detail="Trace not found")

    for tag in (trace.get("container_tag"), trace.get("user_tag"), trace.get("project_tag")):
        if tag:
            try:
                verify_container_ownership(tag, current_user["key_id"])
                break
            except HTTPException:
                continue
    else:
        raise HTTPException(status_code=403, detail="Container access denied")

    return trace


@router.post(
    "/traces/run",
    summary="Run a real recall with trace",
    description="Trigger a real context injection and return the result plus full trace. Always records a trace.",
)
async def run_trace(
    request: ContextInjectRequest,
    current_user: dict = Depends(require_permission("read")),
    _: dict = Depends(check_rate_limit),
):
    user_tag = request.user_tag or current_user["container_tag"]
    project_tag = request.project_tag or current_user["container_tag"]
    verify_container_ownership(user_tag, current_user["key_id"])
    verify_container_ownership(project_tag, current_user["key_id"])

    return await context_inject_service.inject_with_tags(
        user_tag=user_tag,
        project_tag=project_tag,
        query=request.query,
        config=request.config.model_dump(),
        include_trace=True,
    )


@router.get(
    "/embedding-logs",
    summary="List embedding call logs",
    description="Structured log of embedding API calls (memory create, context query). "
    "Useful for diagnosing LLM/embedding failures like 401.",
)
async def list_embedding_logs(
    container_tag: Optional[str] = Query(None, description="Container tag (optional)"),
    kind: Optional[str] = Query(None, description="Filter by kind: memory/context_query/context_chunks"),
    limit: int = Query(50, ge=1, le=200, description="Max results"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    current_user: dict = Depends(require_permission("read")),
    _: dict = Depends(check_rate_limit),
):
    container_tag_was_given = container_tag is not None
    container_tag = container_tag or current_user["container_tag"]
    verify_container_ownership(container_tag, current_user["key_id"])

    include_children = not container_tag_was_given
    logs = await recall_embedding_service.list_logs(
        container_tag=container_tag,
        kind=kind,
        limit=limit,
        offset=offset,
        include_children=include_children,
    )
    total = await recall_embedding_service.count_for_container(
        container_tag, kind, include_children=include_children
    )

    return {"logs": logs, "count": len(logs), "total": total}
