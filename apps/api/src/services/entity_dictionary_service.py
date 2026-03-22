"""
实体词典服务 - 快速实体提取

通过预先构建实体词典，实现毫秒级实体提取，替代 LLM 调用
"""

import logging
from typing import Dict, List, Optional, Any
from ..database import db

logger = logging.getLogger(__name__)


class EntityDictionaryService:
    """实体词典服务 - 快速实体提取"""
    
    def __init__(self):
        self.entity_dict: Dict[str, Dict[str, Any]] = {}
        self._initialized = False
        self._initializing = False
    
    async def initialize(self):
        """
        从数据库加载实体词典（所有用户）
        
        加载所有用户的实体的名称、类型、置信度等信息
        在多用户 schema 架构下，需要遍历所有用户的 schema
        """
        if self._initialized or self._initializing:
            return
        
        self._initializing = True
        
        try:
            # 1. 获取所有用户列表
            users = await db.fetch(
                "SELECT id FROM public.users",
                conn=None  # 确保使用 public schema
            )
            
            # 2. 遍历每个用户的 schema，加载实体
            self.entity_dict.clear()
            
            for user in users:
                user_id = user["id"]
                
                try:
                    # 使用 user_context 确保在正确的 schema 下查询
                    async with db.user_context(user_id):
                        entities = await db.fetch(
                            """
                            SELECT id, name, type, confidence, user_id
                            FROM entities
                            WHERE confidence >= 0.5
                            ORDER BY mention_count DESC
                            """
                        )
                        
                        # 添加到词典
                        for entity in entities:
                            entity_name = entity["name"]
                            entity_info = {
                                "id": str(entity["id"]),
                                "type": entity["type"],
                                "confidence": entity["confidence"],
                                "user_id": entity["user_id"]
                            }
                            
                            # 处理同名实体（不同用户可能有同名实体）
                            if entity_name in self.entity_dict:
                                existing = self.entity_dict[entity_name]
                                if isinstance(existing, list):
                                    existing.append(entity_info)
                                else:
                                    self.entity_dict[entity_name] = [existing, entity_info]
                            else:
                                self.entity_dict[entity_name] = entity_info
                
                except Exception as e:
                    logger.error(f"加载用户 {user_id} 的实体失败: {e}")
                    # 继续加载其他用户的实体
                    continue
            
            self._initialized = True
            self._initializing = False
            
            logger.info(f"实体词典初始化完成，共加载 {len(self.entity_dict)} 个实体（来自 {len(users)} 个用户）")
        
        except Exception as e:
            self._initializing = False
            logger.error(f"实体词典初始化失败: {e}")
            raise
    
    def extract_entities_fast(
        self,
        query: str,
        user_id: Optional[str] = None
    ) -> List[str]:
        """
        快速提取查询中的实体（字符串匹配）
        
        Args:
            query: 查询文本
            user_id: 用户 ID（用于过滤同名实体）
        
        Returns:
            匹配到的实体名称列表
        """
        if not self._initialized:
            logger.warning("实体词典未初始化，请先调用 initialize()")
            return []
        
        entities = []
        
        # 按实体名称长度降序排序（优先匹配长实体名）
        sorted_names = sorted(
            self.entity_dict.keys(),
            key=lambda x: len(x),
            reverse=True
        )
        
        for name in sorted_names:
            if name in query:
                entity_info = self.entity_dict[name]
                
                # 如果指定了 user_id，过滤只属于该用户的实体
                if user_id:
                    if isinstance(entity_info, list):
                        # 多个同名实体，检查是否有属于该用户的
                        for info in entity_info:
                            if info.get("user_id") == user_id:
                                entities.append(name)
                                break
                    else:
                        # 单个实体，检查是否属于该用户
                        if entity_info.get("user_id") == user_id:
                            entities.append(name)
                else:
                    # 未指定 user_id，直接添加
                    entities.append(name)
        
        return entities
    
    def get_entity_info(self, entity_name: str) -> Optional[Dict[str, Any]]:
        """
        获取实体信息
        
        Args:
            entity_name: 实体名称
        
        Returns:
            实体信息字典
        """
        if not self._initialized:
            logger.warning("实体词典未初始化")
            return None
        
        return self.entity_dict.get(entity_name)
    
    async def refresh(self):
        """
        刷新词典（新实体入库后调用）
        
        重新从数据库加载所有实体
        """
        logger.info("刷新实体词典...")
        
        # 标记为未初始化，强制重新加载
        self._initialized = False
        self.entity_dict.clear()
        
        await self.initialize()
    
    def add_entity(self, entity_name: str, entity_info: Dict[str, Any]):
        """
        添加单个实体到词典（用于增量更新）
        
        Args:
            entity_name: 实体名称
            entity_info: 实体信息
        """
        if entity_name in self.entity_dict:
            existing = self.entity_dict[entity_name]
            if isinstance(existing, list):
                existing.append(entity_info)
            else:
                self.entity_dict[entity_name] = [existing, entity_info]
        else:
            self.entity_dict[entity_name] = entity_info
    
    def remove_entity(self, entity_name: str):
        """
        从词典中移除实体
        
        Args:
            entity_name: 实体名称
        """
        if entity_name in self.entity_dict:
            del self.entity_dict[entity_name]
    
    def get_stats(self) -> Dict[str, Any]:
        """
        获取词典统计信息
        
        Returns:
            统计信息字典
        """
        return {
            "initialized": self._initialized,
            "entity_count": len(self.entity_dict),
            "sample_entities": list(self.entity_dict.keys())[:10] if self.entity_dict else []
        }


# 全局服务实例
entity_dictionary_service: Optional[EntityDictionaryService] = None


def get_entity_dictionary_service() -> EntityDictionaryService:
    """获取实体词典服务实例"""
    global entity_dictionary_service
    if entity_dictionary_service is None:
        entity_dictionary_service = EntityDictionaryService()
    return entity_dictionary_service
