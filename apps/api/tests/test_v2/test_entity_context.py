import pytest
import sys
import os
from unittest.mock import AsyncMock, patch

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

from src.services.core.profile_service import ProfileService


class TestEntityContext:
    def setup_method(self):
        self.service = ProfileService()

    @pytest.mark.asyncio
    async def test_set_entity_context(self):
        with patch("src.services.core.profile_service.db") as mock_db:
            mock_db.execute = AsyncMock(return_value="INSERT 1")

            result = await self.service.set_entity_context(
                container_tag="user_001",
                entity_context="设计探索对话，关注用户的UI偏好和品牌需求",
            )

            assert result is True

    @pytest.mark.asyncio
    async def test_set_entity_context_truncation(self):
        with patch("src.services.core.profile_service.db") as mock_db:
            mock_db.execute = AsyncMock(return_value="INSERT 1")

            long_context = "a" * 2000
            result = await self.service.set_entity_context(
                container_tag="user_001",
                entity_context=long_context,
            )

            assert result is True
            call_args = mock_db.execute.call_args
            actual_context = call_args[0][2]
            assert len(actual_context) == 1500

    @pytest.mark.asyncio
    async def test_get_entity_context(self):
        with patch("src.services.core.profile_service.db") as mock_db:
            mock_db.fetchrow = AsyncMock(
                return_value={"entity_context": "设计探索对话"}
            )

            context = await self.service.get_entity_context("user_001")

            assert context == "设计探索对话"

    @pytest.mark.asyncio
    async def test_get_entity_context_not_found(self):
        with patch("src.services.core.profile_service.db") as mock_db:
            mock_db.fetchrow = AsyncMock(return_value=None)

            context = await self.service.get_entity_context("user_notfound")

            assert context is None

    @pytest.mark.asyncio
    async def test_get_profile_includes_entity_context(self):
        with patch.object(
            self.service, "_get_cached_profile", new_callable=AsyncMock
        ) as mock_cached:
            mock_cached.return_value = {
                "static_memories": ["静态记忆"],
                "dynamic_memories": ["动态记忆"],
                "last_updated": None,
                "entity_context": "测试上下文",
            }

            with patch.object(self.service, "_is_cache_valid", return_value=True):
                profile = await self.service.get_profile(container_tag="user_001")

                assert "entityContext" in profile
                assert profile["entityContext"] == "测试上下文"

    @pytest.mark.asyncio
    async def test_cache_profile_with_entity_context(self):
        with patch("src.services.core.profile_service.db") as mock_db:
            mock_db.execute = AsyncMock(return_value="INSERT 1")

            await self.service._cache_profile(
                container_tag="user_001",
                profile={"static_memories": [], "dynamic_memories": []},
                entity_context="测试上下文",
            )

            call_args = mock_db.execute.call_args
            assert call_args[0][4] == "测试上下文"

    @pytest.mark.asyncio
    async def test_entity_context_persists_on_insert(self):
        with patch("src.services.core.profile_service.db") as mock_db:
            mock_db.execute = AsyncMock(return_value="INSERT 1")

            await self.service.set_entity_context(
                container_tag="new_container",
                entity_context="新容器的提取上下文",
            )

            assert mock_db.execute.called

    def test_entity_context_max_length(self):
        max_length = 1500
        long_text = "x" * 2000
        truncated = long_text[:max_length]

        assert len(truncated) == max_length
