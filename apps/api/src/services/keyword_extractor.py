"""
关键词提取器
支持 jieba 分词和 LLM 提取两种方式
"""
import jieba
import jieba.analyse
from typing import List, Dict, Any, Optional


class KeywordExtractor:
    """关键词提取器"""
    
    def __init__(self):
        """初始化"""
        # 加载停用词
        self.stop_words = set([
            "的", "了", "在", "是", "我", "有", "和", "就",
            "不", "人", "都", "一", "一个", "上", "也", "很",
            "到", "说", "要", "去", "你", "会", "着", "没有",
            "看", "好", "自己", "这", "那", "什么", "怎么"
        ])
    
    def extract_jieba(self, text: str, top_k: int = 10) -> List[str]:
        """
        使用 jieba TF-IDF 提取关键词
        
        Args:
            text: 输入文本
            top_k: 返回关键词数量
        
        Returns:
            关键词列表
        """
        # 使用 TF-IDF 算法提取关键词
        keywords = jieba.analyse.extract_tags(text, topK=top_k, withWeight=False)
        return keywords
    
    def extract_jieba_cut(self, text: str) -> List[str]:
        """
        使用 jieba 分词 + 过滤
        
        Args:
            text: 输入文本
        
        Returns:
            关键词列表
        """
        # 分词
        words = jieba.cut(text)
        
        # 过滤
        keywords = [
            w for w in words
            if len(w) >= 2  # 长度 >= 2
            and w not in self.stop_words  # 不是停用词
            and not w.isdigit()  # 不是纯数字
        ]
        
        return list(set(keywords))  # 去重


# 全局实例
keyword_extractor: Optional[KeywordExtractor] = None


def get_keyword_extractor() -> KeywordExtractor:
    """获取关键词提取器实例"""
    global keyword_extractor
    if keyword_extractor is None:
        keyword_extractor = KeywordExtractor()
    return keyword_extractor
