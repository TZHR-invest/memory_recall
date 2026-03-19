"""
Embedding 缓存服务
"""
import hashlib
from typing import Optional, List, Dict
from collections import OrderedDict


class EmbeddingCache:
    """
    Embedding 缓存服务
    
    使用 LRU（最近最少使用）策略管理缓存
    """
    
    def __init__(self, max_size: int = 1000):
        """
        初始化缓存
        
        Args:
            max_size: 最大缓存数量（默认 1000）
        """
        self.max_size = max_size
        self.cache: OrderedDict[str, List[float]] = OrderedDict()
        self.stats = {
            "hits": 0,
            "misses": 0
        }
    
    def _hash(self, text: str) -> str:
        """
        生成文本的哈希值
        
        Args:
            text: 输入文本
        
        Returns:
            MD5 哈希值
        """
        return hashlib.md5(text.encode('utf-8')).hexdigest()
    
    def get(self, text: str) -> Optional[List[float]]:
        """
        获取缓存的 embedding
        
        Args:
            text: 输入文本
        
        Returns:
            向量列表，未命中返回 None
        """
        key = self._hash(text)
        
        if key in self.cache:
            # 命中：移动到末尾（最近使用）
            self.cache.move_to_end(key)
            self.stats["hits"] += 1
            return self.cache[key]
        
        self.stats["misses"] += 1
        return None
    
    def set(self, text: str, embedding: List[float]) -> None:
        """
        设置缓存
        
        Args:
            text: 输入文本
            embedding: 向量表示
        """
        key = self._hash(text)
        
        # 如果已存在，先删除旧的
        if key in self.cache:
            del self.cache[key]
        
        # 检查缓存大小
        while len(self.cache) >= self.max_size:
            # 删除最旧的（第一个）
            self.cache.popitem(last=False)
        
        # 添加新缓存
        self.cache[key] = embedding
    
    def get_hit_rate(self) -> float:
        """
        获取缓存命中率
        
        Returns:
            命中率（0.0 - 1.0）
        """
        total = self.stats["hits"] + self.stats["misses"]
        if total == 0:
            return 0.0
        return self.stats["hits"] / total
    
    def get_stats(self) -> Dict[str, any]:
        """
        获取缓存统计信息
        
        Returns:
            统计信息字典
        """
        return {
            "size": len(self.cache),
            "max_size": self.max_size,
            "hits": self.stats["hits"],
            "misses": self.stats["misses"],
            "hit_rate": self.get_hit_rate()
        }
    
    def clear(self) -> None:
        """清空缓存"""
        self.cache.clear()
        self.stats = {"hits": 0, "misses": 0}


# 全局缓存实例
_embedding_cache: Optional[EmbeddingCache] = None


def get_embedding_cache(max_size: int = 1000) -> EmbeddingCache:
    """
    获取全局 Embedding 缓存实例
    
    Args:
        max_size: 最大缓存数量
    
    Returns:
        EmbeddingCache 实例
    """
    global _embedding_cache
    if _embedding_cache is None:
        _embedding_cache = EmbeddingCache(max_size)
    return _embedding_cache
