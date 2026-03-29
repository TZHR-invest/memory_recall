"""
OpenCode Plugin Integration Tests.
Tests the full flow of OpenCode plugin integration.
"""

import pytest
import sys
import os
from unittest.mock import AsyncMock, patch, MagicMock

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

from src.plugins.opencode.tool import SupermemoryTool
from src.plugins.opencode.context import inject_context, should_inject_context
from src.plugins.opencode.client import OpenCodeClient


class TestOpenCodeClient:
    def test_client_initialization(self):
        client = OpenCodeClient(
            base_url="http://localhost:8000",
            container_tag_prefix="opencode",
        )
        assert client.base_url == "http://localhost:8000"
        assert client.container_tag_prefix == "opencode"

    def test_generate_container_tag_user(self):
        client = OpenCodeClient(container_tag_prefix="opencode")
        tag = client._generate_container_tag(scope="user", user_id="user_001")

        assert tag.startswith("opencode_user_")

    def test_generate_container_tag_project(self):
        client = OpenCodeClient(container_tag_prefix="opencode")
        tag = client._generate_container_tag(scope="project", project_id="proj_001")

        assert tag.startswith("opencode_project_")

    @pytest.mark.asyncio
    async def test_client_add_memory(self):
        client = OpenCodeClient(base_url="http://localhost:8000")

        with patch.object(
            client, "_make_request", new_callable=AsyncMock
        ) as mock_request:
            mock_request.return_value = {"id": "mem_123", "content": "Test"}

            result = await client.add_memory(
                content="Test memory",
                container_tag="test_user",
            )
            assert result["id"] == "mem_123"


class TestSupermemoryTool:
    def test_tool_definition(self):
        tool = SupermemoryTool()
        definition = tool.get_definition()

        assert definition["name"] == "supermemory"
        assert "mode" in definition["parameters"]["properties"]

    @pytest.mark.asyncio
    async def test_add_mode(self):
        tool = SupermemoryTool()

        with patch("src.plugins.opencode.tool.get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client._generate_container_tag = MagicMock(return_value="test_tag")
            mock_client.add_memory = AsyncMock(return_value={"id": "mem_123"})
            mock_get_client.return_value = mock_client

            result = await tool.execute(
                mode="add",
                content="Test memory",
                scope="user",
                type="preference",
            )

            assert result["success"] is True

    @pytest.mark.asyncio
    async def test_search_mode(self):
        tool = SupermemoryTool()

        with patch("src.plugins.opencode.tool.get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client._generate_container_tag = MagicMock(return_value="test_tag")
            mock_client.search = AsyncMock(
                return_value={
                    "results": [{"id": "mem_123", "content": "Test"}],
                    "count": 1,
                }
            )
            mock_get_client.return_value = mock_client

            result = await tool.execute(
                mode="search",
                query="test query",
                scope="user",
            )

            assert result["success"] is True
            assert len(result["results"]) == 1

    @pytest.mark.asyncio
    async def test_profile_mode(self):
        tool = SupermemoryTool()

        with patch("src.plugins.opencode.tool.get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client._generate_container_tag = MagicMock(return_value="test_tag")
            mock_client.get_profile = AsyncMock(
                return_value={
                    "profile": {"static": ["fact1"], "dynamic": []},
                }
            )
            mock_get_client.return_value = mock_client

            result = await tool.execute(mode="profile", scope="user")

            assert result["success"] is True
            assert "profile" in result

    @pytest.mark.asyncio
    async def test_list_mode(self):
        tool = SupermemoryTool()

        with patch("src.plugins.opencode.tool.get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client._generate_container_tag = MagicMock(return_value="test_tag")
            mock_client.list_memories = AsyncMock(
                return_value={
                    "memories": [{"id": "mem_123"}],
                    "count": 1,
                }
            )
            mock_get_client.return_value = mock_client

            result = await tool.execute(mode="list", scope="user", limit=10)

            assert result["success"] is True
            assert len(result["memories"]) == 1

    @pytest.mark.asyncio
    async def test_forget_mode(self):
        tool = SupermemoryTool()

        with patch("src.plugins.opencode.tool.get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.forget_memory = AsyncMock(return_value={"forgotten": True})
            mock_get_client.return_value = mock_client

            result = await tool.execute(mode="forget", memoryId="mem_123")

            assert result["success"] is True


class TestContextInjection:
    def test_should_inject_context_with_keyword(self):
        message = "Remember that I like coffee"
        assert should_inject_context(message) is True

    def test_should_inject_context_without_keyword(self):
        message = "Hello, how are you?"
        assert should_inject_context(message) is False

    def test_should_inject_context_in_code_block(self):
        message = "```remember this```"
        assert should_inject_context(message) is False

    @pytest.mark.asyncio
    async def test_inject_context(self):
        with patch("src.plugins.opencode.context.get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client._generate_container_tag = MagicMock(return_value="test_tag")
            mock_client.get_profile = AsyncMock(
                return_value={
                    "profile": {"static": ["fact1"], "dynamic": []},
                }
            )
            mock_get_client.return_value = mock_client

            result = await inject_context(
                user_id="user_001",
                project_id="proj_001",
                user_message="What do you know?",
            )

            assert result is not None
            assert "[SUPERMEMORY]" in result


class TestPrivacyProtection:
    def test_strip_private_tags(self):
        from src.plugins.opencode.context import strip_private_tags

        content = "Public <private>secret</private> more public"
        result = strip_private_tags(content)

        assert "secret" not in result
        assert "Public" in result
        assert "more public" in result

    def test_is_fully_private(self):
        from src.plugins.opencode.context import is_fully_private

        assert is_fully_private("<private>all content</private>") is True
        assert is_fully_private("some public <private>secret</private>") is False

    @pytest.mark.asyncio
    async def test_add_memory_strips_private(self):
        tool = SupermemoryTool()

        with patch("src.plugins.opencode.tool.get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client._generate_container_tag = MagicMock(return_value="test_tag")
            mock_client.add_memory = AsyncMock(return_value={"id": "mem_123"})
            mock_get_client.return_value = mock_client

            await tool.execute(
                mode="add",
                content="Public <private>secret</private> content",
                scope="user",
            )

            call_args = mock_client.add_memory.call_args
            assert "secret" not in call_args[1]["content"]
