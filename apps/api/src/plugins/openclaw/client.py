from typing import Dict, Any, Optional
from src.client import MemoryRecallClient


class OpenClawClient:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.client = MemoryRecallClient(
            base_url=config.get("baseUrl", "http://localhost:8000"),
            api_key=config.get("apiKey"),
        )
        self.container_tag = config.get("containerTag", "openclaw_default")

    async def store(
        self, content: str, container_tag: Optional[str] = None
    ) -> Dict[str, Any]:
        return await self.client.add_memory(
            content=content,
            container_tag=container_tag or self.container_tag,
        )

    async def search(
        self, query: str, limit: int = 5, container_tag: Optional[str] = None
    ) -> list:
        return await self.client.search(
            query=query,
            container_tag=container_tag or self.container_tag,
            limit=limit,
        )

    async def profile(
        self, query: Optional[str] = None, container_tag: Optional[str] = None
    ) -> Dict[str, Any]:
        return await self.client.get_profile(
            container_tag=container_tag or self.container_tag,
            query=query,
        )

    async def forget(
        self, memory_id: str, container_tag: Optional[str] = None
    ) -> Dict[str, Any]:
        return await self.client.delete_memory(
            memory_id=memory_id,
            container_tag=container_tag or self.container_tag,
        )

    async def close(self):
        await self.client.close()
