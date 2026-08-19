"""
crystal 剩余端点桩（api-contract §2.5：debug）

M2 已完成：证据层（evidence.py）、对账（reconcile.py）、召回（search.py）、
工作台（workbench.py）；M3 已完成：迁移（migrate.py）。
此处只留 debug（trace/embedding 日志）桩。
"""

from typing import Dict

from fastapi import APIRouter, Depends

from src.api.auth import require_permission

from .errors import CrystalAPIError

stub_router = APIRouter(tags=["crystal-stubs"])


def _admin_user(current_user: Dict) -> Dict:
    """admin 判定（api-contract §1.3）：is_test 或权限含 debug"""
    if not (current_user.get("is_test") or "debug" in current_user.get("permissions", [])):
        raise CrystalAPIError(403, "Admin permission required.")
    return current_user


# ---- 调试（§2.5，admin；trace/embedding 日志，M2 收尾） ----


@stub_router.get("/api/v2/debug/traces", status_code=501)
async def debug_traces(
    current_user: Dict = Depends(require_permission("read")),
):
    _admin_user(current_user)
    raise CrystalAPIError(501, "Debug traces endpoint is planned for M2 wrap-up, not yet implemented.")


@stub_router.get("/api/v2/debug/embedding-logs", status_code=501)
async def debug_embedding_logs(
    current_user: Dict = Depends(require_permission("read")),
):
    _admin_user(current_user)
    raise CrystalAPIError(501, "Debug embedding-logs endpoint is planned for M2 wrap-up, not yet implemented.")
