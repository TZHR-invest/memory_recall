"""
语义去重服务
基于 embedding 相似度进行语义去重
"""

from typing import List, Optional, Dict, Any
from dataclasses import dataclass
import numpy as np


@dataclass
class DedupItem:
    content: str
    source: str
    priority: int
    embedding: Optional[List[float]] = None
    id: Optional[str] = None
    relation_type: Optional[str] = None  # updates/extends/derives 语义关系类型


SOURCE_PRIORITY = {
    "profile": 4,
    "projectMemory": 3,
    "userMemory": 2,
    "chunk": 1,
}


class SemanticDedupService:
    def compute_cosine_similarity(
        self,
        a: List[float],
        b: List[float],
    ) -> float:
        if len(a) != len(b) or len(a) == 0:
            return 0.0

        a_arr = np.array(a, dtype=np.float32)
        b_arr = np.array(b, dtype=np.float32)

        norm_a = np.linalg.norm(a_arr)
        norm_b = np.linalg.norm(b_arr)

        if norm_a == 0 or norm_b == 0:
            return 0.0

        return float(np.dot(a_arr, b_arr) / (norm_a * norm_b))

    async def deduplicate(
        self,
        items: List[DedupItem],
        threshold: float = 0.85,
        dropped_log: Optional[list] = None,
    ) -> List[DedupItem]:
        if len(items) <= 1:
            return items

        items_with_embedding = [i for i in items if i.embedding is not None]
        items_without_embedding = [i for i in items if i.embedding is None]

        sorted_items = sorted(items_with_embedding, key=lambda x: -x.priority)

        kept: List[DedupItem] = []

        for item in sorted_items:
            is_duplicate = False

            for kept_item in kept:
                if kept_item.embedding is not None and item.embedding is not None:
                    similarity = self.compute_cosine_similarity(
                        kept_item.embedding,
                        item.embedding,
                    )

                    if similarity >= threshold:
                        is_duplicate = True
                        if dropped_log is not None:
                            dropped_log.append(
                                {
                                    "id": item.id,
                                    "source": item.source,
                                    "content": item.content[:200],
                                    "duplicate_of": {
                                        "id": kept_item.id,
                                        "source": kept_item.source,
                                    },
                                    "similarity": round(similarity, 4),
                                }
                            )
                        break

            if not is_duplicate:
                kept.append(item)

        kept.extend(items_without_embedding)

        return kept

    async def deduplicate_with_stats(
        self,
        items: List[DedupItem],
        threshold: float = 0.85,
    ) -> Dict[str, Any]:
        deduped = await self.deduplicate(items, threshold)

        stats = {
            "total": len(items),
            "after_dedup": len(deduped),
            "removed": len(items) - len(deduped),
            "by_source": {},
        }

        for source in SOURCE_PRIORITY.keys():
            original_count = len([i for i in items if i.source == source])
            kept_count = len([i for i in deduped if i.source == source])
            stats["by_source"][source] = {
                "original": original_count,
                "kept": kept_count,
                "removed": original_count - kept_count,
            }

        return {
            "items": deduped,
            "stats": stats,
        }

    def compute_similarity_matrix(
        self,
        items: List[DedupItem],
    ) -> np.ndarray:
        n = len(items)
        if n == 0:
            return np.array([])

        embeddings = []
        for item in items:
            if item.embedding:
                embeddings.append(item.embedding)
            else:
                embeddings.append([0.0] * 1024)

        embeddings_arr = np.array(embeddings, dtype=np.float32)

        norms = np.linalg.norm(embeddings_arr, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        normalized = embeddings_arr / norms

        similarity_matrix = np.dot(normalized, normalized.T)

        return similarity_matrix


semantic_dedup_service = SemanticDedupService()
