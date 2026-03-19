"""
缓存管理器
提供内存缓存，用于优化 LLM 和 Embedding 调用
"""
import hashlib
import json
import time
from typing import Any, Optional, Dict
from collections import OrderedDict
import threading


class CacheManager:
    """
    缓存管理器
    
    使用 LRU (Least Recently Used) 缓存策略
    支持过期时间和最大缓存大小限制
    """
    
    def __init__(self, max_size: int = 1000, default_ttl: int = 3600):
        """
        初始化缓存管理器
        
        Args:
            max_size: 最大缓存条目数
            default_ttl: 默认过期时间（秒）
        """
        self.max_size = max_size
        self.default_ttl = default_ttl
        self._cache: OrderedDict[str, Dict[str, Any]] = OrderedDict()
        self._lock = threading.RLock()
        
        # 统计信息
        self._hits = 0
        self._misses = 0
    
    def _generate_key(self, *args, **kwargs) -> str:
        """
        生成缓存键
        
        Args:
            *args: 位置参数
            **kwargs: 关键字参数
        
        Returns:
            缓存键（MD5 哈希）
        """
        # 将参数转换为可哈希的字符串
        key_data = {
            "args": args,
            "kwargs": kwargs
        }
        key_str = json.dumps(key_data, sort_keys=True, default=str)
        
        # 生成 MD5 哈希
        return hashlib.md5(key_str.encode()).hexdigest()
    
    def get(self, key: str) -> Optional[Any]:
        """
        获取缓存值
        
        Args:
            key: 缓存键
        
        Returns:
            缓存值，不存在或已过期返回 None
        """
        with self._lock:
            if key not in self._cache:
                self._misses += 1
                return None
            
            entry = self._cache[key]
            
            # 检查是否过期
            if entry["expires_at"] and time.time() > entry["expires_at"]:
                # 删除过期条目
                del self._cache[key]
                self._misses += 1
                return None
            
            # 更新 LRU 顺序
            self._cache.move_to_end(key)
            self._hits += 1
            
            return entry["value"]
    
    def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = None
    ) -> None:
        """
        设置缓存值
        
        Args:
            key: 缓存键
            value: 缓存值
            ttl: 过期时间（秒），None 表示使用默认值
        """
        with self._lock:
            # 计算过期时间
            ttl = ttl if ttl is not None else self.default_ttl
            expires_at = time.time() + ttl if ttl > 0 else None
            
            # 如果键已存在，先删除
            if key in self._cache:
                del self._cache[key]
            
            # 检查是否需要清理
            while len(self._cache) >= self.max_size:
                # 删除最旧的条目
                self._cache.popitem(last=False)
            
            # 添加新条目
            self._cache[key] = {
                "value": value,
                "expires_at": expires_at,
                "created_at": time.time()
            }
    
    def delete(self, key: str) -> bool:
        """
        删除缓存值
        
        Args:
            key: 缓存键
        
        Returns:
            是否成功删除
        """
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                return True
            return False
    
    def clear(self) -> None:
        """清空缓存"""
        with self._lock:
            self._cache.clear()
            self._hits = 0
            self._misses = 0
    
    def stats(self) -> Dict[str, Any]:
        """
        获取缓存统计信息
        
        Returns:
            统计信息字典
        """
        with self._lock:
            total_requests = self._hits + self._misses
            hit_rate = self._hits / total_requests if total_requests > 0 else 0
            
            return {
                "size": len(self._cache),
                "max_size": self.max_size,
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": hit_rate,
                "total_requests": total_requests
            }
    
    # ============ 便捷方法 ============
    
    def cache_llm_result(
        self,
        prompt: str,
        result: Any,
        ttl: Optional[int] = None
    ) -> None:
        """
        缓存 LLM 结果
        
        Args:
            prompt: 提示词
            result: LLM 返回结果
            ttl: 过期时间
        """
        key = self._generate_key("llm", prompt)
        self.set(key, result, ttl)
    
    def get_llm_result(self, prompt: str) -> Optional[Any]:
        """
        获取缓存的 LLM 结果
        
        Args:
            prompt: 提示词
        
        Returns:
            缓存的结果，不存在返回 None
        """
        key = self._generate_key("llm", prompt)
        return self.get(key)
    
    def cache_embedding(
        self,
        text: str,
        embedding: list,
        ttl: Optional[int] = None
    ) -> None:
        """
        缓存 Embedding 结果
        
        Args:
            text: 输入文本
            embedding: 向量表示
            ttl: 过期时间
        """
        key = self._generate_key("embedding", text)
        self.set(key, embedding, ttl)
    
    def get_embedding(self, text: str) -> Optional[list]:
        """
        获取缓存的 Embedding 结果
        
        Args:
            text: 输入文本
        
        Returns:
            缓存的向量，不存在返回 None
        """
        key = self._generate_key("embedding", text)
        return self.get(key)


# 全局缓存管理器实例
cache_manager = CacheManager(
    max_size=1000,
    default_ttl=3600  # 1 小时
)
