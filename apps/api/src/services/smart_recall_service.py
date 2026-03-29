"""
智能召回服务
直接使用混合召回（向量+关键词+图谱）
使用 v3.0 DAG 架构 (raw_messages + summaries)
"""

from typing import List, Dict, Any, Optional
from datetime import datetime
import logging
from ..llm.client import get_llm_client
from ..database import db

logger = logging.getLogger(__name__)


class SmartRecallService:
    """智能召回路由服务 (v3.0 DAG 架构)"""

    def __init__(self):
        self.llm_client = get_llm_client()

    async def smart_recall(
        self, query: str, user_id: str, limit: int = 20, detail_level: str = "medium"
    ) -> Dict[str, Any]:
        """
        智能召回：直接使用混合召回（向量+关键词+图谱）

        Args:
            query: 用户查询
            user_id: 用户 ID
            limit: 返回数量
            detail_level: 详情级别

        Returns:
            召回结果和路由决策信息
        """
        db.set_current_user(user_id)

        logger.info(f"[Smart Recall] 查询: {query}")

        from .jieba_service import extract_time_keywords

        time_result = extract_time_keywords(query)
        time_keywords = query if time_result else None

        memories = await self._execute_hybrid_recall(
            {"query": query, "limit": limit, "time_keywords": time_keywords},
            user_id,
            limit,
        )

        from .llm_recall_service import get_llm_recall_service

        llm_recall = get_llm_recall_service()

        llm_result = await llm_recall.generate_recall_response(
            query=query,
            memory_results=memories,
            detail_level=detail_level,
            user_id=user_id,
        )

        return {
            "answer": llm_result["answer"],
            "used_memories": llm_result["used_memories"],
            "memory_count": llm_result["memory_count"],
            "route_decision": {
                "strategy": "hybrid_recall",
                "reason": "使用混合召回（向量+关键词+图谱），综合多种方式获取最佳结果",
                "params": {"query": query},
            },
        }

    async def _execute_hybrid_recall(
        self, params: Dict, user_id: str, limit: int
    ) -> List[Dict]:
        from .core.lossless_recall_service import lossless_recall_service
        from .jieba_service import extract_time_keywords

        query = params.get("query", "")
        time_keywords = params.get("time_keywords")

        time_range = None
        if time_keywords:
            time_result = extract_time_keywords(time_keywords)
            if time_result:
                time_range = {
                    "start_time": time_result["start"],
                    "end_time": time_result["end"],
                }

        results = await lossless_recall_service.hybrid_recall(
            query=query,
            user_id=user_id,
            scope="all",
            limit=params.get("limit", limit),
            min_similarity=0.3,
            time_range=time_range,
        )

        return results


smart_recall_service: Optional[SmartRecallService] = None


def get_smart_recall_service() -> SmartRecallService:
    """获取智能召回服务实例"""
    global smart_recall_service
    if smart_recall_service is None:
        smart_recall_service = SmartRecallService()
    return smart_recall_service
