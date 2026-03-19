"""
查询解析模块
支持自然语言查询解析，提取时间、地点、人物、情绪等信息
"""
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
import re
import json


class QueryParser:
    """查询解析器"""
    
    def __init__(self):
        """初始化查询解析器"""
        # 时间关键词映射
        self.time_keywords = {
            "今天": self._get_today,
            "昨天": self._get_yesterday,
            "前天": self._get_day_before_yesterday,
            "本周": self._get_this_week,
            "上周": self._get_last_week,
            "本月": self._get_this_month,
            "上月": self._get_last_month,
            "最近": self._get_recent,
            "最近几天": lambda: self._get_recent_days(3),
            "最近一周": lambda: self._get_recent_days(7),
            "最近半个月": lambda: self._get_recent_days(15),
            "最近一个月": lambda: self._get_recent_days(30),
        }
        
        # 情绪关键词映射
        self.emotion_keywords = {
            "开心": ["开心", "高兴", "快乐", "愉快", "兴奋", "满意"],
            "伤心": ["伤心", "难过", "悲伤", "沮丧", "失落", "心痛"],
            "愤怒": ["愤怒", "生气", "恼火", "不满", "烦躁"],
            "焦虑": ["焦虑", "紧张", "担心", "不安", "恐惧"],
            "平静": ["平静", "放松", "安宁", "淡然"],
        }
        
        # 地点关键词
        self.location_keywords = ["在", "去", "到", "来自", "于"]
        self.location_suffixes = ["店", "馆", "场", "院", "楼", "室", "厅", "房", "园", "街", "路"]
        
        # 人物关键词
        self.people_keywords = ["和", "与", "跟", "同", "一起"]
        
        # 标签关键词映射
        self.tag_keywords = {
            "社交": ["见面", "聊天", "聚", "会面", "约", "吃饭", "喝咖啡", "聚会"],
            "工作": ["开会", "项目", "工作", "任务", "报告", "讨论", "加班"],
            "学习": ["学习", "读书", "上课", "培训", "考试", "复习"],
            "旅行": ["旅行", "旅游", "出差", "游玩", "度假"],
            "运动": ["运动", "健身", "跑步", "游泳", "打球", "锻炼"],
            "家庭": ["家", "父母", "孩子", "老婆", "老公", "家人"],
            "购物": ["购物", "买", "逛街", "网购"],
            "娱乐": ["看电影", "游戏", "娱乐", "唱歌", "KTV"],
        }
    
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
            "emotion": None,
            "tags": [],
            "keywords": [],
            "intent": "query_content"
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
        
        # 解析情绪
        emotion = self._parse_emotion(query)
        if emotion:
            result["emotion"] = emotion
        
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
        
        # 最近 N 天/周/月
        recent_pattern = r"最近(\d+)(天|周|个月|月)"
        match = re.search(recent_pattern, query)
        if match:
            num = int(match.group(1))
            unit = match.group(2)
            
            if unit == "天":
                start = now - timedelta(days=num)
            elif unit == "周":
                start = now - timedelta(weeks=num)
            else:  # 个月/月
                start = now - timedelta(days=num * 30)
            
            return {
                "start": start,
                "end": now,
                "original_text": match.group(0),
                "type": "recent"
            }
        
        # 检查固定时间关键词
        for keyword, time_func in self.time_keywords.items():
            if keyword in query:
                try:
                    start, end = time_func()
                    return {
                        "start": start,
                        "end": end,
                        "original_text": keyword,
                        "type": "keyword"
                    }
                except:
                    continue
        
        # 解析具体日期（例如：2024-01-01, 1月1日, 1月1号）
        date_patterns = [
            r'(\d{4})[年\-/](\d{1,2})[月\-/](\d{1,2})[日号]?',  # 2024年1月1日
            r'(\d{1,2})[月\-/](\d{1,2})[日号]?',  # 1月1日
        ]
        
        for pattern in date_patterns:
            match = re.search(pattern, query)
            if match:
                groups = match.groups()
                if len(groups) == 3:
                    year, month, day = int(groups[0]), int(groups[1]), int(groups[2])
                else:
                    year = now.year
                    month, day = int(groups[0]), int(groups[1])
                
                try:
                    start = datetime(year, month, day, 0, 0, 0)
                    end = datetime(year, month, day, 23, 59, 59)
                    return {
                        "start": start,
                        "end": end,
                        "original_text": match.group(0),
                        "type": "specific_date"
                    }
                except:
                    continue
        
        return None
    
    def _parse_people(self, query: str) -> List[str]:
        """解析人物"""
        people = []
        
        # 人物称呼模式（前置词 + 人物类型）
        person_prefixes = ["老", "小", "大", "阿"]
        person_types = ["同学", "朋友", "同事", "老板", "领导", "客户", "家人", "亲戚", "邻居"]
        
        # 动词停用词（这些词后面通常不是人名）
        verb_stopwords = ["见面", "吃饭", "聊天", "开会", "讨论", "工作", "学习", "聚", "约", "汇报", "商量"]
        
        # 副词/后缀词（这些词紧跟在人名后面，需要去除）
        suffix_words = ["一起", "一同", "共同"]
        
        # 主要人物连接词（按优先级排序）
        main_connectors = ["和", "与", "跟", "同"]
        
        # 优先使用主要连接词
        for keyword in main_connectors:
            if keyword in query:
                # 分割句子
                parts = query.split(keyword, 1)  # 只分割一次
                if len(parts) > 1:
                    # 提取关键词后面的词（假设是人名）
                    next_part = parts[1].strip()
                    
                    # 去除副词后缀
                    for suffix in suffix_words:
                        if next_part.startswith(suffix):
                            next_part = next_part[len(suffix):].strip()
                    
                    # 尝试匹配称呼模式（老同学、小李、大客户等）
                    for prefix in person_prefixes:
                        for ptype in person_types:
                            pattern = prefix + ptype
                            if next_part.startswith(pattern):
                                people.append(pattern)
                                return list(set(people))
                    
                    # 尝试匹配单纯人物类型（同学、朋友等）
                    for ptype in person_types:
                        if next_part.startswith(ptype):
                            people.append(ptype)
                            return list(set(people))
                    
                    # 提取第一个词（假设是人名）
                    # 使用更精确的分词：按空格、标点、动词分词
                    words = re.split(r'[\s，。！？、]|' + '|'.join(verb_stopwords), next_part)
                    words = [w.strip() for w in words if w.strip()]
                    
                    if words:
                        name = words[0]
                        # 检查是否包含动词，如果包含则截取
                        for verb in verb_stopwords:
                            if verb in name:
                                name = name.split(verb)[0]
                                break
                        
                        # 检查是否以副词结尾，如果是则去除
                        for suffix in suffix_words:
                            if name.endswith(suffix):
                                name = name[:-len(suffix)]
                        
                        # 假设人名不超过 4 个字
                        if len(name) <= 4 and len(name) >= 2:
                            people.append(name)
        
        return list(set(people))
    
    def _parse_location(self, query: str) -> Optional[str]:
        """解析位置"""
        for keyword in self.location_keywords:
            if keyword in query:
                parts = query.split(keyword)
                if len(parts) > 1:
                    # 提取关键词后面的位置
                    location_text = parts[1].strip()
                    words = re.findall(r'[\u4e00-\u9fa5]+', location_text)
                    
                    if words:
                        # 提取可能的位置名称
                        location_name = words[0]
                        
                        # 检查是否包含位置后缀
                        for suffix in self.location_suffixes:
                            if suffix in location_name:
                                # 提取完整的位置名称
                                idx = location_name.index(suffix) + len(suffix)
                                return location_name[:idx]
                        
                        # 如果没有后缀，返回第一个词
                        if len(location_name) <= 6:  # 假设位置名称不超过 6 个字
                            return location_name
        
        return None
    
    def _parse_emotion(self, query: str) -> Optional[str]:
        """解析情绪"""
        for emotion, keywords in self.emotion_keywords.items():
            for keyword in keywords:
                if keyword in query:
                    return emotion
        
        return None
    
    def _parse_tags(self, query: str) -> List[str]:
        """解析标签"""
        tags = []
        
        for tag, keywords in self.tag_keywords.items():
            for keyword in keywords:
                if keyword in query:
                    tags.append(tag)
                    break
        
        return list(set(tags))
    
    def _extract_keywords(self, query: str) -> List[str]:
        """提取关键词"""
        # 停用词
        stopwords = set([
            "的", "了", "在", "是", "我", "有", "和", "就", "不", "人", "都", "一", "一个",
            "上", "也", "很", "到", "说", "要", "去", "你", "会", "着", "没有", "看", "好",
            "自己", "这", "那", "什么", "怎么", "为什么", "哪", "哪天", "几点", "多少"
        ])
        
        # 提取中文词汇
        words = re.findall(r'[\u4e00-\u9fa5]+', query)
        
        # 过滤停用词和短词
        keywords = [w for w in words if w not in stopwords and len(w) >= 2]
        
        # 去重并限制数量
        return list(set(keywords))[:10]
    
    def _determine_intent(self, query: str) -> str:
        """判断查询意图"""
        # 数量意图
        count_keywords = ["多少", "几个", "几次", "数量"]
        if any(kw in query for kw in count_keywords):
            return "query_count"
        
        # 时间意图
        time_keywords = ["什么时候", "哪天", "几点", "时间", "日期"]
        if any(kw in query for kw in time_keywords):
            return "query_time"
        
        # 地点意图
        location_keywords = ["在哪", "哪里", "什么地方"]
        if any(kw in query for kw in location_keywords):
            return "query_location"
        
        # 人物意图
        people_keywords = ["谁", "和谁", "跟谁"]
        if any(kw in query for kw in people_keywords):
            return "query_people"
        
        # 总结意图
        summary_keywords = ["总结", "概括", "回顾", "梳理"]
        if any(kw in query for kw in summary_keywords):
            return "summary"
        
        # 默认：查询内容
        return "query_content"
    
    # 时间范围计算函数
    def _get_today(self):
        """获取今天的时间范围"""
        now = datetime.now()
        return (
            now.replace(hour=0, minute=0, second=0, microsecond=0),
            now.replace(hour=23, minute=59, second=59, microsecond=999999)
        )
    
    def _get_yesterday(self):
        """获取昨天的时间范围"""
        now = datetime.now()
        yesterday = now - timedelta(days=1)
        return (
            yesterday.replace(hour=0, minute=0, second=0, microsecond=0),
            yesterday.replace(hour=23, minute=59, second=59, microsecond=999999)
        )
    
    def _get_day_before_yesterday(self):
        """获取前天的时间范围"""
        now = datetime.now()
        day_before = now - timedelta(days=2)
        return (
            day_before.replace(hour=0, minute=0, second=0, microsecond=0),
            day_before.replace(hour=23, minute=59, second=59, microsecond=999999)
        )
    
    def _get_this_week(self):
        """获取本周的时间范围"""
        now = datetime.now()
        start = now - timedelta(days=now.weekday())
        end = now + timedelta(days=6 - now.weekday())
        return (
            start.replace(hour=0, minute=0, second=0, microsecond=0),
            end.replace(hour=23, minute=59, second=59, microsecond=999999)
        )
    
    def _get_last_week(self):
        """获取上周的时间范围"""
        now = datetime.now()
        start = now - timedelta(days=now.weekday() + 7)
        end = now - timedelta(days=now.weekday() + 1)
        return (
            start.replace(hour=0, minute=0, second=0, microsecond=0),
            end.replace(hour=23, minute=59, second=59, microsecond=999999)
        )
    
    def _get_this_month(self):
        """获取本月的时间范围"""
        now = datetime.now()
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        # 下个月的第一天
        if now.month == 12:
            end = now.replace(year=now.year + 1, month=1, day=1) - timedelta(seconds=1)
        else:
            end = now.replace(month=now.month + 1, day=1) - timedelta(seconds=1)
        return (start, end)
    
    def _get_last_month(self):
        """获取上月的时间范围"""
        now = datetime.now()
        if now.month == 1:
            start = now.replace(year=now.year - 1, month=12, day=1, hour=0, minute=0, second=0, microsecond=0)
        else:
            start = now.replace(month=now.month - 1, day=1, hour=0, minute=0, second=0, microsecond=0)
        
        end = now.replace(day=1, hour=23, minute=59, second=59, microsecond=999999) - timedelta(seconds=1)
        return (start, end)
    
    def _get_recent(self):
        """获取最近的时间范围（默认 7 天）"""
        return self._get_recent_days(7)
    
    def _get_recent_days(self, days: int):
        """获取最近 N 天的时间范围"""
        now = datetime.now()
        start = now - timedelta(days=days)
        return (
            start.replace(hour=0, minute=0, second=0, microsecond=0),
            now
        )


# 全局查询解析器实例
query_parser = QueryParser()
