"""
查询解析模块
"""
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
import re


class QueryParser:
    """查询解析器"""
    
    def parse(self, query: str) -> Dict[str, Any]:
        """
        解析用户查询
        
        Args:
            query: 查询文本
        
        Returns:
            解析后的查询结构
        """
        result = {
            "original_query": query,
            "time_range": None,
            "people": [],
            "location": None,
            "tags": [],
            "keywords": [],
            "intent": "query_content"  # 默认意图：查询内容
        }
        
        # 解析时间范围
        time_range = self._parse_time(query)
        if time_range:
            result["time_range"] = time_range
        
        # 解析人物
        people = self._parse_people(query)
        if people:
            result["people"] = people
        
        # 解析位置
        location = self._parse_location(query)
        if location:
            result["location"] = location
        
        # 解析标签
        tags = self._parse_tags(query)
        if tags:
            result["tags"] = tags
        
        # 提取关键词
        keywords = self._extract_keywords(query)
        if keywords:
            result["keywords"] = keywords
        
        # 判断意图
        result["intent"] = self._determine_intent(query)
        
        return result
    
    def _parse_time(self, query: str) -> Optional[Dict[str, Any]]:
        """解析时间范围"""
        now = datetime.now()
        
        # 时间关键词映射
        time_keywords = {
            "今天": (now.replace(hour=0, minute=0, second=0, microsecond=0), 
                     now.replace(hour=23, minute=59, second=59, microsecond=999999)),
            "昨天": ((now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0),
                     (now - timedelta(days=1)).replace(hour=23, minute=59, second=59, microsecond=999999)),
            "前天": ((now - timedelta(days=2)).replace(hour=0, minute=0, second=0, microsecond=0),
                     (now - timedelta(days=2)).replace(hour=23, minute=59, second=59, microsecond=999999)),
            "本周": (now - timedelta(days=now.weekday()), now + timedelta(days=6-now.weekday())),
            "上周": (now - timedelta(days=now.weekday()+7), now - timedelta(days=now.weekday()+1)),
            "本月": (now.replace(day=1, hour=0, minute=0, second=0, microsecond=0),
                     (now.replace(day=1, hour=23, minute=59, second=59, microsecond=999999) + 
                      timedelta(days=32)).replace(day=1) - timedelta(seconds=1)),
            "上月": ((now.replace(day=1) - timedelta(days=1)).replace(day=1, hour=0, minute=0, second=0, microsecond=0),
                     (now.replace(day=1, hour=23, minute=59, second=59, microsecond=999999) - timedelta(seconds=1))),
        }
        
        # 最近 N 天/周/月
        recent_pattern = r"最近(\d+)(天|周|个月)"
        match = re.search(recent_pattern, query)
        if match:
            num = int(match.group(1))
            unit = match.group(2)
            
            if unit == "天":
                start = now - timedelta(days=num)
            elif unit == "周":
                start = now - timedelta(weeks=num)
            else:  # 个月
                start = now - timedelta(days=num*30)
            
            return {
                "start": start,
                "end": now,
                "original_text": match.group(0)
            }
        
        # 检查时间关键词
        for keyword, (start, end) in time_keywords.items():
            if keyword in query:
                return {
                    "start": start,
                    "end": end,
                    "original_text": keyword
                }
        
        return None
    
    def _parse_people(self, query: str) -> List[str]:
        """解析人物"""
        # 常见的人物关键词
        people_keywords = ["和", "与", "跟", "同"]
        
        people = []
        
        # 简单的人物提取（实际应该用 NER 或 LLM）
        for keyword in people_keywords:
            if keyword in query:
                # 提取关键词后面的人名（简化处理）
                parts = query.split(keyword)
                if len(parts) > 1:
                    # 提取第一个词（假设是人名）
                    name = parts[1].strip().split()[0] if parts[1].strip() else None
                    if name and len(name) <= 4:  # 假设人名不超过 4 个字
                        people.append(name)
        
        return list(set(people))
    
    def _parse_location(self, query: str) -> Optional[str]:
        """解析位置"""
        # 常见的位置关键词
        location_keywords = ["在", "去", "到", "来自"]
        location_suffixes = ["店", "馆", "场", "院", "楼", "室", "厅", "房"]
        
        for keyword in location_keywords:
            if keyword in query:
                parts = query.split(keyword)
                if len(parts) > 1:
                    # 提取关键词后面的位置（简化处理）
                    location_text = parts[1].strip().split()[0] if parts[1].strip() else None
                    
                    if location_text:
                        # 检查是否包含位置后缀
                        for suffix in location_suffixes:
                            if suffix in location_text:
                                # 提取完整的位置名称
                                idx = location_text.index(suffix) + len(suffix)
                                return location_text[:idx]
                        
                        # 如果没有后缀，返回第一个词
                        if len(location_text) <= 6:  # 假设位置名称不超过 6 个字
                            return location_text
        
        return None
    
    def _parse_tags(self, query: str) -> List[str]:
        """解析标签"""
        # 标签关键词映射
        tag_keywords = {
            "社交": ["见面", "聊天", "聚", "会面", "约", "吃饭", "喝咖啡"],
            "工作": ["开会", "项目", "工作", "任务", "报告", "讨论"],
            "学习": ["学习", "读书", "上课", "培训", "考试"],
            "旅行": ["旅行", "旅游", "出差", "去", "玩"],
            "运动": ["运动", "健身", "跑步", "游泳", "打球"],
            "家庭": ["家", "父母", "孩子", "老婆", "老公"],
        }
        
        tags = []
        
        for tag, keywords in tag_keywords.items():
            for keyword in keywords:
                if keyword in query:
                    tags.append(tag)
                    break
        
        return list(set(tags))
    
    def _extract_keywords(self, query: str) -> List[str]:
        """提取关键词"""
        # 移除停用词
        stopwords = set(["的", "了", "在", "是", "我", "有", "和", "就", "不", "人", "都", "一", "一个", "上", "也", "很", "到", "说", "要", "去", "你", "会", "着", "没有", "看", "好", "自己", "这"])
        
        # 简单的分词（实际应该用 jieba 等分词工具）
        words = re.findall(r'[\u4e00-\u9fa5]+', query)
        
        keywords = [w for w in words if w not in stopwords and len(w) >= 2]
        
        return list(set(keywords))[:10]  # 最多返回 10 个关键词
    
    def _determine_intent(self, query: str) -> str:
        """判断查询意图"""
        # 数量意图
        count_keywords = ["多少", "几个", "几次", "数量"]
        if any(kw in query for kw in count_keywords):
            return "query_count"
        
        # 时间意图
        time_keywords = ["什么时候", "哪天", "几点", "时间"]
        if any(kw in query for kw in time_keywords):
            return "query_time"
        
        # 默认：查询内容
        return "query_content"


# 全局查询解析器实例
query_parser = QueryParser()
