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
    "/api/stats",
    summary="统计信息",
    description="获取记忆系统的统计信息",
    tags=["统计"],
    responses={
        200: {
            "description": "统计信息",
            "content": {
                "application/json": {
                    "example": {
                        "code": 200,
                        "message": "success",
                        "data": {
                            "total_memories": 1000,
                            "active_memories": 950,
                            "archived_memories": 30,
                            "deleted_memories": 20,
                            "memories_by_input_type": {
                                "text": 800,
                                "image": 150,
                                "audio": 50
                            },
                            "memories_this_week": 50,
                            "memories_this_month": 200,
                            "storage_used_mb": 125.5,
                            "avg_embedding_dimension": 2048
                        }
                    }
                }
            }
        }
    }
)
async def get_stats():
    """
    获取统计信息
    
    返回记忆系统的各种统计数据：
    - 总记忆数量
    - 各状态记忆数量
    - 按输入类型分类
    - 时间统计
    - 存储使用
    """
    try:
        # 总记忆数量
        total = await db.fetchval("SELECT COUNT(*) FROM memories")
        
        # 各状态记忆数量
        active = await db.fetchval("SELECT COUNT(*) FROM memories WHERE status = 'active'")
        archived = await db.fetchval("SELECT COUNT(*) FROM memories WHERE status = 'archived'")
        deleted = await db.fetchval("SELECT COUNT(*) FROM memories WHERE status = 'deleted'")
        
        # 按输入类型分类
        input_type_stats = await db.fetch("""
            SELECT input_type, COUNT(*) as count
            FROM memories
            WHERE status = 'active'
            GROUP BY input_type
        """)
        
        memories_by_type = {row['input_type']: row['count'] for row in input_type_stats}
        
        # 本周和本月记忆数量
        now = datetime.utcnow()
        week_start = now - timedelta(days=now.weekday())
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        
        this_week = await db.fetchval(
            "SELECT COUNT(*) FROM memories WHERE created_at >= $1 AND status = 'active'",
            week_start
        )
        
        this_month = await db.fetchval(
            "SELECT COUNT(*) FROM memories WHERE created_at >= $1 AND status = 'active'",
            month_start
        )
        
        # 存储使用（估算）
        # 先获取总行数和有 embedding 的行数
        storage_stats = await db.fetchrow("""
            SELECT 
                COUNT(*) as total_rows,
                COUNT(embedding) as rows_with_embedding
            FROM memories
            WHERE status = 'active'
        """)
        
        # 估算存储使用（MB）
        if storage_stats and storage_stats['rows_with_embedding'] > 0:
            # 假设每条记录平均大小（包括 embedding）
            avg_row_size = 2048  # embedding size (8 bytes * 2048 dimensions)
            storage_mb = (storage_stats['rows_with_embedding'] * avg_row_size) / (1024 * 1024)
        else:
            storage_mb = 0
        
        # 平均访问次数
        avg_access = await db.fetchval(
            "SELECT AVG(access_count) FROM memories WHERE status = 'active'"
        ) or 0
        
        # 重要记忆数量
        important_count = await db.fetchval(
            "SELECT COUNT(*) FROM memories WHERE importance_score >= 0.8 AND status = 'active'"
        )
        
        return {
            "code": 200,
            "message": "success",
            "data": {
                "total_memories": total,
                "active_memories": active,
                "archived_memories": archived,
                "deleted_memories": deleted,
                "memories_by_input_type": memories_by_type,
                "memories_this_week": this_week,
                "memories_this_month": this_month,
                "storage_used_mb": round(storage_mb, 2),
                "avg_access_count": round(float(avg_access), 2),
                "important_memories": important_count,
                "timestamp": datetime.utcnow().isoformat()
            }
        }
    except Exception as e:
        return {
            "code": 500,
            "message": str(e),
            "data": None
        }


@router.get(
    "/api/stats/timeline",
    summary="时间线统计",
    description="按时间统计记忆数量",
    tags=["统计"]
)
async def get_timeline_stats(
    days: int = 30,
    group_by: str = "day"
):
    """
    获取时间线统计
    
    - **days**: 统计最近多少天，默认 30 天
    - **group_by**: 分组方式（day/week/month）
    """
    try:
        now = datetime.utcnow()
        start_date = now - timedelta(days=days)
        
        # 按天分组
        if group_by == "day":
            stats = await db.fetch("""
                SELECT 
                    DATE(created_at) as date,
                    COUNT(*) as count
                FROM memories
                WHERE created_at >= $1
                AND status = 'active'
                GROUP BY DATE(created_at)
                ORDER BY date DESC
            """, start_date)
        
        # 按周分组
        elif group_by == "week":
            stats = await db.fetch("""
                SELECT 
                    DATE_TRUNC('week', created_at) as week_start,
                    COUNT(*) as count
                FROM memories
                WHERE created_at >= $1
                AND status = 'active'
                GROUP BY DATE_TRUNC('week', created_at)
                ORDER BY week_start DESC
            """, start_date)
        
        # 按月分组
        else:
            stats = await db.fetch("""
                SELECT 
                    DATE_TRUNC('month', created_at) as month_start,
                    COUNT(*) as count
                FROM memories
                WHERE created_at >= $1
                AND status = 'active'
                GROUP BY DATE_TRUNC('month', created_at)
                ORDER BY month_start DESC
            """, start_date)
        
        return {
            "code": 200,
            "message": "success",
            "data": {
                "period": {
                    "start": start_date.isoformat(),
                    "end": now.isoformat(),
                    "days": days,
                    "group_by": group_by
                },
                "stats": [dict(row) for row in stats]
            }
        }
    except Exception as e:
        return {
            "code": 500,
            "message": str(e),
            "data": None
        }


@router.get(
    "/api/stats/tags",
    summary="标签统计",
    description="统计标签使用情况",
    tags=["统计"]
)
async def get_tag_stats(limit: int = 20):
    """
    获取标签统计
    
    - **limit**: 返回数量限制，默认 20
    """
    try:
        # 获取标签统计
        stats = await db.fetch("""
            SELECT 
                unnest(tags) as tag,
                COUNT(*) as count
            FROM memories
            WHERE status = 'active'
            AND tags IS NOT NULL
            GROUP BY tag
            ORDER BY count DESC
            LIMIT $1
        """, limit)
        
        return {
            "code": 200,
            "message": "success",
            "data": {
                "tags": [dict(row) for row in stats],
                "total_unique_tags": len(stats)
            }
        }
    except Exception as e:
        return {
            "code": 500,
            "message": str(e),
            "data": None
        }


@router.get(
    "/api/stats/locations",
    summary="地点统计",
    description="统计地点使用情况",
    tags=["统计"]
)
async def get_location_stats(limit: int = 20):
    """
    获取地点统计
    
    - **limit**: 返回数量限制，默认 20
    """
    try:
        stats = await db.fetch("""
            SELECT 
                location_name as location,
                COUNT(*) as count
            FROM memories
            WHERE status = 'active'
            AND location_name IS NOT NULL
            GROUP BY location_name
            ORDER BY count DESC
            LIMIT $1
        """, limit)
        
        return {
            "code": 200,
            "message": "success",
            "data": {
                "locations": [dict(row) for row in stats]
            }
        }
    except Exception as e:
        return {
            "code": 500,
            "message": str(e),
            "data": None
        }


@router.get(
    "/api/stats/people",
    summary="人物统计",
    description="统计人物出现情况",
    tags=["统计"]
)
async def get_people_stats(limit: int = 20):
    """
    获取人物统计
    
    - **limit**: 返回数量限制，默认 20
    """
    try:
        # 从 people JSON 字段中提取人物统计
        stats = await db.fetch("""
            SELECT 
                person->>'name' as name,
                COUNT(*) as count
            FROM memories,
                jsonb_array_elements(people) as person
            WHERE status = 'active'
            AND people IS NOT NULL
            GROUP BY person->>'name'
            ORDER BY count DESC
            LIMIT $1
        """, limit)
        
        return {
            "code": 200,
            "message": "success",
            "data": {
                "people": [dict(row) for row in stats]
            }
        }
    except Exception as e:
        return {
            "code": 500,
            "message": str(e),
            "data": None
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

