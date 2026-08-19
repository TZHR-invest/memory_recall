"""
crystal 状态查询（召回）端点（/api/v2/search 等，api-contract §2.3）

M2 落地：
- POST /api/v2/search —— 三级管道召回（预过滤→向量粗排→精排→截断可见）
- POST /api/v2/context-inject —— 注入 payload（画像偏好层 + 状态查询）
- GET  /api/v2/claims/{id} —— claim 详情 + 证据 + 谱系
- GET  /api/v2/claims/{id}/lineage —— 谱系树
"""

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from src.api.auth import require_permission
from src.database import db

from .errors import CrystalAPIError, ok_response
from .recall_service import (
    get_claim_detail,
    get_claim_lineage,
    search_claims,
)
from .security import owner_from_user, verify_scope_ownership

router = APIRouter(tags=["crystal-recall"])


class SearchRequest(BaseModel):
    """POST /api/v2/search（api-contract §4.2）"""

    query: str = Field(..., min_length=1, description="查询文本")
    scope: Optional[str] = Field(None, description="项目作用域（可选，预过滤）")
    claim_kind: Optional[str] = Field(None, description="claim_kind 过滤（可选）")
    limit: int = Field(10, ge=1, le=100, description="返回上限")
    include_explain: bool = Field(False, description="true 时返回 explain（粗排全貌/精排分数/截断项）")


class ContextInjectRequest(BaseModel):
    """POST /api/v2/context-inject（recall-design §5）"""

    query: Optional[str] = Field(None, description="任务上下文查询（可选）")
    scope: Optional[str] = Field(None, description="项目作用域（可选）")
    config: Optional[Dict[str, Any]] = Field(None, description="注入配置（预留）")
    include_explain: bool = Field(False, description="true 时返回 explain")
    exclude_claim_ids: Optional[list] = Field(None, description="跨轮去重排除的 claim_id（沿用 v5 exclude_memory_ids）")


@router.post("/api/v2/search")
async def search(
    request: SearchRequest,
    current_user: Dict = Depends(require_permission("read")),
):
    """状态查询召回（US-S1/S2 / A4/A5）

    include_explain=true 时返回 explain，并落 crystal.workbench_review
    （G1：洞察面召回复盘历史可回看，A5 无静默丢弃）。
    """
    owner = owner_from_user(current_user)
    scope = verify_scope_ownership(request.scope, current_user["key_id"])
    result = await search_claims(
        query=request.query,
        owner_type=owner["owner_type"],
        owner_id=owner["owner_id"],
        scope=scope,
        claim_kind=request.claim_kind,
        limit=request.limit,
        include_explain=request.include_explain,
        save_trace=request.include_explain,
        trace_source="search",
    )
    return ok_response(result)


@router.post("/api/v2/context-inject")
async def context_inject(
    request: ContextInjectRequest,
    current_user: Dict = Depends(require_permission("read")),
):
    """注入 payload（recall-design §5）：画像偏好层（claim_kind=preference active）+ 任务上下文状态查询"""
    owner = owner_from_user(current_user)
    scope = verify_scope_ownership(request.scope, current_user["key_id"])

    exclude = set(request.exclude_claim_ids or [])

    # ① 画像偏好层：claim_kind=preference 的 active claim（v1 #16 画像=Claim 读视图）
    async with db.get_connection() as conn:
        preference_claims = await conn.fetch(
            """SELECT id, statement, content_confidence FROM crystal.claim
               WHERE owner_type=$1 AND owner_id=$2 AND status='active' AND claim_kind='preference'
               ORDER BY content_confidence DESC NULLS LAST
               LIMIT 20""",
            owner["owner_type"],
            owner["owner_id"],
        )

    # ② 任务上下文：query 动态检索（有 query 时）
    search_result = None
    if request.query:
        search_result = await search_claims(
            query=request.query,
            owner_type=owner["owner_type"],
            owner_id=owner["owner_id"],
            scope=scope,
            limit=10,
            include_explain=request.include_explain,
            save_trace=request.include_explain,
            trace_source="context_inject",
        )

    # 组装注入 payload
    profile_layer = [
        {"claim_id": c["id"], "statement": c["statement"]}
        for c in preference_claims
        if c["id"] not in exclude
    ]
    task_context = []
    if search_result:
        task_context = [
            {
                "claim_id": r["claim_id"],
                "statement": r["statement"],
                "claim_kind": r["claim_kind"],
                "content_confidence": r["content_confidence"],
                "scores": r["scores"],
            }
            for r in search_result["results"]
            if r["claim_id"] not in exclude
        ]

    response: Dict[str, Any] = {
        "profile": profile_layer,
        "memories": task_context,
        "excluded": list(exclude) if exclude else None,
    }
    if request.include_explain and search_result and "explain" in search_result:
        response["explain"] = search_result["explain"]
        if search_result.get("trace_id"):
            response["trace_id"] = search_result["trace_id"]

    return ok_response(response)


@router.get("/api/v2/claims/{claim_id}")
async def get_claim(
    claim_id: str,
    current_user: Dict = Depends(require_permission("read")),
):
    """claim 详情 + 证据 + 谱系（A2/A3）"""
    owner = owner_from_user(current_user)
    detail = await get_claim_detail(
        claim_id, owner["owner_type"], owner["owner_id"]
    )
    if detail is None:
        raise CrystalAPIError(404, f"Claim '{claim_id}' not found.")
    return ok_response(detail)


@router.get("/api/v2/claims/{claim_id}/lineage")
async def get_claim_lineage_route(
    claim_id: str,
    current_user: Dict = Depends(require_permission("read")),
):
    """claim 谱系树（A3）"""
    owner = owner_from_user(current_user)
    lineage = await get_claim_lineage(
        claim_id, owner["owner_type"], owner["owner_id"]
    )
    if lineage is None:
        raise CrystalAPIError(404, f"Claim '{claim_id}' not found.")
    return ok_response(lineage)
