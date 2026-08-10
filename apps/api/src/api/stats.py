"""
Personal Data Stats API.

Read-only statistics about a user's data in this container:
- GET /stats/overview    totals: memories (static/dynamic/forgotten), entities, relations, documents, content size, recall count
- GET /stats/timeline    memory creation trend (day/week/month, zero-filled)
- GET /stats/entities    entity type distribution, top entities, relation types
- GET /stats/activity    recall behavior + embedding call health

All endpoints reuse API key auth and container ownership checks.
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from src.api.auth import (
    check_rate_limit,
    require_permission,
    verify_container_ownership,
)
from src.database import db

router = APIRouter(prefix="/stats", tags=["Stats"])


async def _resolve_container(
    container_tag: Optional[str], current_user: dict
) -> str:
    container_tag = container_tag or current_user["container_tag"]
    verify_container_ownership(container_tag, current_user["key_id"])
    return container_tag


@router.get(
    "/overview",
    summary="个人数据概览",
    description="当前容器的记忆/实体/关系/文档总量与构成。",
)
async def get_overview(
    container_tag: Optional[str] = Query(None, description="Container tag (optional)"),
    current_user: dict = Depends(require_permission("read")),
    _: dict = Depends(check_rate_limit),
):
    c = await _resolve_container(container_tag, current_user)

    memories = await db.fetchrow(
        """
        SELECT
            COUNT(*) FILTER (WHERE is_latest = TRUE AND is_forgotten = FALSE) AS total,
            COUNT(*) FILTER (WHERE is_latest = TRUE AND is_forgotten = FALSE AND is_static = TRUE) AS static,
            COUNT(*) FILTER (WHERE is_latest = TRUE AND is_forgotten = FALSE AND is_static = FALSE) AS dynamic,
            COUNT(*) FILTER (WHERE is_latest = TRUE AND is_forgotten = FALSE AND is_inference = TRUE) AS inferred,
            COUNT(*) FILTER (WHERE is_forgotten = TRUE) AS forgotten,
            COUNT(*) FILTER (WHERE is_latest = FALSE) AS old_versions,
            COUNT(*) FILTER (WHERE embedding IS NOT NULL) AS with_embedding,
            COUNT(*) AS all_rows,
            COALESCE(AVG(confidence) FILTER (WHERE is_latest = TRUE AND is_forgotten = FALSE), 0) AS avg_confidence
        FROM memories
        WHERE container_tag = $1
        """,
        c,
    )
    entities = await db.fetchval(
        "SELECT COUNT(*) FROM entities WHERE container_tag = $1", c
    )
    relations = await db.fetchval(
        "SELECT COUNT(*) FROM entity_relations WHERE container_tag = $1", c
    )
    memory_relations = await db.fetchval(
        """
        SELECT COUNT(*) FROM memory_relations mr
        JOIN memories m ON m.id = mr.from_memory_id
        WHERE m.container_tag = $1
        """,
        c,
    )
    docs = await db.fetchrow(
        """
        SELECT
            COUNT(*) AS total,
            COUNT(*) FILTER (WHERE status = 'done') AS done,
            COALESCE(SUM(token_count), 0) AS total_tokens,
            COALESCE(SUM(chunk_count), 0) AS total_chunks
        FROM documents
        WHERE container_tag = $1
        """,
        c,
    )
    traces = await db.fetchrow(
        """
        SELECT
            COUNT(*) AS total,
            COUNT(*) FILTER (WHERE error IS NOT NULL) AS errors
        FROM recall_traces
        WHERE container_tag = $1 OR user_tag = $1 OR project_tag = $1
        """,
        c,
    )
    embedding_calls = await db.fetchrow(
        """
        SELECT
            COUNT(*) AS total,
            COUNT(*) FILTER (WHERE ok = TRUE) AS ok,
            COUNT(*) FILTER (WHERE cache_hit = TRUE) AS cache_hits
        FROM recall_embedding_logs
        WHERE container_tag = $1
        """,
        c,
    )

    return {
        "container_tag": c,
        "memories": dict(memories),
        "entities": entities,
        "entity_relations": relations,
        "memory_relations": memory_relations,
        "documents": dict(docs),
        "recalls": dict(traces),
        "embedding_calls": dict(embedding_calls),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


@router.get(
    "/timeline",
    summary="记忆新增趋势",
    description="近 N 天记忆新增数量，按天/周/月分组（缺数据日期补零）。",
)
async def get_timeline(
    container_tag: Optional[str] = Query(None, description="Container tag (optional)"),
    days: int = Query(30, ge=1, le=365),
    group_by: str = Query("day", pattern="^(day|week|month)$"),
    current_user: dict = Depends(require_permission("read")),
    _: dict = Depends(check_rate_limit),
):
    c = await _resolve_container(container_tag, current_user)
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=days - 1)

    if group_by == "day":
        sql = """
            SELECT created_at::date AS bucket, COUNT(*) AS count
            FROM memories
            WHERE container_tag = $1 AND is_latest = TRUE AND is_forgotten = FALSE
              AND created_at >= $2
            GROUP BY created_at::date
        """
    elif group_by == "week":
        sql = """
            SELECT DATE_TRUNC('week', created_at) AS bucket, COUNT(*) AS count
            FROM memories
            WHERE container_tag = $1 AND is_latest = TRUE AND is_forgotten = FALSE
              AND created_at >= $2
            GROUP BY DATE_TRUNC('week', created_at)
        """
    else:
        sql = """
            SELECT DATE_TRUNC('month', created_at) AS bucket, COUNT(*) AS count
            FROM memories
            WHERE container_tag = $1 AND is_latest = TRUE AND is_forgotten = FALSE
              AND created_at >= $2
            GROUP BY DATE_TRUNC('month', created_at)
        """

    rows = await db.fetch(sql, c, start)
    counts = {}
    for r in rows:
        b = r["bucket"]
        counts[b.date() if isinstance(b, datetime) else b] = r["count"]

    points: List[Dict[str, Any]] = []
    if group_by == "day":
        step = timedelta(days=1)
    elif group_by == "week":
        step = timedelta(weeks=1)
        start = start - timedelta(days=start.weekday())
    else:
        step = None

    if step is None:
        # month: iterate from start month to now month
        bucket = start.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        end_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        while bucket <= end_month:
            points.append({"date": bucket.date().isoformat(), "count": counts.get(bucket.date(), 0)})
            y = bucket.year + (1 if bucket.month == 12 else 0)
            m = 1 if bucket.month == 12 else bucket.month + 1
            bucket = bucket.replace(year=y, month=m)
    else:
        bucket = start
        while bucket <= now:
            points.append({"date": bucket.date().isoformat(), "count": counts.get(bucket.date(), 0)})
            bucket = bucket + step

    total = sum(p["count"] for p in points)
    return {
        "group_by": group_by,
        "days": days,
        "total": total,
        "points": points,
    }


@router.get(
    "/entities",
    summary="知识图谱构成",
    description="实体类型分布、Top 实体、实体关系类型分布。",
)
async def get_entities(
    container_tag: Optional[str] = Query(None, description="Container tag (optional)"),
    top_n: int = Query(10, ge=1, le=50),
    current_user: dict = Depends(require_permission("read")),
    _: dict = Depends(check_rate_limit),
):
    c = await _resolve_container(container_tag, current_user)

    by_type = await db.fetch(
        """
        SELECT type, COUNT(*) AS count
        FROM entities
        WHERE container_tag = $1
        GROUP BY type ORDER BY count DESC
        """,
        c,
    )
    top = await db.fetch(
        """
        SELECT name, type, mention_count
        FROM entities
        WHERE container_tag = $1
        ORDER BY mention_count DESC, name
        LIMIT $2
        """,
        c,
        top_n,
    )
    relation_types = await db.fetch(
        """
        SELECT relation_type, COUNT(*) AS count, ROUND(AVG(weight)::numeric, 3) AS avg_weight
        FROM entity_relations
        WHERE container_tag = $1
        GROUP BY relation_type ORDER BY count DESC
        """,
        c,
    )
    isolated = await db.fetchval(
        """
        SELECT COUNT(*) FROM entities e
        WHERE e.container_tag = $1
          AND NOT EXISTS (
              SELECT 1 FROM entity_relations r
              WHERE r.container_tag = $1
                AND (r.from_entity_id = e.id OR r.to_entity_id = e.id)
          )
        """,
        c,
    )

    return {
        "by_type": [dict(r) for r in by_type],
        "top": [dict(r) for r in top],
        "relation_types": [dict(r) for r in relation_types],
        "isolated_entities": isolated,
    }


@router.get(
    "/activity",
    summary="召回与 embedding 健康",
    description="召回运行情况（次数/成功率/耗时）与 embedding 调用健康（成功率/缓存率/错误）。",
)
async def get_activity(
    container_tag: Optional[str] = Query(None, description="Container tag (optional)"),
    days: int = Query(7, ge=1, le=90),
    current_user: dict = Depends(require_permission("read")),
    _: dict = Depends(check_rate_limit),
):
    c = await _resolve_container(container_tag, current_user)
    since = datetime.now(timezone.utc) - timedelta(days=days)

    recalls = await db.fetchrow(
        """
        SELECT
            COUNT(*) AS total,
            COUNT(*) FILTER (WHERE error IS NOT NULL) AS errors,
            ROUND(AVG(total_ms)::numeric, 1) AS avg_ms,
            ROUND((percentile_cont(0.95) WITHIN GROUP (ORDER BY total_ms))::numeric, 1) AS p95_ms
        FROM recall_traces
        WHERE (container_tag = $1 OR user_tag = $1 OR project_tag = $1) AND created_at >= $2
        """,
        c,
        since,
    )
    mode_dist = await db.fetch(
        """
        SELECT mode, COUNT(*) AS count
        FROM recall_traces
        WHERE (container_tag = $1 OR user_tag = $1 OR project_tag = $1) AND created_at >= $2
        GROUP BY mode ORDER BY count DESC
        """,
        c,
        since,
    )
    recall_trend = await db.fetch(
        """
        SELECT created_at::date AS bucket, COUNT(*) AS count
        FROM recall_traces
        WHERE (container_tag = $1 OR user_tag = $1 OR project_tag = $1) AND created_at >= $2
        GROUP BY created_at::date ORDER BY bucket
        """,
        c,
        since,
    )
    embeddings = await db.fetchrow(
        """
        SELECT
            COUNT(*) AS total,
            COUNT(*) FILTER (WHERE ok = TRUE) AS ok,
            COUNT(*) FILTER (WHERE cache_hit = TRUE) AS cache_hits,
            ROUND(AVG(elapsed_ms)::numeric, 1) AS avg_ms,
            COALESCE(SUM(text_len), 0) AS total_chars
        FROM recall_embedding_logs
        WHERE container_tag = $1 AND created_at >= $2
        """,
        c,
        since,
    )
    emb_by_kind = await db.fetch(
        """
        SELECT kind, COUNT(*) AS count,
               COUNT(*) FILTER (WHERE ok = TRUE) AS ok,
               COUNT(*) FILTER (WHERE cache_hit = TRUE) AS cache_hits
        FROM recall_embedding_logs
        WHERE container_tag = $1 AND created_at >= $2
        GROUP BY kind ORDER BY count DESC
        """,
        c,
        since,
    )
    emb_errors = await db.fetch(
        """
        SELECT COALESCE(error, '') AS error, COUNT(*) AS count
        FROM recall_embedding_logs
        WHERE container_tag = $1 AND created_at >= $2 AND ok = FALSE AND error IS NOT NULL AND error <> ''
        GROUP BY error ORDER BY count DESC LIMIT 5
        """,
        c,
        since,
    )
    top_queries = await db.fetch(
        """
        SELECT query, COUNT(*) AS count
        FROM recall_traces
        WHERE (container_tag = $1 OR user_tag = $1 OR project_tag = $1)
          AND created_at >= $2 AND query IS NOT NULL AND query <> ''
        GROUP BY query ORDER BY count DESC LIMIT 5
        """,
        c,
        since,
    )

    return {
        "days": days,
        "recalls": dict(recalls),
        "recall_by_mode": [dict(r) for r in mode_dist],
        "recall_trend": [dict(r) for r in recall_trend],
        "top_queries": [dict(r) for r in top_queries],
        "embedding": dict(embeddings),
        "embedding_by_kind": [dict(r) for r in emb_by_kind],
        "embedding_errors": [dict(r) for r in emb_errors],
    }
