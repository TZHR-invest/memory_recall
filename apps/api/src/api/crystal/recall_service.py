"""
crystal 召回服务（读路径核心，recall-design v1）

三级管道：结构化预过滤（scope + active）→ 向量粗排（pgvector HNSW top-K）→
精排（相关 × content，一期 reuse 恒 1）→ 截断可见（explain 契约，不静默丢弃）。
"""

import logging
from typing import Any, Dict, List, Optional

from src.database import db
from src.embedding.client import get_embedding_client

logger = logging.getLogger(__name__)

TOP_K_DEFAULT = 50          # 粗排候选数（recall-design §1 ②）
LOW_CONFIDENCE_THRESHOLD = 0.4  # 低置信阈值（recall-design §3 / workbench §3.3）
CONTENT_UNKNOWN_FALLBACK = 0.4  # content_confidence NULL 兜底（recall-design §2）


def _relevance_from_cosine(cosine: float) -> float:
    """cosine 相似度（-1..1）→ 0..1（recall-design §8：先 (cos+1)/2）"""
    return round((cosine + 1) / 2, 4)


def _embedding_to_str(embedding: Optional[List[float]]) -> Optional[str]:
    """pgvector 传参格式（v5 memory_store._embedding_to_str 同款）："[1.0,2.0,...]" """
    if not embedding:
        return None
    return "[" + ",".join(str(x) for x in embedding) + "]"


def content_factor(content_confidence: Optional[float]) -> float:
    """content 因子（recall-design §2）：NULL/UNKNOWN 按 0.4 低置信兜底（标注不丢弃）"""
    if content_confidence is None:
        return CONTENT_UNKNOWN_FALLBACK
    return float(content_confidence)


def final_score(relevance: float, content_confidence: Optional[float], reuse: float = 1.0) -> float:
    """精排公式（recall-design §2）：final = relevance × content × reuse（一期 reuse 恒 1）"""
    return round(relevance * content_factor(content_confidence) * reuse, 4)


async def _prefilter(
    conn,
    owner_type: str,
    owner_id: str,
    scope: Optional[str],
    claim_kind: Optional[str],
) -> List[Dict[str, Any]]:
    """结构化预过滤（§1 ①）：owner + active + scope 匹配（NULL=全局）+ 可选 claim_kind。

    返回候选（含 id/statement/claim_kind/content_confidence/scope/embedding）。
    """
    conditions = ["owner_type=$1", "owner_id=$2", "status='active'"]
    params: List[Any] = [owner_type, owner_id]
    if scope is not None:
        # scope 匹配：请求 scope 时，claim.scope == scope 或 claim.scope IS NULL（全局知识可见）
        conditions.append("(scope=$3::text OR scope IS NULL)")
        params.append(scope)
    else:
        # 请求 scope=NULL（全局）：只匹配全局（不含项目级），recall-design §1 ④
        conditions.append("scope IS NULL")
    if claim_kind is not None:
        conditions.append(f"claim_kind=${len(params) + 1}")
        params.append(claim_kind)

    where = " AND ".join(conditions)
    rows = await conn.fetch(
        f"""SELECT id, statement, claim_kind, content_confidence, scope, embedding
            FROM crystal.claim
            WHERE {where}""",
        *params,
    )
    return [dict(r) for r in rows]


async def search_claims(
    query: str,
    owner_type: str,
    owner_id: str,
    scope: Optional[str],
    claim_kind: Optional[str] = None,
    limit: int = 10,
    include_explain: bool = False,
) -> Dict[str, Any]:
    """状态查询召回（US-S1/S2 / A4/A5）。

    返回 {results, explain?}；explain 契约见 recall-design §4。
    """
    # ① 预过滤
    async with db.get_connection() as conn:
        prefiltered = await _prefilter(conn, owner_type, owner_id, scope, claim_kind)

        # ② 向量粗排：query embedding → cosine top-K
        relevance_by_id: Dict[str, float] = {}
        try:
            embedding_client = get_embedding_client()
            query_embedding = await embedding_client.embed(query)
        except Exception as e:
            logger.error(f"crystal 召回 embedding 失败: {e}")
            query_embedding = None

        if query_embedding is not None:
            # 只对预过滤候选做向量排序（避免全表扫）
            ids = [c["id"] for c in prefiltered]
            if ids:
                rows = await conn.fetch(
                    """SELECT id, 1 - (embedding <=> $1::vector) AS cosine
                       FROM crystal.claim
                       WHERE id = ANY($2::text[])
                         AND embedding IS NOT NULL
                       ORDER BY 1 - (embedding <=> $1::vector) DESC
                       LIMIT $3""",
                    _embedding_to_str(query_embedding),
                    ids,
                    TOP_K_DEFAULT,
                )
                for r in rows:
                    relevance_by_id[r["id"]] = _relevance_from_cosine(r["cosine"])

        # ③ 精排（内存计算）
        ranked = []
        for c in prefiltered:
            relevance = relevance_by_id.get(c["id"], 0.0)  # 无向量/未命中 → 0
            conf = c["content_confidence"]
            ranked.append(
                {
                    "claim_id": c["id"],
                    "statement": c["statement"],
                    "claim_kind": c["claim_kind"],
                    "content_confidence": conf,
                    "scope": c["scope"],
                    "relevance": relevance,
                    "content": content_factor(conf),
                    "reuse": 1.0,
                    "final": final_score(relevance, conf),
                }
            )
        ranked.sort(key=lambda x: x["final"], reverse=True)

        # ④ 截断：top limit 进 results，其余进 truncated（不静默丢弃）
        results = ranked[:limit]
        truncated = []
        for i, item in enumerate(ranked[limit:], start=limit + 1):
            reason = "cap_limit"
            truncated.append(
                {
                    "claim_id": item["claim_id"],
                    "rank": i,
                    "final": item["final"],
                    "reason": reason,
                }
            )

        # 低置信标注（只标注不丢弃）
        low_confidence = [
            {"claim_id": c["claim_id"], "content_confidence": c["content_confidence"]}
            for c in results
            if c["content_confidence"] is None
            or c["content_confidence"] < LOW_CONFIDENCE_THRESHOLD
        ]

        # 组装响应
        out_results = []
        for i, item in enumerate(results, start=1):
            out_results.append(
                {
                    "claim_id": item["claim_id"],
                    "statement": item["statement"],
                    "claim_kind": item["claim_kind"],
                    "content_confidence": item["content_confidence"],
                    "status": "active",
                    "scope": item["scope"],
                    "scores": {
                        "relevance": item["relevance"],
                        "content": item["content"],
                        "reuse": item["reuse"],
                        "final": item["final"],
                    },
                }
            )

        response: Dict[str, Any] = {"results": out_results}

        if include_explain:
            explain = {
                "query": query,
                "prefilter": {
                    "owner_id": owner_id,
                    "scope": scope,
                    "scope_matched": len(prefiltered),
                    "active_only": True,
                },
                "candidates": [
                    {"claim_id": c["claim_id"], "relevance": c["relevance"], "rank": i}
                    for i, c in enumerate(ranked, start=1)
                ],
                "ranked": [
                    {
                        "claim_id": c["claim_id"],
                        "relevance": c["relevance"],
                        "content": c["content"],
                        "reuse": c["reuse"],
                        "final": c["final"],
                        "rank": i,
                    }
                    for i, c in enumerate(ranked, start=1)
                ],
                "truncated": truncated,
                "low_confidence": low_confidence,
            }
            response["explain"] = explain

        return response


async def get_claim_detail(
    claim_id: str,
    owner_type: str,
    owner_id: str,
) -> Optional[Dict[str, Any]]:
    """claim 详情 + 证据（claim_evidence）+ 谱系（出/入边）（api-contract §2.3 / A2 / A3）"""
    async with db.get_connection() as conn:
        claim = await conn.fetchrow(
            """SELECT * FROM crystal.claim
               WHERE id=$1 AND owner_type=$2 AND owner_id=$3""",
            claim_id,
            owner_type,
            owner_id,
        )
        if not claim:
            return None

        evidences = await conn.fetch(
            """SELECT e.id, e.content, e.source_kind, e.scope, e.observed_at, ce.role
               FROM crystal.claim_evidence ce
               JOIN crystal.evidence e ON e.id = ce.evidence_id
               WHERE ce.claim_id=$1
               ORDER BY ce.created_at DESC""",
            claim_id,
        )
        out_edges = await conn.fetch(
            """SELECT id, from_claim_id, to_claim_id, edge_type, reason, created_at
               FROM crystal.lineage_edge
               WHERE from_claim_id=$1
               ORDER BY created_at DESC""",
            claim_id,
        )
        in_edges = await conn.fetch(
            """SELECT id, from_claim_id, to_claim_id, edge_type, reason, created_at
               FROM crystal.lineage_edge
               WHERE to_claim_id=$1
               ORDER BY created_at DESC""",
            claim_id,
        )
        usage = await conn.fetchrow(
            "SELECT reuse_count, outcome_good, outcome_bad, last_used_at FROM crystal.claim_usage WHERE claim_id=$1",
            claim_id,
        )

    return {
        "claim_id": claim["id"],
        "statement": claim["statement"],
        "claim_kind": claim["claim_kind"],
        "content_confidence": claim["content_confidence"],
        "status": claim["status"],
        "scope": claim["scope"],
        "owner_type": claim["owner_type"],
        "owner_id": claim["owner_id"],
        "created_at": claim["created_at"].isoformat() if claim["created_at"] else None,
        "evidences": [
            {
                "evidence_id": e["id"],
                "content": e["content"],
                "source_kind": e["source_kind"],
                "scope": e["scope"],
                "observed_at": e["observed_at"].isoformat() if e["observed_at"] else None,
                "role": e["role"],
            }
            for e in evidences
        ],
        "lineage": {
            "out": [
                {
                    "edge_id": e["id"],
                    "from_claim_id": e["from_claim_id"],
                    "to_claim_id": e["to_claim_id"],
                    "edge_type": e["edge_type"],
                    "reason": e["reason"],
                    "created_at": e["created_at"].isoformat() if e["created_at"] else None,
                }
                for e in out_edges
            ],
            "in": [
                {
                    "edge_id": e["id"],
                    "from_claim_id": e["from_claim_id"],
                    "to_claim_id": e["to_claim_id"],
                    "edge_type": e["edge_type"],
                    "reason": e["reason"],
                    "created_at": e["created_at"].isoformat() if e["created_at"] else None,
                }
                for e in in_edges
            ],
        },
        "usage": {
            "reuse_count": usage["reuse_count"] if usage else 0,
            "outcome_good": usage["outcome_good"] if usage else 0,
            "outcome_bad": usage["outcome_bad"] if usage else 0,
            "last_used_at": usage["last_used_at"].isoformat() if usage and usage["last_used_at"] else None,
        },
    }


async def get_claim_lineage(
    claim_id: str,
    owner_type: str,
    owner_id: str,
) -> Optional[Dict[str, Any]]:
    """claim 谱系树（api-contract §2.3 / A3）"""
    detail = await get_claim_detail(claim_id, owner_type, owner_id)
    if detail is None:
        return None
    return {
        "claim_id": claim_id,
        "statement": detail["statement"],
        "status": detail["status"],
        "lineage": detail["lineage"],
    }
