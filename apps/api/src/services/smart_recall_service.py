"""
智能召回服务
直接使用混合召回（向量+关键词+图谱）
"""

from typing import List, Dict, Any, Optional
from datetime import datetime
import logging
from ..llm.client import get_llm_client
from ..database import db

logger = logging.getLogger(__name__)


# ==================== 智能召回服务 ====================


class SmartRecallService:
    """智能召回路由服务"""

    def __init__(self):
        self.llm_client = get_llm_client()

    async def smart_recall(
        self, query: str, user_id: str, limit: int = 10, detail_level: str = "medium"
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

        # 提取时间关键词（用于时间过滤）
        from .jieba_service import extract_time_keywords

        time_result = extract_time_keywords(query)
        time_keywords = query if time_result else None

        # 直接使用混合召回（最快）
        memories = await self._execute_hybrid_recall(
            {"query": query, "limit": limit, "time_keywords": time_keywords},
            user_id,
            limit,
        )

        # 生成回答
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
        """执行混合召回"""
        from .recall_service import get_recall_service
        from .jieba_service import extract_time_keywords
        from datetime import datetime

        recall_service = get_recall_service()

        query = params.get("query", "")
        time_keywords = params.get("time_keywords")
        location_filter = params.get("location_filter")
        person_filter = params.get("person_filter")
        weights = params.get("weights", {"vector": 0.5, "keyword": 0.3, "graph": 0.2})

        # 解析时间
        time_range = None
        if time_keywords:
            time_result = extract_time_keywords(time_keywords)
            if time_result:
                time_range = {
                    "start_time": time_result["start"],
                    "end_time": time_result["end"],
                }

        results = await recall_service.search(
            query=query,
            limit=params.get("limit", limit),
            time_range=time_range,
            location_filter=location_filter,
            person_filter=person_filter,
            hybrid_weight=weights.get("vector", 0.5),
            enable_graph=True,
            user_id=user_id,
        )

        return results


# 全局实例
smart_recall_service: Optional[SmartRecallService] = None


def get_smart_recall_service() -> SmartRecallService:
    """获取智能召回服务实例"""
    global smart_recall_service
    if smart_recall_service is None:
        smart_recall_service = SmartRecallService()
    return smart_recall_service
