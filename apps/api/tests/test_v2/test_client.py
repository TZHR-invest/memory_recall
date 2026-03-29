import pytest
import sys
import os
from unittest.mock import AsyncMock, patch, MagicMock

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

from src.client import MemoryRecallClient, SyncMemoryRecallClient


class TestMemoryRecallClient:
    def test_init(self):
        client = MemoryRecallClient(
            base_url="http://localhost:8000",
            api_key="test_key",
        )
        assert client.base_url == "http://localhost:8000"
        assert client.api_key == "test_key"

    def test_base_url_trailing_slash(self):
        client = MemoryRecallClient(base_url="http://localhost:8000/")
        assert client.base_url == "http://localhost:8000"


class TestMemoryRecallClientAsync:
    @pytest.mark.asyncio
    async def test_add_memory(self):
        client = MemoryRecallClient(base_url="http://localhost:8000")

        with patch.object(client, "_get_client") as mock_get_client:
            mock_http_client = MagicMock()
            mock_http_client.post = AsyncMock(
                return_value=MagicMock(
                    json=lambda: {"id": "mem_123"},
                    raise_for_status=lambda: None,
                )
            )
            mock_get_client.return_value = mock_http_client

            result = await client.add_memory(
                content="test content",
                container_tag="user_001",
            )

            assert result["id"] == "mem_123"

    @pytest.mark.asyncio
    async def test_search(self):
        client = MemoryRecallClient(base_url="http://localhost:8000")

        with patch.object(client, "_get_client") as mock_get_client:
            mock_http_client = MagicMock()
            mock_http_client.post = AsyncMock(
                return_value=MagicMock(
                    json=lambda: {"results": [{"id": "mem_1"}]},
                    raise_for_status=lambda: None,
                )
            )
            mock_get_client.return_value = mock_http_client

            results = await client.search(
                query="test query",
                container_tag="user_001",
            )

            assert len(results) == 1

    @pytest.mark.asyncio
    async def test_get_profile(self):
        client = MemoryRecallClient(base_url="http://localhost:8000")

        with patch.object(client, "_get_client") as mock_get_client:
            mock_http_client = MagicMock()
            mock_http_client.get = AsyncMock(
                return_value=MagicMock(
                    json=lambda: {
                        "profile": {
                            "static": ["fact1"],
                            "dynamic": ["recent1"],
                        },
                    },
                    raise_for_status=lambda: None,
                )
            )
            mock_get_client.return_value = mock_http_client

            profile = await client.get_profile(container_tag="user_001")

            assert profile["profile"]["static"] == ["fact1"]


class TestSyncMemoryRecallClient:
    def test_init(self):
        client = SyncMemoryRecallClient(
            base_url="http://localhost:8000",
            api_key="test_key",
        )
        assert client.base_url == "http://localhost:8000"
        assert client.api_key == "test_key"

    def test_add_memory(self):
        client = SyncMemoryRecallClient(base_url="http://localhost:8000")

        with patch.object(client, "_get_client") as mock_get_client:
            mock_http_client = MagicMock()
            mock_http_client.post = MagicMock(
                return_value=MagicMock(
                    json=lambda: {"id": "mem_123"},
                    raise_for_status=lambda: None,
                )
            )
            mock_get_client.return_value = mock_http_client

            result = client.add_memory(
                content="test content",
                container_tag="user_001",
            )

            assert result["id"] == "mem_123"
