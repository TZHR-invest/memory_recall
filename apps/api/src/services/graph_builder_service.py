"""
图谱构建服务

借鉴 Mem0 的设计：
1. 使用 Function Calling 提取实体和关系
2. 智能更新逻辑（LLM 判断 ADD/UPDATE/DELETE/NONE）
3. 并发处理
4. 智能确认和软过滤
"""

import asyncio
import json
from typing import List, Dict, Optional, Any
from datetime import datetime
from ..database import db
from .graph_tools import GRAPH_TOOLS, EXTRACT_ENTITIES_TOOL, ESTABLISH_RELATIONS_TOOL
from .prompts import (
    ENTITY_EXTRACTION_PROMPT,
    RELATION_EXTRACTION_PROMPT,
    get_entity_extraction_prompt,
    get_relation_extraction_prompt
)
from .llm_recall_service import get_llm_recall_service
from .confirmation_service import get_confirmation_service
from .soft_filter_service import get_soft_filter_service


class GraphBuilderService:
    """图谱构建服务"""
    
    def __init__(self):
        """初始化服务"""
        self.llm_service = get_llm_recall_service()
        self.confirmation_service = get_confirmation_service()
        self.soft_filter_service = get_soft_filter_service()
    
    async def build_graph(
        self,
        content: str,
        user_id: str,
        memory_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        run_id: Optional[str] = None,
        enable_adaptive: bool = True,  # 废弃参数，保留以兼容旧代码
        enable_confirmation: bool = False
    ) -> Dict[str, Any]:
        """
        构建图谱
        
        流程（修正后）：
        1. 实体提取（Function Calling）
        2. 智能确认判断（新实体/低置信度/冲突）
        3. 关系推理
        4. 存储实体和关系
        
        Args:
            content: 记忆内容
            user_id: 用户 ID
            memory_id: 记忆 ID（可选）
            agent_id: Agent ID（可选）
            run_id: Run ID（可选）
            enable_adaptive: 废弃参数（保留以兼容旧代码）
            enable_confirmation: 是否启用智能确认（默认 False）
        
        Returns:
            构建结果，包含：
            - entities: 提取的实体列表
            - relations: 提取的关系列表
            - entity_count: 实体数量
            - relation_count: 关系数量
            - confirmations: 确认队列（如果启用）
        """
        try:
            # 1. 实体提取
            entities = await self._extract_entities(content)
            
            if not entities:
                return {
                    "entities": [],
                    "relations": [],
                    "entity_count": 0,
                    "relation_count": 0,
                    "status": "no_entities"
                }
            
            # 2. 智能确认
            confirmations = []
            if enable_confirmation:
                # 获取已存在的实体和关系
                existing_entities = await self._get_existing_entities(user_id)
                existing_relations = await self._get_existing_relations(user_id)
                
                # 检查每个实体是否需要确认
                for entity in entities:
                    entity_relations = [
                        r for r in await self._extract_relations(content, [entity])
                    ]
                    
                    confirmation = await self.confirmation_service.should_confirm(
                        entity=entity,
                        relations=entity_relations,
                        existing_entities=existing_entities,
                        existing_relations=existing_relations
                    )
                    
                    if confirmation:
                        # 发送确认请求
                        confirmation_id = await self.confirmation_service.send_confirmation(
                            user_id=user_id,
                            confirmation=confirmation
                        )
                        confirmations.append({
                            "confirmation_id": confirmation_id,
                            **confirmation
                        })
            
            # 3. 关系推理
            relations = await self._extract_relations(content, entities)
            
            # 4. 存储实体
            entity_ids = {}
            for entity in entities:
                entity_id = await self._upsert_entity(
                    name=entity["entity"],
                    entity_type=entity["entity_type"],
                    user_id=user_id,
                    agent_id=agent_id,
                    confidence=entity.get("confidence", 0.8)
                )
                entity_ids[entity["entity"]] = entity_id
                
                # 如果提供了 memory_id，创建记忆-实体关联
                if memory_id and entity_id:
                    await self._create_memory_entity_link(
                        memory_id=memory_id,
                        entity_id=entity_id,
                        mention_context=content
                    )
            
            # 5. 存储关系
            stored_relations = []
            for relation in relations:
                success = await self._upsert_relation(
                    from_entity=relation["source"],
                    to_entity=relation["destination"],
                    relation_type=relation["relationship"],
                    confidence=relation.get("confidence", 0.8),
                    user_id=user_id,
                    agent_id=agent_id
                )
                if success:
                    stored_relations.append(relation)
            
            return {
                "entities": entities,
                "relations": stored_relations,
                "entity_count": len(entities),
                "relation_count": len(stored_relations),
                "confirmations": confirmations if enable_confirmation else None,
                "status": "success"
            }
            
        except Exception as e:
            print(f"构建图谱失败: {e}")
            return {
                "entities": [],
                "relations": [],
                "entity_count": 0,
                "relation_count": 0,
                "confirmations": None,
                "status": "error",
                "error": str(e)
            }
    
    async def _extract_entities(self, content: str) -> List[Dict[str, Any]]:
        """
        提取实体（Function Calling）
        
        Args:
            content: 文本内容
        
        Returns:
            实体列表，每个实体包含：
            - entity: 实体名称
            - entity_type: 实体类型
            - confidence: 置信度（可选）
        """
        try:
            # 调用 LLM Function Calling
            response = await self.llm_service.call_with_tools(
                system_prompt=get_entity_extraction_prompt(),
                user_prompt=f"请从以下文本中提取实体：\n\n{content}",
                tools=[EXTRACT_ENTITIES_TOOL]
            )
            
            # 解析工具调用结果
            if response.get("tool_calls"):
                for tool_call in response["tool_calls"]:
                    if tool_call["function"]["name"] == "extract_entities":
                        entities = tool_call["function"]["arguments"].get("entities", [])
                        # 确保每个实体都有置信度
                        for entity in entities:
                            if "confidence" not in entity:
                                entity["confidence"] = 0.8
                        return entities
            
            # 如果没有工具调用，尝试从 JSON 响应中解析
            if response.get("content"):
                entities = self._parse_entities_from_json(response["content"])
                if entities:
                    return entities
            
            return []
            
        except Exception as e:
            print(f"提取实体失败: {e}")
            # 降级处理：返回空列表
            return []
    
    async def _extract_relations(
        self,
        content: str,
        entities: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        提取关系（Function Calling）
        
        Args:
            content: 文本内容
            entities: 已提取的实体列表
        
        Returns:
            关系列表，每个关系包含：
            - source: 源实体名称
            - destination: 目标实体名称
            - relationship: 关系类型
            - confidence: 置信度（可选）
        """
        try:
            if not entities:
                return []
            
            entity_names = [e["entity"] for e in entities]
            entity_list_str = ", ".join(entity_names)
            
            # 调用 LLM Function Calling
            response = await self.llm_service.call_with_tools(
                system_prompt=get_relation_extraction_prompt(),
                user_prompt=f"实体列表：{entity_list_str}\n\n文本：{content}",
                tools=[ESTABLISH_RELATIONS_TOOL]
            )
            
            # 解析工具调用结果
            if response.get("tool_calls"):
                for tool_call in response["tool_calls"]:
                    if tool_call["function"]["name"] == "establish_relations":
                        relations = tool_call["function"]["arguments"].get("relations", [])
                        # 确保每个关系都有置信度
                        for relation in relations:
                            if "confidence" not in relation:
                                relation["confidence"] = 0.8
                        return relations
            
            # 如果没有工具调用，尝试从 JSON 响应中解析
            if response.get("content"):
                relations = self._parse_relations_from_json(response["content"])
                if relations:
                    return relations
            
            return []
            
        except Exception as e:
            print(f"提取关系失败: {e}")
            # 降级处理：返回空列表
            return []
    

    async def _upsert_entity(
        self,
        name: str,
        entity_type: str,
        user_id: str,
        agent_id: Optional[str] = None,
        confidence: float = 0.8
    ) -> Optional[str]:
        """
        存储或更新实体
        
        Args:
            name: 实体名称
            entity_type: 实体类型
            user_id: 用户 ID
            agent_id: Agent ID
            confidence: 置信度
        
        Returns:
            实体 ID
        """
        try:
            # 检查实体是否存在
            existing = await db.fetchrow(
                """
                SELECT id FROM entities 
                WHERE name = $1 AND type = $2 AND user_id = $3
                """,
                name, entity_type, user_id
            )
            
            if existing:
                # 更新提及次数
                await db.execute(
                    """
                    UPDATE entities 
                    SET mention_count = mention_count + 1,
                        last_mentioned_at = NOW(),
                        confidence = GREATEST(confidence, $1),
                        updated_at = NOW()
                    WHERE id = $2
                    """,
                    confidence, str(existing["id"])
                )
                return str(existing["id"])
            else:
                # 创建新实体
                result = await db.fetchrow(
                    """
                    INSERT INTO entities (name, type, user_id, agent_id, confidence, last_mentioned_at)
                    VALUES ($1, $2, $3, $4, $5, NOW())
                    RETURNING id
                    """,
                    name, entity_type, user_id, agent_id, confidence
                )
                return str(result["id"]) if result else None
                
        except Exception as e:
            print(f"存储实体失败: {e}")
            return None
    
    async def _upsert_relation(
        self,
        from_entity: str,
        to_entity: str,
        relation_type: str,
        confidence: float,
        user_id: str,
        agent_id: Optional[str] = None
    ) -> bool:
        """
        存储或更新关系
        
        Args:
            from_entity: 源实体名称
            to_entity: 目标实体名称
            relation_type: 关系类型
            confidence: 置信度
            user_id: 用户 ID
            agent_id: Agent ID
        
        Returns:
            是否成功
        """
        try:
            # 获取实体 ID
            from_id = await db.fetchval(
                "SELECT id FROM entities WHERE name = $1 AND user_id = $2",
                from_entity, user_id
            )
            to_id = await db.fetchval(
                "SELECT id FROM entities WHERE name = $1 AND user_id = $2",
                to_entity, user_id
            )
            
            if not from_id or not to_id:
                return False
            
            # 检查关系是否存在
            existing = await db.fetchrow(
                """
                SELECT id FROM relations 
                WHERE from_entity_id = $1 AND to_entity_id = $2 AND relation_type = $3
                """,
                str(from_id), str(to_id), relation_type
            )
            
            if existing:
                # 更新权重
                await db.execute(
                    """
                    UPDATE relations 
                    SET weight = LEAST(weight + 0.1, 1.0),
                        confidence = GREATEST(confidence, $1),
                        updated_at = NOW()
                    WHERE id = $2
                    """,
                    confidence, str(existing["id"])
                )
            else:
                # 创建新关系
                await db.execute(
                    """
                    INSERT INTO relations (from_entity_id, to_entity_id, relation_type, weight, confidence, user_id, agent_id)
                    VALUES ($1, $2, $3, $4, $5, $6, $7)
                    """,
                    str(from_id), str(to_id), relation_type, confidence, confidence, user_id, agent_id
                )
            
            return True
            
        except Exception as e:
            print(f"存储关系失败: {e}")
            return False
    
    async def _create_memory_entity_link(
        self,
        memory_id: str,
        entity_id: str,
        mention_context: Optional[str] = None
    ) -> bool:
        """
        创建记忆-实体关联
        
        Args:
            memory_id: 记忆 ID
            entity_id: 实体 ID
            mention_context: 提及上下文
        
        Returns:
            是否成功
        """
        try:
            # 检查是否已存在
            existing = await db.fetchrow(
                """
                SELECT id FROM memory_entities 
                WHERE memory_id = $1 AND entity_id = $2
                """,
                memory_id, entity_id
            )
            
            if not existing:
                await db.execute(
                    """
                    INSERT INTO memory_entities (memory_id, entity_id, mention_context)
                    VALUES ($1, $2, $3)
                    """,
                    memory_id, entity_id, mention_context
                )
            
            return True
            
        except Exception as e:
            print(f"创建记忆-实体关联失败: {e}")
            return False
    
    def _parse_entities_from_json(self, content: str) -> List[Dict[str, Any]]:
        """
        从 JSON 内容中解析实体
        
        Args:
            content: JSON 字符串
        
        Returns:
            实体列表
        """
        try:
            data = json.loads(content)
            if isinstance(data, dict) and "entities" in data:
                return data["entities"]
            elif isinstance(data, list):
                return data
            return []
        except json.JSONDecodeError:
            return []
    
    def _parse_relations_from_json(self, content: str) -> List[Dict[str, Any]]:
        """
        从 JSON 内容中解析关系
        
        Args:
            content: JSON 字符串
        
        Returns:
            关系列表
        """
        try:
            data = json.loads(content)
            if isinstance(data, dict) and "relations" in data:
                return data["relations"]
            elif isinstance(data, list):
                return data
            return []
        except json.JSONDecodeError:
            return []
    
    async def _get_existing_entities(self, user_id: str) -> List[Dict[str, Any]]:
        """
        获取已存在的实体
        
        Args:
            user_id: 用户 ID
        
        Returns:
            实体列表
        """
        try:
            entities = await db.fetch(
                """
                SELECT name, type, confidence
                FROM entities
                WHERE user_id = $1
                ORDER BY last_mentioned_at DESC
                LIMIT 100
                """,
                user_id
            )
            
            return [
                {
                    "name": e["name"],
                    "type": e["type"],
                    "confidence": e["confidence"]
                }
                for e in entities
            ]
        except Exception as e:
            print(f"获取已存在实体失败: {e}")
            return []
    
    async def _get_existing_relations(self, user_id: str) -> List[Dict[str, Any]]:
        """
        获取已存在的关系
        
        Args:
            user_id: 用户 ID
        
        Returns:
            关系列表
        """
        try:
            relations = await db.fetch(
                """
                SELECT 
                    e1.name as source,
                    e2.name as destination,
                    r.relation_type,
                    r.confidence
                FROM relations r
                JOIN entities e1 ON r.from_entity_id = e1.id
                JOIN entities e2 ON r.to_entity_id = e2.id
                WHERE r.user_id = $1
                ORDER BY r.updated_at DESC
                LIMIT 100
                """,
                user_id
            )
            
            return [
                {
                    "source": r["source"],
                    "destination": r["destination"],
                    "relationship": r["relation_type"],
                    "confidence": r["confidence"]
                }
                for r in relations
            ]
        except Exception as e:
            print(f"获取已存在关系失败: {e}")
            return []
    
    async def get_entity_network(
        self,
        entity_name: str,
        user_id: str,
        depth: int = 2
    ) -> Dict[str, Any]:
        """
        获取实体的关系网络
        
        Args:
            entity_name: 实体名称
            user_id: 用户 ID
            depth: 关系深度
        
        Returns:
            包含实体和关系的网络数据
        """
        try:
            # 获取实体
            entity = await db.fetchrow(
                """
                SELECT * FROM entities 
                WHERE name = $1 AND user_id = $2
                """,
                entity_name, user_id
            )
            
            if not entity:
                return {"nodes": [], "edges": []}
            
            # 获取相关关系
            relations = await db.fetch(
                """
                SELECT 
                    r.*,
                    e1.name as from_name,
                    e2.name as to_name
                FROM relations r
                JOIN entities e1 ON r.from_entity_id = e1.id
                JOIN entities e2 ON r.to_entity_id = e2.id
                WHERE r.user_id = $1 
                AND (r.from_entity_id = $2 OR r.to_entity_id = $2)
                """,
                user_id, str(entity["id"])
            )
            
            # 构建网络数据
            nodes = [
                {
                    "id": str(entity["id"]),
                    "name": entity["name"],
                    "type": entity["type"],
                    "confidence": entity["confidence"],
                    "mention_count": entity["mention_count"]
                }
            ]
            
            edges = []
            seen_entities = {str(entity["id"])}
            
            for relation in relations:
                # 添加关系边
                edges.append({
                    "source": relation["from_name"],
                    "target": relation["to_name"],
                    "type": relation["relation_type"],
                    "weight": relation["weight"],
                    "confidence": relation["confidence"]
                })
                
                # 添加相关实体节点
                if relation["from_name"] != entity_name:
                    from_entity = await db.fetchrow(
                        "SELECT * FROM entities WHERE id = $1",
                        relation["from_entity_id"]
                    )
                    if from_entity and str(from_entity["id"]) not in seen_entities:
                        nodes.append({
                            "id": str(from_entity["id"]),
                            "name": from_entity["name"],
                            "type": from_entity["type"],
                            "confidence": from_entity["confidence"],
                            "mention_count": from_entity["mention_count"]
                        })
                        seen_entities.add(str(from_entity["id"]))
                
                if relation["to_name"] != entity_name:
                    to_entity = await db.fetchrow(
                        "SELECT * FROM entities WHERE id = $1",
                        relation["to_entity_id"]
                    )
                    if to_entity and str(to_entity["id"]) not in seen_entities:
                        nodes.append({
                            "id": str(to_entity["id"]),
                            "name": to_entity["name"],
                            "type": to_entity["type"],
                            "confidence": to_entity["confidence"],
                            "mention_count": to_entity["mention_count"]
                        })
                        seen_entities.add(str(to_entity["id"]))
            
            return {
                "nodes": nodes,
                "edges": edges
            }
            
        except Exception as e:
            print(f"获取实体网络失败: {e}")
            return {"nodes": [], "edges": []}


# 全局图谱构建服务实例
graph_builder_service: Optional[GraphBuilderService] = None


def get_graph_builder_service() -> GraphBuilderService:
    """获取图谱构建服务实例"""
    global graph_builder_service
    if graph_builder_service is None:
        graph_builder_service = GraphBuilderService()
    return graph_builder_service
