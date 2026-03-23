"""
召回服务
实现向量相似度 + 关键词混合检索
"""

from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import json
from ..database import db
from ..embedding.client import get_embedding_client
from ..llm.client import get_llm_client
from ..models.memory import Memory


class RecallService:
    """召回服务"""

    def __init__(self):
        """初始化服务"""
        self.embedding_client = get_embedding_client()
        self.llm_client = get_llm_client()

    async def search(
        self,
        query: str,
        limit: int = 50,
        time_range: Optional[Dict[str, datetime]] = None,
        location_filter: Optional[str] = None,
        person_filter: Optional[str] = None,
        tag_filter: Optional[str] = None,
        min_similarity: float = 0.05,
        hybrid_weight: float = 0.7,
        keywords: Optional[List[str]] = None,
        enable_graph: bool = False,
        user_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        混合检索记忆

        Args:
            query: 查询文本
            limit: 返回数量限制
            time_range: 时间范围过滤，包含 start_time 和 end_time
            location_filter: 地点过滤
            person_filter: 人物过滤
            tag_filter: 标签过滤
            min_similarity: 最小相似度阈值
            hybrid_weight: 混合权重（向量相似度权重，1-hybrid_weight 为关键词权重）
            keywords: 预提取的关键词列表（来自 LLM 解析）
            enable_graph: 是否启用图谱增强召回
            user_id: 用户 ID（启用图谱召回时必需）

        Returns:
            检索结果列表，包含记忆数据和相似度分数
        """
        # 调试日志
        import logging

        logger = logging.getLogger(__name__)
        logger.info(
            f"[DEBUG] search called with query={query}, limit={limit}, min_similarity={min_similarity}, enable_graph={enable_graph}, user_id={user_id}"
        )

        # 1. 生成查询向量
        query_embedding = self.embedding_client.embed(query)

        if not query_embedding:
            return []

        # 如果启用图谱召回，使用三路混合召回
        if enable_graph and user_id:
            try:
                from .graph_recall_service import get_graph_recall_service

                graph_service = get_graph_recall_service()

                # 定义图谱召回的权重配置
                graph_weights = {
                    "vector": hybrid_weight * 0.7,  # 向量权重
                    "keyword": (1 - hybrid_weight) * 0.6,  # 关键词权重
                    "graph": 0.2,  # 图谱权重
                }

                # 调用图谱服务的混合召回（传递时间过滤）
                results = await graph_service.hybrid_recall(
                    query=query,
                    user_id=user_id,
                    limit=limit,
                    weights=graph_weights,
                    time_range=time_range,  # ✅ 传递时间过滤
                )

                # 过滤低相似度结果
                results = [
                    r for r in results if r.get("similarity", 0) >= min_similarity
                ]

                return results[:limit]

            except Exception as e:
                # 如果图谱召回失败，回退到传统召回
                import logging

                logging.warning(f"图谱召回失败，回退到传统召回: {e}")

        # 2. 向量相似度检索
        vector_results = await self._vector_search(
            query_embedding,
            limit * 2,  # 获取更多结果用于混合排序
            time_range,
            location_filter,
            person_filter,
            tag_filter,
        )

        # 3. 关键词检索
        keyword_results = await self._keyword_search(
            query,
            limit * 2,
            time_range,
            location_filter,
            person_filter,
            tag_filter,
            keywords=keywords,
        )

        # 4. 混合排序
        results = self._hybrid_rank(vector_results, keyword_results, hybrid_weight)

        # 5. 过滤低相似度结果
        results = [r for r in results if r["similarity"] >= min_similarity]

        # 6. 返回 Top-N 结果
        return results[:limit]

    async def _vector_search(
        self,
        query_embedding: List[float],
        limit: int,
        time_range: Optional[Dict[str, datetime]] = None,
        location_filter: Optional[str] = None,
        person_filter: Optional[str] = None,
        tag_filter: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        向量相似度检索

        Args:
            query_embedding: 查询向量
            limit: 返回数量限制
            time_range: 时间范围过滤
            location_filter: 地点过滤
            person_filter: 人物过滤
            tag_filter: 标签过滤

        Returns:
            检索结果列表
        """
        # 构建基础 SQL
        sql = """
            SELECT 
                id, content, input_type, created_at,
                time_value, location_name, people, emotion, tags,
                1 - (embedding <=> $1::vector) as similarity
            FROM memories
            WHERE status = 'active'
                AND embedding IS NOT NULL
        """

        # 将向量转换为字符串格式
        embedding_str = "[" + ",".join(map(str, query_embedding)) + "]"
        params = [embedding_str]
        param_count = 1

        # 添加时间过滤
        if time_range:
            if time_range.get("start_time"):
                param_count += 1
                sql += f" AND time_value >= ${param_count}"
                params.append(time_range["start_time"])
            if time_range.get("end_time"):
                param_count += 1
                sql += f" AND time_value <= ${param_count}"
                params.append(time_range["end_time"])

        # 添加地点过滤
        if location_filter:
            param_count += 1
            sql += f" AND location_name LIKE ${param_count}"
            params.append(location_filter)

        # 添加人物过滤
        if person_filter:
            param_count += 1
            sql += f" AND (people::text LIKE ${param_count} OR content LIKE ${param_count})"
            params.append(f"%{person_filter}%")

        # 添加标签过滤
        if tag_filter:
            param_count += 1
            sql += f" AND ${param_count} = ANY(tags)"
            params.append(tag_filter)

        # 添加排序和限制
        sql += f" ORDER BY similarity DESC LIMIT ${param_count + 1}"
        params.append(limit)

        # 执行查询
        rows = await db.fetch(sql, *params)

        return [dict(row) for row in rows]

    async def _keyword_search(
        self,
        query: str,
        limit: int,
        time_range: Optional[Dict[str, datetime]] = None,
        location_filter: Optional[str] = None,
        person_filter: Optional[str] = None,
        tag_filter: Optional[str] = None,
        keywords: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        关键词检索

        使用 LIKE 查询支持中文关键词匹配

        Args:
            query: 查询文本
            limit: 返回数量限制
            time_range: 时间范围过滤
            location_filter: 地点过滤
            person_filter: 人物过滤
            tag_filter: 标签过滤
            keywords: 预提取的关键词列表

        Returns:
            检索结果列表
        """
        # 使用传入的关键词，如果没有则使用 Jieba 提取
        if not keywords:
            from .jieba_service import extract_keywords

            keywords = extract_keywords(query, min_length=2)

        if not keywords:
            return []

        # 构建 SQL - 使用 LIKE ANY 匹配关键词
        sql = """
            SELECT 
                id, content, input_type, created_at,
                time_value, location_name, people, emotion, tags
            FROM memories
            WHERE status = 'active'
                AND content LIKE ANY($1::text[])
        """

        # 构建 LIKE 模式
        like_patterns = [f"%{kw}%" for kw in keywords]
        params = [like_patterns]
        param_count = 1

        # 添加时间过滤
        if time_range:
            if time_range.get("start_time"):
                param_count += 1
                sql += f" AND time_value >= ${param_count}"
                params.append(time_range["start_time"])
            if time_range.get("end_time"):
                param_count += 1
                sql += f" AND time_value <= ${param_count}"
                params.append(time_range["end_time"])

        # 添加地点过滤
        if location_filter:
            param_count += 1
            sql += f" AND location_name LIKE ${param_count}"
            params.append(location_filter)

        # 添加人物过滤
        if person_filter:
            param_count += 1
            sql += f" AND (people::text LIKE ${param_count} OR content LIKE ${param_count})"
            params.append(f"%{person_filter}%")

        # 添加标签过滤
        if tag_filter:
            param_count += 1
            sql += f" AND ${param_count} = ANY(tags)"
            params.append(tag_filter)

        # 添加限制
        sql += f" LIMIT ${param_count + 1}"
        params.append(limit)

        # 执行查询
        rows = await db.fetch(sql, *params)

        # 计算匹配分数
        results = []
        for row in rows:
            result = dict(row)
            # 计算关键词匹配数量
            match_count = sum(1 for kw in keywords if kw in result["content"])
            # 归一化到 0-1 范围
            result["similarity"] = match_count / len(keywords) if keywords else 0
            results.append(result)

        # 按匹配分数排序
        results.sort(key=lambda x: x["similarity"], reverse=True)

        return results

    def _hybrid_rank(
        self,
        vector_results: List[Dict[str, Any]],
        keyword_results: List[Dict[str, Any]],
        vector_weight: float,
    ) -> List[Dict[str, Any]]:
        """
        混合排序

        Args:
            vector_results: 向量检索结果
            keyword_results: 关键词检索结果
            vector_weight: 向量权重

        Returns:
            混合排序后的结果
        """
        # 构建记忆 ID 到分数的映射
        scores = {}

        # 向量相似度分数
        for result in vector_results:
            memory_id = result["id"]
            scores[memory_id] = {
                "data": result,
                "vector_score": result["similarity"],
                "keyword_score": 0.0,
            }

        # 关键词分数
        for result in keyword_results:
            memory_id = result["id"]
            if memory_id in scores:
                scores[memory_id]["keyword_score"] = result["similarity"]
            else:
                scores[memory_id] = {
                    "data": result,
                    "vector_score": 0.0,
                    "keyword_score": result["similarity"],
                }

        # 计算混合分数
        keyword_weight = 1 - vector_weight
        results = []

        for memory_id, score_data in scores.items():
            hybrid_score = (
                score_data["vector_score"] * vector_weight
                + score_data["keyword_score"] * keyword_weight
            )

            result = score_data["data"].copy()
            result["similarity"] = hybrid_score
            result["vector_score"] = score_data["vector_score"]
            result["keyword_score"] = score_data["keyword_score"]

            results.append(result)

        # 按混合分数排序
        results.sort(key=lambda x: x["similarity"], reverse=True)

        return results

    async def search_by_time(
        self, start_time: datetime, end_time: datetime, limit: int = 50
    ) -> List[Memory]:
        """
        按时间范围检索记忆

        Args:
            start_time: 开始时间
            end_time: 结束时间
            limit: 返回数量限制

        Returns:
            记忆列表
        """
        rows = await db.fetch(
            """
            SELECT * FROM memories
            WHERE time_value >= $1 AND time_value <= $2
            AND status = 'active'
            ORDER BY time_value DESC
            LIMIT $3
        """,
            start_time,
            end_time,
            limit,
        )

        return [self._row_to_memory(row) for row in rows]

    async def search_by_location(
        self, location_name: str, limit: int = 50
    ) -> List[Memory]:
        """
        按地点检索记忆

        Args:
            location_name: 地点名称
            limit: 返回数量限制

        Returns:
            记忆列表
        """
        rows = await db.fetch(
            """
            SELECT * FROM memories
            WHERE location_name LIKE $1
            AND status = 'active'
            ORDER BY created_at DESC
            LIMIT $2
        """,
            f"%{location_name}%",
            limit,
        )

        return [self._row_to_memory(row) for row in rows]

    async def search_by_person(self, person_name: str, limit: int = 50) -> List[Memory]:
        """
        按人物检索记忆

        Args:
            person_name: 人物名称
            limit: 返回数量限制

        Returns:
            记忆列表
        """
        rows = await db.fetch(
            """
            SELECT * FROM memories
            WHERE people @> $1::jsonb
            AND status = 'active'
            ORDER BY created_at DESC
            LIMIT $2
        """,
            f'[{{"name": "{person_name}"}}]',
            limit,
        )

        return [self._row_to_memory(row) for row in rows]

    async def search_by_tags(self, tags: List[str], limit: int = 50) -> List[Memory]:
        """
        按标签检索记忆

        Args:
            tags: 标签列表
            limit: 返回数量限制

        Returns:
            记忆列表
        """
        rows = await db.fetch(
            """
            SELECT * FROM memories
            WHERE tags && $1
            AND status = 'active'
            ORDER BY created_at DESC
            LIMIT $2
        """,
            tags,
            limit,
        )

        return [self._row_to_memory(row) for row in rows]

    async def get_recent(self, days: int = 7, limit: int = 50) -> List[Memory]:
        """
        获取最近的记忆

        Args:
            days: 最近多少天
            limit: 返回数量限制

        Returns:
            记忆列表
        """
        start_time = datetime.now() - timedelta(days=days)

        rows = await db.fetch(
            """
            SELECT * FROM memories
            WHERE created_at >= $1
            AND status = 'active'
            ORDER BY created_at DESC
            LIMIT $2
        """,
            start_time,
            limit,
        )

        return [self._row_to_memory(row) for row in rows]

    def _row_to_memory(self, row: Dict[str, Any]) -> Memory:
        """将数据库行转换为 Memory 对象"""
        from ..models.memory import (
            TimeInfo,
            LocationInfo,
            PersonInfo,
            EmotionInfo,
            DurationInfo,
            TopicInfo,
            Attachment,
        )

        # 解析 JSON 字段
        import json

        # 处理 embedding 字段（从字符串转换为列表）
        embedding_data = row.get("embedding")
        if embedding_data and isinstance(embedding_data, str):
            # 解析向量字符串 "[0.1,0.2,...]" 为列表
            embedding_data = json.loads(embedding_data)

        people_data = row.get("people")
        people = None
        if people_data:
            if isinstance(people_data, str):
                people_data = json.loads(people_data)
            people = [PersonInfo(**p) for p in people_data]

        emotion_data = row.get("emotion")
        emotion = None
        if emotion_data:
            if isinstance(emotion_data, str):
                emotion_data = json.loads(emotion_data)
            emotion = EmotionInfo(**emotion_data)

        tags_data = row.get("tags")
        tags = None
        if tags_data:
            if isinstance(tags_data, str):
                tags_data = json.loads(tags_data)
            tags = tags_data

        duration_data = row.get("duration")
        duration = None
        if duration_data:
            if isinstance(duration_data, str):
                duration_data = json.loads(duration_data)
            duration = DurationInfo(**duration_data)

        topic_data = row.get("topic")
        topic = None
        if topic_data:
            if isinstance(topic_data, str):
                topic_data = json.loads(topic_data)
            topic = TopicInfo(**topic_data)

        attachments_data = row.get("attachments")
        attachments = None
        if attachments_data:
            if isinstance(attachments_data, str):
                attachments_data = json.loads(attachments_data)
            attachments = [Attachment(**a) for a in attachments_data]

        # 构建时间信息
        time_info = None
        if row.get("time_value"):
            time_info = TimeInfo(
                value=row["time_value"],
                period=row.get("time_period"),
                source=row.get("time_source"),
                confidence=row.get("time_confidence"),
            )

        # 构建位置信息
        location_info = None
        if row.get("location_name"):
            location_info = LocationInfo(
                name=row["location_name"],
                address=row.get("location_address"),
                latitude=row.get("location_latitude"),
                longitude=row.get("location_longitude"),
                need_confirm=row.get("location_need_confirm", False),
            )

        return Memory(
            id=row["id"],
            content=row["content"],
            input_type=row["input_type"],
            created_at=row["created_at"],
            updated_at=row.get("updated_at"),
            time=time_info,
            location=location_info,
            people=people,
            emotion=emotion,
            tags=tags,
            duration=duration,
            topic=topic,
            attachments=attachments,
            embedding=embedding_data,
            access_count=row.get("access_count", 0),
            last_accessed_at=row.get("last_accessed_at"),
            importance_score=row.get("importance_score", 0.5),
            status=row.get("status", "active"),
        )


# 全局召回服务实例
recall_service: Optional[RecallService] = None


def get_recall_service() -> RecallService:
    """获取召回服务实例"""
    global recall_service
    if recall_service is None:
        recall_service = RecallService()
    return recall_service
