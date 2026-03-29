import hashlib
from typing import Dict, Any, Optional, List
from src.client import MemoryRecallClient


class OpenCodeClient:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.client = MemoryRecallClient(
            base_url=config.get("baseUrl", "http://localhost:8000"),
            api_key=config.get("apiKey"),
        )
        self.container_tag_prefix = config.get("containerTagPrefix", "opencode")

    def get_user_tag(self, git_email: Optional[str] = None) -> str:
        if self.config.get("userContainerTag"):
            return self.config["userContainerTag"]
        email = git_email or "default"
        hash_val = hashlib.sha256(email.encode()).hexdigest()[:12]
        return f"{self.container_tag_prefix}_user_{hash_val}"

    def get_project_tag(self, directory: str) -> str:
        if self.config.get("projectContainerTag"):
            return self.config["projectContainerTag"]
        hash_val = hashlib.sha256(directory.encode()).hexdigest()[:12]
        return f"{self.container_tag_prefix}_project_{hash_val}"

    async def add(
        self,
        content: str,
        container_tag: str,
        memory_type: Optional[str] = None,
        is_static: bool = False,
    ) -> Dict[str, Any]:
        metadata = {}
        if memory_type:
            metadata["type"] = memory_type
        return await self.client.add_memory(
            content=content,
            container_tag=container_tag,
            metadata=metadata,
            is_static=is_static,
        )

    async def search(
        self,
        query: str,
        container_tag: str,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        return await self.client.search(
            query=query,
            container_tag=container_tag,
            limit=limit,
        )

    async def profile(
        self,
        container_tag: str,
        query: Optional[str] = None,
    ) -> Dict[str, Any]:
        return await self.client.get_profile(
            container_tag=container_tag,
            query=query,
        )

    async def list_memories(
        self,
        container_tag: str,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        return await self.client.list_memories(
            container_tag=container_tag,
            limit=limit,
        )

    async def forget(self, memory_id: str) -> Dict[str, Any]:
        return await self.client.delete_memory(memory_id=memory_id)

    async def close(self):
        await self.client.close()
