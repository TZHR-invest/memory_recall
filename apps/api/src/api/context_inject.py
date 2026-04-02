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
    inject_profile: bool = Field(True, description="是否注入用户画像")
    max_profile_items: int = Field(10, ge=1, le=50, description="最大画像条目数")
    max_memories: int = Field(5, ge=1, le=20, description="最大记忆数")
    max_chunks: int = Field(3, ge=1, le=10, description="最大文档片段数")
    enable_semantic_dedup: bool = Field(True, description="启用语义去重")
    dedup_threshold: float = Field(0.85, ge=0.0, le=1.0, description="去重阈值")
    enable_graph_recall: bool = Field(True, description="启用图谱召回")
    graph_max_depth: int = Field(2, ge=1, le=5, description="图谱遍历深度")
    graph_max_nodes: int = Field(5, ge=1, le=20, description="最大图谱节点数")
    language: str = Field("auto", description="语言设置")
    enable_chunks_search: bool = Field(True, description="启用文档片段搜索")
    chunks_similarity_threshold: float = Field(
        0.3, ge=0.0, le=1.0, description="文档片段相似度阈值"
    )


class ContextInjectRequest(BaseModel):
    container_tag: Optional[str] = Field(None, description="容器标识")
    query: Optional[str] = Field(None, description="用户输入，用于语义搜索")
    config: ContextInjectConfig = Field(
        default_factory=ContextInjectConfig, description="注入配置"
    )


class ContextSource(BaseModel):
    profile: List[str] = Field(default_factory=list, description="画像内容")
    memories: List[Dict[str, Any]] = Field(default_factory=list, description="记忆列表")
    chunks: List[Dict[str, Any]] = Field(
        default_factory=list, description="文档片段列表"
    )


class ContextStats(BaseModel):
    total_items: int = Field(0, description="总条目数")
    after_dedup: int = Field(0, description="去重后条目数")
    deduped_count: int = Field(0, description="被去重的条目数")
    profile_count: int = Field(0, description="画像条目数")
    memories_count: int = Field(0, description="记忆条目数")
    chunks_count: int = Field(0, description="文档片段条目数")


class ContextInjectResponse(BaseModel):
    context: str = Field(..., description="格式化后的上下文")
    sources: ContextSource = Field(
        default_factory=ContextSource, description="数据来源"
    )
    stats: ContextStats = Field(default_factory=ContextStats, description="统计信息")


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
    """,
)
async def context_inject(
    request: ContextInjectRequest,
    current_user: Dict = Depends(require_permission("read")),
    _: Dict = Depends(check_rate_limit),
):
    from src.services.core.context_inject_service import context_inject_service

    container_tag = request.container_tag or current_user["container_tag"]
    verify_container_ownership(container_tag, current_user["key_id"])

    try:
        result = await context_inject_service.inject(
            container_tag=container_tag,
            query=request.query,
            config=request.config.model_dump(),
        )
        return result
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Context injection failed: {str(e)}",
        )
