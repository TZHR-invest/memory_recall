"""
crystal /api/v2 路由包（M2：两链路落地 + 工作台）

- evidence_router：证据层 4 端点（真实写入，含幂等）
- reconcile_router：对账触发/job 状态
- search_router：召回（search/context-inject/claims）
- workbench_router：裁决面 + 洞察面
- stub_router：debug/migrate 桩（M2 收尾 / M3）
- worker：后台对账 worker（main.py lifespan 启停）
"""

from fastapi import APIRouter

from .evidence import router as evidence_router
from .reconcile import router as reconcile_router
from .search import router as search_router
from .stubs import stub_router
from .workbench import router as workbench_router

router = APIRouter()
router.include_router(evidence_router)
router.include_router(reconcile_router)
router.include_router(search_router)
router.include_router(workbench_router)
router.include_router(stub_router)

__all__ = [
    "router",
    "evidence_router",
    "reconcile_router",
    "search_router",
    "workbench_router",
    "stub_router",
]
