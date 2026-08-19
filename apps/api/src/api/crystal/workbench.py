"""
crystal 工作台端点（/api/v2/workbench，workbench 设计 v1）

裁决面：confirm（+Δ content）/ correct（特权 Evidence → supersede）/ forget（retract）/
promote-scope（scope 提权审计）
洞察面：overview（统计）/ reviews（召回复盘 trace）
权限：个人 key 只看自己 owner；admin 的 debug 日志与个人数据隔离（A11）。
"""

import json
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from src.api.auth import require_permission
from src.database import db

from .errors import CrystalAPIError, ok_response
from .reconcile_service import reconcile_confirm, reconcile_correction, reconcile_forget
from .recall_service import search_claims
from .security import owner_from_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v2/workbench", tags=["crystal-workbench"])


class CorrectRequest(BaseModel):
    new_statement: str = Field(..., min_length=1, description="用户给出的正确版本")
    reason: str = Field("用户纠正", description="纠正原因（可选）")
    source_ref: Optional[Dict[str, Any]] = Field(None, description="出处 {session_id, message_id}")


class ConfirmRequest(BaseModel):
    pass  # 无 body 需要；确认即认可


class ForgetRequest(BaseModel):
    reason: str = Field("用户遗忘", description="遗忘原因（可选）")


class PromoteScopeRequest(BaseModel):
    action: str = Field(..., description="adopt | reject")
    reason: Optional[str] = Field(None, description="审计理由")


# ==================== 裁决面 ====================


@router.post("/claims/{claim_id}/confirm")
async def workbench_confirm(
    claim_id: str,
    current_user: Dict = Depends(require_permission("write")),
):
    """确认：用户认可当前 claim 为真 → +Δ content（US-W1 / A6）"""
    owner = owner_from_user(current_user)
    try:
        result = await reconcile_confirm(
            claim_id,
            owner["owner_type"],
            owner["owner_id"],
            actor_id=current_user["key_id"],
        )
    except ValueError as e:
        raise CrystalAPIError(404, str(e))
    return ok_response(result)


@router.post("/claims/{claim_id}/correct")
async def workbench_correct(
    claim_id: str,
    request: CorrectRequest,
    current_user: Dict = Depends(require_permission("write")),
):
    """纠错：创建 user_correction Evidence → 对账特权 supersede（US-W1 / A3 / A6）"""
    owner = owner_from_user(current_user)
    try:
        result = await reconcile_correction(
            claim_id,
            request.new_statement,
            owner["owner_type"],
            owner["owner_id"],
            source_ref=request.source_ref,
            actor_id=current_user["key_id"],
            reason=request.reason,
        )
    except ValueError as e:
        raise CrystalAPIError(404, str(e))
    return ok_response(result)


@router.post("/claims/{claim_id}/forget")
async def workbench_forget(
    claim_id: str,
    request: ForgetRequest,
    current_user: Dict = Depends(require_permission("write")),
):
    """遗忘：retract 边，该 claim 失活（US-W1 / A6）"""
    owner = owner_from_user(current_user)
    try:
        result = await reconcile_forget(
            claim_id,
            owner["owner_type"],
            owner["owner_id"],
            actor_id=current_user["key_id"],
            reason=request.reason,
        )
    except ValueError as e:
        raise CrystalAPIError(404, str(e))
    return ok_response(result)


@router.post("/claims/{claim_id}/promote-scope")
async def workbench_promote_scope(
    claim_id: str,
    request: PromoteScopeRequest,
    current_user: Dict = Depends(require_permission("write")),
):
    """scope 提权审计：采纳 → generalizes 边（claim→无 scope 新 claim）；拒绝 → 留痕（US-W2 / A7）

    一期简化（workbench §3.2）：采纳 = 创建无 scope 新 claim + generalizes 边 + 继承证据；
    拒绝 = 只记 claim_activity（decision: reject）。不自动提权。
    """
    if request.action not in ("adopt", "reject"):
        raise CrystalAPIError(400, "action must be 'adopt' or 'reject'")

    owner = owner_from_user(current_user)
    async with db.get_connection() as conn:
        claim = await conn.fetchrow(
            """SELECT id, statement, claim_kind, content_confidence, scope, owner_type, owner_id
               FROM crystal.claim
               WHERE id=$1 AND owner_type=$2 AND owner_id=$3""",
            claim_id,
            owner["owner_type"],
            owner["owner_id"],
        )
        if not claim:
            raise CrystalAPIError(404, f"Claim '{claim_id}' not found or not owned by you")
        if claim["scope"] is None:
            raise CrystalAPIError(400, "Claim is already global (scope=NULL)")

        new_claim_id = None
        if request.action == "adopt":
            async with conn.transaction():
                # 无 scope 新 claim（继承 statement/kind/confidence）
                new_claim_id = await conn.fetchval(
                    """INSERT INTO crystal.claim
                       (statement, claim_kind, content_confidence, scope, owner_type, owner_id,
                        status, created_at)
                       VALUES ($1, $2, $3, NULL, $4, $5, 'active', NOW())
                       RETURNING id""",
                    claim["statement"],
                    claim["claim_kind"],
                    claim["content_confidence"],
                    owner["owner_type"],
                    owner["owner_id"],
                )
                # generalizes 边（claim → 无 scope 新 claim）
                await conn.execute(
                    """INSERT INTO crystal.lineage_edge
                       (from_claim_id, to_claim_id, edge_type, reason, created_at)
                       VALUES ($1, $2, 'generalizes', $3, NOW())""",
                    claim_id,
                    new_claim_id,
                    f"scope 提权（用户审计采纳）: {request.reason or ''}",
                )
                # 继承证据（claim_evidence 复制）
                await conn.execute(
                    """INSERT INTO crystal.claim_evidence (claim_id, evidence_id, role, created_at)
                       SELECT $1, evidence_id, 'support', NOW()
                       FROM crystal.claim_evidence WHERE claim_id=$2""",
                    new_claim_id,
                    claim_id,
                )
                # claim_activity（建议采纳）
                await conn.execute(
                    """INSERT INTO crystal.claim_activity
                       (claim_id, action, actor_type, actor_id, triggered_by_evidence_id,
                        detail, created_at)
                       VALUES ($1, 'promoted_scope', 'user', $2, NULL, $3, NOW())""",
                    claim_id,
                    current_user["key_id"],
                    json.dumps(
                        {"decision": "adopt", "new_claim_id": new_claim_id, "reason": request.reason}
                    ),
                )
        else:
            # 拒绝：只留痕，不影响原 claim
            await conn.execute(
                """INSERT INTO crystal.claim_activity
                   (claim_id, action, actor_type, actor_id, triggered_by_evidence_id,
                    detail, created_at)
                   VALUES ($1, 'promoted_scope', 'user', $2, NULL, $3, NOW())""",
                claim_id,
                current_user["key_id"],
                json.dumps({"decision": "reject", "reason": request.reason}),
            )

    return ok_response(
        {
            "claim_id": claim_id,
            "action": request.action,
            "new_claim_id": new_claim_id,
            "status": "recorded",
        }
    )


# ==================== 洞察面 ====================


async def _overview_stats(owner_type: str, owner_id: str) -> Dict[str, Any]:
    """洞察统计（workbench §4.1，只统计个人 owner 数据）"""
    async with db.get_connection() as conn:
        # 拓扑
        claim_topo = await conn.fetch(
            """SELECT status, COUNT(*) AS cnt FROM crystal.claim
               WHERE owner_type=$1 AND owner_id=$2 GROUP BY status""",
            owner_type,
            owner_id,
        )
        edge_counts = await conn.fetch(
            """SELECT le.edge_type, COUNT(*) AS cnt
               FROM crystal.lineage_edge le
               JOIN crystal.claim c ON c.id = le.from_claim_id
               WHERE c.owner_type=$1 AND c.owner_id=$2
               GROUP BY le.edge_type""",
            owner_type,
            owner_id,
        )
        evidence_link_count = await conn.fetchval(
            """SELECT COUNT(*) FROM crystal.claim_evidence ce
               JOIN crystal.claim c ON c.id = ce.claim_id
               WHERE c.owner_type=$1 AND c.owner_id=$2""",
            owner_type,
            owner_id,
        )
        # 价值信号分布
        conf_buckets = await conn.fetch(
            """SELECT
                 SUM(CASE WHEN content_confidence IS NULL THEN 1 ELSE 0 END) AS unknown,
                 SUM(CASE WHEN content_confidence < 0.4 THEN 1 ELSE 0 END) AS low,
                 SUM(CASE WHEN content_confidence >= 0.4 AND content_confidence <= 0.7 THEN 1 ELSE 0 END) AS mid,
                 SUM(CASE WHEN content_confidence > 0.7 THEN 1 ELSE 0 END) AS high
               FROM crystal.claim
               WHERE owner_type=$1 AND owner_id=$2""",
            owner_type,
            owner_id,
        )
        # source_kind 构成
        source_kinds = await conn.fetch(
            """SELECT source_kind, COUNT(*) AS cnt FROM crystal.evidence
               WHERE owner_type=$1 AND owner_id=$2 GROUP BY source_kind""",
            owner_type,
            owner_id,
        )
        # 处理健康
        processing = await conn.fetch(
            """SELECT processing_state, COUNT(*) AS cnt FROM crystal.evidence_processing p
               JOIN crystal.evidence e ON e.id = p.evidence_id
               WHERE e.owner_type=$1 AND e.owner_id=$2
               GROUP BY processing_state""",
            owner_type,
            owner_id,
        )

    return {
        "topology": {
            "claims": {r["status"]: r["cnt"] for r in claim_topo},
            "lineage_edges": {r["edge_type"]: r["cnt"] for r in edge_counts},
            "evidence_links": evidence_link_count,
        },
        "value_distribution": {
            "content_confidence": {
                "unknown": conf_buckets[0]["unknown"] or 0 if conf_buckets else 0,
                "low": conf_buckets[0]["low"] or 0 if conf_buckets else 0,
                "mid": conf_buckets[0]["mid"] or 0 if conf_buckets else 0,
                "high": conf_buckets[0]["high"] or 0 if conf_buckets else 0,
            }
        },
        "source_kind_composition": {r["source_kind"]: r["cnt"] for r in source_kinds},
        "processing_health": {r["processing_state"]: r["cnt"] for r in processing},
    }


@router.get("/overview")
async def workbench_overview(
    current_user: Dict = Depends(require_permission("read")),
):
    """洞察统计（US-W4 / A8）"""
    owner = owner_from_user(current_user)
    stats = await _overview_stats(owner["owner_type"], owner["owner_id"])
    return ok_response(stats)


@router.get("/reviews")
async def workbench_reviews(
    type: Optional[str] = Query(None, description="low_confidence | promotion | recall"),
    limit: int = Query(20, ge=1, le=100),
    cursor: Optional[str] = Query(None),
    current_user: Dict = Depends(require_permission("read")),
):
    """召回复盘列表 / 假说池 / 提权建议（US-W5 / A8）

    - type=recall: 最近召回 trace（落库 workbench_review，M2 先返回空）
    - type=low_confidence: 低置信 claim（假说池，workbench §3.3）
    - type=promotion: scope 提权建议（claim_activity promoted_scope 审计）
    """
    owner = owner_from_user(current_user)
    async with db.get_connection() as conn:
        if type == "low_confidence":
            rows = await conn.fetch(
                """SELECT id, statement, claim_kind, content_confidence, scope, status, created_at
                   FROM crystal.claim
                   WHERE owner_type=$1 AND owner_id=$2
                     AND (content_confidence IS NULL OR content_confidence < 0.4)
                   ORDER BY created_at DESC LIMIT $3""",
                owner["owner_type"],
                owner["owner_id"],
                limit,
            )
            items = [
                {
                    "claim_id": r["id"],
                    "statement": r["statement"],
                    "claim_kind": r["claim_kind"],
                    "content_confidence": r["content_confidence"],
                    "status": r["status"],
                    "scope": r["scope"],
                    "reason": "low_confidence",
                }
                for r in rows
            ]
            return ok_response({"type": "low_confidence", "items": items})
        if type == "promotion":
            rows = await conn.fetch(
                """SELECT ca.id, ca.claim_id, ca.detail, ca.created_at
                   FROM crystal.claim_activity ca
                   JOIN crystal.claim c ON c.id = ca.claim_id
                   WHERE ca.action='promoted_scope'
                     AND c.owner_type=$1 AND c.owner_id=$2
                   ORDER BY ca.created_at DESC LIMIT $3""",
                owner["owner_type"],
                owner["owner_id"],
                limit,
            )
            items = [
                {
                    "activity_id": r["id"],
                    "claim_id": r["claim_id"],
                    "detail": r["detail"],
                    "created_at": r["created_at"].isoformat() if r["created_at"] else None,
                }
                for r in rows
            ]
            return ok_response({"type": "promotion", "items": items})
        # 默认 recall（M2：workbench_review 表 M2 落，先空）
        return ok_response({"type": "recall", "items": [], "next_cursor": None})


@router.get("/reviews/{trace_id}")
async def workbench_review_detail(
    trace_id: str,
    current_user: Dict = Depends(require_permission("read")),
):
    """单次召回复盘 trace（US-W5 / A5；M2 落库 workbench_review 后有数据）"""
    raise CrystalAPIError(501, "Recall review detail is available after M2 review persistence.")


# ==================== 补充：claims 读端点（api-contract §2.3） ====================


@router.get("/claims")
async def workbench_claims(
    status: Optional[str] = Query(None, description="active/superseded/disputed/retracted"),
    claim_kind: Optional[str] = Query(None),
    scope: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    current_user: Dict = Depends(require_permission("read")),
):
    """我记住了什么（workbench §6：claim 列表，active 优先）"""
    owner = owner_from_user(current_user)
    conditions = ["owner_type=$1", "owner_id=$2"]
    params: List[Any] = [owner["owner_type"], owner["owner_id"]]
    if status:
        conditions.append(f"status=${len(params) + 1}")
        params.append(status)
    if claim_kind:
        conditions.append(f"claim_kind=${len(params) + 1}")
        params.append(claim_kind)
    if scope is not None:
        conditions.append(f"(scope=${len(params) + 1}::text OR scope IS NULL)")
        params.append(scope)
    where = " AND ".join(conditions)
    async with db.get_connection() as conn:
        rows = await conn.fetch(
            f"""SELECT id, statement, claim_kind, content_confidence, scope, status, created_at
                FROM crystal.claim
                WHERE {where}
                ORDER BY CASE status WHEN 'active' THEN 0 ELSE 1 END, created_at DESC
                LIMIT ${len(params) + 1}""",
            *params,
            limit,
        )
    items = [
        {
            "claim_id": r["id"],
            "statement": r["statement"],
            "claim_kind": r["claim_kind"],
            "content_confidence": r["content_confidence"],
            "scope": r["scope"],
            "status": r["status"],
            "created_at": r["created_at"].isoformat() if r["created_at"] else None,
        }
        for r in rows
    ]
    return ok_response({"items": items, "count": len(items)})
