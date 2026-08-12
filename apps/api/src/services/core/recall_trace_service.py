"""
Recall Trace service.

Per-request recall pipeline observability:
- Collects per-channel recall details (profile/vector/memory_graph/entity_graph/chunks)
- Records dedup kept/dropped and final injection order
- Persists to recall_traces table; supports list/detail queries and cleanup

Instrumentation is read-only: it never modifies recall logic.
"""

import json
import logging
import random
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from src.config import settings
from src.database import db

logger = logging.getLogger(__name__)

TRACE_ID_PREFIX = "trace_"


def _truncate(text: Optional[str], max_len: Optional[int] = None) -> Optional[str]:
    """Truncate content for storage (privacy & size control)."""
    if not text:
        return text
    limit = max_len if max_len is not None else settings.TRACE_CONTENT_MAX_LEN
    if len(text) <= limit:
        return text
    return text[:limit] + "…"


class RecallTrace:
    """Collects per-channel recall details for a single request."""

    def __init__(
        self,
        mode: str,
        container_tag: str,
        user_tag: Optional[str],
        project_tag: Optional[str],
        query: Optional[str],
        config: Dict[str, Any],
    ) -> None:
        self.mode = mode
        self.container_tag = container_tag
        self.user_tag = user_tag
        self.project_tag = project_tag
        self.query = query
        self.config = config
        self.error: Optional[str] = None
        self._start = time.monotonic()

        self.channels: Dict[str, Any] = {
            "profile": {"enabled": bool(config.get("inject_profile", False))},
            "vector": {"threshold": config.get("memory_similarity_threshold", 0.3), "hits": []},
            "memory_graph": {"enabled": bool(config.get("enable_memory_graph", True)), "paths": []},
            "entity_graph": {"enabled": bool(config.get("enable_entity_graph", True)), "entity_paths": [], "memories": []},
            "chunks": {"threshold": config.get("chunks_similarity_threshold", 0.3), "hits": [], "entity_hits": []},
        }
        self.dedup: Dict[str, Any] = {"threshold": config.get("dedup_threshold", 0.85), "kept": [], "dropped": []}
        self.final: List[Dict[str, Any]] = []
        self.elapsed_ms: Dict[str, float] = {}
        self._last_elapsed_mark = self._start

    # ---------- channel recorders (read-only instrumentation) ----------

    def record_profile(self, static: List[str], dynamic: List[str], enabled: bool) -> None:
        self.channels["profile"].update(
            {
                "enabled": enabled,
                "static_count": len(static),
                "dynamic_count": len(dynamic),
                "items": [_truncate(s) for s in static[:100]] + [_truncate(d) for d in dynamic[:50]],
            }
        )

    def record_vector(self, hits: List[Dict[str, Any]], threshold: float, scope: Optional[str] = None) -> None:
        self.channels["vector"]["threshold"] = threshold
        for h in hits:
            similarity = float(h.get("similarity") or 0.0)
            hit = {
                "id": h.get("id"),
                "content": _truncate(h.get("content")),
                "similarity": round(similarity, 4),
                "passed": similarity >= threshold,
            }
            if scope:
                hit["scope"] = scope
            self.channels["vector"]["hits"].append(hit)

    def record_memory_graph(
        self, from_id: str, relation_type: str, target: Dict[str, Any], added: bool, scope: Optional[str] = None
    ) -> None:
        path = {
            "from_id": from_id,
            "relation_type": relation_type,
            "to_id": target.get("id"),
            "content": _truncate(target.get("content")),
            "added": added,
        }
        if scope:
            path["scope"] = scope
        self.channels["memory_graph"]["paths"].append(path)

    def record_entity_graph_entities(self, entity_names: List[str], scope: Optional[str] = None) -> None:
        if scope:
            self.channels["entity_graph"].setdefault("query_entities", []).append(
                {"names": entity_names, "scope": scope}
            )
        else:
            self.channels["entity_graph"]["query_entities"] = entity_names

    def record_entity_graph_path(self, entity: str, relation_type: str, to_entity: str, scope: Optional[str] = None) -> None:
        path = {"entity": entity, "relation_type": relation_type, "to_entity": to_entity}
        if scope:
            path["scope"] = scope
        self.channels["entity_graph"]["entity_paths"].append(path)

    def record_entity_graph_memory(self, memory: Dict[str, Any], scope: Optional[str] = None) -> None:
        item = {"id": memory.get("id"), "content": _truncate(memory.get("content"))}
        if scope:
            item["scope"] = scope
        self.channels["entity_graph"]["memories"].append(item)

    def record_chunks(self, hits: List[Dict[str, Any]], threshold: float, scope: Optional[str] = None) -> None:
        self.channels["chunks"]["threshold"] = threshold
        for h in hits:
            similarity = float(h.get("similarity") or 0.0)
            hit = {
                "id": h.get("id"),
                "document_id": h.get("document_id"),
                "title": h.get("title"),
                "content": _truncate(h.get("content")),
                "similarity": round(similarity, 4),
                "passed": similarity >= threshold,
            }
            if scope:
                hit["scope"] = scope
            self.channels["chunks"]["hits"].append(hit)

    def record_chunk_entity_hit(self, chunk: Dict[str, Any], scope: Optional[str] = None) -> None:
        item = {
            "id": chunk.get("id"),
            "document_id": chunk.get("document_id"),
            "title": chunk.get("title"),
            "content": _truncate(chunk.get("content")),
        }
        if scope:
            item["scope"] = scope
        self.channels["chunks"]["entity_hits"].append(item)

    def record_dedup(self, kept: List[Any], dropped: List[Dict[str, Any]], threshold: float) -> None:
        self.dedup["threshold"] = threshold
        self.dedup["kept"] = [
            {"id": getattr(i, "id", None), "source": getattr(i, "source", None)} for i in kept
        ]
        self.dedup["dropped"] = dropped

    def record_final(self, items: List[Any]) -> None:
        self.final = [
            {
                "id": getattr(i, "id", None),
                "content": _truncate(getattr(i, "content", None)),
                "source": getattr(i, "source", None),
                "relation_type": getattr(i, "relation_type", None),
            }
            for i in items
        ]

    def mark_error(self, error: str) -> None:
        self.error = _truncate(error, 500)

    # ---------- timing ----------

    def _mark(self, channel: str) -> None:
        now = time.monotonic()
        self.elapsed_ms[channel] = round((now - self._last_elapsed_mark) * 1000, 2)
        self._last_elapsed_mark = now

    def mark_profile(self) -> None:
        self._mark("profile")

    def mark_memories(self) -> None:
        self._mark("memories")

    def mark_chunks(self) -> None:
        self._mark("chunks")

    def mark_dedup(self) -> None:
        self._mark("dedup")

    def mark_format(self) -> None:
        self._mark("format")

    def total_ms(self) -> float:
        return round((time.monotonic() - self._start) * 1000, 2)

    # ---------- serialization / summary ----------

    def to_dict(self, include_config: bool = True) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "mode": self.mode,
            "container_tag": self.container_tag,
            "user_tag": self.user_tag,
            "project_tag": self.project_tag,
            "query": _truncate(self.query, 500),
            "channels": self.channels,
            "dedup": self.dedup,
            "final": self.final,
            "elapsed_ms": self.elapsed_ms,
            "total_ms": self.total_ms(),
            "error": self.error,
        }
        if include_config:
            data["config"] = self.config
        return data

    def summary(self) -> Dict[str, Any]:
        return {
            "profile": self.channels["profile"].get("static_count", 0) + self.channels["profile"].get("dynamic_count", 0),
            "vector": len(self.channels["vector"]["hits"]),
            "memory_graph": len(self.channels["memory_graph"]["paths"]),
            "entity_graph": len(self.channels["entity_graph"]["memories"]) + len(self.channels["entity_graph"]["entity_paths"]),
            "chunks": len(self.channels["chunks"]["hits"]) + len(self.channels["chunks"]["entity_hits"]),
            "kept": len(self.dedup["kept"]),
            "dropped": len(self.dedup["dropped"]),
            "final": len(self.final),
        }


def _row_to_trace_dict(row: Dict[str, Any], include_detail: bool) -> Dict[str, Any]:
    def _json(v: Any) -> Any:
        if isinstance(v, str):
            try:
                return json.loads(v)
            except Exception:
                return {}
        return v or ([] if isinstance(v, list) else {})

    base = {
        "id": row["id"],
        "container_tag": row["container_tag"],
        "mode": row["mode"],
        "user_tag": row["user_tag"],
        "project_tag": row["project_tag"],
        "query": row["query"],
        "total_ms": float(row["total_ms"] or 0),
        "error": row["error"],
        "created_at": row["created_at"].isoformat() if row["created_at"] else None,
        "summary": _json(row.get("summary")),
        "elapsed_ms": _json(row.get("elapsed_ms")),
    }
    if include_detail:
        base.update(
            {
                "config": _json(row.get("config")),
                "channels": _json(row.get("channels")),
                "dedup": _json(row.get("dedup")),
                "final": _json(row.get("final")),
            }
        )
    return base


class RecallTraceService:
    async def should_record(self, force: bool = False) -> bool:
        """Whether a request should be traced (sampling-aware)."""
        if not settings.TRACE_ENABLED:
            return False
        if force:
            return True
        rate = max(0.0, min(1.0, settings.TRACE_SAMPLE_RATE))
        return rate >= 1.0 or random.random() < rate

    async def save(self, trace: RecallTrace) -> Optional[str]:
        """Persist a trace. Returns trace id or None."""
        try:
            data = trace.to_dict()
            row = await db.fetchrow(
                """
                INSERT INTO recall_traces (
                    container_tag, mode, user_tag, project_tag, query,
                    config, channels, dedup, final, elapsed_ms, total_ms, summary, error
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
                RETURNING id
                """,
                trace.container_tag,
                trace.mode,
                trace.user_tag,
                trace.project_tag,
                _truncate(trace.query, 500),
                json.dumps(data.get("config") or {}, ensure_ascii=False),
                json.dumps(data["channels"], ensure_ascii=False),
                json.dumps(data["dedup"], ensure_ascii=False),
                json.dumps(data["final"], ensure_ascii=False),
                json.dumps(data["elapsed_ms"], ensure_ascii=False),
                data["total_ms"],
                json.dumps(trace.summary(), ensure_ascii=False),
                trace.error,
            )
            return str(row["id"]) if row else None
        except Exception as e:
            logger.warning(f"Failed to save recall trace: {e}")
            return None

    async def list_traces_for_container(
        self,
        container_tag: str,
        limit: int = 20,
        offset: int = 0,
        include_children: bool = False,
    ) -> List[Dict[str, Any]]:
        prefix_match = f"{container_tag}_%"
        rows = await db.fetch(
            """
            SELECT id, container_tag, mode, user_tag, project_tag, query,
                   total_ms, error, created_at, summary, elapsed_ms
            FROM recall_traces
            WHERE (container_tag = $1 OR user_tag = $1 OR project_tag = $1)
               OR ($4 = TRUE AND (container_tag LIKE $2 OR user_tag LIKE $2 OR project_tag LIKE $2))
            ORDER BY created_at DESC
            LIMIT $3 OFFSET $5
            """,
            container_tag,
            prefix_match,
            limit,
            include_children,
            offset,
        )
        return [_row_to_trace_dict(r, include_detail=False) for r in rows]

    async def count_for_container(self, container_tag: str, include_children: bool = False) -> int:
        prefix_match = f"{container_tag}_%"
        row = await db.fetchrow(
            """
            SELECT COUNT(*) AS n FROM recall_traces
            WHERE (container_tag = $1 OR user_tag = $1 OR project_tag = $1)
               OR ($3 = TRUE AND (container_tag LIKE $2 OR user_tag LIKE $2 OR project_tag LIKE $2))
            """,
            container_tag,
            prefix_match,
            include_children,
        )
        return int(row["n"]) if row else 0

    async def get_trace(self, trace_id: str) -> Optional[Dict[str, Any]]:
        row = await db.fetchrow(
            """
            SELECT id, container_tag, mode, user_tag, project_tag, query,
                   config, channels, dedup, final, elapsed_ms, total_ms,
                   summary, error, created_at
            FROM recall_traces
            WHERE id = $1
            """,
            trace_id,
        )
        return _row_to_trace_dict(row, include_detail=True) if row else None

    async def cleanup(self, retention_days: int) -> int:
        """Delete traces older than retention_days. Returns deleted count."""
        result = await db.execute(
            """
            DELETE FROM recall_traces
            WHERE created_at < NOW() - ($1::int || ' days')::interval
            """,
            retention_days,
        )
        try:
            return int(result.split()[-1]) if result else 0
        except Exception:
            return 0


recall_trace_service = RecallTraceService()
