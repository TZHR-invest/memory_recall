"""
Memory Recall API - Unified v5.0
个人记忆管理与召回系统的 RESTful API
"""

import json
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from contextlib import asynccontextmanager
import traceback

from src.config import settings
from src.database import db
from src.background.scheduler import scheduler, setup_background_tasks
from src.routes import health

from src.api import memories, graph, auth_endpoints, embed, context_inject, debug, stats
from src.api.crystal import router as crystal_router
from src.api.crystal.errors import (
    CrystalAPIError,
    crystal_error_handler,
)


class UnicodeJSONResponse(JSONResponse):
    def render(self, content) -> bytes:
        return json.dumps(
            content,
            ensure_ascii=False,
            allow_nan=False,
            indent=None,
            separators=(",", ":"),
        ).encode("utf-8")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    try:
        await db.connect()
        print("✅ 数据库连接成功")

        vector_ext = await db.fetchval(
            "SELECT extname FROM pg_extension WHERE extname = 'vector'"
        )
        if vector_ext:
            print("✅ pgvector 扩展已启用")
        else:
            print("⚠️  pgvector 扩展未启用，向量功能将不可用")

        setup_background_tasks()
        await scheduler.start()
        print("✅ 后台任务调度器已启动")

        from src.api.crystal.worker import start_crystal_worker

        start_crystal_worker()
        print("✅ crystal 对账 worker 已启动")
    except Exception as e:
        print(f"❌ 数据库连接失败: {e}")
        raise

    yield

    try:
        from src.api.crystal.worker import stop_crystal_worker

        stop_crystal_worker()
        print("✅ crystal 对账 worker 已停止")
    except Exception as e:
        print(f"⚠️  crystal 对账 worker 停止出错: {e}")

    try:
        await scheduler.stop()
        print("✅ 后台任务调度器已停止")
    except Exception as e:
        print(f"⚠️  调度器关闭时出错: {e}")

    try:
        await db.disconnect()
        print("✅ 数据库连接已关闭")
    except Exception as e:
        print(f"⚠️  数据库关闭时出错: {e}")


app = FastAPI(
    title="Memory Recall API",
    description="""
# Memory Recall API v5.0

简化的个人记忆管理系统，支持向量检索和知识图谱。

## 认证

所有端点需要 API Key 认证：
- Header: `X-API-Key: <your-api-key>`
- 通过 `/auth/keys` 创建和管理 API Key

## 主要功能

### 📝 记忆管理
- 创建、查询、更新、删除记忆
- 自动实体提取和关系检测
- 静态/动态记忆分离

### 🔍 智能检索
- 语义搜索
- 用户画像聚合
- 知识图谱可视化

## 技术栈

- **FastAPI**: 高性能异步 Web 框架
- **PostgreSQL + pgvector**: 向量数据库
- **火山引擎**: Embedding 和 LLM 服务
    """,
    version="5.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    default_response_class=UnicodeJSONResponse,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = []
    for error in exc.errors():
        errors.append(
            {
                "loc": error.get("loc", []),
                "msg": str(error.get("msg", "")),
                "type": error.get("type", ""),
            }
        )
    if request.url.path.startswith("/api/v2"):
        # crystal：统一信封（api-contract §3.1 422）
        return UnicodeJSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=crystal_error_payload(422, "请求参数验证失败", errors),
        )
    # v5：保持原样（v5 零影响）
    return UnicodeJSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "code": 422,
            "message": "请求参数验证失败",
            "errors": errors,
        },
    )


def crystal_error_payload(code: int, message: str, detail=None) -> dict:
    """crystal 统一错误体（api-contract §3.2）"""
    body = {"code": code, "message": message}
    if detail is not None:
        body["detail"] = detail
    return body


# ==================== crystal /api/v2 异常处理（api-contract §3） ====================
# 注册顺序即匹配优先级：CrystalAPIError（crystal 专用子类）→ 最优先；
# 其余 handler 内按路径分流：/api/v2 → crystal 统一信封，其余 → v5 原样（v5 零影响）。
# 注意：v5 的 HTTPException 未注册统一信封（沿用 FastAPI 默认 JSONResponse），
# crystal 用 CrystalAPIError 子类 + 专用 handler，互不干扰。
app.add_exception_handler(CrystalAPIError, crystal_error_handler)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    if request.url.path.startswith("/api/v2"):
        # crystal：统一信封（api-contract §3.1 500）
        print(f"❌ crystal 未处理异常: {exc}")
        print(traceback.format_exc())
        return UnicodeJSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=crystal_error_payload(
                500,
                "服务器内部错误",
                str(exc) if settings.APP_DEBUG else "Internal server error",
            ),
        )
    # v5：保持原样
    print(f"❌ 未处理的异常: {exc}")
    print(traceback.format_exc())
    return UnicodeJSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "code": 500,
            "message": "服务器内部错误",
            "detail": str(exc) if settings.APP_DEBUG else "Internal server error",
        },
    )


# ==================== 注册路由 ====================

app.include_router(health.router, tags=["健康检查"])
app.include_router(memories.router)
app.include_router(graph.router)
app.include_router(auth_endpoints.router)
app.include_router(embed.router)
app.include_router(context_inject.router)
app.include_router(debug.router)
app.include_router(stats.router)
app.include_router(crystal_router, tags=["crystal /api/v2"])


# ==================== 根路径 ====================


@app.get("/", tags=["元数据"])
async def root():
    return {
        "message": "Memory Recall API",
        "version": "5.0.0",
        "docs": "/docs",
        "health": "/health",
        "endpoints": {
            "memories": "POST /memories",
            "list": "GET /memories",
            "profile": "GET /profile",
            "search": "POST /search",
            "graph": "GET /graph",
            "documents": "POST /documents",
            "embed": "POST /embed",
            "context_inject": "POST /context-inject",
            "auth": "POST /auth/keys",
        },
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.APP_DEBUG,
        log_level="info",
        access_log=True,
    )
