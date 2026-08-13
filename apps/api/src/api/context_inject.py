"""
统一上下文注入 API
提供 /context-inject 端点，在后端完成所有上下文获取和去重
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any

from src.api.auth import (
    require_permission,
    check_rate_limit,
    verify_container_ownership,
)

router = APIRouter(tags=["Context Injection"])


class ContextInjectConfig(BaseModel):
    inject_profile: bool = Field(False, description="是否注入用户画像")
    max_profile_items: int = Field(10, ge=1, le=50, description="最大画像条目数（dynamic 动态记忆上限）")
    max_static_profile_items: int = Field(
        30, ge=1, le=100, description="最大静态画像条目数（static 永久特征，行为规则全量注入、临时记录填剩余额度）"
    )
    max_memories: int = Field(5, ge=1, le=20, description="最大记忆数")
    max_chunks: int = Field(3, ge=1, le=10, description="最大文档片段数")
    enable_semantic_dedup: bool = Field(True, description="启用语义去重")
    dedup_threshold: float = Field(0.85, ge=0.0, le=1.0, description="去重阈值")
    enable_memory_graph: bool = Field(True, description="启用 Memory Graph 召回")
    memory_graph_depth: int = Field(2, ge=1, le=5, description="Memory Graph 遍历深度")
    memory_graph_nodes: int = Field(
        5, ge=1, le=20, description="Memory Graph 最大节点数"
    )
    enable_entity_graph: bool = Field(True, description="启用 Entity Graph 召回")
    entity_graph_depth: int = Field(2, ge=1, le=5, description="Entity Graph 遍历深度")
    entity_graph_nodes: int = Field(
        3, ge=1, le=20, description="Entity Graph 最大节点数"
    )
    memory_similarity_threshold: float = Field(
        0.40, ge=0.0, le=1.0, description="记忆相似度阈值"
    )
    language: str = Field("auto", description="语言设置")
    enable_chunks_search: bool = Field(True, description="启用文档片段搜索")
    chunks_similarity_threshold: float = Field(
        0.45, ge=0.0, le=1.0, description="文档片段相似度阈值"
    )
    entity_chunk_threshold: float = Field(
        0.30,
        ge=0.0,
        le=1.0,
        description="实体匹配文档片段相似度阈值（实体匹配是精确证据，阈值应低于向量检索）",
    )


class ContextInjectRequest(BaseModel):
    user_tag: Optional[str] = Field(
        None, description="用户容器标识（用户画像、用户记忆、用户文档）"
    )
    project_tag: Optional[str] = Field(
        None, description="项目容器标识（项目记忆、项目文档）"
    )
    query: Optional[str] = Field(None, description="用户输入，用于语义搜索")
    config: ContextInjectConfig = Field(
        default_factory=ContextInjectConfig, description="注入配置"
    )
    include_trace: bool = Field(False, description="响应中附带本次召回 Trace 明细")


class ContextSource(BaseModel):
    profile: List[str] = Field(default_factory=list, description="画像内容")
    memories: List[Dict[str, Any]] = Field(
        default_factory=list, description="项目记忆列表"
    )
    user_memories: List[Dict[str, Any]] = Field(
        default_factory=list, description="用户记忆列表"
    )
    chunks: List[Dict[str, Any]] = Field(
        default_factory=list, description="项目文档片段列表"
    )
    user_chunks: List[Dict[str, Any]] = Field(
        default_factory=list, description="用户文档片段列表"
    )


class ContextStats(BaseModel):
    total_items: int = Field(0, description="总条目数")
    after_dedup: int = Field(0, description="去重后条目数")
    deduped_count: int = Field(0, description="被去重的条目数")
    capped_count: int = Field(0, description="最终注入条目数（cap 后）")
    profile_count: int = Field(0, description="画像条目数")
    project_memories_count: int = Field(0, description="项目记忆条目数")
    user_memories_count: int = Field(0, description="用户记忆条目数")
    memories_count: int = Field(0, description="记忆条目数（向后兼容）")
    chunks_count: int = Field(0, description="文档片段条目数")
    failed_channels: List[str] = Field(
        default_factory=list, description="失败的召回通道（profile/memories/chunks）"
    )


class ContextInjectResponse(BaseModel):
    context: str = Field(..., description="格式化后的上下文")
    sources: ContextSource = Field(
        default_factory=ContextSource, description="数据来源"
    )
    stats: ContextStats = Field(default_factory=ContextStats, description="统计信息")
    failed_channels: List[str] = Field(
        default_factory=list, description="失败的召回通道（profile/memories/chunks）"
    )
    trace: Optional[Dict[str, Any]] = Field(None, description="召回 Trace 明细（include_trace=true 时返回）")


@router.post(
    "/context-inject",
    response_model=ContextInjectResponse,
    summary="统一上下文注入",
    description="""
    统一上下文注入接口，在后端完成所有数据获取和语义去重。
    
    相比分别调用 /profile、/search、/documents/search：
    - 减少API调用次数
    - 复用数据库中的embedding，避免重复计算
    - 降低延迟
    
    ## 调用方式
    提供 user_tag 和 project_tag：
    - user_tag: 用于用户画像、用户记忆、用户文档
    - project_tag: 用于项目记忆、项目文档
    
    单通道失败时返回成功通道的部分结果，并在 failed_channels 中标记失败通道；
    仅当全部通道失败或请求级错误时返回 500。
    """,
)
async def context_inject(
    request: ContextInjectRequest,
    current_user: Dict = Depends(require_permission("read")),
    _: Dict = Depends(check_rate_limit),
):
    from src.services.core.context_inject_service import context_inject_service

    user_tag = request.user_tag or current_user["container_tag"]
    project_tag = request.project_tag or current_user["container_tag"]

    verify_container_ownership(user_tag, current_user["key_id"])
    verify_container_ownership(project_tag, current_user["key_id"])

    try:
        result = await context_inject_service.inject_with_tags(
            user_tag=user_tag,
            project_tag=project_tag,
            query=request.query,
            config=request.config.model_dump(),
            include_trace=request.include_trace,
        )
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Context injection failed: {str(e)}",
        )
