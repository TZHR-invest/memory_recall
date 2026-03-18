"""
火山引擎 Embedding 客户端
使用 LAS 服务多模态向量化 API
"""
from typing import List, Optional, Dict, Any
import requests
from ..config import settings


class EmbeddingClient:
    """火山引擎 Embedding 客户端"""
    
    def __init__(self):
        """初始化客户端"""
        # 优先使用 LAS API Key，否则使用 volc API Key
        self.api_key = settings.LAS_API_KEY or settings.VOLC_API_KEY
        if not self.api_key:
            raise ValueError("LAS_API_KEY 或 VOLC_API_KEY 未配置")
        
        # 使用 LAS 服务端点
        self.base_url = settings.LAS_API_BASE
        self.model = settings.LAS_EMBEDDING_MODEL
        self.dimension = 2048  # doubao-embedding-vision-250615 支持 1024 或 2048
    
    def embed(self, text: str) -> Optional[List[float]]:
        """
        生成文本的向量表示
        
        Args:
            text: 输入文本
        
        Returns:
            向量列表，失败返回 None
        """
        try:
            url = f"{self.base_url}/embeddings/multimodal"
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": self.model,
                "encoding_format": "float",
                "dimensions": self.dimension,
                "input": [
                    {
                        "type": "text",
                        "text": text
                    }
                ]
            }
            
            response = requests.post(url, json=payload, headers=headers, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            if 'data' in data:
                # 处理单个或多个结果
                if isinstance(data['data'], list):
                    return data['data'][0]['embedding']
                else:
                    return data['data']['embedding']
            
            print(f"Embedding 生成失败: 响应格式错误")
            return None
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
            url = f"{self.base_url}/embeddings/multimodal"
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            # 构造输入
            inputs = [{"type": "text", "text": text} for text in texts]
            payload = {
                "model": self.model,
                "encoding_format": "float",
                "dimensions": self.dimension,
                "input": inputs
            }
            
            response = requests.post(url, json=payload, headers=headers, timeout=60)
            response.raise_for_status()
            
            data = response.json()
            if 'data' in data:
                if isinstance(data['data'], list):
                    return [item['embedding'] for item in data['data']]
                else:
                    return [data['data']['embedding']]
            
            print(f"批量 Embedding 生成失败: 响应格式错误")
            return None
        except Exception as e:
            print(f"批量 Embedding 生成失败: {e}")
            return None
    
    def embed_image(self, image_url: str, text: Optional[str] = None) -> Optional[List[float]]:
        """
        生成图片（或图文）的向量表示
        
        Args:
            image_url: 图片 URL
            text: 可选的文本描述
        
        Returns:
            向量列表，失败返回 None
        """
        try:
            url = f"{self.base_url}/embeddings/multimodal"
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            # 构造输入
            inputs = [
                {
                    "type": "image_url",
                    "image_url": {"url": image_url}
                }
            ]
            if text:
                inputs.append({"type": "text", "text": text})
            
            payload = {
                "model": self.model,
                "encoding_format": "float",
                "dimensions": self.dimension,
                "input": inputs
            }
            
            response = requests.post(url, json=payload, headers=headers, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            if 'data' in data:
                if isinstance(data['data'], list):
                    return data['data'][0]['embedding']
                else:
                    return data['data']['embedding']
            
            return None
        except Exception as e:
            print(f"图片 Embedding 生成失败: {e}")
            return None


# 全局 Embedding 客户端实例
_embedding_client: Optional[EmbeddingClient] = None


def get_embedding_client() -> EmbeddingClient:
    """获取 Embedding 客户端实例"""
    global _embedding_client
    if _embedding_client is None:
        _embedding_client = EmbeddingClient()
    return _embedding_client
