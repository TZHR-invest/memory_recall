"""
记忆管理 API 路由
"""
from fastapi import APIRouter, HTTPException, Query, Body
from typing import List, Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field

from ..models.memory import Memory, MemoryCreate, MemoryUpdate
from ..services.memory_service import memory_service
from ..services.recall_service import get_recall_service
from ..services.query_parser import query_parser
from ..database import db

router = APIRouter(prefix="/memories", tags=["记忆管理"])


# ==================== 请求模型 ====================

class SearchRequest(BaseModel):
    """搜索请求"""
    query: str = Field(..., description="搜索查询文本")
    limit: int = Field(10, ge=1, le=100, description="返回数量限制")
    min_similarity: float = Field(0.25, ge=0.0, le=1.0, description="最小相似度阈值（默认0.25，提高准确性）")
    hybrid_weight: float = Field(0.6, ge=0.0, le=1.0, description="向量检索权重（默认0.6，增加关键词权重）")


class RecallRequest(BaseModel):
    """召回请求"""
    query: str = Field(..., description="自然语言查询")
    limit: int = Field(10, ge=1, le=100, description="返回数量限制")
    use_parser: bool = Field(True, description="是否使用自然语言解析")
    min_similarity: float = Field(0.25, ge=0.0, le=1.0, description="最小相似度阈值（默认0.25）")


class NaturalLanguageQuery(BaseModel):
    """自然语言查询请求"""
    query: str = Field(..., description="自然语言查询文本")
    limit: int = Field(10, ge=1, le=100, description="返回数量限制")


# ==================== CRUD 端点 ====================

@router.post(
    "",
    response_model=dict,
    summary="创建记忆",
    description="创建一条新的记忆记录",
    responses={
        200: {
            "description": "创建成功",
            "content": {
                "application/json": {
                    "example": {
                        "code": 200,
                        "message": "success",
                        "data": {
                            "id": "mem_abc123def456",
                            "content": "今天和老同学在咖啡店见面聊天",
                            "input_type": "text",
                            "created_at": "2024-01-01T12:00:00"
                        }
                    }
                }
            }
        },
        500: {"description": "服务器内部错误"}
    }
)
async def create_memory(memory: MemoryCreate):
    """
    创建记忆
    
    - **content**: 记忆内容（必填）
    - **input_type**: 输入类型（text/image/audio），默认 text
    - **time**: 时间信息（可选）
    - **location**: 地点信息（可选）
    - **people**: 人物信息（可选）
    - **emotion**: 情绪信息（可选）
    - **tags**: 标签列表（可选）
    """
    try:
        # 如果是文本输入且没有提供结构化数据，使用文本处理器
        if memory.input_type == "text" and not any([
            memory.time, memory.location, memory.people,
            memory.emotion, memory.tags
        ]):
            result = await memory_service.process_text_input(memory.content, auto_confirm=True)
            if result["success"]:
                memory_id = result.get("memory_id")
                if memory_id:
                    created_memory = await memory_service.get(memory_id)
                    return {
                        "code": 200,
                        "message": "success",
                        "data": created_memory.model_dump()
                    }
            else:
                raise HTTPException(status_code=500, detail=result.get("error", "处理失败"))
        
        # 否则直接创建
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


@router.get(
    "",
    response_model=dict,
    summary="列出记忆",
    description="获取记忆列表，支持分页和状态过滤",
    responses={
        200: {
            "description": "成功",
            "content": {
                "application/json": {
                    "example": {
                        "code": 200,
                        "message": "success",
                        "data": {
                            "memories": [],
                            "count": 0,
                            "total": 100,
                            "has_more": True
                        }
                    }
                }
            }
        }
    }
)
async def list_memories(
    limit: int = Query(50, ge=1, le=100, description="数量限制"),
    offset: int = Query(0, ge=0, description="偏移量"),
    status: str = Query("active", description="状态过滤（active/archived/deleted）"),
    order_by: str = Query("created_at", description="排序字段"),
    order: str = Query("desc", description="排序方向（asc/desc）")
):
    """
    列出记忆
    
    - **limit**: 每页数量，1-100，默认 50
    - **offset**: 偏移量，默认 0
    - **status**: 状态过滤，默认 active
    - **order_by**: 排序字段，默认 created_at
    - **order**: 排序方向，默认 desc
    """
    memories = await memory_service.list(limit, offset, status)
    
    # 获取总数
    total = await db.fetchval(
        "SELECT COUNT(*) FROM memories WHERE status = $1",
        status
    )
    
    return {
        "code": 200,
        "message": "success",
        "data": {
            "memories": [m.model_dump() for m in memories],
            "count": len(memories),
            "total": total,
            "has_more": offset + limit < total
        }
    }


@router.get(
    "/{memory_id}",
    response_model=dict,
    summary="获取单个记忆",
    description="根据 ID 获取记忆详情",
    responses={
        200: {"description": "成功"},
        404: {"description": "记忆不存在"}
    }
)
async def get_memory(memory_id: str):
    """
    获取记忆
    
    - **memory_id**: 记忆 ID
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


@router.put(
    "/{memory_id}",
    response_model=dict,
    summary="更新记忆",
    description="更新记忆内容",
    responses={
        200: {"description": "更新成功"},
        404: {"description": "记忆不存在"}
    }
)
async def update_memory(memory_id: str, updates: MemoryUpdate):
    """
    更新记忆（完整更新）
    
    - **memory_id**: 记忆 ID
    - **updates**: 更新数据
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


@router.delete(
    "/{memory_id}",
    response_model=dict,
    summary="删除记忆",
    description="删除记忆（软删除）",
    responses={
        200: {"description": "删除成功"},
        404: {"description": "记忆不存在"}
    }
)
async def delete_memory(memory_id: str):
    """
    删除记忆（软删除）
    
    - **memory_id**: 记忆 ID
    """
    success = await memory_service.delete(memory_id)
    
    if not success:
        raise HTTPException(status_code=404, detail="Memory not found")
    
    return {
        "code": 200,
        "message": "success",
        "data": None
    }


# ==================== 搜索端点 ====================

@router.post(
    "/search",
    response_model=dict,
    summary="语义搜索",
    description="使用向量相似度和关键词混合检索记忆",
    responses={
        200: {
            "description": "搜索成功",
            "content": {
                "application/json": {
                    "example": {
                        "code": 200,
                        "message": "success",
                        "data": {
                            "results": [
                                {
                                    "id": "mem_abc123",
                                    "content": "今天在咖啡店见面",
                                    "similarity": 0.95,
                                    "vector_score": 0.92,
                                    "keyword_score": 0.98
                                }
                            ],
                            "count": 1,
                            "query": "咖啡店"
                        }
                    }
                }
            }
        }
    }
)
async def search_memories(request: SearchRequest):
    """
    语义搜索记忆
    
    使用向量相似度 + 关键词混合检索：
    - **query**: 搜索查询文本
    - **limit**: 返回数量，默认 10
    - **min_similarity**: 最小相似度阈值，默认 0.5
    - **hybrid_weight**: 向量检索权重，默认 0.7（关键词权重为 0.3）
    """
    try:
        recall_service = get_recall_service()
        
        results = await recall_service.search(
            query=request.query,
            limit=request.limit,
            min_similarity=request.min_similarity,
            hybrid_weight=request.hybrid_weight
        )
        
        return {
            "code": 200,
            "message": "success",
            "data": {
                "results": results,
                "count": len(results),
                "query": request.query
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/recall",
    response_model=dict,
    summary="自然语言召回",
    description="使用自然语言查询召回相关记忆",
    responses={
        200: {
            "description": "召回成功",
            "content": {
                "application/json": {
                    "example": {
                        "code": 200,
                        "message": "success",
                        "data": {
                            "results": [],
                            "count": 3,
                            "parsed_query": {
                                "time_range": {"start": "2024-01-01", "end": "2024-01-07"},
                                "location": "咖啡店",
                                "people": ["老同学"],
                                "keywords": ["见面", "聊天"]
                            }
                        }
                    }
                }
            }
        }
    }
)
async def recall_memories(request: RecallRequest):
    """
    自然语言召回记忆
    
    智能解析自然语言查询（默认使用 Jieba 分词）：
    - **query**: 自然语言查询，例如"上周在咖啡店和老同学见面"
    - **limit**: 返回数量，默认 10
    - **use_parser**: 是否使用自然语言解析，默认 True
    - **min_similarity**: 最小相似度阈值，默认 0.25
    
    支持的查询类型：
    - 时间查询："上周发生了什么"、"最近3天"
    - 地点查询："在咖啡店发生了什么"
    - 人物查询："和老同学相关的记忆"
    - 情绪查询："最近开心的事"
    - 混合查询："上周在咖啡店和老同学见面"
    """
    try:
        recall_service = get_recall_service()
        
        # 解析查询（默认使用 Jieba 分词，速度快）
        parsed_query = None
        if request.use_parser:
            # 使用 Jieba 分词
            from ..services.jieba_service import extract_keywords, extract_time_keywords
            import time
            
            start_time = time.time()
            keywords = extract_keywords(request.query)
            time_range = extract_time_keywords(request.query)
            jieba_time = (time.time() - start_time) * 1000
            
            parsed_query = {
                "source": "jieba",
                "keywords": keywords,
                "time_range": time_range,
                "location": None,  # Jieba 不提取地点
                "people": [],  # Jieba 不提取人物
                "parse_time_ms": jieba_time
            }
        
        # 构建过滤条件
        time_range = None
        location_filter = None
        person_filter = None
        
        if parsed_query:
            # 时间范围（转换格式）
            if parsed_query.get("time_range"):
                tr = parsed_query["time_range"]
                if tr.get("start") and tr.get("end"):
                    from datetime import datetime
                    time_range = {
                        "start_time": datetime.fromisoformat(str(tr["start"])) if isinstance(tr["start"], str) else tr["start"],
                        "end_time": datetime.fromisoformat(str(tr["end"])) if isinstance(tr["end"], str) else tr["end"]
                    }
            
            # 地点
            if parsed_query.get("location"):
                location_filter = parsed_query["location"]
            
            # 人物
            if parsed_query.get("people") and len(parsed_query["people"]) > 0:
                person_filter = parsed_query["people"][0]
        
        # 执行搜索
        results = await recall_service.search(
            query=request.query,
            limit=request.limit,
            time_range=time_range,
            location_filter=location_filter,
            person_filter=person_filter,
            min_similarity=request.min_similarity,
            keywords=parsed_query.get("keywords") if parsed_query else None
        )
        
        return {
            "code": 200,
            "message": "success",
            "data": {
                "results": results,
                "count": len(results),
                "parsed_query": parsed_query
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==================== 专用搜索端点 ====================

@router.get(
    "/search/time",
    response_model=dict,
    summary="按时间搜索",
    description="按时间范围搜索记忆",
    deprecated=True
)
async def search_by_time(
    start: datetime = Query(..., description="开始时间"),
    end: datetime = Query(..., description="结束时间"),
    limit: int = Query(50, ge=1, le=100, description="数量限制")
):
    """
    按时间范围搜索记忆
    
    - **start**: 开始时间（ISO 8601 格式）
    - **end**: 结束时间（ISO 8601 格式）
    - **limit**: 数量限制
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


@router.get(
    "/search/location",
    response_model=dict,
    summary="按地点搜索",
    description="按地点搜索记忆",
    deprecated=True
)
async def search_by_location(
    location: str = Query(..., description="地点名称"),
    limit: int = Query(50, ge=1, le=100, description="数量限制")
):
    """
    按地点搜索记忆
    
    - **location**: 地点名称
    - **limit**: 数量限制
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


@router.get(
    "/search/person",
    response_model=dict,
    summary="按人物搜索",
    description="按人物搜索记忆",
    deprecated=True
)
async def search_by_person(
    person: str = Query(..., description="人物名称"),
    limit: int = Query(50, ge=1, le=100, description="数量限制")
):
    """
    按人物搜索记忆
    
    - **person**: 人物名称
    - **limit**: 数量限制
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


# ==================== 批量操作端点 ====================

@router.post(
    "/batch",
    response_model=dict,
    summary="批量创建记忆",
    description="批量创建多条记忆"
)
async def batch_create_memories(memories: List[MemoryCreate]):
    """
    批量创建记忆
    
    - **memories**: 记忆列表（最多 100 条）
    """
    if len(memories) > 100:
        raise HTTPException(status_code=400, detail="Maximum 100 memories per batch")
    
    try:
        created_ids = []
        for memory in memories:
            memory_id = await memory_service.create(memory)
            created_ids.append(memory_id)
        
        return {
            "code": 200,
            "message": "success",
            "data": {
                "created_count": len(created_ids),
                "memory_ids": created_ids
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete(
    "/batch",
    response_model=dict,
    summary="批量删除记忆",
    description="批量删除多条记忆"
)
async def batch_delete_memories(memory_ids: List[str] = Body(...)):
    """
    批量删除记忆
    
    - **memory_ids**: 记忆 ID 列表（最多 100 条）
    """
    if len(memory_ids) > 100:
        raise HTTPException(status_code=400, detail="Maximum 100 memories per batch")
    
    try:
        deleted_count = 0
        for memory_id in memory_ids:
            if await memory_service.delete(memory_id):
                deleted_count += 1
        
        return {
            "code": 200,
            "message": "success",
            "data": {
                "deleted_count": deleted_count
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
