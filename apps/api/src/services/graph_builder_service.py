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
from .entity_dictionary_service import get_entity_dictionary_service


class GraphBuilderService:
    """图谱构建服务"""
    
    def __init__(self):
        """初始化服务"""
        self.llm_service = get_llm_recall_service()
        self.confirmation_service = get_confirmation_service()
        self.entity_dict = get_entity_dictionary_service()
        
        # 地点归一化映射
        self.location_normalization = {
            # 咖啡店
            "星巴克": "咖啡店",
            "瑞幸": "咖啡店",
            "costa": "咖啡店",
            "costa咖啡": "咖啡店",
            
            # 餐厅
            "肯德基": "快餐店",
            "KFC": "快餐店",
            "麦当劳": "快餐店",
            "海底捞": "火锅店",
            "西贝": "餐厅",
            
            # 商场
            "万达": "商场",
            "大悦城": "商场",
            "恒隆": "商场",
            
            # 公园
            "颐和园": "公园",
            "天坛": "公园",
            "北海公园": "公园",
            
            # 公司
            "腾讯": "公司",
            "阿里": "公司",
            "阿里巴巴": "公司",
            "字节": "公司",
            "字节跳动": "公司",
        }
    
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
        1. 实体提取（Function Calling）+ 归一化
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
            - need_confirm: 是否需要确认（归一化）
        """
        # 设置当前用户 schema
        db.set_current_user(user_id)
        
        try:
            # 1. 实体提取 + 归一化
            entities_result = await self._extract_entities(content, user_id)
            
            # 检查是否需要确认
            if isinstance(entities_result, dict) and entities_result.get("need_confirm"):
                return {
                    "entities": [],
                    "relations": [],
                    "entity_count": 0,
                    "relation_count": 0,
                    "confirmations": None,
                    **entities_result,
                    "status": "need_confirmation"
                }
            
            entities = entities_result
            
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
            
            # 6. 刷新实体词典（新实体入库后更新词典）
            if entity_ids:
                try:
                    await self.entity_dict.refresh()
                except Exception as e:
                    print(f"刷新实体词典失败: {e}")
            
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
    
    async def extract_entities(self, content: str, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        提取实体（公共 API）
        
        Args:
            content: 文本内容
            user_id: 用户 ID（可选，用于归一化智能询问）
        
        Returns:
            实体列表或确认请求
        """
        return await self._extract_entities(content, user_id)
    
    async def infer_relations(
        self,
        entities: List[Dict[str, Any]],
        context: str
    ) -> List[Dict[str, Any]]:
        """
        推理关系（公共 API）
        
        Args:
            entities: 实体列表
            context: 上下文文本
        
        Returns:
            关系列表，每个关系包含：
            - source: 源实体名称
            - destination: 目标实体名称
            - relationship: 关系类型
            - confidence: 置信度
        """
        return await self._extract_relations(context, entities)
    
    async def _extract_entities(self, content: str, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        提取实体（Function Calling）+ 归一化
        
        Args:
            content: 文本内容
            user_id: 用户 ID（用于智能询问）
        
        Returns:
            实体列表或确认请求：
            - 正常情况：实体列表
            - 需要确认：{"need_confirm": True, ...}
        """
        try:
            # 调用 LLM Function Calling
            response = await self.llm_service.call_with_tools(
                system_prompt=get_entity_extraction_prompt(),
                user_prompt=f"请从以下文本中提取实体：\n\n{content}",
                tools=[EXTRACT_ENTITIES_TOOL]
            )
            
            # 解析工具调用结果
            entities = []
            if response.get("tool_calls"):
                for tool_call in response["tool_calls"]:
                    if tool_call["function"]["name"] == "extract_entities":
                        entities = tool_call["function"]["arguments"].get("entities", [])
                        # 确保每个实体都有置信度
                        for entity in entities:
                            if "confidence" not in entity:
                                entity["confidence"] = 0.8
            
            # 如果没有工具调用，尝试从 JSON 响应中解析
            if not entities and response.get("content"):
                entities = self._parse_entities_from_json(response["content"])
            
            if not entities:
                return []
            
            # ===== 归一化处理 =====
            normalization_tasks = []
            
            for entity in entities:
                # 地点归一化（自动）
                if entity.get("entity_type") == "location":
                    normalized = self.location_normalization.get(entity["entity"])
                    if normalized:
                        normalization_tasks.append(
                            self._create_normalization_relation(
                                entity["entity"], normalized, "is_a"
                            )
                        )
                
                # 人物归一化（智能询问）
                if entity.get("entity_type") == "person" and user_id:
                    similar_entities = await self._find_similar_entities(
                        entity["entity"], user_id
                    )
                    
                    if similar_entities:
                        # 返回确认请求
                        return {
                            "need_confirm": True,
                            "confirm_type": "entity_normalization",
                            "question": f"'{entity['entity']}'是否就是之前提到的'{similar_entities[0]}'？",
                            "entities": [entity["entity"], similar_entities[0]],
                            "original_entities": entities
                        }
            
            # 执行归一化关系创建（并发）
            if normalization_tasks:
                await asyncio.gather(*normalization_tasks, return_exceptions=True)
            
            return entities
            
        except Exception as e:
            print(f"提取实体失败: {e}")
            # 降级处理：返回空列表
            return []
    
    async def _create_normalization_relation(
        self,
        source_entity: str,
        target_entity: str,
        relation_type: str
    ):
        """
        创建归一化关系
        
        Args:
            source_entity: 源实体名称（如"星巴克"）
            target_entity: 目标实体名称（如"咖啡店"）
            relation_type: 关系类型（"is_a" 或 "same_as"）
        """
        try:
            # 获取或创建实体
            source_id = await self._upsert_entity(
                name=source_entity,
                entity_type="location",
                user_id="system",  # 归一化关系属于系统级
                confidence=1.0
            )
            
            target_id = await self._upsert_entity(
                name=target_entity,
                entity_type="location_type",
                user_id="system",
                confidence=1.0
            )
            
            if source_id and target_id:
                await self._upsert_relation(
                    from_entity=source_entity,
                    to_entity=target_entity,
                    relation_type=relation_type,
                    confidence=1.0,
                    user_id="system"
                )
                
        except Exception as e:
            print(f"创建归一化关系失败: {e}")
    
    async def _find_similar_entities(
        self,
        entity_name: str,
        user_id: str
    ) -> List[str]:
        """
        查找相似实体（用于智能询问）
        
        Args:
            entity_name: 实体名称
            user_id: 用户 ID
        
        Returns:
            相似实体名称列表
        """
        try:
            # 查询用户的人物实体
            entities = await db.fetch(
                """
                SELECT name, similarity($1, name) as sim
                FROM entities
                WHERE user_id = $2
                AND type = 'person'
                AND name % $1  -- 使用 pg_trgm 相似度匹配
                ORDER BY sim DESC
                LIMIT 3
                """,
                entity_name, user_id
            )
            
            # 过滤掉相似度过低的
            similar = [e["name"] for e in entities if e["sim"] > 0.6]
            
            return similar
            
        except Exception as e:
            print(f"查找相似实体失败: {e}")
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
                WHERE name = $1 AND entity_type = $2
                """,
                name, entity_type
            )
            
            if existing:
                # 更新提及次数和置信度
                await db.execute(
                    """
                    UPDATE entities 
                    SET confidence = GREATEST(confidence, $1),
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
                    INSERT INTO entities (name, entity_type, confidence)
                    VALUES ($1, $2, $3)
                    RETURNING id
                    """,
                    name, entity_type, confidence
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
                "SELECT id FROM entities WHERE name = $1",
                from_entity
            )
            to_id = await db.fetchval(
                "SELECT id FROM entities WHERE name = $1",
                to_entity
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
                    INSERT INTO relations (from_entity_id, to_entity_id, relation_type, weight, confidence)
                    VALUES ($1, $2, $3, $4, $5)
                    """,
                    str(from_id), str(to_id), relation_type, confidence, confidence
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
        # 设置当前用户 schema
        db.set_current_user(user_id)
        
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
    
    async def parse_relation_from_text(self, text: str) -> List[Dict[str, Any]]:
        """
        从自然语言文本中解析实体关系（支持多个关系）
        
        Args:
            text: 用户输入的文本
        
        Returns:
            关系列表，每个关系包含：
            - entity1: 实体1名称
            - entity2: 实体2名称
            - relation_type: 关系类型
            - context: 上下文信息（可选）
            - confidence: 置信度（0-1）
            如果解析失败，返回包含 error 字段的列表
        """
        try:
            # 构建提示词
            prompt = f"""用户输入："{text}"

请从这句话中提取所有实体关系，返回 JSON 数组格式：

[
    {{
        "entity1": "实体1名称",
        "entity2": "实体2名称",
        "relation_type": "关系类型",
        "context": "上下文信息（可选）",
        "confidence": 0.9
    }},
    ...
]

支持的关系类型：
- same_as: 同一实体（老张 same_as 张三）
- is_a: 归属类型（星巴克 is_a 咖啡店）
- related_to: 相关关系
- family: 家人
- friend: 朋友
- colleague: 同事

注意：
1. 一句话可能包含多个关系，请全部提取
2. 只返回 JSON 数组，不要其他说明
3. 如果无法识别，返回空数组 []
4. confidence 范围 0-1

示例：
输入："老张就是我的大学室友张三"
输出：
[
    {{"entity1": "老张", "entity2": "张三", "relation_type": "same_as", "confidence": 0.9}},
    {{"entity1": "张三", "entity2": "大学室友", "relation_type": "related_to", "confidence": 0.8}}
]

输入："我老婆小红是我同事李四的表妹"
输出：
[
    {{"entity1": "小红", "entity2": "老婆", "relation_type": "family", "confidence": 0.9}},
    {{"entity1": "李四", "entity2": "同事", "relation_type": "colleague", "confidence": 0.9}},
    {{"entity1": "小红", "entity2": "李四", "relation_type": "family", "confidence": 0.85}}
]"""

            # 调用 LLM
            from ..llm.client import get_llm_client
            llm_client = get_llm_client()
            
            parsed = llm_client.extract_json(
                prompt=prompt,
                temperature=0.3,
                max_tokens=1000
            )
            
            if not parsed:
                return [{"error": "解析失败，无法从文本中提取关系"}]
            
            # 确保返回的是列表
            if isinstance(parsed, dict):
                # 如果是单个关系对象，转换为列表
                if "error" in parsed:
                    return [parsed]
                parsed = [parsed]
            
            # 验证每个关系的必要字段
            validated_relations = []
            for relation in parsed:
                if "error" in relation:
                    continue
                
                required_fields = ["entity1", "entity2", "relation_type"]
                if all(field in relation for field in required_fields):
                    # 确保置信度在有效范围内
                    if "confidence" not in relation:
                        relation["confidence"] = 0.8
                    else:
                        relation["confidence"] = max(0.0, min(1.0, float(relation["confidence"])))
                    validated_relations.append(relation)
            
            return validated_relations if validated_relations else [{"error": "未提取到有效关系"}]
            
        except Exception as e:
            print(f"解析实体关系失败: {e}")
            return [{"error": f"解析失败: {str(e)}"}]
    
    async def create_relation_from_parsed(
        self,
        parsed: Dict[str, Any],
        user_id: str
    ) -> Dict[str, Any]:
        """
        根据解析结果创建关系（支持单个关系，向后兼容）
        
        Args:
            parsed: LLM 解析结果（单个关系）
            user_id: 用户 ID
        
        Returns:
            创建结果，包含：
            - success: 是否成功
            - entity1_id: 实体1 ID
            - entity2_id: 实体2 ID
            - relation_type: 关系类型
            - error: 错误信息（如果失败）
        """
        # 将单个关系包装成列表，调用批量创建方法
        results = await self.create_relations_from_parsed([parsed], user_id)
        
        if results["success_count"] > 0:
            return {
                "success": True,
                "entity1_id": results["created"][0].get("entity1_id"),
                "entity2_id": results["created"][0].get("entity2_id"),
                "relation_type": results["created"][0].get("relation_type")
            }
        else:
            return {
                "success": False,
                "error": results["failed"][0].get("error", "创建关系失败") if results["failed"] else "创建关系失败"
            }
    
    async def create_relations_from_parsed(
        self,
        parsed_list: List[Dict[str, Any]],
        user_id: str
    ) -> Dict[str, Any]:
        """
        根据解析结果创建多个关系
        
        Args:
            parsed_list: LLM 解析结果列表
            user_id: 用户 ID
        
        Returns:
            创建结果，包含：
            - created: 成功创建的关系列表
            - failed: 创建失败的关系列表
            - total: 总数
            - success_count: 成功数量
        """
        created = []
        failed = []
        
        for parsed in parsed_list:
            # 跳过包含错误的关系
            if parsed.get("error"):
                failed.append({**parsed, "error": parsed["error"]})
                continue
            
            entity1 = parsed.get("entity1")
            entity2 = parsed.get("entity2")
            relation_type = parsed.get("relation_type")
            confidence = parsed.get("confidence", 0.8)
            context = parsed.get("context")
            
            if not all([entity1, entity2, relation_type]):
                failed.append({
                    **parsed,
                    "error": "缺少必要字段：entity1、entity2 或 relation_type"
                })
                continue
            
            try:
                # 1. 创建或获取实体（自动推断类型）
                entity1_type = self._infer_entity_type(entity1, relation_type)
                entity2_type = self._infer_entity_type(entity2, relation_type)
                
                e1_id = await self._upsert_entity(
                    name=entity1,
                    entity_type=entity1_type,
                    user_id=user_id,
                    confidence=confidence
                )
                
                e2_id = await self._upsert_entity(
                    name=entity2,
                    entity_type=entity2_type,
                    user_id=user_id,
                    confidence=confidence
                )
                
                if not e1_id or not e2_id:
                    failed.append({
                        **parsed,
                        "error": "创建实体失败"
                    })
                    continue
                
                # 2. 创建关系
                success = await self._upsert_relation(
                    from_entity=entity1,
                    to_entity=entity2,
                    relation_type=relation_type,
                    confidence=confidence,
                    user_id=user_id
                )
                
                if success:
                    created.append({
                        **parsed,
                        "entity1_id": e1_id,
                        "entity2_id": e2_id
                    })
                else:
                    failed.append({
                        **parsed,
                        "error": "创建关系失败"
                    })
                    
            except Exception as e:
                failed.append({
                    **parsed,
                    "error": str(e)
                })
        
        # 3. 刷新实体词典（如果有成功创建的关系）
        if created:
            try:
                await self.entity_dict.refresh()
            except Exception as e:
                print(f"刷新实体词典失败: {e}")
        
        return {
            "created": created,
            "failed": failed,
            "total": len(parsed_list),
            "success_count": len(created)
        }
    
    def _infer_entity_type(self, entity_name: str, relation_type: str) -> str:
        """
        推断实体类型
        
        Args:
            entity_name: 实体名称
            relation_type: 关系类型
        
        Returns:
            推断的实体类型
        """
        # 基于关系类型推断
        if relation_type in ["family", "friend", "colleague"]:
            return "person"
        elif relation_type == "is_a":
            # 第一个实体是具体实例，第二个是类型
            return "unknown"
        elif relation_type == "same_as":
            return "person"  # 通常用于人物别名
        
        # 基于名称特征推断
        if entity_name in self.location_normalization:
            return "location"
        
        # 默认类型
        return "unknown"
    
    async def get_all_entities(
        self,
        user_id: str,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        获取用户所有实体
        
        Args:
            user_id: 用户 ID
            limit: 返回数量限制
        
        Returns:
            实体列表
        """
        # 设置当前用户 schema
        db.set_current_user(user_id)
        
        try:
            entities = await db.fetch(
                """
                SELECT 
                    id,
                    name,
                    type,
                    confidence,
                    mention_count,
                    created_at
                FROM entities
                WHERE user_id = $1
                ORDER BY mention_count DESC, created_at DESC
                LIMIT $2
                """,
                user_id,
                limit
            )
            
            result = []
            for e in entities:
                result.append({
                    "id": str(e["id"]),
                    "name": e["name"],
                    "type": e["type"],
                    "confidence": float(e["confidence"]) if e["confidence"] else 0.8,
                    "mention_count": e["mention_count"],
                    "created_at": e["created_at"].isoformat() if e["created_at"] else None
                })
            
            return result
        
        except Exception as e:
            print(f"获取所有实体失败: {e}")
            return []
    
    async def get_all_relations(
        self,
        user_id: str,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        获取用户所有关系
        
        Args:
            user_id: 用户 ID
            limit: 返回数量限制
        
        Returns:
            关系列表
        """
        # 设置当前用户 schema
        db.set_current_user(user_id)
        
        try:
            relations = await db.fetch(
                """
                SELECT 
                    r.id,
                    r.relation_type,
                    r.confidence,
                    r.weight,
                    r.created_at,
                    e1.name as from_entity,
                    e1.id as from_entity_id,
                    e2.name as to_entity,
                    e2.id as to_entity_id
                FROM relations r
                JOIN entities e1 ON r.from_entity_id = e1.id
                JOIN entities e2 ON r.to_entity_id = e2.id
                WHERE r.user_id = $1
                ORDER BY r.weight DESC, r.created_at DESC
                LIMIT $2
                """,
                user_id,
                limit
            )
            
            result = []
            for r in relations:
                result.append({
                    "id": str(r["id"]),
                    "source": r["from_entity"],
                    "source_id": str(r["from_entity_id"]),
                    "relationship": r["relation_type"],
                    "destination": r["to_entity"],
                    "destination_id": str(r["to_entity_id"]),
                    "confidence": float(r["confidence"]) if r["confidence"] else 0.8,
                    "weight": r["weight"],
                    "created_at": r["created_at"].isoformat() if r["created_at"] else None
                })
            
            return result
        
        except Exception as e:
            print(f"获取所有关系失败: {e}")
            return []


# 全局图谱构建服务实例
graph_builder_service: Optional[GraphBuilderService] = None


def get_graph_builder_service() -> GraphBuilderService:
    """获取图谱构建服务实例"""
    global graph_builder_service
    if graph_builder_service is None:
        graph_builder_service = GraphBuilderService()
    return graph_builder_service
