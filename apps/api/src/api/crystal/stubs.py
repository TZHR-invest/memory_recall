"""
crystal M2 端点桩（api-contract §2.2–§2.5）

M1 只落"路由 + 鉴权 + 501 桩"，业务逻辑随 M2（milestone §3.5 文档门槛已满足，
但 M1 出口标准 = 空表可写 + v5 零影响；对账/召回/工作台归 M2）。

桩语义：
- 501 Not Implemented + 统一错误信封；客户端可据此知道"路由存在、待 M2"
- 鉴权已生效（read/write/admin），越权提前 403 —— M1 出口"骨架路由鉴权冒烟"即验证此点
"""

from typing import Dict, Optional

from fastapi import APIRouter, Depends

from src.api.auth import get_current_user, require_permission

from .errors import CrystalAPIError, ok_response

stub_router = APIRouter(tags=["crystal-stubs"])

# ---- 对账（§2.2，M2） ----


def _admin_user(current_user: Dict) -> Dict:
    """admin 判定（api-contract §1.3）：is_test 或权限含 debug"""
    if not (current_user.get("is_test") or "debug" in current_user.get("permissions", [])):
        raise CrystalAPIError(403, "Admin permission required.")
    return current_user


@stub_router.post("/api/v2/reconcile/run", status_code=501)
async def reconcile_run(
    evidence_id: Optional[str] = None,
    current_user: Dict = Depends(require_permission("write")),
):
    raise CrystalAPIError(501, "Reconcile endpoint is planned for M2, not yet implemented.")


@stub_router.get("/api/v2/reconcile/jobs/{job_id}", status_code=501)
async def reconcile_job(
    job_id: str,
    current_user: Dict = Depends(require_permission("read")),
):
    raise CrystalAPIError(501, "Reconcile endpoint is planned for M2, not yet implemented.")


# ---- 状态查询 / 召回（§2.3，M2） ----


@stub_router.post("/api/v2/search", status_code=501)
async def search(
    current_user: Dict = Depends(require_permission("read")),
):
    raise CrystalAPIError(501, "Search endpoint is planned for M2, not yet implemented.")


@stub_router.post("/api/v2/context-inject", status_code=501)
async def context_inject(
    current_user: Dict = Depends(require_permission("read")),
):
    raise CrystalAPIError(501, "Context-inject endpoint is planned for M2, not yet implemented.")


@stub_router.get("/api/v2/claims/{claim_id}", status_code=501)
async def get_claim(
    claim_id: str,
    current_user: Dict = Depends(require_permission("read")),
):
    raise CrystalAPIError(501, "Claim detail endpoint is planned for M2, not yet implemented.")


@stub_router.get("/api/v2/claims/{claim_id}/lineage", status_code=501)
async def get_claim_lineage(
    claim_id: str,
    current_user: Dict = Depends(require_permission("read")),
):
    raise CrystalAPIError(501, "Claim lineage endpoint is planned for M2, not yet implemented.")


# ---- 个人工作台（§2.4，M2 / MR-011） ----


@stub_router.post("/api/v2/workbench/claims/{claim_id}/confirm", status_code=501)
async def workbench_confirm(
    claim_id: str,
    current_user: Dict = Depends(require_permission("write")),
):
    raise CrystalAPIError(501, "Workbench confirm endpoint is planned for M2, not yet implemented.")


@stub_router.post("/api/v2/workbench/claims/{claim_id}/correct", status_code=501)
async def workbench_correct(
    claim_id: str,
    current_user: Dict = Depends(require_permission("write")),
):
    raise CrystalAPIError(501, "Workbench correct endpoint is planned for M2, not yet implemented.")


@stub_router.post("/api/v2/workbench/claims/{claim_id}/forget", status_code=501)
async def workbench_forget(
    claim_id: str,
    current_user: Dict = Depends(require_permission("write")),
):
    raise CrystalAPIError(501, "Workbench forget endpoint is planned for M2, not yet implemented.")


@stub_router.post("/api/v2/workbench/claims/{claim_id}/promote-scope", status_code=501)
async def workbench_promote_scope(
    claim_id: str,
    current_user: Dict = Depends(require_permission("write")),
):
    raise CrystalAPIError(501, "Workbench promote-scope endpoint is planned for M2, not yet implemented.")


@stub_router.get("/api/v2/workbench/overview", status_code=501)
async def workbench_overview(
    current_user: Dict = Depends(require_permission("read")),
):
    raise CrystalAPIError(501, "Workbench overview endpoint is planned for M2, not yet implemented.")


@stub_router.get("/api/v2/workbench/reviews", status_code=501)
async def workbench_reviews(
    current_user: Dict = Depends(require_permission("read")),
):
    raise CrystalAPIError(501, "Workbench reviews endpoint is planned for M2, not yet implemented.")


@stub_router.get("/api/v2/workbench/reviews/{trace_id}", status_code=501)
async def workbench_review_detail(
    trace_id: str,
    current_user: Dict = Depends(require_permission("read")),
):
    raise CrystalAPIError(501, "Workbench review detail endpoint is planned for M2, not yet implemented.")


# ---- 调试 / 迁移（§2.5，admin；M2/M3） ----


@stub_router.get("/api/v2/debug/traces", status_code=501)
async def debug_traces(
    current_user: Dict = Depends(require_permission("read")),
):
    _admin_user(current_user)
    raise CrystalAPIError(501, "Debug traces endpoint is planned for M2, not yet implemented.")


@stub_router.get("/api/v2/debug/embedding-logs", status_code=501)
async def debug_embedding_logs(
    current_user: Dict = Depends(require_permission("read")),
):
    _admin_user(current_user)
    raise CrystalAPIError(501, "Debug embedding-logs endpoint is planned for M2, not yet implemented.")


@stub_router.post("/api/v2/migrate/run", status_code=501)
async def migrate_run(
    current_user: Dict = Depends(require_permission("write")),
):
    _admin_user(current_user)
    raise CrystalAPIError(501, "Migrate endpoint is planned for M3, not yet implemented.")


@stub_router.get("/api/v2/migrate/status", status_code=501)
async def migrate_status(
    current_user: Dict = Depends(require_permission("read")),
):
    _admin_user(current_user)
    raise CrystalAPIError(501, "Migrate status endpoint is planned for M3, not yet implemented.")
