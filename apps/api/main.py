"""
Memory Recall API - 主入口
个人记忆管理与召回系统的 RESTful API
"""

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from contextlib import asynccontextmanager
from datetime import datetime
import traceback

from src.config import settings
from src.database import db
from src.routes import health
from src.routes import memories
from src.routes import upload
from src.routes import files
from src.routes import graph
from src.routes import users
from src.routes import context


# ==================== 应用生命周期管理 ====================


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时连接数据库
    try:
        await db.connect()
        print("✅ 数据库连接成功")

        # 验证数据库扩展
        vector_ext = await db.fetchval(
            "SELECT extname FROM pg_extension WHERE extname = 'vector'"
        )
        if vector_ext:
            print("✅ pgvector 扩展已启用")
        else:
            print("⚠️  pgvector 扩展未启用，向量功能将不可用")
    except Exception as e:
        print(f"❌ 数据库连接失败: {e}")
        raise

    yield

    # 关闭时断开数据库
    try:
        await db.disconnect()
        print("✅ 数据库连接已关闭")
    except Exception as e:
        print(f"⚠️  数据库关闭时出错: {e}")


# ==================== 创建 FastAPI 应用 ====================

app = FastAPI(
    title="Memory Recall API",
    description="""
# 个人记忆管理与召回系统

一个基于向量检索的个人记忆管理系统，支持自然语言查询和智能召回。

## 主要功能

### 📝 记忆管理
- **创建记忆**: 支持文本、图片、音频等多种输入类型
- **查询记忆**: 支持分页、过滤、排序
- **更新记忆**: 支持部分更新和完整更新
- **删除记忆**: 软删除机制，支持恢复

### 🔍 智能检索
- **语义搜索**: 基于向量相似度的语义搜索
- **混合检索**: 向量检索 + 关键词检索混合排序
- **自然语言查询**: 支持时间、地点、人物等自然语言查询
- **多维度过滤**: 时间范围、地点、人物、标签等

### 📊 统计分析
- **记忆统计**: 总量、分类、时间分布
- **标签统计**: 标签使用频率
- **地点统计**: 地点出现频率
- **人物统计**: 人物出现频率

## 技术栈

- **FastAPI**: 高性能异步 Web 框架
- **PostgreSQL**: 关系型数据库
- **pgvector**: PostgreSQL 向量扩展
- **火山引擎**: Embedding 和 LLM 服务

## API 版本

当前版本: v1

所有 API 端点前缀: `/api/v1`
    """,
    version=settings.APP_VERSION,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    contact={
        "name": "Memory Recall Team",
        "email": "support@memoryrecall.ai",
    },
    license_info={
        "name": "MIT License",
        "url": "https://opensource.org/licenses/MIT",
    },
)


# ==================== CORS 配置 ====================

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境应该限制
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ==================== 异常处理 ====================


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """请求验证异常处理"""
    errors = []
    for error in exc.errors():
        errors.append(
            {
                "loc": error.get("loc", []),
                "msg": str(error.get("msg", "")),
                "type": error.get("type", ""),
            }
        )
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "code": 422,
            "message": "请求参数验证失败",
            "errors": errors,
            "body": str(exc.body) if exc.body else None,
        },
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """全局异常处理"""
    # 记录错误日志
    print(f"❌ 未处理的异常: {exc}")
    print(traceback.format_exc())

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "code": 500,
            "message": "服务器内部错误",
            "detail": str(exc) if settings.APP_DEBUG else "Internal server error",
        },
    )


# ==================== 注册路由 ====================

# 健康检查（无前缀）
app.include_router(health.router, tags=["健康检查"])

# API 路由（带版本前缀）
app.include_router(users.router, prefix="/api/v1", tags=["用户管理"])
app.include_router(memories.router, prefix="/api/v1", tags=["记忆管理"])
app.include_router(upload.router, prefix="/api/v1", tags=["图片上传"])
app.include_router(files.router, prefix="/api/v1", tags=["文件上传"])
app.include_router(graph.router, tags=["图谱增强召回"])
app.include_router(context.router, prefix="/api/v1", tags=["上下文管理"])


# ==================== 根路径和元数据 ====================


@app.get(
    "/",
    summary="API 根路径",
    description="返回 API 基本信息",
    tags=["元数据"],
    responses={
        200: {
            "description": "API 基本信息",
            "content": {
                "application/json": {
                    "example": {
                        "message": "Memory Recall API",
                        "version": "1.0.0",
                        "docs": "/docs",
                        "health": "/health",
                        "endpoints": {
                            "memories": "/api/v1/memories",
                            "search": "/api/v1/memories/search",
                            "recall": "/api/v1/memories/recall",
                            "stats": "/api/stats",
                        },
                    }
                }
            },
        }
    },
)
async def root():
    """API 根路径"""
    return {
        "message": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "docs": "/docs",
        "redoc": "/redoc",
        "health": "/health",
        "endpoints": {
            "memories": "/api/v1/memories",
            "search": "/api/v1/memories/search",
            "recall": "/api/v1/memories/recall",
            "stats": "/api/stats",
            "timeline_stats": "/api/stats/timeline",
            "tag_stats": "/api/stats/tags",
            "location_stats": "/api/stats/locations",
            "people_stats": "/api/stats/people",
        },
    }


@app.get(
    "/api",
    summary="API 端点列表",
    description="返回所有可用的 API 端点",
    tags=["元数据"],
)
async def api_info():
    """API 端点列表"""
    return {
        "version": "v1",
        "base_url": "/api/v1",
        "endpoints": {
            "memories": {
                "list": "GET /api/v1/memories",
                "create": "POST /api/v1/memories",
                "get": "GET /api/v1/memories/{id}",
                "update": "PUT /api/v1/memories/{id}",
                "delete": "DELETE /api/v1/memories/{id}",
                "batch_create": "POST /api/v1/memories/batch",
                "batch_delete": "DELETE /api/v1/memories/batch",
            },
            "search": {
                "semantic": "POST /api/v1/memories/search",
                "natural_language": "POST /api/v1/memories/recall",
            },
            "stats": {
                "overview": "GET /api/stats",
                "timeline": "GET /api/stats/timeline",
                "tags": "GET /api/stats/tags",
                "locations": "GET /api/stats/locations",
                "people": "GET /api/stats/people",
            },
            "health": {"check": "GET /health", "database": "GET /health/db"},
        },
    }


@app.get(
    "/openapi",
    summary="OpenAPI 规范",
    description="返回 OpenAPI JSON 规范",
    tags=["元数据"],
)
async def openapi_spec():
    """OpenAPI 规范"""
    return app.openapi()


# ==================== 启动配置 ====================

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
_level = ("info",)
