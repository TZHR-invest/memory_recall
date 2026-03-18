"""
健康检查路由
"""
from fastapi import APIRouter
from src.database import db
from src.config import settings

router = APIRouter()


@router.get("/health")
async def health_check():
    """健康检查"""
    return {
        "status": "healthy",
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "env": settings.APP_ENV
    }


@router.get("/health/db")
async def database_health():
    """数据库健康检查"""
    try:
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
        
        return {
            "status": "healthy",
            "database": {
                "connected": True,
                "version": version,
                "pgvector": vector_ext is not None,
                "tables": len(tables)
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
