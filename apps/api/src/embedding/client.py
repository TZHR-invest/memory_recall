"""
火山引擎 Embedding 客户端
基于 OpenAI 兼容 API
"""
from typing import List, Optional
from openai import OpenAI
from ..config import settings


class EmbeddingClient:
    """火山引擎 Embedding 客户端"""
    
    def __init__(self):
        """初始化客户端"""
        if not settings.VOLC_API_KEY:
            raise ValueError("VOLC_API_KEY 未配置")
        
        self.client = OpenAI(
            api_key=settings.VOLC_API_KEY,
            base_url=settings.VOLC_API_BASE
        )
        self.model = settings.VOLC_EMBEDDING_MODEL
        self.dimension = 1024  # doubao-embedding-vision-251215 输出 1024 维向量
    
    def embed(self, text: str) -> Optional[List[float]]:
        """
        生成文本的向量表示
        
        Args:
            text: 输入文本
        
        Returns:
            向量列表，失败返回 None
        """
        try:
            response = self.client.embeddings.create(
                model=self.model,
                input=text
            )
            
            return response.data[0].embedding
        except Exception as e:
            print(f"Embedding 生成失败: {e}")
            return None
    
    def embed_batch(self, texts: List[str]) -> Optional[List[List[float]]]:
        """
        批量生成文本的向量表示
        
        Args:
            texts: 输入文本列表
        
        Returns:
            向量列表，失败返回 None
        """
        try:
            response = self.client.embeddings.create(
                model=self.model,
                input=texts
            )
            
            return [item.embedding for item in response.data]
        except Exception as e:
            print(f"批量 Embedding 生成失败: {e}")
            return None


# 全局 Embedding 客户端实例
_embedding_client: Optional[EmbeddingClient] = None


def get_embedding_client() -> EmbeddingClient:
    """获取 Embedding 客户端实例"""
    global _embedding_client
    if _embedding_client is None:
        _embedding_client = EmbeddingClient()
    return _embedding_client
