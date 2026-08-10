"""
火山引擎 Embedding 客户端
使用火山引擎方舟多模态向量化 API
"""

from typing import List, Optional, Dict, Any
import asyncio
import logging
import httpx

logger = logging.getLogger(__name__)

try:
    from ..config import settings
    from ..cache.manager import cache_manager
except ImportError:
    from config import settings
    from cache.manager import cache_manager


class EmbeddingClient:
    """火山引擎 Embedding 客户端"""

    def __init__(self):
        """初始化客户端"""
        self.api_key = settings.VOLC_API_KEY
        if not self.api_key:
            raise ValueError("VOLC_API_KEY 未配置")

        self.base_url = settings.VOLC_API_BASE
        self.model = "doubao-embedding-vision-251215"
        self.dimension = 1024
        self._client: Optional[httpx.AsyncClient] = None
        self.last_error: Optional[str] = None
        self.last_cache_hit: bool = False

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=30.0)
        return self._client

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None

    async def embed(self, text: str, use_cache: bool = True) -> Optional[List[float]]:
        if use_cache:
            cached = cache_manager.get_embedding(text)
            if cached is not None:
                self.last_cache_hit = True
                return cached
        self.last_cache_hit = False

        try:
            client = await self._get_client()
            url = f"{self.base_url}/embeddings/multimodal"
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }
            payload = {
                "model": self.model,
                "input": [{"type": "text", "text": text}],
                "encoding_format": "float",
                "dimensions": self.dimension,
            }

            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()

            data = response.json()
            if "data" in data:
                if isinstance(data["data"], list):
                    result = data["data"][0]["embedding"]
                else:
                    result = data["data"]["embedding"]

                if use_cache and result:
                    cache_manager.cache_embedding(text, result)

                self.last_error = None
                return result

            return None
        except Exception as e:
            self.last_error = str(e)
            logger.error(f"Embedding 生成失败: {e}")
            return None

    async def embed_batch(self, texts: List[str]) -> Optional[List[List[float]]]:
        """批量生成 embedding。火山引擎多模态端点不支持多输入批量返回，
        改用 asyncio.gather 并行调用单条 embed，利用缓存+并发实现加速。"""
        try:
            results = await asyncio.gather(
                *[self.embed(text, use_cache=True) for text in texts],
                return_exceptions=True,
            )
            embeddings = []
            for i, r in enumerate(results):
                if isinstance(r, Exception):
                    logger.warning(f"embed_batch 第{i}条失败: {r}")
                    embeddings.append(None)
                elif r is None:
                    embeddings.append(None)
                else:
                    embeddings.append(r)
            return embeddings
        except Exception as e:
            logger.error(f"批量 Embedding 生成失败: {e}")
            return None

    async def embed_image(
        self, image_url: str, text: Optional[str] = None
    ) -> Optional[List[float]]:
        try:
            client = await self._get_client()
            url = f"{self.base_url}/embeddings/multimodal"
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }

            inputs = [{"type": "image_url", "image_url": {"url": image_url}}]
            if text:
                inputs.append({"type": "text", "text": text})

            payload = {
                "model": self.model,
                "input": inputs,
                "encoding_format": "float",
                "dimensions": self.dimension,
            }

            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()

            data = response.json()
            if "data" in data:
                if isinstance(data["data"], list):
                    return data["data"][0]["embedding"]
                else:
                    return data["data"]["embedding"]

            return None
        except Exception as e:
            self.last_error = str(e)
            logger.error(f"图片 Embedding 生成失败: {e}")
            return None


_embedding_client: Optional[EmbeddingClient] = None


def get_embedding_client() -> EmbeddingClient:
    """获取 Embedding 客户端实例"""
    global _embedding_client
    if _embedding_client is None:
        _embedding_client = EmbeddingClient()
    return _embedding_client
