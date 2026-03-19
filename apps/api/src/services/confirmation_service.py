"""
智能确认服务（Phase 3 - 任务 1）

目标：避免错误累积，在新实体、低置信度、关系冲突时请求用户确认

确认场景：
1. 新实体首次出现 - 置信度 < 0.8 需要确认
2. 置信度过低 - 置信度 < 0.6 需要确认
3. 关系冲突 - 同一实体有冲突的关系需要确认
"""

from typing import Dict, List, Optional, Any
from datetime import datetime
import uuid


class ConfirmationService:
    """智能确认服务"""
    
    def __init__(self):
        """初始化确认服务"""
        # 确认阈值
        self.new_entity_threshold = 0.8  # 新实体置信度阈值
        self.low_confidence_threshold = 0.6  # 低置信度阈值
        
        # 待确认队列（内存存储，后续可改为数据库）
        self.pending_confirmations: Dict[str, Dict[str, Any]] = {}
    
    async def should_confirm(
        self,
        entity: Dict[str, Any],
        relations: List[Dict[str, Any]],
        existing_entities: List[Dict[str, Any]],
        existing_relations: List[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        """
        判断是否需要用户确认
        
        Args:
            entity: 待确认的实体，包含：
                - entity: 实体名称
                - entity_type: 实体类型
                - confidence: 置信度
            relations: 与该实体相关的关系列表
            existing_entities: 已存在的实体列表
            existing_relations: 已存在的关系列表
        
        Returns:
            如果需要确认，返回确认信息字典；否则返回 None
        """
        entity_name = entity.get("entity")
        entity_type = entity.get("entity_type")
        confidence = entity.get("confidence", 0.8)
        
        # 1. 检查是否是新实体
        is_new_entity = not any(
            e.get("name") == entity_name or e.get("entity") == entity_name
            for e in existing_entities
        )
        
        if is_new_entity:
            # 新实体首次出现，检查置信度
            if confidence < self.new_entity_threshold:
                return {
                    "type": "new_entity",
                    "entity": entity,
                    "reason": f"新实体首次出现，置信度较低（{confidence:.2f} < {self.new_entity_threshold}）",
                    "suggestion": f"是否要将'{entity_name}'添加为新实体（类型：{entity_type}）？",
                    "confidence": confidence,
                    "timestamp": datetime.now().isoformat()
                }
        
        # 2. 检查置信度是否过低
        if confidence < self.low_confidence_threshold:
            return {
                "type": "low_confidence",
                "entity": entity,
                "reason": f"实体置信度过低（{confidence:.2f} < {self.low_confidence_threshold}）",
                "suggestion": f"实体'{entity_name}'的置信度较低，是否确认添加？",
                "confidence": confidence,
                "timestamp": datetime.now().isoformat()
            }
        
        # 3. 检查关系冲突
        conflict = await self._check_relation_conflict(
            entity_name,
            relations,
            existing_relations
        )
        
        if conflict:
            return {
                "type": "relation_conflict",
                "entity": entity,
                "relations": relations,
                "conflict": conflict,
                "reason": f"实体'{entity_name}'存在关系冲突",
                "suggestion": f"实体'{entity_name}'与现有关系存在冲突，请确认是否继续？",
                "confidence": confidence,
                "timestamp": datetime.now().isoformat()
            }
        
        # 不需要确认
        return None
    
    async def _check_relation_conflict(
        self,
        entity_name: str,
        new_relations: List[Dict[str, Any]],
        existing_relations: List[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        """
        检查关系冲突
        
        冲突类型：
        1. 同一实体有矛盾的关系类型（如：friend vs colleague）
        2. 同一实体有矛盾的关系方向
        
        Args:
            entity_name: 实体名称
            new_relations: 新的关系列表
            existing_relations: 已存在的关系列表
        
        Returns:
            如果存在冲突，返回冲突信息；否则返回 None
        """
        # 找到与该实体相关的现有关系
        related_existing = [
            r for r in existing_relations
            if r.get("source") == entity_name or r.get("destination") == entity_name
        ]
        
        if not related_existing or not new_relations:
            return None
        
        # 定义冲突的关系类型
        conflict_types = {
            "friend": ["colleague", "family"],  # 朋友 vs 同事/家人
            "colleague": ["friend", "family"],  # 同事 vs 朋友/家人
            "family": ["friend", "colleague"],  # 家人 vs 朋友/同事
            "likes": ["dislikes"],              # 喜欢 vs 不喜欢
            "dislikes": ["likes"],              # 不喜欢 vs 喜欢
        }
        
        # 检查每个新关系
        for new_rel in new_relations:
            new_type = new_rel.get("relationship")
            new_target = new_rel.get("destination") or new_rel.get("source")
            
            # 检查是否有冲突
            for existing_rel in related_existing:
                existing_type = existing_rel.get("relationship")
                existing_target = existing_rel.get("destination") or existing_rel.get("source")
                
                # 如果目标实体相同
                if new_target == existing_target:
                    # 检查关系类型是否冲突
                    if existing_type in conflict_types.get(new_type, []):
                        return {
                            "new_relation": new_rel,
                            "existing_relation": existing_rel,
                            "conflict_type": "type_conflict",
                            "message": f"关系类型冲突：{new_type} vs {existing_type}"
                        }
        
        return None
    
    async def send_confirmation(
        self,
        user_id: str,
        confirmation: Dict[str, Any]
    ) -> str:
        """
        发送确认请求
        
        Args:
            user_id: 用户 ID
            confirmation: 确认信息
        
        Returns:
            确认 ID
        """
        # 生成确认 ID
        confirmation_id = str(uuid.uuid4())
        
        # 存储确认请求
        self.pending_confirmations[confirmation_id] = {
            "user_id": user_id,
            "confirmation": confirmation,
            "status": "pending",
            "created_at": datetime.now().isoformat()
        }
        
        # TODO: 发送飞书消息卡片
        # 这里暂时只记录日志
        print(f"[确认请求] 用户: {user_id}, 确认ID: {confirmation_id}")
        print(f"  类型: {confirmation['type']}")
        print(f"  原因: {confirmation['reason']}")
        print(f"  建议: {confirmation['suggestion']}")
        
        return confirmation_id
    
    async def handle_response(
        self,
        confirmation_id: str,
        response: str
    ) -> Dict[str, Any]:
        """
        处理用户回复
        
        Args:
            confirmation_id: 确认 ID
            response: 用户回复（"confirm" 或 "reject"）
        
        Returns:
            处理结果
        """
        # 获取确认请求
        confirmation_request = self.pending_confirmations.get(confirmation_id)
        
        if not confirmation_request:
            return {
                "status": "error",
                "message": "确认请求不存在或已过期"
            }
        
        # 更新状态
        confirmation_request["status"] = response
        confirmation_request["responded_at"] = datetime.now().isoformat()
        
        # 返回结果
        if response == "confirm":
            return {
                "status": "confirmed",
                "message": "用户已确认",
                "confirmation": confirmation_request["confirmation"]
            }
        elif response == "reject":
            return {
                "status": "rejected",
                "message": "用户已拒绝",
                "confirmation": confirmation_request["confirmation"]
            }
        else:
            return {
                "status": "error",
                "message": f"未知的回复类型: {response}"
            }
    
    def get_pending_confirmations(self, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        获取待确认列表
        
        Args:
            user_id: 用户 ID（可选，不传则返回所有）
        
        Returns:
            待确认列表
        """
        confirmations = []
        
        for conf_id, conf_data in self.pending_confirmations.items():
            if conf_data["status"] == "pending":
                if user_id is None or conf_data["user_id"] == user_id:
                    confirmations.append({
                        "confirmation_id": conf_id,
                        **conf_data
                    })
        
        return confirmations
    
    def clear_confirmation(self, confirmation_id: str) -> bool:
        """
        清除确认请求
        
        Args:
            confirmation_id: 确认 ID
        
        Returns:
            是否成功
        """
        if confirmation_id in self.pending_confirmations:
            del self.pending_confirmations[confirmation_id]
            return True
        return False


# 全局确认服务实例
confirmation_service: Optional[ConfirmationService] = None


def get_confirmation_service() -> ConfirmationService:
    """获取确认服务实例"""
    global confirmation_service
    if confirmation_service is None:
        confirmation_service = ConfirmationService()
    return confirmation_service
