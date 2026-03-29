"""
记忆管理 API 路由
"""

from fastapi import APIRouter, HTTPException, Query, Body
from typing import List, Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field

from ..models.memory import MemoryCreate
from ..services.unified_memory_service import unified_memory_service
from ..services.core.lossless_recall_service import lossless_recall_service
from ..services.llm_recall_service import get_llm_recall_service
from ..database import db

router = APIRouter(prefix="/memories", tags=["记忆管理"])


# ==================== 请求模型 ====================


class SearchRequest(BaseModel):
    """搜索请求"""

    query: str = Field(..., description="搜索查询文本")
    user_id: str = Field(..., description="用户 ID")
    limit: int = Field(10, ge=1, le=100, description="返回数量限制")
    min_similarity: float = Field(
        0.15, ge=0.0, le=1.0, description="最小相似度阈值（默认0.15）"
    )
    hybrid_weight: float = Field(
        0.6, ge=0.0, le=1.0, description="向量检索权重（默认0.6，增加关键词权重）"
    )


class RecallRequest(BaseModel):
    """召回请求"""

    query: str = Field(..., description="自然语言查询")
    user_id: str = Field(..., description="用户 ID")
    limit: int = Field(20, ge=1, le=100, description="返回数量限制")
    use_parser: bool = Field(True, description="是否使用自然语言解析")
    min_similarity: float = Field(
        0.05, ge=0.0, le=1.0, description="最小相似度阈值（默认0.05）"
    )
    detail_level: str = Field(
        "medium", description="回答详情级别 (brief/medium/detailed)"
    )
    use_smart_recall: bool = Field(
        True,
        description="是否使用智能召回（Function Calling，LLM自动选择策略，默认启用）",
    )


class NaturalLanguageQuery(BaseModel):
    """自然语言查询请求"""

    query: str = Field(..., description="自然语言查询文本")
    limit: int = Field(10, ge=1, le=100, description="返回数量限制")


class CreateMemoryWithGraphRequest(BaseModel):
    """创建记忆（带图谱构建）请求"""

    content: str = Field(..., description="记忆内容")
    user_id: str = Field(..., description="用户 ID")
    enable_graph: bool = Field(True, description="是否启用图谱构建")
    enable_confirmation: bool = Field(False, description="是否启用智能确认")
    use_unified: bool = Field(True, description="是否使用统一提取（1次LLM调用）")


class SmartRecallRequest(BaseModel):
    """智能召回请求"""

    query: str = Field(..., description="自然语言查询")
    user_id: str = Field(..., description="用户 ID")
    limit: int = Field(10, ge=1, le=100, description="返回数量限制")
    detail_level: str = Field(
        "medium", description="回答详情级别 (brief/medium/detailed)"
    )


# ==================== CRUD 端点 ====================


@router.post(
    "",
    response_model=dict,
    summary="创建记忆",
    description="创建一条新的记忆记录（使用统一 DAG 架构）",
    responses={
        200: {
            "description": "创建成功",
            "content": {
                "application/json": {
                    "example": {
                        "code": 200,
                        "message": "success",
                        "data": {
                            "id": "raw_abc123def456",
                            "content": "今天和老同学在咖啡店见面聊天",
                            "memory_type": "preference",
                            "source": "manual",
                            "created_at": "2024-01-01T12:00:00",
                        },
                    }
                }
            },
        },
        500: {"description": "服务器内部错误"},
    },
)
async def create_memory(
    memory: MemoryCreate, user_id: str = Query(..., description="用户 ID")
):
    """
    创建记忆（统一 DAG 架构）

    - **content**: 记忆内容（必填）
    - **input_type**: 输入类型（text/image/audio），默认 text
    - **time**: 时间信息（可选）
    - **location**: 地点信息（可选）
    - **people**: 人物信息（可选）
    - **emotion**: 情绪信息（可选）
    - **tags**: 标签列表（可选）
    - **user_id**: 用户 ID（必填）
    """
    db.set_current_user(user_id)

    try:
        metadata = {}
        if memory.location:
            metadata["location_name"] = memory.location.name
            metadata["location_address"] = memory.location.address
            metadata["location_latitude"] = memory.location.latitude
            metadata["location_longitude"] = memory.location.longitude
        if memory.people:
            metadata["people"] = [p.model_dump() for p in memory.people]
        if memory.emotion:
            metadata["emotion"] = memory.emotion.model_dump()
        if memory.tags:
            metadata["tags"] = memory.tags
        if memory.time:
            metadata["time_value"] = memory.time.value

        result = await unified_memory_service.store(
            user_id=user_id,
            content=memory.content,
            source="manual",
            memory_type="preference",
            metadata=metadata,
        )

        memory_data = await unified_memory_service.get_memory_by_id(
            result["raw_message_id"]
        )

        return {
            "code": 200,
            "message": "success",
            "data": {
                "id": result["raw_message_id"],
                "content": memory.content,
                "memory_type": result["memory_type"],
                "source": result["source"],
                "is_long_document": result.get("is_long_document", False),
                "entities": result.get("entities", []),
                "entities_count": result.get("entities_count", 0),
                "tags": memory_data.get("tags", []) if memory_data else [],
                "created_at": memory_data.get("created_at") if memory_data else None,
            },
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
                            "has_more": True,
                        },
                    }
                }
            },
        }
    },
)
async def list_memories(
    user_id: str = Query(..., description="用户 ID"),
    limit: int = Query(50, ge=1, le=100, description="数量限制"),
    offset: int = Query(0, ge=0, description="偏移量"),
    status: str = Query("active", description="状态过滤（active/archived/deleted）"),
    order_by: str = Query("created_at", description="排序字段"),
    order: str = Query("desc", description="排序方向（asc/desc）"),
):
    """
    列出记忆（v3.0 DAG 架构，从 raw_messages 表查询）

    - **user_id**: 用户 ID（必填）
    - **limit**: 每页数量，1-100，默认 50
    - **offset**: 偏移量，默认 0
    - **status**: 状态过滤（当前仅支持 active）
    - **order_by**: 排序字段，默认 created_at
    - **order**: 排序方向，默认 desc
    """
    memories = await unified_memory_service.get_user_memories(user_id, limit)

    total = await db.fetchval(
        "SELECT COUNT(*) FROM raw_messages WHERE user_id = $1", user_id
    )

    return {
        "code": 200,
        "message": "success",
        "data": {
            "memories": memories,
            "count": len(memories),
            "total": total or 0,
            "has_more": offset + limit < (total or 0),
        },
    }


@router.get(
    "/{memory_id}",
    response_model=dict,
    summary="获取单个记忆",
    description="根据 ID 获取记忆详情（DAG 架构）",
    responses={200: {"description": "成功"}, 404: {"description": "记忆不存在"}},
)
async def get_memory(memory_id: str, user_id: str = Query(..., description="用户 ID")):
    """
    获取记忆（DAG 架构）

    - **memory_id**: 记忆 ID（支持 raw_xxx 或 sum_xxx 格式）
    - **user_id**: 用户 ID（必填）
    """
    db.set_current_user(user_id)

    memory = await unified_memory_service.get_memory_by_id(memory_id)

    if not memory:
        raise HTTPException(status_code=404, detail="Memory not found")

    return {"code": 200, "message": "success", "data": memory}


@router.put(
    "/{memory_id}",
    response_model=dict,
    summary="更新记忆",
    description="更新记忆内容（暂不支持 - DAG 架构下需要重新设计）",
    responses={
        200: {"description": "更新成功"},
        404: {"description": "记忆不存在"},
        501: {"description": "功能暂未实现"},
    },
    deprecated=True,
)
async def update_memory(
    memory_id: str,
    updates: Dict[str, Any] = Body(...),
    user_id: str = Query(..., description="用户 ID"),
):
    raise HTTPException(
        status_code=501,
        detail="Update endpoint is not yet supported in DAG architecture. TODO: Implement update in UnifiedMemoryService.",
    )


@router.delete(
    "/{memory_id}",
    response_model=dict,
    summary="删除记忆",
    description="删除记忆（DAG 架构 - 硬删除）",
    responses={200: {"description": "删除成功"}, 404: {"description": "记忆不存在"}},
)
async def delete_memory(
    memory_id: str, user_id: str = Query(..., description="用户 ID")
):
    db.set_current_user(user_id)

    success = await unified_memory_service.delete_memory(memory_id)

    if not success:
        raise HTTPException(status_code=404, detail="Memory not found")

    return {"code": 200, "message": "success", "data": None}


# ==================== 搜索端点 ====================


@router.post(
    "/search",
    response_model=dict,
    summary="语义搜索",
    description="使用向量相似度和关键词混合检索记忆（DAG 架构）",
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
                                    "id": "raw_abc123",
                                    "content": "今天在咖啡店见面",
                                    "similarity": 0.95,
                                    "source": "vector",
                                }
                            ],
                            "count": 1,
                            "query": "咖啡店",
                        },
                    }
                }
            },
        }
    },
)
async def search_memories(request: SearchRequest):
    db.set_current_user(request.user_id)

    try:
        results = await lossless_recall_service.hybrid_recall(
            query=request.query,
            user_id=request.user_id,
            scope="all",
            limit=request.limit,
            min_similarity=request.min_similarity,
        )

        return {
            "code": 200,
            "message": "success",
            "data": {"results": results, "count": len(results), "query": request.query},
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/recall",
    response_model=dict,
    summary="自然语言召回",
    description="使用自然语言查询召回相关记忆，并生成自然语言回答",
    responses={
        200: {
            "description": "召回成功",
            "content": {
                "application/json": {
                    "example": {
                        "code": 200,
                        "message": "success",
                        "data": {
                            "answer": "上周你主要做了几件事...",
                            "used_memories": [],
                            "memory_count": 3,
                            "parsed_query": {
                                "time_range": {
                                    "start": "2024-01-01",
                                    "end": "2024-01-07",
                                },
                                "keywords": ["工作", "会议"],
                            },
                        },
                    }
                }
            },
        }
    },
)
async def recall_memories(request: RecallRequest):
    """
    自然语言召回记忆

    智能解析自然语言查询并生成自然语言回答：
    - **query**: 自然语言查询，例如"上周在咖啡店和老同学见面"
    - **user_id**: 用户 ID（必填）
    - **limit**: 返回数量，默认 20
    - **use_parser**: 是否使用自然语言解析，默认 True
    - **min_similarity**: 最小相似度阈值，默认 0.05
    - **detail_level**: 回答详情级别，默认 medium
    - **use_smart_recall**: 是否使用智能召回，默认 True（推荐）

    召回方式：
    - **智能召回（默认）**: LLM 自动选择最佳召回策略（向量/关键词/图谱/时间/混合）
    - **混合召回**: 固定使用向量+关键词+图谱混合召回

    支持的查询类型：
    - 时间查询："上周做了什么"、"最近3天"
    - 地点查询："在咖啡店发生了什么"
    - 人物查询："和老同学相关的记忆"
    - 情绪查询："最近开心的事"
    - 混合查询："上周在咖啡店和老同学见面"
    """
    # 设置当前用户
    db.set_current_user(request.user_id)

    try:
        # ⭐ 使用智能召回（推荐）
        if request.use_smart_recall:
            from ..services.smart_recall_service import get_smart_recall_service

            smart_recall = get_smart_recall_service()

            result = await smart_recall.smart_recall(
                query=request.query,
                user_id=request.user_id,
                limit=request.limit,
                detail_level=request.detail_level,
            )

            return {
                "code": 200,
                "message": "success",
                "data": {
                    "answer": result["answer"],
                    "used_memories": result["used_memories"],
                    "memory_count": result["memory_count"],
                    "route_decision": result["route_decision"],
                    "recall_mode": "smart_recall",
                },
            }

        from ..services.core.lossless_recall_service import lossless_recall_service

        llm_recall = get_llm_recall_service()

        parsed_query = None
        if request.use_parser:
            from ..services.jieba_service import (
                extract_keywords,
                extract_time_keywords,
                extract_location,
                extract_person,
            )
            import time

            start_time = time.time()
            keywords = extract_keywords(request.query)
            time_range_parsed = extract_time_keywords(request.query)
            location = extract_location(request.query)
            person = extract_person(request.query)
            jieba_time = (time.time() - start_time) * 1000

            parsed_query = {
                "source": "jieba",
                "keywords": keywords,
                "time_range": time_range_parsed,
                "location": location,
                "people": [person] if person else [],
                "parse_time_ms": jieba_time,
            }

        time_range = None
        if parsed_query and parsed_query.get("time_range"):
            tr = parsed_query["time_range"]
            if tr.get("start") and tr.get("end"):
                from datetime import datetime

                time_range = {
                    "start_time": datetime.fromisoformat(str(tr["start"]))
                    if isinstance(tr["start"], str)
                    else tr["start"],
                    "end_time": datetime.fromisoformat(str(tr["end"]))
                    if isinstance(tr["end"], str)
                    else tr["end"],
                }

        memory_results = await lossless_recall_service.hybrid_recall(
            query=request.query,
            user_id=request.user_id,
            scope="all",
            limit=request.limit,
            min_similarity=request.min_similarity,
            time_range=time_range,
        )

        # 调用 LLM 生成回答
        llm_result = await llm_recall.generate_recall_response(
            query=request.query,
            memory_results=memory_results,
            detail_level=request.detail_level,
        )

        return {
            "code": 200,
            "message": "success",
            "data": {
                "answer": llm_result["answer"],
                "used_memories": llm_result["used_memories"],
                "memory_count": llm_result["memory_count"],
                "parsed_query": parsed_query,
                "recall_mode": "hybrid_recall",
            },
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/{memory_id}/expand",
    response_model=dict,
    summary="展开 DAG 节点",
    description="从摘要节点展开查看关联的原始消息或子摘要",
    responses={
        200: {
            "description": "展开成功",
            "content": {
                "application/json": {
                    "example": {
                        "code": 200,
                        "message": "success",
                        "data": {
                            "root_id": "sum_xxx",
                            "type": "summary",
                            "nodes": [
                                {
                                    "id": "raw_xxx",
                                    "type": "raw_message",
                                    "content": "...",
                                }
                            ],
                            "total_nodes": 5,
                        },
                    }
                }
            },
        }
    },
)
async def expand_memory(
    memory_id: str,
    user_id: str = Query(..., description="用户 ID"),
    depth: int = Query(10, ge=1, le=50, description="展开深度"),
    max_tokens: int = Query(5000, ge=100, le=50000, description="最大 Token 数"),
):
    """
    展开 DAG 节点

    - **memory_id**: 记忆 ID（可以是 raw_message 或 summary）
    - **user_id**: 用户 ID（必填）
    - **depth**: 展开深度，默认 10
    - **max_tokens**: 最大返回 Token 数，默认 5000
    """
    from ..services.core.dag_expand_service import dag_expand_service
    from ..services.core.raw_message_store import RawMessageStore

    db.set_current_user(user_id)

    try:
        if memory_id.startswith("raw_"):
            raw_store = RawMessageStore()
            msg = await raw_store.get_by_id(memory_id)
            if not msg:
                raise HTTPException(status_code=404, detail="Memory not found")

            return {
                "code": 200,
                "message": "success",
                "data": {
                    "root_id": memory_id,
                    "type": "raw_message",
                    "nodes": [
                        {
                            "id": msg.id,
                            "type": "raw_message",
                            "content": msg.content,
                            "token_count": msg.token_count,
                            "created_at": msg.created_at.isoformat()
                            if msg.created_at
                            else None,
                        }
                    ],
                    "total_nodes": 1,
                },
            }

        if memory_id.startswith("sum_"):
            result = await dag_expand_service.expand_to_messages(
                summary_id=memory_id,
                max_tokens=max_tokens,
            )

            if "error" in result:
                raise HTTPException(status_code=404, detail=result["error"])

            return {
                "code": 200,
                "message": "success",
                "data": {
                    "root_id": memory_id,
                    "type": "summary",
                    "nodes": result.get("messages", []),
                    "total_nodes": result.get("total_messages", 0),
                    "total_tokens": result.get("total_tokens", 0),
                },
            }

        raise HTTPException(status_code=400, detail="Invalid memory ID format")

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/smart-recall",
    response_model=dict,
    summary="智能召回（Function Calling）",
    description="让 LLM 自动选择最佳召回策略，支持向量、关键词、图谱、时间等多种召回方式",
    responses={
        200: {
            "description": "召回成功",
            "content": {
                "application/json": {
                    "example": {
                        "code": 200,
                        "message": "success",
                        "data": {
                            "answer": "你上周在咖啡店见了张三...",
                            "used_memories": [],
                            "memory_count": 3,
                            "route_decision": {
                                "strategy": "graph_recall",
                                "reason": "查询涉及人物关系，适合图谱召回",
                                "params": {"entity_name": "张三"},
                            },
                        },
                    }
                }
            },
        }
    },
)
async def smart_recall_memories(request: SmartRecallRequest):
    """
    智能召回记忆（Function Calling）

    让 LLM 自动选择最佳召回策略：
    - **query**: 自然语言查询
    - **user_id**: 用户 ID（必填）
    - **limit**: 返回数量，默认 10
    - **detail_level**: 回答详情级别，默认 medium

    支持的召回策略：
    - vector_recall: 向量相似度召回（语义查询）
    - keyword_recall: 关键词召回（精确匹配）
    - graph_recall: 图谱召回（实体关系）
    - time_recall: 时间召回（时间范围）
    - hybrid_recall: 混合召回（推荐，综合多种方式）

    示例查询：
    - "张三的朋友" → graph_recall
    - "最近一周" → time_recall
    - "咖啡店" → keyword_recall
    - "开心的事情" → vector_recall
    - "上周在咖啡店见的朋友" → hybrid_recall
    """
    db.set_current_user(request.user_id)

    try:
        from ..services.smart_recall_service import get_smart_recall_service

        smart_recall = get_smart_recall_service()

        result = await smart_recall.smart_recall(
            query=request.query,
            user_id=request.user_id,
            limit=request.limit,
            detail_level=request.detail_level,
        )

        return {"code": 200, "message": "success", "data": result}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==================== 批量操作端点 ====================


@router.post(
    "/batch",
    response_model=dict,
    summary="批量创建记忆",
    description="批量创建多条记忆（DAG 架构）",
)
async def batch_create_memories(
    memories: List[MemoryCreate],
    user_id: str = Query(..., description="用户 ID"),
):
    if len(memories) > 100:
        raise HTTPException(status_code=400, detail="Maximum 100 memories per batch")

    db.set_current_user(user_id)

    try:
        created_ids = []
        for memory in memories:
            metadata = {}
            if memory.location:
                metadata["location_name"] = memory.location.name
                metadata["location_address"] = memory.location.address
                metadata["location_latitude"] = memory.location.latitude
                metadata["location_longitude"] = memory.location.longitude
            if memory.people:
                metadata["people"] = [p.model_dump() for p in memory.people]
            if memory.emotion:
                metadata["emotion"] = memory.emotion.model_dump()
            if memory.tags:
                metadata["tags"] = memory.tags
            if memory.time:
                metadata["time_value"] = memory.time.value

            result = await unified_memory_service.store(
                user_id=user_id,
                content=memory.content,
                source="manual",
                memory_type="preference",
                metadata=metadata,
            )
            created_ids.append(result["raw_message_id"])

        return {
            "code": 200,
            "message": "success",
            "data": {"created_count": len(created_ids), "memory_ids": created_ids},
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/with-graph",
    response_model=dict,
    summary="创建记忆（带图谱构建）",
    description="创建记忆并并发构建知识图谱",
    responses={
        200: {
            "description": "创建成功",
            "content": {
                "application/json": {
                    "example": {
                        "success": True,
                        "memory_id": "uuid",
                        "graph": {
                            "entities": [...],
                            "relations": [...],
                            "entity_count": 4,
                            "relation_count": 2,
                        },
                    }
                }
            },
        }
    },
)
async def create_memory_with_graph(request: CreateMemoryWithGraphRequest):
    db.set_current_user(request.user_id)

    try:
        result = await unified_memory_service.store(
            user_id=request.user_id,
            content=request.content,
            source="manual",
            memory_type="preference",
            enable_graph=request.enable_graph,
        )

        return {
            "success": True,
            "memory_id": result["raw_message_id"],
            "graph": {
                "entities": result.get("entities", []),
                "entities_count": result.get("entities_count", 0),
            },
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete(
    "/batch",
    response_model=dict,
    summary="批量删除记忆",
    description="批量删除多条记忆（DAG 架构）",
)
async def batch_delete_memories(
    memory_ids: List[str] = Body(...),
    user_id: str = Query(..., description="用户 ID"),
):
    if len(memory_ids) > 100:
        raise HTTPException(status_code=400, detail="Maximum 100 memories per batch")

    db.set_current_user(user_id)

    try:
        deleted_count = 0
        for memory_id in memory_ids:
            if await unified_memory_service.delete_memory(memory_id):
                deleted_count += 1

        return {
            "code": 200,
            "message": "success",
            "data": {"deleted_count": deleted_count},
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==================== DAG 展开端点 ====================


class ExpandRequest(BaseModel):
    """展开摘要请求"""

    summary_id: str = Field(..., description="摘要 ID")
    user_id: str = Field(..., description="用户 ID")
    max_tokens: int = Field(5000, ge=100, le=50000, description="最大 token 数")


@router.post(
    "/expand",
    response_model=dict,
    summary="展开摘要",
    description="展开摘要获取原始消息列表",
)
async def expand_summary(request: ExpandRequest):
    """
    展开摘要

    - **summary_id**: 摘要 ID（必填）
    - **user_id**: 用户 ID（必填）
    - **max_tokens**: 最大 token 数（默认 5000）
    """
    db.set_current_user(request.user_id)

    try:
        from src.services.core.dag_expand_service import dag_expand_service

        result = await dag_expand_service.expand_to_messages(
            summary_id=request.summary_id,
            max_tokens=request.max_tokens,
        )

        if "error" in result:
            raise HTTPException(status_code=404, detail=result["error"])

        return {
            "code": 200,
            "message": "success",
            "data": result,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"展开失败：{str(e)}")
