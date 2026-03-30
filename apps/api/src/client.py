"""
Unified client interface for memory recall system.
"""

from typing import Optional, List, Dict, Any
import httpx


class MemoryRecallClient:
    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        api_key: Optional[str] = None,
        timeout: float = 300.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self):
        await self._get_client()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            headers = {}
            if self.api_key:
                headers["X-API-Key"] = self.api_key
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers=headers,
                timeout=self.timeout,
            )
        return self._client

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None

    async def add_memory(
        self,
        content: str,
        container_tag: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        is_static: bool = False,
        skip_extraction: bool = False,
    ) -> Dict[str, Any]:
        client = await self._get_client()
        body = {
            "content": content,
            "is_static": is_static,
            "metadata": metadata or {},
            "skip_extraction": skip_extraction,
        }
        if container_tag:
            body["container_tag"] = container_tag
        response = await client.post("/memories", json=body)
        response.raise_for_status()
        return response.json()

    async def search(
        self,
        query: str,
        container_tag: Optional[str] = None,
        limit: int = 5,
        threshold: float = 0.6,
    ) -> List[Dict[str, Any]]:
        client = await self._get_client()
        body = {
            "query": query,
            "limit": limit,
            "threshold": threshold,
        }
        if container_tag:
            body["container_tag"] = container_tag
        response = await client.post("/search", json=body)
        response.raise_for_status()
        return response.json().get("results", [])

    async def get_profile(
        self,
        container_tag: Optional[str] = None,
        query: Optional[str] = None,
        max_static: int = 10,
        max_dynamic: int = 10,
    ) -> Dict[str, Any]:
        client = await self._get_client()
        params = {
            "max_static": max_static,
            "max_dynamic": max_dynamic,
        }
        if container_tag:
            params["container_tag"] = container_tag
        if query:
            params["query"] = query

        response = await client.get("/profile", params=params)
        response.raise_for_status()
        return response.json()

    async def delete_memory(
        self,
        memory_id: str,
        container_tag: Optional[str] = None,
    ) -> Dict[str, Any]:
        client = await self._get_client()
        response = await client.post(
            f"/memories/{memory_id}/forget",
            json={"container_tag": container_tag} if container_tag else {},
        )
        response.raise_for_status()
        return response.json()

    async def restore_memory(
        self,
        memory_id: str,
        container_tag: Optional[str] = None,
    ) -> Dict[str, Any]:
        client = await self._get_client()
        response = await client.post(
            f"/memories/{memory_id}/restore",
            json={"container_tag": container_tag} if container_tag else {},
        )
        response.raise_for_status()
        return response.json()

    async def list_memories(
        self,
        container_tag: Optional[str] = None,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        client = await self._get_client()
        params = {"limit": limit}
        if container_tag:
            params["container_tag"] = container_tag
        response = await client.get("/memories", params=params)
        response.raise_for_status()
        return response.json().get("memories", [])

    async def get_memory(self, memory_id: str) -> Dict[str, Any]:
        client = await self._get_client()
        response = await client.get(f"/memories/{memory_id}")
        response.raise_for_status()
        return response.json()

    async def update_memory(
        self,
        memory_id: str,
        new_content: str,
    ) -> Dict[str, Any]:
        client = await self._get_client()
        response = await client.post(
            f"/memories/{memory_id}/update",
            json={"content": new_content},
        )
        response.raise_for_status()
        return response.json()

    async def get_history(self, memory_id: str) -> List[Dict[str, Any]]:
        client = await self._get_client()
        response = await client.get(f"/memories/{memory_id}/history")
        response.raise_for_status()
        return response.json().get("history", [])

    async def add_document(
        self,
        content: str,
        title: Optional[str] = None,
        source: Optional[str] = None,
        doc_type: str = "text",
    ) -> Dict[str, Any]:
        client = await self._get_client()
        response = await client.post(
            "/documents",
            json={
                "content": content,
                "title": title,
                "source": source,
                "doc_type": doc_type,
            },
        )
        response.raise_for_status()
        return response.json()

    async def list_documents(
        self,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        client = await self._get_client()
        response = await client.get("/documents", params={"limit": limit})
        response.raise_for_status()
        return response.json().get("documents", [])


class SyncMemoryRecallClient:
    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        api_key: Optional[str] = None,
        timeout: float = 30.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self._client: Optional[httpx.Client] = None

    def _get_client(self) -> httpx.Client:
        if self._client is None:
            headers = {}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
            self._client = httpx.Client(
                base_url=self.base_url,
                headers=headers,
                timeout=self.timeout,
            )
        return self._client

    def close(self):
        if self._client:
            self._client.close()
            self._client = None

    def add_memory(
        self,
        content: str,
        container_tag: str,
        metadata: Optional[Dict[str, Any]] = None,
        is_static: bool = False,
    ) -> Dict[str, Any]:
        client = self._get_client()
        response = client.post(
            "/memories",
            json={
                "content": content,
                "container_tag": container_tag,
                "is_static": is_static,
                "metadata": metadata or {},
            },
        )
        response.raise_for_status()
        return response.json()

    def search(
        self,
        query: str,
        container_tag: str,
        limit: int = 5,
        threshold: float = 0.6,
    ) -> List[Dict[str, Any]]:
        client = self._get_client()
        response = client.post(
            "/search",
            json={
                "query": query,
                "container_tag": container_tag,
                "limit": limit,
                "threshold": threshold,
            },
        )
        response.raise_for_status()
        return response.json().get("results", [])

    def get_profile(
        self,
        container_tag: str,
        query: Optional[str] = None,
        max_static: int = 10,
        max_dynamic: int = 10,
    ) -> Dict[str, Any]:
        client = self._get_client()
        params = {
            "container_tag": container_tag,
            "max_static": max_static,
            "max_dynamic": max_dynamic,
        }
        if query:
            params["query"] = query

        response = client.get("/profile", params=params)
        response.raise_for_status()
        return response.json()

    def list_memories(
        self,
        container_tag: str,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        client = self._get_client()
        response = client.get(
            "/memories",
            params={
                "container_tag": container_tag,
                "limit": limit,
            },
        )
        response.raise_for_status()
        return response.json().get("memories", [])
