"""
OpenClaw Plugin Integration Tests.
Tests the full flow of OpenClaw plugin integration.
"""

import pytest
import sys
import os
from unittest.mock import AsyncMock, patch, MagicMock

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

from src.plugins.openclaw.client import OpenClawClient
from src.plugins.openclaw.tools import (
    MemoryStoreTool,
    MemorySearchTool,
    MemoryProfileTool,
    MemoryForgetTool,
)
from src.plugins.openclaw.hooks import before_agent_start, agent_end


class TestOpenClawClient:
    def test_client_initialization(self):
        client = OpenClawClient(
            base_url="http://localhost:8000",
            container_tag="test_user",
        )
        assert client.base_url == "http://localhost:8000"
        assert client.container_tag == "test_user"

    @pytest.mark.asyncio
    async def test_client_add_memory(self):
        client = OpenClawClient(
            base_url="http://localhost:8000",
            container_tag="test_user",
        )

        with patch.object(
            client, "_make_request", new_callable=AsyncMock
        ) as mock_request:
            mock_request.return_value = {
                "id": "mem_test123",
                "content": "Test memory",
                "container_tag": "test_user",
            }

            result = await client.add_memory("Test memory", is_static=True)
            assert result["id"] == "mem_test123"


class TestMemoryStoreTool:
    def test_tool_definition(self):
        tool = MemoryStoreTool()
        definition = tool.get_definition()

        assert definition["name"] == "memory_store"
        assert "content" in definition["parameters"]["properties"]
        assert "containerTag" in definition["parameters"]["properties"]

    @pytest.mark.asyncio
    async def test_tool_execute(self):
        tool = MemoryStoreTool()

        with patch("src.plugins.openclaw.tools.get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.add_memory = AsyncMock(
                return_value={"id": "mem_123", "content": "Test"}
            )
            mock_get_client.return_value = mock_client

            result = await tool.execute(content="Test memory", containerTag="user_001")

            assert result["success"] is True
            assert "memory" in result


class TestMemorySearchTool:
    def test_tool_definition(self):
        tool = MemorySearchTool()
        definition = tool.get_definition()

        assert definition["name"] == "memory_search"
        assert "query" in definition["parameters"]["properties"]

    @pytest.mark.asyncio
    async def test_tool_execute(self):
        tool = MemorySearchTool()

        with patch("src.plugins.openclaw.tools.get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.search = AsyncMock(
                return_value={
                    "results": [
                        {"id": "mem_123", "content": "Test", "similarity": 0.9}
                    ],
                    "count": 1,
                }
            )
            mock_get_client.return_value = mock_client

            result = await tool.execute(query="test query", containerTag="user_001")

            assert result["success"] is True
            assert len(result["results"]) == 1


class TestMemoryProfileTool:
    def test_tool_definition(self):
        tool = MemoryProfileTool()
        definition = tool.get_definition()

        assert definition["name"] == "memory_profile"

    @pytest.mark.asyncio
    async def test_tool_execute(self):
        tool = MemoryProfileTool()

        with patch("src.plugins.openclaw.tools.get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.get_profile = AsyncMock(
                return_value={
                    "profile": {
                        "static": ["fact1"],
                        "dynamic": ["fact2"],
                    },
                }
            )
            mock_get_client.return_value = mock_client

            result = await tool.execute(containerTag="user_001")

            assert result["success"] is True
            assert "profile" in result


class TestMemoryForgetTool:
    def test_tool_definition(self):
        tool = MemoryForgetTool()
        definition = tool.get_definition()

        assert definition["name"] == "memory_forget"
        assert "memoryId" in definition["parameters"]["properties"]

    @pytest.mark.asyncio
    async def test_tool_execute(self):
        tool = MemoryForgetTool()

        with patch("src.plugins.openclaw.tools.get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.forget_memory = AsyncMock(return_value={"forgotten": True})
            mock_get_client.return_value = mock_client

            result = await tool.execute(memoryId="mem_123")

            assert result["success"] is True


class TestBeforeAgentStartHook:
    @pytest.mark.asyncio
    async def test_hook_auto_recall(self):
        config = {
            "containerTag": "user_001",
            "autoRecall": True,
            "maxRecallResults": 5,
        }

        with patch("src.plugins.openclaw.hooks.get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.get_profile = AsyncMock(
                return_value={
                    "profile": {"static": ["fact1"], "dynamic": []},
                }
            )
            mock_client.search = AsyncMock(
                return_value={
                    "results": [{"content": "result1"}],
                }
            )
            mock_get_client.return_value = mock_client

            context = await before_agent_start(
                config=config,
                user_message="What do you know about me?",
            )

            assert context is not None
            assert "fact1" in context or "User Profile" in context

    @pytest.mark.asyncio
    async def test_hook_disabled(self):
        config = {
            "containerTag": "user_001",
            "autoRecall": False,
        }

        context = await before_agent_start(config=config, user_message="Hello")

        assert context is None


class TestAgentEndHook:
    @pytest.mark.asyncio
    async def test_hook_auto_capture(self):
        config = {
            "containerTag": "user_001",
            "autoCapture": True,
        }

        conversation = [
            {"role": "user", "content": "I like coffee"},
            {"role": "assistant", "content": "I'll remember that"},
        ]

        with patch("src.plugins.openclaw.hooks.get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.add_memory = AsyncMock(return_value={"id": "mem_123"})
            mock_get_client.return_value = mock_client

            await agent_end(config=config, conversation=conversation)

            mock_client.add_memory.assert_called_once()

    @pytest.mark.asyncio
    async def test_hook_disabled(self):
        config = {
            "containerTag": "user_001",
            "autoCapture": False,
        }

        conversation = [
            {"role": "user", "content": "Hello"},
        ]

        with patch("src.plugins.openclaw.hooks.get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_get_client.return_value = mock_client

            await agent_end(config=config, conversation=conversation)

            mock_client.add_memory.assert_not_called()
