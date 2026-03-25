"""
智能召回路由服务
通过 Function Calling 让 LLM 自动选择最佳召回策略
"""

from typing import List, Dict, Any, Optional
from datetime import datetime
import json
import logging
from ..llm.client import get_llm_client
from ..database import db

logger = logging.getLogger(__name__)


# ==================== Function Calling 工具定义 ====================

VECTOR_RECALL_TOOL = {
    "type": "function",
    "function": {
        "name": "vector_recall",
        "description": "使用向量相似度召回记忆。适合语义化查询，如'关于项目讨论的记忆'、'开心的事情'、'有意义的对话'。优点：能理解语义相似性，召回概念相关的记忆。",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "查询文本（可以是原始查询或语义改写）",
                },
                "limit": {
                    "type": "integer",
                    "description": "返回数量，默认10",
                    "default": 10,
                },
                "min_similarity": {
                    "type": "number",
                    "description": "最小相似度阈值（0-1），默认0.1",
                    "default": 0.1,
                },
                "reason": {"type": "string", "description": "选择此召回方式的原因"},
            },
            "required": ["query", "reason"],
        },
    },
}

KEYWORD_RECALL_TOOL = {
    "type": "function",
    "function": {
        "name": "keyword_recall",
        "description": "使用关键词匹配召回记忆。适合明确关键词的查询，如'咖啡店'、'张三'、'项目X'。优点：精确匹配，召回率高。",
        "parameters": {
            "type": "object",
            "properties": {
                "keywords": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "关键词列表（从查询中提取）",
                },
                "limit": {
                    "type": "integer",
                    "description": "返回数量，默认10",
                    "default": 10,
                },
                "reason": {"type": "string", "description": "选择此召回方式的原因"},
            },
            "required": ["keywords", "reason"],
        },
    },
}

GRAPH_RECALL_TOOL = {
    "type": "function",
    "function": {
        "name": "graph_recall",
        "description": "使用知识图谱召回记忆。适合实体关系查询，如'张三的朋友'、'在咖啡店见的人'、'参与项目的人'。优点：利用实体关系网络，召回关联性强的记忆。",
        "parameters": {
            "type": "object",
            "properties": {
                "entity_name": {
                    "type": "string",
                    "description": "实体名称（如'张三'、'咖啡店'）",
                },
                "relation_type": {
                    "type": "string",
                    "description": "关系类型（可选），如'friend'、'colleague'、'met_at'",
                    "default": None,
                },
                "limit": {
                    "type": "integer",
                    "description": "返回数量，默认10",
                    "default": 10,
                },
                "reason": {"type": "string", "description": "选择此召回方式的原因"},
            },
            "required": ["entity_name", "reason"],
        },
    },
}

TIME_RECALL_TOOL = {
    "type": "function",
    "function": {
        "name": "time_recall",
        "description": "使用时间范围召回记忆。适合时间明确的查询，如'上周'、'最近3天'、'2024年1月'。优点：精确的时间过滤，快速定位记忆。",
        "parameters": {
            "type": "object",
            "properties": {
                "start_date": {
                    "type": "string",
                    "description": "开始日期（YYYY-MM-DD格式）",
                },
                "end_date": {
                    "type": "string",
                    "description": "结束日期（YYYY-MM-DD格式）",
                },
                "limit": {
                    "type": "integer",
                    "description": "返回数量，默认20",
                    "default": 20,
                },
                "reason": {"type": "string", "description": "选择此召回方式的原因"},
            },
            "required": ["start_date", "end_date", "reason"],
        },
    },
}

HYBRID_RECALL_TOOL = {
    "type": "function",
    "function": {
        "name": "hybrid_recall",
        "description": "混合召回策略（推荐）。结合向量、关键词、图谱三种方式，通过加权融合获得最佳召回效果。适合大多数查询场景，特别是复杂查询。",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "原始查询文本"},
                "time_keywords": {
                    "type": "string",
                    "description": "时间关键词（可选），如'最近一周'、'上周'",
                    "default": None,
                },
                "location_filter": {
                    "type": "string",
                    "description": "地点过滤（可选）",
                    "default": None,
                },
                "person_filter": {
                    "type": "string",
                    "description": "人物过滤（可选）",
                    "default": None,
                },
                "limit": {
                    "type": "integer",
                    "description": "返回数量，默认10",
                    "default": 10,
                },
                "weights": {
                    "type": "object",
                    "properties": {
                        "vector": {
                            "type": "number",
                            "description": "向量权重，默认0.5",
                        },
                        "keyword": {
                            "type": "number",
                            "description": "关键词权重，默认0.3",
                        },
                        "graph": {"type": "number", "description": "图谱权重，默认0.2"},
                    },
                    "description": "召回权重配置（可选）",
                    "default": {"vector": 0.5, "keyword": 0.3, "graph": 0.2},
                },
                "reason": {"type": "string", "description": "选择此召回方式的原因"},
            },
            "required": ["query", "reason"],
        },
    },
}

ALL_RECALL_TOOLS = [
    VECTOR_RECALL_TOOL,
    KEYWORD_RECALL_TOOL,
    GRAPH_RECALL_TOOL,
    TIME_RECALL_TOOL,
    HYBRID_RECALL_TOOL,
]


# ==================== 智能召回服务 ====================


class SmartRecallService:
    """智能召回路由服务"""

    def __init__(self):
        self.llm_client = get_llm_client()

    async def smart_recall(
        self, query: str, user_id: str, limit: int = 10, detail_level: str = "medium"
    ) -> Dict[str, Any]:
        """
        智能召回：让 LLM 自动选择召回策略

        Args:
            query: 用户查询
            user_id: 用户 ID
            limit: 返回数量
            detail_level: 详情级别

        Returns:
            召回结果和路由决策信息
        """
        db.set_current_user(user_id)

        # 1. 调用 LLM 选择召回策略
        route_decision = await self._select_recall_strategy(query)

        logger.info(f"[Smart Recall] 查询: {query}")
        logger.info(f"[Smart Recall] 决策: {route_decision['strategy']}")
        logger.info(f"[Smart Recall] 原因: {route_decision['reason']}")

        # 2. 执行召回
        if route_decision["strategy"] == "vector_recall":
            memories = await self._execute_vector_recall(
                route_decision["params"], user_id, limit
            )
        elif route_decision["strategy"] == "keyword_recall":
            memories = await self._execute_keyword_recall(
                route_decision["params"], user_id, limit
            )
        elif route_decision["strategy"] == "graph_recall":
            memories = await self._execute_graph_recall(
                route_decision["params"],
                user_id,
                limit,
                query,  # ⭐ 传入原始查询
            )
        elif route_decision["strategy"] == "time_recall":
            memories = await self._execute_time_recall(
                route_decision["params"], user_id, limit
            )
        elif route_decision["strategy"] == "hybrid_recall":
            memories = await self._execute_hybrid_recall(
                route_decision["params"], user_id, limit
            )
        else:
            # 降级：使用混合召回
            logger.warning(f"未知策略: {route_decision['strategy']}，降级到混合召回")
            memories = await self._execute_hybrid_recall(
                {"query": query, "limit": limit}, user_id, limit
            )

        # 3. 生成回答
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
                "strategy": route_decision["strategy"],
                "reason": route_decision["reason"],
                "params": route_decision["params"],
                "fallback_used": len(memories) > 0
                and route_decision["strategy"] == "graph_recall",
            },
        }

    async def _select_recall_strategy(self, query: str) -> Dict[str, Any]:
        """
        选择召回策略（基于规则，无需 LLM）

        Returns:
            {
                "strategy": "vector_recall" | "keyword_recall" | ...,
                "reason": "选择原因",
                "params": {...}
            }
        """
        # 使用规则快速判断（无需 LLM 调用）
        query_lower = query.lower()
        
        # 时间关键词
        time_keywords = ["昨天", "前天", "上周", "上周", "本月", "最近", "今天", "明天", "后天"]
        has_time = any(kw in query for kw in time_keywords)
        
        # 实体关系关键词
        relation_patterns = ["的朋友", "的同事", "的同学", "的家人", "认识", "关系"]
        has_relation = any(pattern in query for pattern in relation_patterns)
        
        # 明确关键词（人名、地点等）
        from .jieba_service import extract_keywords, extract_person, extract_location
        keywords = extract_keywords(query)
        person = extract_person(query)
        location = extract_location(query)
        
        # 判断策略
        if has_relation and person:
            # 实体关系查询 → 图谱召回
            return {
                "strategy": "graph_recall",
                "reason": "检测到实体关系查询，使用图谱召回",
                "params": {"entity_name": person, "relation_type": self._extract_relation_type(query)},
            }
        
        if has_time and not has_relation:
            # 时间查询 → 混合召回（带时间过滤）
            return {
                "strategy": "hybrid_recall",
                "reason": "检测到时间关键词，使用混合召回",
                "params": {"query": query, "time_keywords": query},
            }
        
        if person or location:
            # 包含明确实体 → 关键词召回
            return {
                "strategy": "keyword_recall",
                "reason": f"检测到明确关键词：{person or location}，使用关键词召回",
                "params": {"keywords": keywords, "limit": 10},
            }
        
        if len(keywords) <= 2 and keywords:
            # 简短查询 → 关键词召回
            return {
                "strategy": "keyword_recall",
                "reason": "查询简短，使用关键词召回",
                "params": {"keywords": keywords, "limit": 10},
            }
        
        # 默认 → 向量召回（语义匹配）
        return {
            "strategy": "vector_recall",
            "reason": "语义化查询，使用向量召回",
            "params": {"query": query, "min_similarity": 0.1},
        }

    def _extract_relation_type(self, query: str) -> Optional[str]:
        """从查询中提取关系类型"""
        relation_map = {
            "的朋友": "friend",
            "的同事": "colleague",
            "的同学": "classmate",
            "的家人": "family",
        }
        for pattern, rel_type in relation_map.items():
            if pattern in query:
                return rel_type
        return None
        """
        system_prompt = """你是一个智能记忆召回路由助手。

你的任务是根据用户查询，选择最合适的召回策略。

**召回策略说明：**
1. **vector_recall**：向量相似度召回
   - 适合：语义化查询，如"开心的事情"、"关于项目的记忆"
   - 优点：理解语义相似性

2. **keyword_recall**：关键词召回
   - 适合：明确关键词，如"咖啡店"、"张三"
   - 优点：精确匹配，召回率高

3. **graph_recall**：图谱召回
   - 适合：实体关系查询，如"张三的朋友"、"在咖啡店见的人"
   - 优点：利用关系网络

4. **time_recall**：时间召回
   - 适合：时间明确的查询，如"上周"、"最近3天"
   - 优点：精确时间过滤

5. **hybrid_recall**：混合召回（推荐）
   - 适合：复杂查询、不确定查询意图
   - 优点：综合多种方式，效果最佳

**选择原则：**
- 时间明确的查询 → time_recall
- 明确关键词 → keyword_recall
- 实体关系查询 → graph_recall
- 语义化查询 → vector_recall
- 复杂/不确定查询 → hybrid_recall

请选择最合适的策略并调用对应的函数。"""

        user_prompt = f"用户查询：{query}\n\n请选择最合适的召回策略。"

        try:
            response = await self._call_llm_with_tools(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                tools=ALL_RECALL_TOOLS,
            )

            if response.get("tool_calls"):
                tool_call = response["tool_calls"][0]
                strategy = tool_call["function"]["name"]
                params = tool_call["function"]["arguments"]
                reason = params.pop("reason", "未提供原因")

                return {"strategy": strategy, "reason": reason, "params": params}

            # 如果 LLM 没有调用工具，降级到混合召回
            logger.warning("LLM 未调用工具，降级到混合召回")
            return {
                "strategy": "hybrid_recall",
                "reason": "LLM 未做出决策，使用默认混合召回",
                "params": {"query": query},
            }

        except Exception as e:
            logger.error(f"选择召回策略失败: {e}")
            # 降级到混合召回
            return {
                "strategy": "hybrid_recall",
                "reason": f"决策失败: {str(e)}，使用默认混合召回",
                "params": {"query": query},
            }

    async def _call_llm_with_tools(
        self, system_prompt: str, user_prompt: str, tools: List[Dict]
    ) -> Dict[str, Any]:
        """调用 LLM Function Calling"""
        try:
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ]

            response = self.llm_client.client.chat.completions.create(
                model=self.llm_client.model,
                messages=messages,
                tools=tools,
                tool_choice="auto",
                temperature=0.3,
                max_tokens=1000,
            )

            message = response.choices[0].message

            result = {"content": message.content, "tool_calls": []}

            if message.tool_calls:
                for tool_call in message.tool_calls:
                    try:
                        arguments = json.loads(tool_call.function.arguments)
                    except json.JSONDecodeError:
                        arguments = {}

                    result["tool_calls"].append(
                        {
                            "id": tool_call.id,
                            "type": tool_call.type,
                            "function": {
                                "name": tool_call.function.name,
                                "arguments": arguments,
                            },
                        }
                    )

            return result

        except Exception as e:
            logger.error(f"LLM 调用失败: {e}")
            raise

    # ==================== 执行召回 ====================

    async def _execute_vector_recall(
        self, params: Dict, user_id: str, limit: int
    ) -> List[Dict]:
        """执行向量召回"""
        from .recall_service import get_recall_service

        recall_service = get_recall_service()

        query = params.get("query", "")
        min_similarity = params.get("min_similarity", 0.1)

        results = await recall_service.search(
            query=query,
            limit=params.get("limit", limit),
            min_similarity=min_similarity,
            hybrid_weight=1.0,  # 纯向量
            enable_graph=False,
        )

        # 添加召回类型标记
        for r in results:
            r["recall_type"] = "vector"

        return results

    async def _execute_keyword_recall(
        self, params: Dict, user_id: str, limit: int
    ) -> List[Dict]:
        """执行关键词召回"""
        from .recall_service import get_recall_service

        recall_service = get_recall_service()

        keywords = params.get("keywords", [])

        if not keywords:
            return []

        # 用关键词拼接成查询
        query = " ".join(keywords)

        results = await recall_service.search(
            query=query,
            limit=params.get("limit", limit),
            hybrid_weight=0.0,  # 纯关键词
            enable_graph=False,
            keywords=keywords,
        )

        # 添加召回类型标记
        for r in results:
            r["recall_type"] = "keyword"

        return results

    async def _execute_graph_recall(
        self, params: Dict, user_id: str, limit: int, original_query: str = ""
    ) -> List[Dict]:
        """
        执行图谱召回（带降级机制）

        如果图谱召回失败（无实体或无结果），自动降级到混合召回
        """
        from .graph_recall_service import get_graph_recall_service

        graph_service = get_graph_recall_service()

        entity_name = params.get("entity_name", "")
        relation_type = params.get("relation_type")

        # 执行图谱召回
        try:
            if relation_type:
                # 按关系召回
                results = await graph_service.search_by_relation(
                    relation_type=relation_type,
                    user_id=user_id,
                    entity_name=entity_name,
                    limit=params.get("limit", limit),
                )
            else:
                # 按实体召回
                results = await graph_service.search_by_entity(
                    entity_name=entity_name,
                    user_id=user_id,
                    limit=params.get("limit", limit),
                )

            # 如果图谱召回有结果，直接返回
            if results:
                logger.info(f"图谱召回成功，找到 {len(results)} 条记忆")
                return results

            # ⭐ 图谱召回失败，降级到混合召回
            logger.warning(f"图谱召回未找到结果，降级到混合召回")
            logger.warning(f"  实体: {entity_name}, 关系: {relation_type}")

            # 使用原始查询或实体名称作为查询
            fallback_query = original_query or entity_name or ""

            if not fallback_query:
                logger.warning("无可用查询，返回空结果")
                return []

            # 降级到混合召回
            fallback_results = await self._execute_hybrid_recall(
                {"query": fallback_query, "limit": limit}, user_id, limit
            )

            logger.info(f"混合召回找到 {len(fallback_results)} 条记忆")

            return fallback_results

        except Exception as e:
            logger.error(f"图谱召回失败: {e}")

            # 降级到混合召回
            fallback_query = original_query or entity_name or ""
            if fallback_query:
                logger.warning("图谱召回异常，降级到混合召回")
                return await self._execute_hybrid_recall(
                    {"query": fallback_query, "limit": limit}, user_id, limit
                )

            return []

    async def _execute_time_recall(
        self, params: Dict, user_id: str, limit: int
    ) -> List[Dict]:
        """执行时间召回"""
        from .recall_service import get_recall_service
        from datetime import datetime

        recall_service = get_recall_service()

        start_date_str = params.get("start_date", "")
        end_date_str = params.get("end_date", "")

        try:
            start_time = datetime.fromisoformat(start_date_str)
            end_time = datetime.fromisoformat(end_date_str)
            end_time = end_time.replace(hour=23, minute=59, second=59)
        except Exception as e:
            logger.error(f"解析时间失败: {e}")
            return []

        time_range = {"start_time": start_time, "end_time": end_time}

        results = await recall_service.search(
            query="",  # 纯时间过滤
            limit=params.get("limit", limit),
            time_range=time_range,
            enable_graph=False,
        )

        # 添加召回类型标记
        for r in results:
            r["recall_type"] = "time"

        return results

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
