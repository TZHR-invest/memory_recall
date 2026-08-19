"""
crystal 对账端点（/api/v2/reconcile，api-contract §2.2）

M2 落地：
- POST /api/v2/reconcile/run —— 显式触发对账（evidence_id 缺省 = 重跑 pending/failed）
- GET  /api/v2/reconcile/jobs/{job_id} —— 对账 job 状态（M2 简化：直接查 evidence_processing）
"""

from typing import Dict, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from src.api.auth import require_permission
from src.database import db

from .errors import CrystalAPIError, ok_response
from .reconcile_service import reconcile_evidence
from .security import owner_from_user

router = APIRouter(prefix="/api/v2/reconcile", tags=["crystal-reconcile"])


class ReconcileRunRequest(BaseModel):
    evidence_id: Optional[str] = Field(None, description="指定 evidence；缺省 = 重跑该 owner 的 pending/failed")


@router.post("/run", status_code=202)
async def reconcile_run(
    request: ReconcileRunRequest,
    current_user: Dict = Depends(require_permission("write")),
):
    """显式触发对账（调试/运维端点；正常流程由后台 worker 自动跑）"""
    owner = owner_from_user(current_user)

    if request.evidence_id:
        # 校验归属
        async with db.get_connection() as conn:
            ev = await conn.fetchrow(
                """SELECT e.id FROM crystal.evidence e
                   WHERE e.id=$1 AND e.owner_type=$2 AND e.owner_id=$3""",
                request.evidence_id,
                owner["owner_type"],
                owner["owner_id"],
            )
            if not ev:
                raise CrystalAPIError(404, f"Evidence '{request.evidence_id}' not found.")
        result = await reconcile_evidence(request.evidence_id)
        return ok_response({"evidence_id": request.evidence_id, "result": result})

    # 缺省：重跑该 owner 的 pending/failed
    async with db.get_connection() as conn:
        rows = await conn.fetch(
            """SELECT p.evidence_id FROM crystal.evidence_processing p
               JOIN crystal.evidence e ON e.id = p.evidence_id
               WHERE p.processing_state IN ('pending','failed')
                 AND e.owner_type=$1 AND e.owner_id=$2
               LIMIT 50""",
            owner["owner_type"],
            owner["owner_id"],
        )
    results = []
    for r in rows:
        res = await reconcile_evidence(r["evidence_id"])
        results.append({"evidence_id": r["evidence_id"], "result": res})
    return ok_response({"count": len(results), "results": results})


@router.get("/jobs/{job_id}")
async def reconcile_job(
    job_id: str,
    current_user: Dict = Depends(require_permission("read")),
):
    """对账 job 状态（M2 简化：evidence_id 即 job_id，查 evidence_processing）"""
    owner = owner_from_user(current_user)
    async with db.get_connection() as conn:
        row = await conn.fetchrow(
            """SELECT p.processing_state, p.current_step, p.last_error, p.updated_at
               FROM crystal.evidence_processing p
               JOIN crystal.evidence e ON e.id = p.evidence_id
               WHERE p.evidence_id=$1 AND e.owner_type=$2 AND e.owner_id=$3""",
            job_id,
            owner["owner_type"],
            owner["owner_id"],
        )
    if not row:
        raise CrystalAPIError(404, f"Reconcile job '{job_id}' not found.")
    return ok_response(
        {
            "job_id": job_id,
            "state": row["processing_state"],
            "current_step": row["current_step"],
            "last_error": row["last_error"],
            "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
        }
    )
