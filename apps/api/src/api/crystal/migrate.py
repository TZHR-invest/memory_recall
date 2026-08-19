"""
crystal 迁移端点（/api/v2/migrate，api-contract §2.5，admin）

M3 落地：
- POST /api/v2/migrate/run —— 一次性全量迁移（memories → evidence → claim），幂等可重放
- GET  /api/v2/migrate/status —— 迁移进度/断点

权限：admin（is_test 或权限含 debug，api-contract §1.3）。
"""

import asyncio
import logging
from typing import Dict, Optional

from fastapi import APIRouter, BackgroundTasks, Depends

from src.api.auth import require_permission

from .errors import CrystalAPIError, ok_response

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v2/migrate", tags=["crystal-migrate"])


def _admin_user(current_user: Dict) -> Dict:
    """admin 判定（api-contract §1.3）：is_test 或权限含 debug"""
    if not (current_user.get("is_test") or "debug" in current_user.get("permissions", [])):
        raise CrystalAPIError(403, "Admin permission required.")
    return current_user


async def _run_migration_job(owner_id: Optional[str], run_id: Optional[str]) -> None:
    """后台迁移任务：迁移 + 对账（失败记录日志，不阻塞响应）"""
    from migrate_memories import reconcile_migrated, run_migration

    try:
        stats = await run_migration(owner_id=owner_id, run_id=run_id)
        logger.info(f"crystal 迁移完成: {stats}")
        await reconcile_migrated(owner_id)
        logger.info(f"crystal 迁移对账完成: run={run_id}")
    except Exception as e:
        logger.error(f"crystal 迁移失败 run={run_id}: {e}")


@router.post("/run", status_code=202)
async def migrate_run(
    owner_id: Optional[str] = None,
    background_tasks: BackgroundTasks = None,
    current_user: Dict = Depends(require_permission("write")),
):
    """触发一次性全量迁移（幂等可重放；后台执行，返回 run_id）"""
    _admin_user(current_user)
    import uuid

    run_id = f"mig_{uuid.uuid4().hex[:12]}"
    background_tasks.add_task(_run_migration_job, owner_id, run_id)
    return ok_response(
        {"run_id": run_id, "status": "running", "note": "迁移后台执行中；GET /api/v2/migrate/status 查进度"}
    )


@router.get("/status")
async def migrate_status(
    current_user: Dict = Depends(require_permission("read")),
):
    """迁移进度/断点（最新 run）"""
    _admin_user(current_user)
    from src.database import db

    async with db.get_connection() as conn:
        rows = await conn.fetch(
            """SELECT run_id, owner_id, total, migrated, skipped, failed,
                      last_memory_id, status, error, created_at, updated_at
               FROM crystal.migration_state
               ORDER BY updated_at DESC
               LIMIT 10"""
        )
    items = [
        {
            "run_id": r["run_id"],
            "owner_id": r["owner_id"],
            "total": r["total"],
            "migrated": r["migrated"],
            "skipped": r["skipped"],
            "failed": r["failed"],
            "last_memory_id": r["last_memory_id"],
            "status": r["status"],
            "error": r["error"],
            "created_at": r["created_at"].isoformat() if r["created_at"] else None,
            "updated_at": r["updated_at"].isoformat() if r["updated_at"] else None,
        }
        for r in rows
    ]
    return ok_response({"runs": items})
