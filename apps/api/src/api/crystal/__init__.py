"""
crystal /api/v2 路由包（M3：两链路 + 工作台 + 迁移）

- evidence_router：证据层 4 端点（真实写入，含幂等）
- reconcile_router：对账触发/job 状态
- search_router：召回（search/context-inject/claims）
- workbench_router：裁决面 + 洞察面
- migrate_router：admin 迁移（M3）
- stub_router：debug 桩（M2 收尾）
- worker：后台对账 worker（main.py lifespan 启停）
- guards：部署前置闸门（schema 缺失 ⇒ 503 而非裸 500，MR-027 D4）
"""

from fastapi import APIRouter, Depends

from .evidence import router as evidence_router
from .guards import require_crystal_schema
from .migrate import router as migrate_router
from .reconcile import router as reconcile_router
from .search import router as search_router
from .stubs import stub_router
from .workbench import router as workbench_router

# 全部 /api/v2 端点统一带 schema 前置闸门：crystal schema 未初始化（v2 未部署）时
# 返回 503 + 统一信封 + 处置指引，不再把"未部署"暴露成 relation does not exist 的 500。
router = APIRouter(dependencies=[Depends(require_crystal_schema)])
router.include_router(evidence_router)
router.include_router(reconcile_router)
router.include_router(search_router)
router.include_router(workbench_router)
router.include_router(migrate_router)
router.include_router(stub_router)

__all__ = [
    "router",
    "evidence_router",
    "reconcile_router",
    "search_router",
    "workbench_router",
    "migrate_router",
    "stub_router",
]

