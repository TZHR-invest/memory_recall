"""
crystal /api/v2 路由包（M1：证据层真实写入 + 其余端点桩）

- evidence_router：证据层 4 端点（真实写入，含幂等）
- stub_router：对账/召回/工作台/debug/迁移桩（501，M2/M3）
- main.py 注册本包 router 并挂接统一异常 handler（errors.py）
"""

from fastapi import APIRouter

from .evidence import router as evidence_router
from .stubs import stub_router

router = APIRouter()
router.include_router(evidence_router)
router.include_router(stub_router)

__all__ = ["router", "evidence_router", "stub_router"]
