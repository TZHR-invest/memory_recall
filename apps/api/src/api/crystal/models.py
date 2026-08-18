"""
crystal /api/v2 请求/响应模型（api-contract §2 / §4）
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class EvidenceCreateRequest(BaseModel):
    """POST /api/v2/evidence"""

    content: str = Field(..., min_length=1, description="原始观察文本（NOT NULL）")
    source_kind: str = Field(
        ...,
        description="agent_add | outcome_trace | document | user_correction",
    )
    scope: Optional[str] = Field(
        None, description="项目作用域（不含 key_id 前缀）；NULL=全局"
    )
    observed_at: Optional[str] = Field(
        None, description="事件时间 ISO8601；默认=入库时刻，可显式覆盖补录"
    )
    source_ref: Optional[Dict[str, Any]] = Field(
        None, description="出处 {session_id, message_id, plugin, file, ...}"
    )
    extraction_type: Optional[str] = Field(
        None, description="verbatim | paraphrase | inference（B5 门控）"
    )
    idempotency_key: Optional[str] = Field(
        None,
        description="幂等键（推荐 sha256(session_id|message_id|content) 前 32 位）",
    )


class EvidenceListRequest(BaseModel):
    scope: Optional[str] = Field(None, description="项目作用域过滤")
    source_kind: Optional[str] = Field(None, description="来源类型过滤")
    state: Optional[str] = Field(None, description="处理状态过滤 pending/processing/done/failed")
    limit: int = Field(20, ge=1, le=100, description="每页条数")
    cursor: Optional[str] = Field(None, description="游标（base64(observed_at + id)）")
