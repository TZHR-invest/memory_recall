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

from src.api import memories, graph, auth_endpoints, embed, context_inject


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
    except Exception as e:
        print(f"❌ 数据库连接失败: {e}")
        raise

    yield

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
    return UnicodeJSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "code": 422,
            "message": "请求参数验证失败",
            "errors": errors,
        },
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
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
