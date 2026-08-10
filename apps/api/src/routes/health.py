"""
健康检查和统计路由
"""
from fastapi import APIRouter
from src.database import db
from src.config import settings
from datetime import datetime, timedelta
import asyncpg
from src.cache.manager import cache_manager

router = APIRouter()


@router.get(
    "/health",
    summary="健康检查",
    description="检查服务健康状态",
    tags=["健康检查"],
    responses={
        200: {
            "description": "健康状态",
            "content": {
                "application/json": {
                    "example": {
                        "status": "healthy",
                        "app": "Memory Recall API",
                        "version": "1.0.0",
                        "env": "development",
                        "timestamp": "2024-01-01T12:00:00"
                    }
                }
            }
        }
    }
)
async def health_check():
    """
    健康检查
    
    返回服务的基本健康状态信息
    """
    return {
        "status": "healthy",
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "env": settings.APP_ENV,
        "timestamp": datetime.utcnow().isoformat()
    }


@router.get(
    "/health/db",
    summary="数据库健康检查",
    description="检查数据库连接和状态",
    tags=["健康检查"],
    responses={
        200: {
            "description": "数据库健康状态",
            "content": {
                "application/json": {
                    "example": {
                        "status": "healthy",
                        "database": {
                            "connected": True,
                            "version": "PostgreSQL 16.0",
                            "pgvector": True,
                            "tables": 5,
                            "latency_ms": 1.23
                        }
                    }
                }
            }
        }
    }
)
async def database_health():
    """
    数据库健康检查
    
    检查数据库连接、版本、扩展等
    """
    try:
        start_time = datetime.utcnow()
        
        # 测试数据库连接
        result = await db.fetchval("SELECT 1")
        
        # 获取数据库版本
        version = await db.fetchval("SELECT version()")
        
        # 检查 pgvector 扩展
        vector_ext = await db.fetchval(
            "SELECT extname FROM pg_extension WHERE extname = 'vector'"
        )
        
        # 获取表数量
        tables = await db.fetch("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_type = 'BASE TABLE'
        """)
        
        # 计算延迟
        latency = (datetime.utcnow() - start_time).total_seconds() * 1000
        
        return {
            "status": "healthy",
            "database": {
                "connected": True,
                "version": version,
                "pgvector": vector_ext is not None,
                "tables": len(tables),
                "latency_ms": round(latency, 2)
            }
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "database": {
                "connected": False,
                "error": str(e)
            }
        }


@router.get(
    "/api/stats/cache",
    summary="缓存统计",
    description="获取缓存性能统计信息",
    tags=["统计"]
)
async def get_cache_stats():
    """
    获取缓存统计
    
    返回缓存命中率和使用情况
    """
    try:
        stats = cache_manager.stats()
        
        return {
            "code": 200,
            "message": "success",
            "data": {
                "cache": {
                    "size": stats["size"],
                    "max_size": stats["max_size"],
                    "usage_percent": round((stats["size"] / stats["max_size"]) * 100, 2) if stats["max_size"] > 0 else 0,
                },
                "performance": {
                    "hits": stats["hits"],
                    "misses": stats["misses"],
                    "hit_rate": round(stats["hit_rate"] * 100, 2),
                    "total_requests": stats["total_requests"]
                },
                "timestamp": datetime.utcnow().isoformat()
            }
        }
    except Exception as e:
        return {
            "code": 500,
            "message": str(e),
            "data": None
        }


@router.post(
    "/api/stats/cache/clear",
    summary="清空缓存",
    description="清空所有缓存数据",
    tags=["统计"]
)
async def clear_cache():
    """
    清空缓存
    
    用于测试或重置缓存
    """
    try:
        cache_manager.clear()
        
        return {
            "code": 200,
            "message": "缓存已清空",
            "data": None
        }
    except Exception as e:
        return {
            "code": 500,
            "message": str(e),
            "data": None
        }

