from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any

from src.database import db
from src.services.core.memory_service import memory_service
from src.services.core.summary_store import summary_store
from src.services.core.raw_message_store import raw_message_store

router = APIRouter(prefix="/context", tags=["上下文管理"])


class AssembleRequest(BaseModel):
    user_id: str = Field(..., description="用户 ID")
    agent_id: Optional[str] = Field(None, description="Agent ID")
    session_id: str = Field(..., description="会话 ID")
    token_budget: int = Field(100000, ge=1000, le=500000, description="Token 预算")


class CompactRequest(BaseModel):
    user_id: str = Field(..., description="用户 ID")
    agent_id: Optional[str] = Field(None, description="Agent ID")
    session_id: str = Field(..., description="会话 ID")
    token_budget: int = Field(100000, ge=1000, le=500000, description="Token 预算")
    force: bool = Field(False, description="强制压缩")


class DescribeRequest(BaseModel):
    id: str = Field(..., description="要查看的 ID（sum_xxx 或 raw_xxx）")


@router.post(
    "/assemble",
    response_model=dict,
    summary="组装上下文",
    description="组装上下文给 Agent 使用",
)
async def assemble_context(request: AssembleRequest):
    db.set_current_user(request.user_id)

    try:
        result = await memory_service.assemble(
            {
                "user_id": request.user_id,
                "agent_id": request.agent_id,
                "session_id": request.session_id,
                "token_budget": request.token_budget,
            }
        )

        return {
            "code": 200,
            "message": "success",
            "data": result,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"组装失败：{str(e)}")


@router.post(
    "/compact",
    response_model=dict,
    summary="触发压缩",
    description="手动触发 DAG 压缩",
)
async def compact_context(request: CompactRequest):
    db.set_current_user(request.user_id)

    try:
        from src.llm.client import get_llm_client

        llm_client = get_llm_client()

        def summarize_fn(text: str, aggressive: bool = False) -> str:
            prompt = f"请总结以下内容（{'简略' if aggressive else '详细'}）：\n\n{text}"
            return llm_client.chat([{"role": "user", "content": prompt}])

        result = await memory_service.compact(
            {
                "user_id": request.user_id,
                "agent_id": request.agent_id,
                "session_id": request.session_id,
                "token_budget": request.token_budget,
                "force": request.force,
                "summarize_fn": summarize_fn,
            }
        )

        return {
            "code": 200,
            "message": "success",
            "data": result,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"压缩失败：{str(e)}")


@router.post(
    "/describe",
    response_model=dict,
    summary="查看详情",
    description="查看摘要或原始消息的详细信息",
)
async def describe_item(request: DescribeRequest):
    item_id = request.id.strip()

    if item_id.startswith("sum_"):
        summary = await summary_store.get_summary(item_id)
        if not summary:
            raise HTTPException(status_code=404, detail=f"摘要 {item_id} 不存在")

        parents = await summary_store.get_summary_parents(item_id)
        children = await summary_store.get_summary_children(item_id)

        return {
            "code": 200,
            "message": "success",
            "data": {
                "id": summary.summary_id,
                "type": "summary",
                "content": summary.content,
                "token_count": summary.token_count,
                "level": summary.depth,
                "kind": summary.kind,
                "created_at": summary.created_at.isoformat()
                if summary.created_at
                else None,
                "parent_ids": [p.summary_id for p in parents],
                "child_ids": [c.summary_id for c in children],
                "descendant_count": summary.descendant_count,
                "compression_level": summary.compression_level,
            },
        }

    elif item_id.startswith("raw_"):
        message = await raw_message_store.get_by_id(item_id)
        if not message:
            raise HTTPException(status_code=404, detail=f"原始消息 {item_id} 不存在")

        return {
            "code": 200,
            "message": "success",
            "data": {
                "id": message.id,
                "type": "raw_message",
                "content": message.content,
                "token_count": message.token_count,
                "memory_type": message.memory_type,
                "role": message.role,
                "session_id": message.session_id,
                "agent_id": message.agent_id,
                "created_at": message.created_at.isoformat()
                if message.created_at
                else None,
                "tags": message.tags,
                "source_type": message.source_type,
            },
        }

    else:
        raise HTTPException(
            status_code=400,
            detail="无效的 ID 格式，必须以 sum_ 或 raw_ 开头",
        )
