"""
crystal 证据层端点（/api/v2/evidence，api-contract §2.1）

M1 落地：
- POST /api/v2/evidence —— 真实写入（幂等键查重 + 落库 + processing 状态机初始化），202
- GET  /api/v2/evidence/{id} —— evidence 详情 + 处理状态
- GET  /api/v2/evidence —— 分页列表（observed_at DESC，游标分页）
- GET  /api/v2/evidence/{id}/claims —— 该证据支持的所有 claim（经 claim_evidence，M2 对账后有数据）

业务逻辑（对账/召回/提炼）随 M2；M1 只落"写入 + 状态可见 + 溯源骨架"。
"""

import base64
import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query

from src.api.auth import get_current_user, require_permission
from src.database import db

from .errors import CrystalAPIError, ok_response
from .models import EvidenceCreateRequest, EvidenceListRequest
from .security import owner_from_user, verify_scope_ownership

router = APIRouter(prefix="/api/v2/evidence", tags=["crystal-evidence"])

SOURCE_KINDS = {"agent_add", "outcome_trace", "document", "user_correction"}
EXTRACTION_TYPES = {"verbatim", "paraphrase", "inference"}
PROCESSING_STATES = {"pending", "processing", "done", "failed"}


def compute_idempotency_key(
    session_id: Optional[str],
    message_id: Optional[str],
    content: str,
) -> Optional[str]:
    """幂等键（reconciliation-design §4.4）：sha256(session_id|message_id|content) 前 32 位。

    session_id/message_id 缺任一 → None（无幂等保证；客户端仍可显式传 idempotency_key）。
    """
    if not session_id or not message_id:
        return None
    raw = f"{session_id}|{message_id}|{content}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def _parse_observed_at(raw: Optional[str]) -> Optional[datetime]:
    if raw is None:
        return None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        if dt > now + (30 * 24 * 3600):  # 允许最多 30 天未来（时钟漂移容差）
            raise ValueError("observed_at in the future")
        return dt
    except ValueError:
        raise CrystalAPIError(
            400, "Invalid observed_at. Use ISO8601 and not in the future."
        )


def _encode_cursor(observed_at: datetime, evidence_id: str) -> str:
    """游标 = base64(observed_at.isoformat() + '|' + id)（api-contract §5）"""
    raw = f"{observed_at.isoformat()}|{evidence_id}"
    return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("utf-8")


def _decode_cursor(cursor: Optional[str]) -> Optional[tuple]:
    if not cursor:
        return None
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("utf-8")).decode("utf-8")
        observed_at_str, evidence_id = raw.rsplit("|", 1)
        observed_at = datetime.fromisoformat(observed_at_str)
        return observed_at, evidence_id
    except Exception:
        raise CrystalAPIError(400, "Invalid cursor.")


def _row_to_evidence(row: Any) -> Dict[str, Any]:
    """asyncpg Record → API 响应体（embedding 不返回，体积大且属派生）"""
    source_ref = row["source_ref"]
    if isinstance(source_ref, str):
        try:
            source_ref = json.loads(source_ref)
        except (ValueError, TypeError):
            pass  # 非 JSON 字符串原样返回
    return {
        "evidence_id": row["id"],
        "content": row["content"],
        "source_kind": row["source_kind"],
        "scope": row["scope"],
        "owner_type": row["owner_type"],
        "owner_id": row["owner_id"],
        "observed_at": row["observed_at"].isoformat() if row["observed_at"] else None,
        "created_at": row["created_at"].isoformat() if row["created_at"] else None,
        "source_ref": source_ref,
        "extraction_type": row["extraction_type"],
    }


@router.post("", status_code=202)
async def create_evidence(
    request: EvidenceCreateRequest,
    current_user: Dict = Depends(require_permission("write")),
):
    """上报一条 Evidence（api-contract §4.1）：202 + pending；幂等命中返回既有结果。"""
    if request.source_kind not in SOURCE_KINDS:
        raise CrystalAPIError(
            400, f"Invalid source_kind '{request.source_kind}'. Must be one of {sorted(SOURCE_KINDS)}."
        )
    if request.extraction_type is not None and request.extraction_type not in EXTRACTION_TYPES:
        raise CrystalAPIError(
            400,
            f"Invalid extraction_type '{request.extraction_type}'. Must be one of {sorted(EXTRACTION_TYPES)}.",
        )

    owner = owner_from_user(current_user)
    scope = verify_scope_ownership(request.scope, current_user["key_id"])
    observed_at = _parse_observed_at(request.observed_at)

    # 幂等键：显式传的优先；否则由 source_ref 推导（缺 session/message 则无幂等）
    idempotency_key = request.idempotency_key
    if idempotency_key is None and request.source_ref:
        idempotency_key = compute_idempotency_key(
            request.source_ref.get("session_id"),
            request.source_ref.get("message_id"),
            request.content,
        )

    async with db.get_connection() as conn:
        # 幂等查重：同 owner 同键 → 返回既有结果（202 + accepted=false）
        if idempotency_key:
            existing = await conn.fetchrow(
                """SELECT e.*, p.processing_state, p.current_step
                   FROM crystal.evidence e
                   LEFT JOIN crystal.evidence_processing p ON p.evidence_id = e.id
                   WHERE e.owner_type=$1 AND e.owner_id=$2
                     AND e.idempotency_key=$3""",
                owner["owner_type"],
                owner["owner_id"],
                idempotency_key,
            )
            if existing:
                return ok_response(
                    {
                        "evidence_id": existing["id"],
                        "processing_state": existing["processing_state"],
                        "current_step": existing["current_step"],
                        "accepted": False,  # 幂等命中已存在
                    },
                    message="Idempotent hit: evidence already exists",
                )

        # 落库（id/created_at 由 DB 默认生成）
        evidence_id = await conn.fetchval(
            """INSERT INTO crystal.evidence
               (observed_at, source_kind, content, scope, owner_type, owner_id,
                source_ref, extraction_type, idempotency_key)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
               RETURNING id""",
            observed_at or datetime.now(timezone.utc),
            request.source_kind,
            request.content,
            scope,
            owner["owner_type"],
            owner["owner_id"],
            json.dumps(request.source_ref) if request.source_ref else None,
            request.extraction_type,
            idempotency_key,
        )

        # 处理状态机初始化（通用状态机 entity-attributes §3：pending + current_step=embedding）
        await conn.execute(
            """INSERT INTO crystal.evidence_processing
               (evidence_id, processing_state, current_step, updated_at)
               VALUES ($1, 'pending', 'embedding', NOW())""",
            evidence_id,
        )

    return ok_response(
        {
            "evidence_id": evidence_id,
            "processing_state": "pending",
            "current_step": "embedding",
            "accepted": True,
        }
    )


@router.get("/{evidence_id}")
async def get_evidence(
    evidence_id: str,
    current_user: Dict = Depends(require_permission("read")),
):
    """Evidence 详情 + 处理状态（US-E2 / A1 失败可见）"""
    owner = owner_from_user(current_user)
    async with db.get_connection() as conn:
        row = await conn.fetchrow(
            """SELECT e.*, p.processing_state, p.current_step, p.last_error, p.updated_at AS processing_updated_at
               FROM crystal.evidence e
               LEFT JOIN crystal.evidence_processing p ON p.evidence_id = e.id
               WHERE e.id=$1 AND e.owner_type=$2 AND e.owner_id=$3""",
            evidence_id,
            owner["owner_type"],
            owner["owner_id"],
        )
    if not row:
        raise CrystalAPIError(404, f"Evidence '{evidence_id}' not found.")
    data = _row_to_evidence(row)
    data["processing"] = {
        "state": row["processing_state"],
        "current_step": row["current_step"],
        "last_error": row["last_error"],
        "updated_at": row["processing_updated_at"].isoformat()
        if row["processing_updated_at"]
        else None,
    }
    return ok_response(data)


@router.get("")
async def list_evidence(
    scope: Optional[str] = Query(None),
    source_kind: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    cursor: Optional[str] = Query(None),
    current_user: Dict = Depends(require_permission("read")),
):
    """分页列表（observed_at DESC，游标分页，api-contract §5）"""
    owner = owner_from_user(current_user)
    scoped = verify_scope_ownership(scope, current_user["key_id"])
    if source_kind is not None and source_kind not in SOURCE_KINDS:
        raise CrystalAPIError(400, f"Invalid source_kind '{source_kind}'.")
    if state is not None and state not in PROCESSING_STATES:
        raise CrystalAPIError(400, f"Invalid state '{state}'.")

    conditions = ["e.owner_type=$1", "e.owner_id=$2"]
    params: List[Any] = [owner["owner_type"], owner["owner_id"]]
    if scoped is not None:
        conditions.append("e.scope=$3")
        params.append(scoped)
    if source_kind is not None:
        conditions.append(f"e.source_kind=${len(params) + 1}")
        params.append(source_kind)
    if state is not None:
        conditions.append(f"p.processing_state=${len(params) + 1}")
        params.append(state)

    decoded = _decode_cursor(cursor)
    if decoded:
        conditions.append(
            f"(e.observed_at, e.id) < (${len(params) + 1}, ${len(params) + 2})"
        )
        params.extend([decoded[0], decoded[1]])

    where = " AND ".join(conditions)
    async with db.get_connection() as conn:
        rows = await conn.fetch(
            f"""SELECT e.*, p.processing_state, p.current_step
                FROM crystal.evidence e
                LEFT JOIN crystal.evidence_processing p ON p.evidence_id = e.id
                WHERE {where}
                ORDER BY e.observed_at DESC, e.id DESC
                LIMIT ${len(params) + 1}""",
            *params,
            limit + 1,  # 多取一条判断是否还有下一页
        )

    has_more = len(rows) > limit
    page = rows[:limit]
    items = [_row_to_evidence(r) for r in page]
    for item, row in zip(items, page):
        item["processing_state"] = row["processing_state"]

    next_cursor = None
    if has_more and page:
        last = page[-1]
        next_cursor = _encode_cursor(last["observed_at"], last["id"])

    return ok_response({"items": items, "next_cursor": next_cursor, "has_more": has_more})


@router.get("/{evidence_id}/claims")
async def get_evidence_claims(
    evidence_id: str,
    current_user: Dict = Depends(require_permission("read")),
):
    """该证据支持的所有 claim（经 claim_evidence；M2 对账后有数据，A2 溯源）"""
    owner = owner_from_user(current_user)
    async with db.get_connection() as conn:
        ev = await conn.fetchrow(
            """SELECT id FROM crystal.evidence
               WHERE id=$1 AND owner_type=$2 AND owner_id=$3""",
            evidence_id,
            owner["owner_type"],
            owner["owner_id"],
        )
        if not ev:
            raise CrystalAPIError(404, f"Evidence '{evidence_id}' not found.")
        rows = await conn.fetch(
            """SELECT c.id, c.statement, c.claim_kind, c.status, c.content_confidence,
                      ce.role, ce.created_at AS linked_at
               FROM crystal.claim_evidence ce
               JOIN crystal.claim c ON c.id = ce.claim_id
               WHERE ce.evidence_id=$1
               ORDER BY ce.created_at DESC""",
            evidence_id,
        )
    items = [
        {
            "claim_id": r["id"],
            "statement": r["statement"],
            "claim_kind": r["claim_kind"],
            "status": r["status"],
            "content_confidence": r["content_confidence"],
            "role": r["role"],
            "linked_at": r["linked_at"].isoformat() if r["linked_at"] else None,
        }
        for r in rows
    ]
    return ok_response({"evidence_id": evidence_id, "claims": items})
