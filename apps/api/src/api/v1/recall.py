"""
Recall Endpoint

POST /v1/recall - Smart recall memories
"""

from fastapi import APIRouter, Depends
from typing import Optional

from ...models.api import RecallRequest, RecallResponse, RecallResult
from ..auth import get_current_user, check_rate_limit

router = APIRouter(prefix="/recall", tags=["Recall"])


@router.post(
    "",
    response_model=RecallResponse,
    summary="Recall Memories",
    description="Recall relevant memories using hybrid search (vector + keyword + graph)",
)
async def recall_memories(
    request: RecallRequest,
    current_user: dict = Depends(get_current_user),
    _: dict = Depends(check_rate_limit),
):
    """
    Recall memories using hybrid search

    - **query**: Natural language query (required)
    - **limit**: Max results (1-100, default 10)
    - **min_similarity**: Minimum similarity threshold (0.0-1.0)
    - **scope**: all, manual_only, or agent_only
    - **include_expired**: Include expired memories

    Returns ranked results with similarity scores
    """
    from src.services.core.lossless_recall_service import lossless_recall_service
    from src.database import db

    user_id = current_user["user_id"]
    db.set_current_user(user_id)

    results = await lossless_recall_service.hybrid_recall(
        query=request.query,
        user_id=user_id,
        scope=request.scope,
        limit=request.limit,
        min_similarity=request.min_similarity,
    )

    if not request.include_expired:
        results = [r for r in results if not r.get("is_expired", False)]

    recall_results = [
        RecallResult(
            memory_id=r.get("id", r.get("memory_id", "")),
            content=r.get("content", ""),
            similarity=r.get("similarity", r.get("score", 0.0)),
            memory_type=r.get("memory_type", "preference"),
            created_at=r.get("created_at"),
            source=r.get("source", "manual"),
        )
        for r in results[: request.limit]
    ]

    return RecallResponse(
        query=request.query,
        results=recall_results,
        total=len(recall_results),
        recall_mode="hybrid",
    )
