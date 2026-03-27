import asyncio
import logging
import re
from typing import List, Dict, Any, Optional
from datetime import datetime

from src.database import db
from src.embedding.client import get_embedding_client

logger = logging.getLogger(__name__)


class LosslessRecallService:
    def __init__(self):
        self.embedding_client = get_embedding_client()

    async def hybrid_recall(
        self,
        query: str,
        user_id: str,
        agent_id: Optional[str] = None,
        scope: str = "all",
        limit: int = 20,
        min_similarity: float = 0.3,
        time_range: Optional[Dict[str, datetime]] = None,
    ) -> List[Dict[str, Any]]:
        query_embedding = self.embedding_client.embed(query)
        if not query_embedding:
            return []

        agent_filter = self._build_agent_filter(scope, agent_id)

        vector_results, keyword_results, graph_results = await asyncio.gather(
            self._vector_recall(
                query, query_embedding, user_id, agent_filter, limit * 2
            ),
            self._keyword_recall(query, user_id, agent_filter, limit * 2),
            self._graph_recall(query, user_id, agent_id, scope, limit),
        )

        merged = self._merge_results(vector_results, keyword_results, graph_results)

        merged = [r for r in merged if r.get("similarity", 0) >= min_similarity]

        if time_range:
            merged = self._filter_by_time(merged, time_range)

        return merged[:limit]

    def _build_agent_filter(self, scope: str, agent_id: Optional[str]) -> str:
        if scope == "manual_only":
            return "agent_id IS NULL"
        elif scope == "agent_only" and agent_id:
            return f"agent_id = '{agent_id}'"
        else:
            if agent_id:
                return f"(agent_id IS NULL OR agent_id = '{agent_id}')"
            return "agent_id IS NULL"

    async def _vector_recall(
        self,
        query: str,
        query_embedding: List[float],
        user_id: str,
        agent_filter: str,
        limit: int,
    ) -> List[Dict[str, Any]]:
        results = []
        embedding_str = "[" + ",".join(map(str, query_embedding)) + "]"

        raw_results = await db.fetch(
            f"""
            SELECT id, content, agent_id, memory_type, created_at,
                   1 - (embedding <=> $1::vector) AS similarity
            FROM raw_messages
            WHERE user_id = $2 AND {agent_filter}
              AND embedding IS NOT NULL
            ORDER BY embedding <=> $1::vector
            LIMIT $3
        """,
            embedding_str,
            user_id,
            limit,
        )

        for r in raw_results:
            content = r["content"]
            snippet_data = self._extract_snippet(content, query)
            results.append(
                {
                    "type": "raw_message",
                    "id": r["id"],
                    "content": content,
                    "snippet": snippet_data["snippet"],
                    "snippet_highlight": snippet_data["snippet_highlight"],
                    "agent_id": r["agent_id"],
                    "memory_type": r["memory_type"],
                    "similarity": float(r["similarity"]) if r["similarity"] else 0.0,
                    "source": "vector",
                    "expandable": len(content) > 500,
                    "created_at": r["created_at"].isoformat()
                    if r["created_at"]
                    else None,
                }
            )

        summary_results = await db.fetch(
            f"""
            SELECT summary_id, content, agent_id, kind, depth, created_at,
                   1 - (embedding <=> $1::vector) AS similarity
            FROM summaries
            WHERE user_id = $2 AND ({agent_filter.replace("agent_id", "summaries.agent_id")})
              AND embedding IS NOT NULL
            ORDER BY embedding <=> $1::vector
            LIMIT $3
        """,
            embedding_str,
            user_id,
            limit,
        )

        for r in summary_results:
            content = r["content"]
            snippet_data = self._extract_snippet(content, query)
            results.append(
                {
                    "type": "summary",
                    "id": r["summary_id"],
                    "content": content,
                    "snippet": snippet_data["snippet"],
                    "snippet_highlight": snippet_data["snippet_highlight"],
                    "agent_id": r["agent_id"],
                    "kind": r["kind"],
                    "depth": r["depth"],
                    "similarity": float(r["similarity"]) if r["similarity"] else 0.0,
                    "source": "vector",
                    "expandable": True,
                    "created_at": r["created_at"].isoformat()
                    if r["created_at"]
                    else None,
                }
            )

        return results

    async def _keyword_recall(
        self,
        query: str,
        user_id: str,
        agent_filter: str,
        limit: int,
    ) -> List[Dict[str, Any]]:
        results = []

        keywords = self._extract_keywords(query)
        if not keywords:
            return results

        tsquery = " | ".join(keywords)

        raw_results = await db.fetch(
            f"""
            SELECT id, content, agent_id, memory_type, created_at,
                   ts_rank_cd(to_tsvector('simple', content), to_tsquery('simple', $1)) AS rank
            FROM raw_messages
            WHERE user_id = $2 AND {agent_filter}
              AND to_tsvector('simple', content) @@ to_tsquery('simple', $1)
            ORDER BY rank DESC
            LIMIT $3
        """,
            tsquery,
            user_id,
            limit,
        )

        for r in raw_results:
            content = r["content"]
            snippet_data = self._extract_snippet(content, query)
            results.append(
                {
                    "type": "raw_message",
                    "id": r["id"],
                    "content": content,
                    "snippet": snippet_data["snippet"],
                    "snippet_highlight": snippet_data["snippet_highlight"],
                    "agent_id": r["agent_id"],
                    "memory_type": r["memory_type"],
                    "similarity": min(1.0, float(r["rank"]) * 5) if r["rank"] else 0.0,
                    "source": "keyword",
                    "expandable": len(content) > 500,
                    "created_at": r["created_at"].isoformat()
                    if r["created_at"]
                    else None,
                }
            )

        summary_results = await db.fetch(
            f"""
            SELECT summary_id, content, agent_id, kind, depth, created_at,
                   ts_rank_cd(to_tsvector('simple', content), to_tsquery('simple', $1)) AS rank
            FROM summaries
            WHERE user_id = $2 AND ({agent_filter.replace("agent_id", "summaries.agent_id")})
              AND to_tsvector('simple', content) @@ to_tsquery('simple', $1)
            ORDER BY rank DESC
            LIMIT $3
        """,
            tsquery,
            user_id,
            limit,
        )

        for r in summary_results:
            content = r["content"]
            snippet_data = self._extract_snippet(content, query)
            results.append(
                {
                    "type": "summary",
                    "id": r["summary_id"],
                    "content": content,
                    "snippet": snippet_data["snippet"],
                    "snippet_highlight": snippet_data["snippet_highlight"],
                    "agent_id": r["agent_id"],
                    "kind": r["kind"],
                    "depth": r["depth"],
                    "similarity": min(1.0, float(r["rank"]) * 5) if r["rank"] else 0.0,
                    "source": "keyword",
                    "expandable": True,
                    "created_at": r["created_at"].isoformat()
                    if r["created_at"]
                    else None,
                }
            )

        return results

    async def _graph_recall(
        self,
        query: str,
        user_id: str,
        agent_id: Optional[str],
        scope: str,
        limit: int,
    ) -> List[Dict[str, Any]]:
        results = []

        keywords = self._extract_keywords(query)
        if not keywords:
            return results

        for keyword in keywords[:3]:
            entity = await db.fetchrow(
                """
                SELECT id, name, type FROM entities
                WHERE user_id = $1 AND name ILIKE $2
                LIMIT 1
            """,
                user_id,
                f"%{keyword}%",
            )

            if not entity:
                continue

            if scope == "manual_only":
                agent_condition = "AND rm.agent_id IS NULL"
            elif scope == "agent_only" and agent_id:
                agent_condition = f"AND rm.agent_id = '{agent_id}'"
            else:
                if agent_id:
                    agent_condition = (
                        f"AND (rm.agent_id IS NULL OR rm.agent_id = '{agent_id}')"
                    )
                else:
                    agent_condition = "AND rm.agent_id IS NULL"

            message_results = await db.fetch(
                f"""
                SELECT DISTINCT rm.id, rm.content, rm.agent_id, rm.memory_type, rm.created_at
                FROM raw_messages rm
                JOIN memory_entities me ON me.memory_id = rm.id
                WHERE me.entity_id = $1 AND rm.user_id = $2 {agent_condition}
                LIMIT 5
            """,
                entity["id"],
                user_id,
            )

            for r in message_results:
                content = r["content"]
                snippet_data = self._extract_snippet(content, query)
                results.append(
                    {
                        "type": "raw_message",
                        "id": r["id"],
                        "content": content,
                        "snippet": snippet_data["snippet"],
                        "snippet_highlight": snippet_data["snippet_highlight"],
                        "agent_id": r["agent_id"],
                        "memory_type": r["memory_type"],
                        "entity": entity["name"],
                        "similarity": 0.6,
                        "source": "graph",
                        "expandable": len(content) > 500,
                        "created_at": r["created_at"].isoformat()
                        if r["created_at"]
                        else None,
                    }
                )

            summary_results = await db.fetch(
                f"""
                SELECT DISTINCT s.summary_id, s.content, s.agent_id, s.kind, s.depth, s.created_at
                FROM summaries s
                JOIN summary_entities se ON se.summary_id = s.summary_id
                WHERE se.entity_id = $1 AND s.user_id = $2
                LIMIT 5
            """,
                entity["id"],
                user_id,
            )

            for r in summary_results:
                content = r["content"]
                snippet_data = self._extract_snippet(content, query)
                results.append(
                    {
                        "type": "summary",
                        "id": r["summary_id"],
                        "content": content,
                        "snippet": snippet_data["snippet"],
                        "snippet_highlight": snippet_data["snippet_highlight"],
                        "agent_id": r["agent_id"],
                        "kind": r["kind"],
                        "depth": r["depth"],
                        "entity": entity["name"],
                        "similarity": 0.6,
                        "source": "graph",
                        "expandable": True,
                        "created_at": r["created_at"].isoformat()
                        if r["created_at"]
                        else None,
                    }
                )

        return results

    def _extract_keywords(self, query: str) -> List[str]:
        import jieba

        words = jieba.cut(query)
        keywords = [w for w in words if len(w) >= 2 and w.strip()]
        return list(set(keywords))[:5]

    def _extract_snippet(
        self,
        content: str,
        query: str,
        max_chars: int = 300,
        context_chars: int = 100,
    ) -> Dict[str, str]:
        """
        Extract a snippet around the first matching keyword in content.

        Args:
            content: The full text content
            query: The search query to extract keywords from
            max_chars: Maximum snippet length (default 300)
            context_chars: Characters before/after match (default 100)

        Returns:
            Dict with 'snippet' and 'snippet_highlight' keys
        """
        keywords = self._extract_keywords(query)

        # If no keywords or empty content, return first max_chars
        if not keywords or not content:
            snippet = content[:max_chars] if len(content) > max_chars else content
            return {
                "snippet": snippet + "..." if len(content) > max_chars else snippet,
                "snippet_highlight": snippet + "..."
                if len(content) > max_chars
                else snippet,
            }

        # Find first matching keyword position (case-insensitive)
        match_pos = -1
        matched_keyword = None
        content_lower = content.lower()

        for keyword in keywords:
            pos = content_lower.find(keyword.lower())
            if pos != -1:
                match_pos = pos
                matched_keyword = keyword
                break

        # If no match found, return first max_chars
        if match_pos == -1 or matched_keyword is None:
            snippet = content[:max_chars] if len(content) > max_chars else content
            return {
                "snippet": snippet + "..." if len(content) > max_chars else snippet,
                "snippet_highlight": snippet + "..."
                if len(content) > max_chars
                else snippet,
            }

        # Calculate snippet boundaries
        start = max(0, match_pos - context_chars)
        end = min(len(content), match_pos + len(matched_keyword) + context_chars)

        # Adjust to sentence boundaries for cleaner output
        sentence_endings = "。！？\n"
        sentence_starters = "。！？\n"

        # Adjust start to sentence boundary
        if start > 0:
            # Look backwards for sentence ending
            for i in range(start, max(0, start - 50), -1):
                if content[i] in sentence_starters:
                    start = i + 1
                    break

        # Adjust end to sentence boundary
        if end < len(content):
            # Look forwards for sentence ending
            for i in range(end, min(len(content), end + 50)):
                if content[i] in sentence_endings:
                    end = i + 1
                    break

        # Ensure snippet doesn't exceed max_chars
        if end - start > max_chars:
            end = start + max_chars

        # Extract snippet
        snippet = content[start:end]

        # Add ellipsis
        prefix = "..." if start > 0 else ""
        suffix = "..." if end < len(content) else ""
        snippet = prefix + snippet + suffix

        # Generate highlighted version
        snippet_highlight = snippet
        if matched_keyword:
            # Use regex for case-insensitive replacement
            pattern = re.escape(matched_keyword)
            snippet_highlight = re.sub(
                f"({pattern})",
                r"<em>\1</em>",
                snippet,
                flags=re.IGNORECASE,
            )

        return {
            "snippet": snippet,
            "snippet_highlight": snippet_highlight,
        }

    def _merge_results(
        self,
        vector_results: List[Dict],
        keyword_results: List[Dict],
        graph_results: List[Dict],
    ) -> List[Dict]:
        weights = {"vector": 0.5, "keyword": 0.3, "graph": 0.2}

        merged = {}

        for r in vector_results:
            key = f"{r['type']}:{r['id']}"
            merged[key] = r
            merged[key]["final_score"] = r["similarity"] * weights["vector"]
            merged[key]["sources"] = ["vector"]

        for r in keyword_results:
            key = f"{r['type']}:{r['id']}"
            if key in merged:
                merged[key]["final_score"] += r["similarity"] * weights["keyword"]
                merged[key]["sources"].append("keyword")
            else:
                merged[key] = r
                merged[key]["final_score"] = r["similarity"] * weights["keyword"]
                merged[key]["sources"] = ["keyword"]

        for r in graph_results:
            key = f"{r['type']}:{r['id']}"
            if key in merged:
                merged[key]["final_score"] += r["similarity"] * weights["graph"]
                merged[key]["sources"].append("graph")
            else:
                merged[key] = r
                merged[key]["final_score"] = r["similarity"] * weights["graph"]
                merged[key]["sources"] = ["graph"]

        for key in merged:
            merged[key]["similarity"] = merged[key]["final_score"]

        return sorted(merged.values(), key=lambda x: x["final_score"], reverse=True)

    def _filter_by_time(
        self,
        results: List[Dict],
        time_range: Dict[str, datetime],
    ) -> List[Dict]:
        start_time = time_range.get("start_time")
        end_time = time_range.get("end_time")

        filtered = []
        for r in results:
            created_at_str = r.get("created_at")
            if not created_at_str:
                continue

            try:
                created_at = datetime.fromisoformat(
                    created_at_str.replace("Z", "+00:00")
                )
                if start_time and created_at < start_time:
                    continue
                if end_time and created_at > end_time:
                    continue
                filtered.append(r)
            except (ValueError, TypeError):
                continue

        return filtered


lossless_recall_service = LosslessRecallService()
