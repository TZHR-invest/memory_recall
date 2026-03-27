from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any

from src.database import db
from src.services.lossless.memory_recall_engine import memory_recall_engine

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


@router.post(
    "/assemble",
    response_model=dict,
    summary="组装上下文",
    description="组装上下文给 Agent 使用",
)
async def assemble_context(request: AssembleRequest):
    db.set_current_user(request.user_id)

    try:
        result = await memory_recall_engine.assemble(
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

        result = await memory_recall_engine.compact(
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
