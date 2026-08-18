import pytest
import sys
import os
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime, timezone

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

from src.services.core.profile_service import ProfileService


class TestProfileService:
    def setup_method(self):
        self.service = ProfileService()

    @pytest.mark.asyncio
    async def test_get_profile_from_cache(self):
        with patch("src.services.core.profile_service.db") as mock_db:
            mock_db.fetchrow = AsyncMock(
                return_value={
                    "static_memories": ["fact1", "fact2"],
                    "dynamic_memories": ["recent1"],
                    "last_updated": datetime.now(timezone.utc),
                    "entity_context": {},
                }
            )

            with patch.object(self.service, "_is_cache_valid", return_value=True):
                profile = await self.service.get_profile(
                    container_tag="user_001",
                    max_static=10,
                    max_dynamic=10,
                )

            assert profile["profile"]["static"] == ["fact1", "fact2"]
            assert profile["profile"]["dynamic"] == ["recent1"]

    @pytest.mark.asyncio
    async def test_get_profile_with_search(self):
        with patch("src.services.core.profile_service.db") as mock_db:
            mock_db.fetchrow = AsyncMock(
                return_value={
                    "static_memories": ["fact1"],
                    "dynamic_memories": ["recent1"],
                    "last_updated": datetime.now(timezone.utc),
                    "entity_context": {},
                }
            )

            with patch.object(self.service, "_is_cache_valid", return_value=True):
                with patch(
                    "src.services.core.profile_service.memory_store"
                ) as mock_store:
                    mock_store.search = AsyncMock(
                        return_value=[
                            {"id": "mem_1", "content": "test", "similarity": 0.9},
                        ]
                    )

                    profile = await self.service.get_profile(
                        container_tag="user_001",
                        query="test query",
                    )

            assert profile["profile"]["static"] == ["fact1"]
            assert len(profile["searchResults"]) == 1

    @pytest.mark.asyncio
    async def test_invalidate_cache(self):
        with patch("src.services.core.profile_service.db") as mock_db:
            mock_db.execute = AsyncMock(return_value="UPDATE 1")

            await self.service.invalidate_cache("user_001")

            mock_db.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_static_facts(self):
        with patch("src.services.core.profile_service.memory_store") as mock_store:
            mock_memory = MagicMock()
            mock_memory.content = "static fact"
            mock_store.get_static_memories = AsyncMock(return_value=[mock_memory])

            facts = await self.service.get_static_facts("user_001")

            assert facts == ["static fact"]

    @pytest.mark.asyncio
    async def test_get_dynamic_facts(self):
        with patch("src.services.core.profile_service.memory_store") as mock_store:
            mock_memory = MagicMock()
            mock_memory.content = "dynamic fact"
            mock_store.get_dynamic_memories = AsyncMock(return_value=[mock_memory])

            facts = await self.service.get_dynamic_facts("user_001")

            assert facts == ["dynamic fact"]

    def test_is_cache_valid(self):
        cached = {
            "last_updated": datetime.now(timezone.utc),
        }

        result = self.service._is_cache_valid(cached, max_age_minutes=5)

        assert result is True

    def test_is_cache_invalid(self):
        cached = {
            "last_updated": datetime(2020, 1, 1, tzinfo=timezone.utc),
        }

        result = self.service._is_cache_valid(cached, max_age_minutes=5)

        assert result is False

class TestBuildProfileFilter:
    """画像净化（2026-08-18）：_build_profile 过滤 profile_worthy=false 的 static"""

    @pytest.mark.asyncio
    async def test_build_profile_filters_non_profile_static(self):
        """profile_worthy=false 的 static 退出画像缓存，true/无标记保留"""
        from src.services.core.profile_service import ProfileService
        from src.services.core.memory_store import Memory

        svc = ProfileService()
        mems = [
            Memory(id="m1", content="用户喜欢用中文", container_tag="c1", is_static=True,
                   metadata={"profile_worthy": True, "type": "preference"}),
            Memory(id="m2", content="dsh-vision 配置 baseURL", container_tag="c1", is_static=True,
                   metadata={"profile_worthy": False, "type": "learned-pattern"}),
            Memory(id="m3", content="漫剧制作偏好", container_tag="c1", is_static=True,
                   metadata={"type": "preference"}),  # 无标记，默认保留
        ]
        import src.services.core.profile_service as ps_mod
        with patch.object(
            ps_mod.memory_store, "get_static_memories",
            new_callable=AsyncMock, return_value=mems,
        ):
            with patch.object(
                ps_mod.memory_store, "get_dynamic_memories",
                new_callable=AsyncMock, return_value=[],
            ):
                profile = await svc._build_profile("c1", max_static=100, max_dynamic=50)

        assert "用户喜欢用中文" in profile["static_memories"], "profile_worthy=true 应保留"
        assert "dsh-vision 配置 baseURL" not in profile["static_memories"], "profile_worthy=false 应过滤"
        assert "漫剧制作偏好" in profile["static_memories"], "无标记默认保留（尊重 is_static 语义）"
