"""
记忆管理 API 路由
"""
from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional
from datetime import datetime

from ..models.memory import Memory, MemoryCreate, MemoryUpdate
from ..services.memory_service import memory_service
from ..database import db

router = APIRouter(prefix="/memories", tags=["记忆管理"])


@router.post("", response_model=dict)
async def create_memory(memory: MemoryCreate):
    """
    创建记忆
    
    Args:
        memory: 记忆创建数据
    
    Returns:
        创建的记忆信息
    """
    try:
        memory_id = await memory_service.create(memory)
        
        # 获取创建的记忆
        created_memory = await memory_service.get(memory_id)
        
        return {
            "code": 200,
            "message": "success",
            "data": created_memory.model_dump()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{memory_id}", response_model=dict)
async def get_memory(memory_id: str):
    """
    获取记忆
    
    Args:
        memory_id: 记忆 ID
    
    Returns:
        记忆信息
    """
    memory = await memory_service.get(memory_id)
    
    if not memory:
        raise HTTPException(status_code=404, detail="Memory not found")
    
    # 更新访问计数
    await db.execute("""
        UPDATE memories 
        SET access_count = access_count + 1, 
            last_accessed_at = NOW()
        WHERE id = $1
    """, memory_id)
    
    return {
        "code": 200,
        "message": "success",
        "data": memory.model_dump()
    }


@router.patch("/{memory_id}", response_model=dict)
async def update_memory(memory_id: str, updates: MemoryUpdate):
    """
    更新记忆
    
    Args:
        memory_id: 记忆 ID
        updates: 更新数据
    
    Returns:
        更新结果
    """
    success = await memory_service.update(memory_id, updates)
    
    if not success:
        raise HTTPException(status_code=404, detail="Memory not found")
    
    # 获取更新后的记忆
    updated_memory = await memory_service.get(memory_id)
    
    return {
        "code": 200,
        "message": "success",
        "data": updated_memory.model_dump()
    }


@router.delete("/{memory_id}", response_model=dict)
async def delete_memory(memory_id: str):
    """
    删除记忆（软删除）
    
    Args:
        memory_id: 记忆 ID
    
    Returns:
        删除结果
    """
    success = await memory_service.delete(memory_id)
    
    if not success:
        raise HTTPException(status_code=404, detail="Memory not found")
    
    return {
        "code": 200,
        "message": "success",
        "data": None
    }


@router.get("", response_model=dict)
async def list_memories(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    status: str = Query("active")
):
    """
    列出记忆
    
    Args:
        limit: 数量限制
        offset: 偏移量
        status: 状态过滤
    
    Returns:
        记忆列表
    """
    memories = await memory_service.list(limit, offset, status)
    
    return {
        "code": 200,
        "message": "success",
        "data": {
            "memories": [m.model_dump() for m in memories],
            "count": len(memories)
        }
    }


@router.get("/search/time", response_model=dict)
async def search_by_time(
    start: datetime,
    end: datetime,
    limit: int = Query(50, ge=1, le=100)
):
    """
    按时间范围搜索记忆
    
    Args:
        start: 开始时间
        end: 结束时间
        limit: 数量限制
    
    Returns:
        记忆列表
    """
    memories = await memory_service.search_by_time(start, end, limit)
    
    return {
        "code": 200,
        "message": "success",
        "data": {
            "memories": [m.model_dump() for m in memories],
            "count": len(memories)
        }
    }


@router.get("/search/location", response_model=dict)
async def search_by_location(
    location: str,
    limit: int = Query(50, ge=1, le=100)
):
    """
    按位置搜索记忆
    
    Args:
        location: 位置名称
        limit: 数量限制
    
    Returns:
        记忆列表
    """
    memories = await memory_service.search_by_location(location, limit)
    
    return {
        "code": 200,
        "message": "success",
        "data": {
            "memories": [m.model_dump() for m in memories],
            "count": len(memories)
        }
    }


@router.get("/search/person", response_model=dict)
async def search_by_person(
    person: str,
    limit: int = Query(50, ge=1, le=100)
):
    """
    按人物搜索记忆
    
    Args:
        person: 人物名称
        limit: 数量限制
    
    Returns:
        记忆列表
    """
    memories = await memory_service.search_by_person(person, limit)
    
    return {
        "code": 200,
        "message": "success",
        "data": {
            "memories": [m.model_dump() for m in memories],
            "count": len(memories)
        }
    }
