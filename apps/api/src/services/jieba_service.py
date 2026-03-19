"""
Jieba 分词服务
用于快速提取关键词
"""
import jieba
from typing import List, Set

# 停用词表
STOP_WORDS: Set[str] = {
    "的", "了", "在", "是", "我", "有", "和", "就",
    "不", "人", "都", "一", "一个", "上", "也", "很",
    "到", "说", "要", "去", "你", "会", "着", "没有",
    "看", "好", "自己", "这", "那", "什么", "怎么",
    "能", "把", "这个", "他", "她", "它", "我们", "你们",
    "他们", "她们", "它们", "谁", "哪", "哪里", "那里",
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
    
    # 时间关键词映射
    time_keywords = {
        "今天": (now.replace(hour=0, minute=0, second=0), now.replace(hour=23, minute=59, second=59)),
        "昨天": ((now - timedelta(days=1)).replace(hour=0, minute=0, second=0), 
                 (now - timedelta(days=1)).replace(hour=23, minute=59, second=59)),
        "前天": ((now - timedelta(days=2)).replace(hour=0, minute=0, second=0),
                 (now - timedelta(days=2)).replace(hour=23, minute=59, second=59)),
        "最近": (now - timedelta(days=7), now),
        "本周": (now - timedelta(days=now.weekday()), now + timedelta(days=6-now.weekday())),
        "上周": (now - timedelta(days=now.weekday()+7), now - timedelta(days=now.weekday()+1)),
    }
    
    for keyword, (start, end) in time_keywords.items():
        if keyword in text:
            return {
                "start": start,
                "end": end,
                "original_text": keyword
            }
    
    return None