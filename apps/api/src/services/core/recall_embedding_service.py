"""
Embedding call log service.

Structured logging of every embedding API call (memory create, context query, ...):
- Records success/failure/cache-hit with model, error, timing
- Persists to recall_embedding_logs table; supports list queries
- Instrumentation is read-only and never affects recall/creation logic
"""

import logging
import time
from typing import Any, Dict, List, Optional

from src.database import db

logger = logging.getLogger(__name__)


class RecallEmbeddingService:
    """Persists structured embedding call logs for debugging LLM/embedding issues."""

    async def log(
        self,
        container_tag: Optional[str],
        kind: str,
        text: Optional[str],
        ok: bool,
        *,
        cache_hit: bool = False,
        model: Optional[str] = None,
        error: Optional[str] = None,
        elapsed_ms: float = 0,
        output_dim: Optional[int] = None,
    ) -> Optional[str]:
        """Record one embedding call. Never raises: logging must not break the caller."""
        try:
            text_preview = None
            text_len = 0
            if text:
                text_preview = text[:200] + ("…" if len(text) > 200 else "")
                text_len = len(text)
            row = await db.fetchrow(
                """
                INSERT INTO recall_embedding_logs
                    (container_tag, kind, model, text_preview, text_len, ok, cache_hit, error, elapsed_ms, output_dim)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                RETURNING id
                """,
                container_tag or "",
                kind,
                model,
                text_preview,
                text_len,
                ok,
                cache_hit,
                (error or "")[:500],
                elapsed_ms,
                output_dim,
            )
            return row["id"] if row else None
        except Exception as e:
            logger.warning(f"recall_embedding_logs insert failed: {e}")
            return None

    async def list_logs(
        self,
        container_tag: str,
        kind: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
        include_children: bool = False,
    ) -> List[Dict[str, Any]]:
        prefix_match = f"{container_tag}_%"
        if kind:
            rows = await db.fetch(
                """
                SELECT id, container_tag, kind, model, text_preview, text_len, ok,
                       cache_hit, error, elapsed_ms, output_dim, created_at
                FROM recall_embedding_logs
                WHERE kind = $1
                  AND (container_tag = $2 OR ($3 = TRUE AND container_tag LIKE $4))
                ORDER BY created_at DESC
                LIMIT $5 OFFSET $6
                """,
                kind, container_tag, include_children, prefix_match, limit, offset,
            )
        else:
            rows = await db.fetch(
                """
                SELECT id, container_tag, kind, model, text_preview, text_len, ok,
                       cache_hit, error, elapsed_ms, output_dim, created_at
                FROM recall_embedding_logs
                WHERE container_tag = $1 OR ($2 = TRUE AND container_tag LIKE $3)
                ORDER BY created_at DESC
                LIMIT $4 OFFSET $5
                """,
                container_tag, include_children, prefix_match, limit, offset,
            )
        return [dict(r) for r in rows]

    async def count_for_container(
        self, container_tag: str, kind: Optional[str] = None, include_children: bool = False
    ) -> int:
        prefix_match = f"{container_tag}_%"
        if kind:
            row = await db.fetchrow(
                """SELECT COUNT(*) AS n FROM recall_embedding_logs
                   WHERE kind = $1 AND (container_tag = $2 OR ($3 = TRUE AND container_tag LIKE $4))""",
                kind, container_tag, include_children, prefix_match,
            )
        else:
            row = await db.fetchrow(
                """SELECT COUNT(*) AS n FROM recall_embedding_logs
                   WHERE container_tag = $1 OR ($2 = TRUE AND container_tag LIKE $3)""",
                container_tag, include_children, prefix_match,
            )
        return row["n"] if row else 0


recall_embedding_service = RecallEmbeddingService()
