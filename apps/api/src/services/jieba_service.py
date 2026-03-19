"""
Jieba 分词服务
用于快速提取关键词
"""
import jieba
from typing import List, Set, Optional

# 停用词表
STOP_WORDS: Set[str] = {
    "的", "了", "在", "是", "我", "有", "和", "就",
    "不", "人", "都", "一", "一个", "上", "也", "很",
    "到", "说", "要", "去", "你", "会", "着", "没有",
    "看", "好", "自己", "这", "那", "什么", "怎么",
    "能", "把", "这个", "他", "她", "它", "我们", "你们",
    "他们", "她们", "它们", "谁", "哪", "哪里", "那里",
}

# 地点词库
LOCATION_WORDS: Set[str] = {
    "咖啡店", "办公室", "家里", "郊外", "健身房",
    "公司", "学校", "公园", "商场", "餐厅",
    "医院", "图书馆", "电影院", "银行", "超市",
    "机场", "火车站", "酒店", "体育馆", "博物馆"
}

# 人物关系词
PERSON_WORDS: Set[str] = {
    "家人", "老婆", "老公", "孩子", "父母",
    "同事", "老板", "客户", "朋友",
    "老同学", "同学", "医生", "护士"
}


def extract_keywords(text: str, min_length: int = 2) -> List[str]:
    """
    使用 jieba 分词提取关键词
    
    Args:
        text: 输入文本
        min_length: 最小关键词长度
    
    Returns:
        关键词列表
    """
    words = jieba.cut(text)
    
    keywords = [
        w for w in words
        if len(w) >= min_length  # 长度 >= min_length
        and w not in STOP_WORDS  # 不是停用词
        and not w.isdigit()  # 不是纯数字
        and not w.isspace()  # 不是空白
    ]
    
    # 去重并保持顺序
    seen = set()
    result = []
    for w in keywords:
        if w not in seen:
            seen.add(w)
            result.append(w)
    
    return result


def extract_time_keywords(text: str) -> dict:
    """
    提取时间相关关键词
    
    Args:
        text: 输入文本
    
    Returns:
        时间范围信息
    """
    from datetime import datetime, timedelta
    
    now = datetime.now()
    
    # 时间关键词映射（使用整点时间，避免小数秒问题）
    time_keywords = {
        "今天": (
            now.replace(hour=0, minute=0, second=0, microsecond=0),
            now.replace(hour=23, minute=59, second=59, microsecond=0)
        ),
        "昨天": (
            (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0),
            (now - timedelta(days=1)).replace(hour=23, minute=59, second=59, microsecond=0)
        ),
        "前天": (
            (now - timedelta(days=2)).replace(hour=0, minute=0, second=0, microsecond=0),
            (now - timedelta(days=2)).replace(hour=23, minute=59, second=59, microsecond=0)
        ),
        "最近": (
            (now - timedelta(days=7)).replace(hour=0, minute=0, second=0, microsecond=0),
            now.replace(hour=23, minute=59, second=59, microsecond=0)
        ),
        "本周": (
            (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0),
            (now + timedelta(days=6-now.weekday())).replace(hour=23, minute=59, second=59, microsecond=0)
        ),
        "上周": (
            (now - timedelta(days=now.weekday()+7)).replace(hour=0, minute=0, second=0, microsecond=0),
            (now - timedelta(days=now.weekday()+1)).replace(hour=23, minute=59, second=59, microsecond=0)
        ),
    }
    
    for keyword, (start, end) in time_keywords.items():
        if keyword in text:
            return {
                "start": start,
                "end": end,
                "original_text": keyword
            }
    
    return None


def extract_location(text: str) -> Optional[str]:
    """
    提取地点关键词
    
    Args:
        text: 输入文本
    
    Returns:
        地点名称，未找到返回 None
    """
    for word in LOCATION_WORDS:
        if word in text:
            return word
    return None


def extract_person(text: str) -> Optional[str]:
    """
    提取人物关键词
    
    Args:
        text: 输入文本
    
    Returns:
        人物名称，未找到返回 None
    """
    for word in PERSON_WORDS:
        if word in text:
            return word
    return None