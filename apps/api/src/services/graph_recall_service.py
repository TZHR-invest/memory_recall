"""
图谱增强召回服务

参考 Mem0 的设计：
1. 向量搜索实体
2. 图谱遍历关系
3. BM25 重排序
4. 返回关系三元组 + 记忆内容
"""

from typing import List, Dict, Optional, Any
from ..database import db
from .graph_tools import EXTRACT_ENTITIES_TOOL, RELATION_TYPES
from .prompts import ENTITY_EXTRACTION_PROMPT
from .llm_recall_service import get_llm_recall_service
from .embedding_cache import get_embedding_cache
from .entity_dictionary_service import get_entity_dictionary_service
from .jieba_service import extract_keywords
from rank_bm25 import BM25Okapi
import asyncio
import logging
import time

logger = logging.getLogger(__name__)


class GraphEnhancedRecallService:
    """图谱增强召回服务"""
    
    def __init__(self):
        self.llm_service = get_llm_recall_service()
        self.embedding_cache = get_embedding_cache()
        self.entity_dict = get_entity_dictionary_service()
    
    async def search_by_entity(
        self,
        entity_name: str,
        user_id: str,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        实体扩展召回
        
        通过实体名称搜索相关记忆
        
        Args:
            entity_name: 实体名称（如"张三"）
            user_id: 用户 ID
            limit: 返回数量
        
        Returns:
            记忆列表，包含记忆内容和相似度
        """
        
        # 设置当前用户 schema
        db.set_current_user(user_id)
        
        try:
            # 直接通过实体名称查询相关记忆（避免多个同名实体的问题）
            memories = await db.fetch(
                """
                SELECT DISTINCT
                    m.id,
                    m.content,
                    m.created_at,
                    m.location_name,
                    m.people,
                    m.emotion,
                    m.tags,
                    me.mention_context
                FROM memories m
                JOIN memory_entities me ON m.id::uuid = me.memory_id
                JOIN entities e ON me.entity_id = e.id
                WHERE e.name = $1
                AND e.user_id = $2
                AND m.status = 'active'
                ORDER BY m.created_at DESC
                LIMIT $3
                """,
                entity_name, user_id, limit
            )
            
            return [
                {
                    "memory_id": str(m["id"]),
                    "content": m["content"],
                    "created_at": m["created_at"].isoformat() if m["created_at"] else None,
                    "location": m["location_name"],
                    "people": m["people"],
                    "entity": {
                        "name": entity_name,
                        "type": None,
                        "confidence": None
                    },
                    "mention_context": m["mention_context"]
                }
                for m in memories
            ]
        
        except Exception as e:
            logger.error(f"实体扩展召回失败: {e}")
            return []
    
    async def search_by_relation(
        self,
        relation_type: str,
        user_id: str,
        entity_name: Optional[str] = None,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        关系扩展召回
        
        通过关系类型搜索相关记忆
        
        Args:
            relation_type: 关系类型（如"friend"）
            user_id: 用户 ID
            entity_name: 可选的实体名称过滤
            limit: 返回数量
        
        Returns:
            记忆列表
        """
        
        # 设置当前用户 schema
        db.set_current_user(user_id)
        
        try:
            # 1. 查找关系
            if entity_name:
                # 查找特定实体的关系
                relations = await db.fetch(
                    """
                    SELECT 
                        e1.name AS source,
                        r.relation_type,
                        e2.name AS destination,
                        r.weight,
                        r.confidence
                    FROM relations r
                    JOIN entities e1 ON r.from_entity_id = e1.id
                    JOIN entities e2 ON r.to_entity_id = e2.id
                    WHERE r.relation_type = $1
                    AND r.user_id = $2
                    AND (e1.name = $3 OR e2.name = $3)
                    ORDER BY r.weight DESC
                    """,
                    relation_type, user_id, entity_name
                )
            else:
                # 查找所有该类型的关系
                relations = await db.fetch(
                    """
                    SELECT 
                        e1.name AS source,
                        r.relation_type,
                        e2.name AS destination,
                        r.weight,
                        r.confidence
                    FROM relations r
                    JOIN entities e1 ON r.from_entity_id = e1.id
                    JOIN entities e2 ON r.to_entity_id = e2.id
                    WHERE r.relation_type = $1
                    AND r.user_id = $2
                    ORDER BY r.weight DESC
                    LIMIT $3
                    """,
                    relation_type, user_id, limit * 2
                )
            
            if not relations:
                logger.info(f"关系未找到: {relation_type}")
                return []
            
            # 2. 获取相关实体 ID
            entity_names = set()
            for r in relations:
                entity_names.add(r["source"])
                entity_names.add(r["destination"])
            
            # 3. 获取这些实体的记忆
            # 注意：memories 表没有 user_id 字段，通过 entities 表过滤用户
            memories = await db.fetch(
                """
                SELECT DISTINCT
                    m.id,
                    m.content,
                    m.created_at,
                    m.location_name,
                    m.people,
                    array_agg(e.name) AS entities
                FROM memories m
                JOIN memory_entities me ON m.id = me.memory_id
                JOIN entities e ON me.entity_id = e.id
                WHERE e.name = ANY($1)
                AND e.user_id = $2
                AND m.status = 'active'
                GROUP BY m.id, m.content, m.created_at, m.location_name, m.people
                ORDER BY m.created_at DESC
                LIMIT $3
                """,
                list(entity_names), user_id, limit
            )
            
            return [
                {
                    "memory_id": str(m["id"]),
                    "content": m["content"],
                    "created_at": m["created_at"].isoformat() if m["created_at"] else None,
                    "location": m["location_name"],
                    "people": m["people"],
                    "entities": m["entities"],
                    "relations": [
                        {
                            "source": r["source"],
                            "relationship": r["relation_type"],
                            "destination": r["destination"]
                        }
                        for r in relations
                        if r["source"] in m["entities"] or r["destination"] in m["entities"]
                    ]
                }
                for m in memories
            ]
        
        except Exception as e:
            logger.error(f"关系扩展召回失败: {e}")
            return []
    
    async def search_graph(
        self,
        query: str,
        user_id: str,
        limit: int = 10,
        time_range: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        图谱搜索（Mem0 方式 + 归一化关系扩展）
        
        流程：
        1. 提取查询中的实体
        2. 向量相似度搜索实体
        3. **归一化关系扩展**（新增）
        4. 获取实体的关系
        5. BM25 重排序
        6. 返回关系三元组 + 记忆内容
        
        Args:
            query: 查询文本（如"张三的朋友"）
            user_id: 用户 ID
            limit: 返回数量
            time_range: 时间范围过滤
        
        Returns:
            {
                "relations": [关系三元组],
                "memories": [相关记忆]
            }
        """
        
        # 设置当前用户 schema
        db.set_current_user(user_id)
        
        try:
            # 1. 提取实体（使用词典匹配）
            entities = await self._extract_entities_from_query(query, user_id, use_dict=True)
            
            if not entities:
                logger.info(f"查询中未提取到实体: {query}")
                return {"relations": [], "memories": []}
            
            # 2. 向量搜索实体
            entity_results = await self._search_entities_by_name(entities, user_id)
            
            if not entity_results:
                return {"relations": [], "memories": []}
            
            # 3. **归一化关系扩展**（新增）
            expanded_entity_names = await self._expand_entities_by_normalization(
                [e["name"] for e in entity_results],
                user_id
            )
            
            # 更新实体列表
            if len(expanded_entity_names) > len(entities):
                logger.info(f"归一化扩展: {entities} → {expanded_entity_names}")
                entity_results = await self._search_entities_by_name(
                    expanded_entity_names, user_id
                )
            
            # 4. 获取关系
            relations = await self._get_entity_relations(
                [e["id"] for e in entity_results],
                user_id
            )
            
            if not relations:
                return {"relations": [], "memories": []}
            
            # 5. BM25 重排序
            reranked_relations = self._bm25_rerank(query, relations)
            
            # 6. 获取相关记忆（带时间过滤）
            entity_names = set()
            for r in reranked_relations:
                entity_names.add(r["source"])
                entity_names.add(r["destination"])
            
            memories = await self._get_memories_by_entities(list(entity_names), user_id, limit, time_range)
            
            return {
                "relations": reranked_relations[:limit],
                "memories": memories
            }
        
        except Exception as e:
            logger.error(f"图谱搜索失败: {e}")
            return {"relations": [], "memories": []}
    
    async def hybrid_recall(
        self,
        query: str,
        user_id: str,
        limit: int = 10,
        weights: Optional[Dict[str, float]] = None,
        time_range: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        混合召回（向量 + 关键词 + 图谱）
        
        Args:
            query: 查询文本
            user_id: 用户 ID
            limit: 返回数量
            weights: 权重配置
            time_range: 时间范围过滤
        
        Returns:
            排序后的记忆列表
        """
        
        # 设置当前用户 schema
        db.set_current_user(user_id)
        
        if weights is None:
            weights = {
                "vector": 0.5,
                "keyword": 0.3,
                "graph": 0.2
            }
        
        try:
            # 并发执行三路召回
            tasks = [
                self._vector_recall(query, user_id, limit * 2, time_range),
                self._keyword_recall(query, user_id, limit * 2, time_range),
                self._graph_recall(query, user_id, limit * 2, time_range)
            ]
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            vector_results = results[0] if not isinstance(results[0], Exception) else []
            keyword_results = results[1] if not isinstance(results[1], Exception) else []
            graph_results = results[2] if not isinstance(results[2], Exception) else []
            
            # 合并和排序
            merged = self._merge_and_rank(
                vector_results,
                keyword_results,
                graph_results,
                weights
            )
            
            return merged[:limit]
        
        except Exception as e:
            logger.error(f"混合召回失败: {e}")
            return []
    
    # ============ 私有方法 ============
    
    async def _extract_entities_from_query(
        self,
        query: str,
        user_id: Optional[str] = None,
        use_dict: bool = True
    ) -> List[str]:
        """
        从查询中提取实体（词典匹配版）
        
        Args:
            query: 查询文本
            user_id: 用户 ID（用于过滤实体）
            use_dict: 是否使用词典匹配（默认 True，False 则回退到 LLM）
        
        Returns:
            实体名称列表
        """
        
        if use_dict:
            # 使用词典匹配（毫秒级）
            try:
                start_time = time.time()
                
                # 初始化词典（首次调用时）
                if not self.entity_dict._initialized:
                    await self.entity_dict.initialize()
                
                # 快速匹配
                entities = self.entity_dict.extract_entities_fast(query, user_id)
                
                elapsed_ms = (time.time() - start_time) * 1000
                logger.info(f"词典实体提取耗时: {elapsed_ms:.2f}ms, 提取到 {len(entities)} 个实体")
                
                return entities
            
            except Exception as e:
                logger.error(f"词典实体提取失败，回退到 LLM: {e}")
                # 降级到 LLM
                return await self._extract_entities_with_llm(query)
        else:
            # 使用 LLM（1-3 秒）
            return await self._extract_entities_with_llm(query)
    
    async def _extract_entities_with_llm(self, query: str) -> List[str]:
        """使用 LLM 提取实体（降级方案）"""
        
        try:
            response = await self.llm_service.call_with_tools(
                system_prompt="从查询中提取实体名称。",
                user_prompt=query,
                tools=[EXTRACT_ENTITIES_TOOL]
            )
            
            if response.get("tool_calls"):
                entities = response["tool_calls"][0]["function"]["arguments"]["entities"]
                return [e["entity"] for e in entities]
            
            return []
        
        except Exception as e:
            logger.error(f"LLM 提取实体失败: {e}")
            return []
    
    async def _search_entities_by_name(
        self,
        entity_names: List[str],
        user_id: str
    ) -> List[Dict]:
        """通过名称搜索实体（暂不使用向量，直接名称匹配）"""
        
        try:
            entities = await db.fetch(
                """
                SELECT id, name, type, confidence
                FROM entities
                WHERE name = ANY($1)
                AND user_id = $2
                """,
                entity_names, user_id
            )
            
            return [
                {
                    "id": str(e["id"]),
                    "name": e["name"],
                    "type": e["type"],
                    "confidence": e["confidence"]
                }
                for e in entities
            ]
        
        except Exception as e:
            logger.error(f"搜索实体失败: {e}")
            return []
    
    async def _get_entity_relations(
        self,
        entity_ids: List[str],
        user_id: str
    ) -> List[Dict]:
        """获取实体的所有关系（包括归一化关系）"""
        
        try:
            # 查询用户关系 + 系统归一化关系
            relations = await db.fetch(
                """
                SELECT 
                    e1.name AS source,
                    r.relation_type AS relationship,
                    e2.name AS destination,
                    r.weight,
                    r.confidence
                FROM relations r
                JOIN entities e1 ON r.from_entity_id = e1.id
                JOIN entities e2 ON r.to_entity_id = e2.id
                WHERE (r.user_id = $1 OR r.user_id = 'system')
                AND (r.from_entity_id = ANY($2) OR r.to_entity_id = ANY($2))
                ORDER BY r.weight DESC
                """,
                user_id, entity_ids
            )
            
            return [
                {
                    "source": r["source"],
                    "relationship": r["relationship"],
                    "destination": r["destination"],
                    "weight": r["weight"],
                    "confidence": r["confidence"]
                }
                for r in relations
            ]
        
        except Exception as e:
            logger.error(f"获取关系失败: {e}")
            return []
    
    async def _expand_entities_by_normalization(
        self,
        entity_names: List[str],
        user_id: str
    ) -> List[str]:
        """
        通过归一化关系扩展实体
        
        Args:
            entity_names: 原始实体名称列表
            user_id: 用户 ID
        
        Returns:
            扩展后的实体名称列表（包含归一化关系）
        """
        try:
            expanded = list(entity_names)
            
            # 查询归一化关系（same_as, is_a）
            for entity_name in entity_names:
                # 查询实体 ID
                entity_id = await db.fetchval(
                    """
                    SELECT id FROM entities 
                    WHERE name = $1 AND (user_id = $2 OR user_id = 'system')
                    """,
                    entity_name, user_id
                )
                
                if entity_id:
                    # 查询归一化关系
                    related = await db.fetch(
                        """
                        SELECT e.name
                        FROM relations r
                        JOIN entities e ON e.id = r.to_entity_id OR e.id = r.from_entity_id
                        WHERE (r.from_entity_id = $1 OR r.to_entity_id = $1)
                        AND r.relation_type IN ('same_as', 'is_a')
                        AND (r.user_id = $2 OR r.user_id = 'system')
                        """,
                        str(entity_id), user_id
                    )
                    
                    expanded.extend([r["name"] for r in related])
            
            # 去重
            return list(set(expanded))
            
        except Exception as e:
            logger.error(f"归一化关系扩展失败: {e}")
            return entity_names
    
    def _bm25_rerank(
        self,
        query: str,
        relations: List[Dict]
    ) -> List[Dict]:
        """
        BM25 重排序（支持中文分词 + 关系类型中英文匹配）
        
        改进点：
        1. 使用 jieba 分词提取查询关键词，避免 query.split() 无法分隔中文的问题
        2. 将英文关系类型转换成中文，以更好地匹配中文查询
        
        Args:
            query: 查询文本（如"张三的朋友"）
            relations: 关系列表
        
        Returns:
            重排序后的关系列表
        """
        
        if not relations:
            return []
        
        try:
            # 构建文档列表（将英文关系类型转换成中文）
            documents = []
            for r in relations:
                # 将英文关系类型转换成中文（如果存在映射）
                relationship_cn = RELATION_TYPES.get(r["relationship"], r["relationship"])
                documents.append([r["source"], relationship_cn, r["destination"]])
            
            # 使用 Jieba 分词提取关键词（修复中文分词问题）
            tokenized_query = extract_keywords(query, min_length=1)
            
            logger.info(f"BM25 查询分词: '{query}' -> {tokenized_query}")
            logger.info(f"BM25 文档列表（中文关系）: {documents[:3]}...")  # 只打印前3个
            
            # BM25 排序
            bm25 = BM25Okapi(documents)
            top_indices = bm25.get_top_n(tokenized_query, list(range(len(documents))), n=len(documents))
            
            # 返回重排序后的关系
            reranked = [relations[i] for i in top_indices]
            
            logger.info(f"BM25 重排序完成: {len(reranked)} 条关系")
            
            return reranked
        
        except Exception as e:
            logger.error(f"BM25 重排序失败: {e}")
            return relations
    
    async def _get_memories_by_entities(
        self,
        entity_names: List[str],
        user_id: str,
        limit: int,
        time_range: Optional[Dict[str, Any]] = None
    ) -> List[Dict]:
        """
        通过实体获取记忆（按关系权重排序）
        
        排序逻辑：
        1. 关系权重（降序）- 包含高权重关系的记忆排前面
        2. 创建时间（降序）- 权重相同时，最新记忆排前面
        
        Args:
            entity_names: 实体名称列表
            user_id: 用户 ID
            limit: 返回数量
            time_range: 时间范围过滤
        """
        
        try:
            # 构建基础 SQL
            sql = """
                SELECT DISTINCT
                    m.id,
                    m.content,
                    m.created_at,
                    m.time_value,
                    m.location_name,
                    m.people,
                    MAX(r.weight) as max_relation_weight
                FROM memories m
                JOIN memory_entities me ON m.id = me.memory_id
                JOIN entities e ON me.entity_id = e.id
                LEFT JOIN relations r ON (
                    (r.from_entity_id = e.id OR r.to_entity_id = e.id)
                    AND (r.user_id = $2 OR r.user_id = 'system')
                )
                WHERE e.name = ANY($1)
                AND e.user_id = $2
                AND m.status = 'active'
            """
            
            params = [entity_names, user_id]
            param_count = 2
            
            # 添加时间过滤
            if time_range:
                if time_range.get("start_time"):
                    param_count += 1
                    sql += f" AND m.time_value >= ${param_count}"
                    params.append(time_range["start_time"])
                if time_range.get("end_time"):
                    param_count += 1
                    sql += f" AND m.time_value <= ${param_count}"
                    params.append(time_range["end_time"])
            
            sql += """
                GROUP BY m.id
                ORDER BY 
                    max_relation_weight DESC NULLS LAST,
                    m.created_at DESC
                LIMIT $""" + str(param_count + 1)
            
            params.append(limit)
            
            memories = await db.fetch(sql, *params)
            
            return [
                {
                    "memory_id": str(m["id"]),
                    "content": m["content"],
                    "created_at": m["created_at"].isoformat() if m["created_at"] else None,
                    "location": m["location_name"],
                    "people": m["people"],
                    "max_relation_weight": m["max_relation_weight"]
                }
                for m in memories
            ]
        
        except Exception as e:
            logger.error(f"获取记忆失败: {e}")
            return []
    
    async def _vector_recall(self, query: str, user_id: str, limit: int, time_range: Optional[Dict[str, Any]] = None) -> List[Dict]:
        """向量召回（调用现有 RecallService）"""
        try:
            from .recall_service import get_recall_service
            
            recall_service = get_recall_service()
            
            # 调用向量搜索
            query_embedding = recall_service.embedding_client.embed(query)
            if not query_embedding:
                logger.warning(f"生成查询向量失败: {query}")
                return []
            
            # 执行向量搜索（传递时间过滤）
            results = await recall_service._vector_search(
                query_embedding,
                limit,
                time_range=time_range,  # ✅ 传递时间过滤
                location_filter=None,
                person_filter=None,
                tag_filter=None
            )
            
            # 转换格式以匹配混合召回接口
            return [
                {
                    "memory_id": str(r["id"]),
                    "content": r["content"],
                    "created_at": r["created_at"].isoformat() if r.get("created_at") else None,
                    "location": r.get("location_name"),
                    "people": r.get("people"),
                    "similarity": r.get("similarity", 0.0),
                    "recall_type": "vector"
                }
                for r in results
            ]
        
        except Exception as e:
            logger.error(f"向量召回失败: {e}")
            return []
    
    async def _keyword_recall(self, query: str, user_id: str, limit: int, time_range: Optional[Dict[str, Any]] = None) -> List[Dict]:
        """关键词召回（调用现有 RecallService）"""
        try:
            from .recall_service import get_recall_service
            
            recall_service = get_recall_service()
            
            # 执行关键词搜索（传递时间过滤）
            results = await recall_service._keyword_search(
                query,
                limit,
                time_range=time_range,  # ✅ 传递时间过滤
                location_filter=None,
                person_filter=None,
                tag_filter=None,
                keywords=None  # 让 recall_service 自己提取关键词
            )
            
            # 转换格式以匹配混合召回接口
            return [
                {
                    "memory_id": str(r["id"]),
                    "content": r["content"],
                    "created_at": r["created_at"].isoformat() if r.get("created_at") else None,
                    "location": r.get("location_name"),
                    "people": r.get("people"),
                    "similarity": r.get("similarity", 0.0),
                    "recall_type": "keyword"
                }
                for r in results
            ]
        
        except Exception as e:
            logger.error(f"关键词召回失败: {e}")
            return []
    
    async def _graph_recall(self, query: str, user_id: str, limit: int, time_range: Optional[Dict[str, Any]] = None) -> List[Dict]:
        """图谱召回（带时间过滤）"""
        result = await self.search_graph(query, user_id, limit, time_range)
        return result.get("memories", [])
    
    def _merge_and_rank(
        self,
        vector_results: List[Dict],
        keyword_results: List[Dict],
        graph_results: List[Dict],
        weights: Dict[str, float]
    ) -> List[Dict]:
        """合并和排序"""
        
        memory_scores = {}
        memory_data = {}
        
        # 向量结果
        for i, item in enumerate(vector_results):
            memory_id = item.get("memory_id")
            if not memory_id:
                continue
            score = (len(vector_results) - i) / max(len(vector_results), 1) * weights["vector"]
            memory_scores[memory_id] = memory_scores.get(memory_id, 0) + score
            memory_data[memory_id] = item
        
        # 关键词结果
        for i, item in enumerate(keyword_results):
            memory_id = item.get("memory_id")
            if not memory_id:
                continue
            score = (len(keyword_results) - i) / max(len(keyword_results), 1) * weights["keyword"]
            memory_scores[memory_id] = memory_scores.get(memory_id, 0) + score
            memory_data[memory_id] = item
        
        # 图谱结果
        for i, item in enumerate(graph_results):
            memory_id = item.get("memory_id")
            if not memory_id:
                continue
            score = (len(graph_results) - i) / max(len(graph_results), 1) * weights["graph"]
            memory_scores[memory_id] = memory_scores.get(memory_id, 0) + score
            memory_data[memory_id] = item
        
        # 排序
        sorted_ids = sorted(memory_scores.keys(), key=lambda x: memory_scores[x], reverse=True)
        
        # 返回结果
        return [memory_data[mid] for mid in sorted_ids]


# 全局服务实例
graph_recall_service: Optional[GraphEnhancedRecallService] = None


def get_graph_recall_service() -> GraphEnhancedRecallService:
    """获取图谱召回服务实例"""
    global graph_recall_service
    if graph_recall_service is None:
        graph_recall_service = GraphEnhancedRecallService()
    return graph_recall_service
