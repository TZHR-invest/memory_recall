"""
软过滤服务（Phase 3 - 任务 2）

目标：不排除任何结果，只提升权重，支持关系扩展

核心功能：
1. 人物关系扩展："家人" → ["老婆", "老公", "孩子", "父母"]
2. 地点归一化："星巴克" → "咖啡店"
3. 软过滤：匹配结果提升权重，不排除
"""

from typing import Dict, List, Optional, Any
import re


class SoftFilterService:
    """软过滤服务"""
    
    def __init__(self):
        """初始化软过滤服务"""
        # 人物关系扩展映射
        self.person_relation_mapping = {
            "家人": ["老婆", "老公", "孩子", "父母", "爸爸", "妈妈", "儿子", "女儿", "兄弟", "姐妹"],
            "朋友": ["朋友", "哥们", "闺蜜", "老友"],
            "同事": ["同事", "搭档", "合作者"],
            "同学": ["同学", "校友", "学长", "学妹"],
        }
        
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
        
        # 权重提升系数
        self.boost_factor = 0.1
    
    async def apply_soft_filter(
        self,
        results: List[Dict[str, Any]],
        location_filter: Optional[str] = None,
        person_filter: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        应用软过滤
        
        Args:
            results: 搜索结果列表，每个结果应包含：
                - content: 记忆内容
                - similarity: 相似度分数
            location_filter: 地点过滤条件（可选）
            person_filter: 人物过滤条件（可选）
        
        Returns:
            软过滤后的结果列表（不排除任何结果，只提升权重）
        """
        if not results:
            return results
        
        # 复制结果，避免修改原始数据
        filtered_results = [r.copy() for r in results]
        
        # 应用地点过滤
        if location_filter:
            filtered_results = await self._apply_location_filter(
                filtered_results,
                location_filter
            )
        
        # 应用人物过滤
        if person_filter:
            filtered_results = await self._apply_person_filter(
                filtered_results,
                person_filter
            )
        
        # 按相似度重新排序
        filtered_results.sort(key=lambda x: x.get("similarity", 0), reverse=True)
        
        return filtered_results
    
    async def _apply_location_filter(
        self,
        results: List[Dict[str, Any]],
        location_filter: str
    ) -> List[Dict[str, Any]]:
        """
        应用地点过滤
        
        Args:
            results: 搜索结果列表
            location_filter: 地点过滤条件
        
        Returns:
            软过滤后的结果列表
        """
        # 获取归一化的地点
        normalized_location = self._normalize_location(location_filter)
        
        # 扩展地点关键词（包含原始地点和归一化地点）
        location_keywords = [location_filter]
        if normalized_location and normalized_location != location_filter:
            location_keywords.append(normalized_location)
        
        for result in results:
            content = result.get("content", "")
            
            # 检查是否包含地点关键词
            for keyword in location_keywords:
                if keyword in content:
                    # 提升权重
                    original_similarity = result.get("similarity", 0.5)
                    result["similarity"] = min(original_similarity + self.boost_factor, 1.0)
                    result["location_match"] = keyword
                    break
        
        return results
    
    async def _apply_person_filter(
        self,
        results: List[Dict[str, Any]],
        person_filter: str
    ) -> List[Dict[str, Any]]:
        """
        应用人物过滤
        
        Args:
            results: 搜索结果列表
            person_filter: 人物过滤条件
        
        Returns:
            软过滤后的结果列表
        """
        # 获取扩展的人物关键词
        expanded_persons = self._expand_person_relation(person_filter)
        
        # 包含原始人物名称
        person_keywords = [person_filter] + expanded_persons
        
        for result in results:
            content = result.get("content", "")
            
            # 检查是否包含人物关键词
            for keyword in person_keywords:
                if keyword in content:
                    # 提升权重
                    original_similarity = result.get("similarity", 0.5)
                    result["similarity"] = min(original_similarity + self.boost_factor, 1.0)
                    result["person_match"] = keyword
                    break
        
        return results
    
    def _normalize_location(self, location: str) -> Optional[str]:
        """
        地点归一化
        
        Args:
            location: 原始地点名称
        
        Returns:
            归一化后的地点名称
        """
        # 直接匹配
        if location in self.location_normalization:
            return self.location_normalization[location]
        
        # 大小写不敏感匹配
        location_lower = location.lower()
        for key, value in self.location_normalization.items():
            if key.lower() == location_lower:
                return value
        
        return None
    
    def _expand_person_relation(self, person: str) -> List[str]:
        """
        扩展人物关系
        
        Args:
            person: 人物类型或名称
        
        Returns:
            扩展后的人物列表
        """
        # 检查是否是关系类型
        if person in self.person_relation_mapping:
            return self.person_relation_mapping[person]
        
        # 否则返回空列表
        return []
    
    def get_location_keywords(self, location: str) -> List[str]:
        """
        获取地点相关的所有关键词
        
        Args:
            location: 地点名称
        
        Returns:
            相关关键词列表
        """
        keywords = [location]
        
        normalized = self._normalize_location(location)
        if normalized and normalized != location:
            keywords.append(normalized)
        
        return keywords
    
    def get_person_keywords(self, person: str) -> List[str]:
        """
        获取人物相关的所有关键词
        
        Args:
            person: 人物名称或类型
        
        Returns:
            相关关键词列表
        """
        keywords = [person]
        
        expanded = self._expand_person_relation(person)
        keywords.extend(expanded)
        
        return keywords
    
    def add_location_mapping(self, source: str, target: str):
        """
        添加地点映射
        
        Args:
            source: 原始地点名称
            target: 归一化后的地点名称
        """
        self.location_normalization[source] = target
    
    def add_person_mapping(self, relation_type: str, persons: List[str]):
        """
        添加人物关系映射
        
        Args:
            relation_type: 关系类型
            persons: 人物列表
        """
        if relation_type in self.person_relation_mapping:
            self.person_relation_mapping[relation_type].extend(persons)
        else:
            self.person_relation_mapping[relation_type] = persons


# 全局软过滤服务实例
soft_filter_service: Optional[SoftFilterService] = None


def get_soft_filter_service() -> SoftFilterService:
    """获取软过滤服务实例"""
    global soft_filter_service
    if soft_filter_service is None:
        soft_filter_service = SoftFilterService()
    return soft_filter_service
