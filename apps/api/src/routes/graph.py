"""
图谱 API 路由
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List
from ..services.graph_recall_service import get_graph_recall_service
from ..services.graph_builder_service import get_graph_builder_service
from ..database import db
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


class SearchByEntityRequest(BaseModel):
    entity_name: str
    user_id: str
    limit: int = 10


class SearchByRelationRequest(BaseModel):
    relation_type: str
    user_id: str
    entity_name: Optional[str] = None
    limit: int = 10


class SearchGraphRequest(BaseModel):
    query: str
    user_id: str
    limit: int = 10


class HybridRecallRequest(BaseModel):
    query: str
    user_id: str
    limit: int = 10
    weights: Optional[dict] = None


class ConfirmNormalizationRequest(BaseModel):
    entity1: str
    entity2: str
    relation_type: str = "same_as"
    user_id: str


class AddRelationByTextRequest(BaseModel):
    text: str
    user_id: str


@router.post("/api/v1/graph/confirm-normalization")
async def confirm_normalization(request: ConfirmNormalizationRequest):
    """
    确认实体归一化关系
    
    用于用户确认人物归一化关系（如"老张" = "张三"）
    
    示例:
    ```json
    {
        "entity1": "老张",
        "entity2": "张三",
        "relation_type": "same_as",
        "user_id": "user_123"
    }
    ```
    
    relation_type 可选值：
    - "same_as": 同一实体（昵称、外号）
    - "is_a": 归属类型（星巴克 → 咖啡店）
    """
    try:
        builder_service = get_graph_builder_service()
        
        # 创建归一化关系
        await builder_service._create_normalization_relation(
            source_entity=request.entity1,
            target_entity=request.entity2,
            relation_type=request.relation_type
        )
        
        return {
            "success": True,
            "message": f"已创建归一化关系: {request.entity1} {request.relation_type} {request.entity2}",
            "entity1": request.entity1,
            "entity2": request.entity2,
            "relation_type": request.relation_type
        }
    
    except Exception as e:
        logger.error(f"确认归一化关系失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/v1/graph/add-relation-by-text")
async def add_relation_by_text(request: AddRelationByTextRequest):
    """
    通过自然语言添加实体关系（支持一句话多个关系）
    
    用户输入示例：
    - "老张就是我大学室友张三" → 识别出多个关系
    - "我老婆小红是我同事李四的表妹" → 识别出多个关系
    - "星巴克是咖啡店" → 单个关系
    
    流程：
    1. LLM 解析自然语言，提取所有实体和关系
    2. 验证解析结果（置信度 >= 0.7）
    3. 批量创建实体和关系
    
    返回：
    ```json
    {
        "success": true,
        "relations": [
            {
                "entity1": "老张",
                "entity2": "张三",
                "relation_type": "same_as",
                "confidence": 0.9
            },
            {
                "entity1": "张三",
                "entity2": "大学室友",
                "relation_type": "related_to",
                "confidence": 0.8
            }
        ],
        "created_count": 2,
        "message": "已创建 2 个关系"
    }
    ```
    """
    try:
        builder_service = get_graph_builder_service()
        
        # 1. LLM 解析（返回多个关系）
        relations = await builder_service.parse_relation_from_text(request.text)
        
        # 2. 验证是否有有效关系
        if not relations or relations[0].get("error"):
            error_msg = relations[0].get("error", "无法识别关系") if relations else "无法识别关系"
            return {
                "success": False,
                "message": f"无法识别关系: {error_msg}"
            }
        
        # 3. 过滤低置信度的关系
        valid_relations = [
            r for r in relations
            if not r.get("error") and r.get("confidence", 0) >= 0.7
        ]
        
        if not valid_relations:
            return {
                "success": False,
                "message": "所有关系的置信度过低（< 0.7），请更明确地描述关系"
            }
        
        # 4. 批量创建关系
        result = await builder_service.create_relations_from_parsed(valid_relations, request.user_id)
        
        if result["success_count"] > 0:
            # 构建成功消息
            relation_strs = [
                f"{r['entity1']} {r['relation_type']} {r['entity2']}"
                for r in result["created"]
            ]
            
            response = {
                "success": True,
                "relations": result["created"],
                "created_count": result["success_count"],
                "message": f"已创建 {result['success_count']} 个关系：" + "、".join(relation_strs)
            }
            
            # 如果有部分失败，添加警告信息
            if result["failed"]:
                failed_strs = [
                    f"{r.get('entity1', '?')} - {r.get('entity2', '?')}: {r.get('error', '未知错误')}"
                    for r in result["failed"]
                ]
                response["warnings"] = failed_strs
            
            return response
        else:
            return {
                "success": False,
                "message": f"创建关系失败: {result['failed'][0].get('error', '未知错误') if result['failed'] else '未知错误'}"
            }
    
    except Exception as e:
        logger.error(f"通过自然语言添加关系失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/v1/graph/search-by-entity")
async def search_by_entity(request: SearchByEntityRequest):
    """
    实体扩展召回
    
    通过实体名称搜索相关记忆
    
    示例:
    ```json
    {
        "entity_name": "张三",
        "user_id": "user_123",
        "limit": 10
    }
    ```
    """
    from ..database import db
    
    # 设置当前用户 schema
    db.set_current_user(request.user_id)
    
    service = get_graph_recall_service()
    
    try:
        results = await service.search_by_entity(
            entity_name=request.entity_name,
            user_id=request.user_id,
            limit=request.limit
        )
        
        return {
            "success": True,
            "entity": request.entity_name,
            "count": len(results),
            "results": results
        }
    
    except Exception as e:
        logger.error(f"实体扩展召回失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/v1/graph/search-by-relation")
async def search_by_relation(request: SearchByRelationRequest):
    """
    关系扩展召回
    
    通过关系类型搜索相关记忆
    
    示例:
    ```json
    {
        "relation_type": "friend",
        "user_id": "user_123",
        "entity_name": "张三",
        "limit": 10
    }
    ```
    """
    # 设置当前用户 schema
    db.set_current_user(request.user_id)
    
    service = get_graph_recall_service()
    
    try:
        results = await service.search_by_relation(
            relation_type=request.relation_type,
            user_id=request.user_id,
            entity_name=request.entity_name,
            limit=request.limit
        )
        
        return {
            "success": True,
            "relation_type": request.relation_type,
            "count": len(results),
            "results": results
        }
    
    except Exception as e:
        logger.error(f"关系扩展召回失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/v1/graph/search")
async def search_graph(request: SearchGraphRequest):
    """
    图谱搜索（Mem0 方式）
    
    返回关系三元组 + 相关记忆
    
    示例:
    ```json
    {
        "query": "张三的朋友",
        "user_id": "user_123",
        "limit": 10
    }
    ```
    
    返回:
    ```json
    {
        "success": true,
        "relations": [
            {
                "source": "张三",
                "relationship": "friend",
                "destination": "李四"
            }
        ],
        "memories": [
            {
                "id": 1,
                "content": "今天和张三在咖啡店聊天"
            }
        ]
    }
    ```
    """
    # 设置当前用户 schema
    db.set_current_user(request.user_id)
    
    service = get_graph_recall_service()
    
    try:
        results = await service.search_graph(
            query=request.query,
            user_id=request.user_id,
            limit=request.limit
        )
        
        return {
            "success": True,
            "query": request.query,
            "relations_count": len(results.get("relations", [])),
            "memories_count": len(results.get("memories", [])),
            **results
        }
    
    except Exception as e:
        logger.error(f"图谱搜索失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/v1/graph/hybrid-recall")
async def hybrid_recall(request: HybridRecallRequest):
    """
    混合召回（向量 + 关键词 + 图谱）
    
    三路召回合并，权重默认:
    - 向量: 0.5
    - 关键词: 0.3
    - 图谱: 0.2
    
    示例:
    ```json
    {
        "query": "和朋友在咖啡店",
        "user_id": "user_123",
        "limit": 10,
        "weights": {
            "vector": 0.5,
            "keyword": 0.3,
            "graph": 0.2
        }
    }
    ```
    """
    # 设置当前用户 schema
    db.set_current_user(request.user_id)
    
    service = get_graph_recall_service()
    
    try:
        results = await service.hybrid_recall(
            query=request.query,
            user_id=request.user_id,
            limit=request.limit,
            weights=request.weights
        )
        
        return {
            "success": True,
            "query": request.query,
            "count": len(results),
            "results": results
        }
    
    except Exception as e:
        logger.error(f"混合召回失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/v1/graph/entities")
async def get_entity_network(
    user_id: str,
    entity_name: Optional[str] = None,
    limit: int = 20
):
    """
    获取实体网络
    
    查询用户的所有实体或特定实体的关系网络
    
    参数：
    - user_id: 用户 ID（必填）
    - entity_name: 实体名称（可选，如果提供则返回该实体的关系网络）
    - limit: 返回数量限制（默认 20）
    
    返回：
    ```json
    {
        "success": true,
        "entity_name": "张三"（如果指定），
        "entities": [
            {
                "name": "张三",
                "type": "person",
                "relation_count": 3
            }
        ],
        "relations": [
            {
                "source": "张三",
                "relationship": "friend",
                "destination": "李四"
            }
        ]
    }
    ```
    """
    # 设置当前用户 schema
    db.set_current_user(user_id)
    
    try:
        builder_service = get_graph_builder_service()
        
        if entity_name:
            # 查询特定实体的关系网络
            network = await builder_service.get_entity_network(
                entity_name=entity_name,
                user_id=user_id,
                limit=limit
            )
            return {
                "success": True,
                "entity_name": entity_name,
                **network
            }
        else:
            # 查询用户所有实体
            entities = await builder_service.get_all_entities(
                user_id=user_id,
                limit=limit
            )
            relations = await builder_service.get_all_relations(
                user_id=user_id,
                limit=limit
            )
            
            return {
                "success": True,
                "entity_count": len(entities),
                "relation_count": len(relations),
                "entities": entities,
                "relations": relations
            }
    
    except Exception as e:
        logger.error(f"获取实体网络失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/v1/graph/health")
async def health():
    """健康检查"""
    return {"status": "ok", "service": "graph-recall"}
