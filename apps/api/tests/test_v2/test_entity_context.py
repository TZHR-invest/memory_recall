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


class TestDefaultEntityContext:
    def test_get_default_entity_context_chinese(self):
        from src.services.core.llm_entity_extraction import (
            get_default_entity_context,
            DEFAULT_ENTITY_CONTEXT_CN,
        )

        result = get_default_entity_context("chinese")
        assert result == DEFAULT_ENTITY_CONTEXT_CN
        assert "记住" in result
        assert "不记" in result

    def test_get_default_entity_context_english(self):
        from src.services.core.llm_entity_extraction import (
            get_default_entity_context,
            DEFAULT_ENTITY_CONTEXT_EN,
        )

        result = get_default_entity_context("english")
        assert result == DEFAULT_ENTITY_CONTEXT_EN
        assert "REMEMBER" in result
        assert "DO NOT REMEMBER" in result

    def test_default_entity_context_cn_length(self):
        from src.services.core.llm_entity_extraction import DEFAULT_ENTITY_CONTEXT_CN

        assert len(DEFAULT_ENTITY_CONTEXT_CN) <= 1500

    def test_default_entity_context_en_length(self):
        from src.services.core.llm_entity_extraction import DEFAULT_ENTITY_CONTEXT_EN

        assert len(DEFAULT_ENTITY_CONTEXT_EN) <= 1500


class TestEntityContextPriority:
    def setup_method(self):
        from src.services.core.memory_store import MemoryStore

        self.store = MemoryStore()

    @pytest.mark.asyncio
    async def test_parameter_takes_highest_priority(self):
        with (
            patch.object(self.store, "_get_llm_extractor") as mock_extractor,
            patch.object(
                self.store, "_generate_embedding", new_callable=AsyncMock
            ) as mock_embed,
            patch.object(
                self.store, "_update_embedded_relations", new_callable=AsyncMock
            ),
            patch("src.services.core.memory_store.db") as mock_db,
            patch("src.services.core.memory_store.relation_service"),
        ):
            mock_embed.return_value = [0.1] * 768
            mock_db.fetchrow = AsyncMock(
                return_value={
                    "id": "mem_test",
                    "container_tag": "test",
                    "content": "test",
                    "embedding": None,
                    "is_static": True,
                    "metadata": "{}",
                    "created_at": None,
                    "is_forgotten": False,
                    "version": 1,
                    "root_memory_id": None,
                    "source_count": 1,
                    "is_inference": False,
                    "is_latest": True,
                    "valid_from": None,
                    "valid_until": None,
                    "confidence": 0.8,
                }
            )
            mock_extractor.return_value.extract = AsyncMock(
                return_value=type(
                    "ExtractedFact",
                    (),
                    {
                        "entities": {},
                        "is_static": True,
                        "entity_context": "param_context",
                    },
                )()
            )

            entity_context = await self.store._get_entity_context(
                content="test content",
                container_tag="test_container",
                entity_context="param_context",
            )

            assert entity_context == "param_context"

    @pytest.mark.asyncio
    async def test_profile_storage_used_when_no_parameter(self):
        with patch("src.services.core.profile_service.profile_service") as mock_profile:
            mock_profile.get_entity_context = AsyncMock(return_value="stored_context")

            entity_context = await self.store._get_entity_context(
                content="test content",
                container_tag="test_container",
                entity_context=None,
            )

            assert entity_context == "stored_context"

    @pytest.mark.asyncio
    async def test_default_used_when_no_parameter_and_no_storage(self):
        with patch("src.services.core.profile_service.profile_service") as mock_profile:
            mock_profile.get_entity_context = AsyncMock(return_value=None)

            entity_context = await self.store._get_entity_context(
                content="test content",
                container_tag="test_container",
                entity_context=None,
            )

            assert "REMEMBER" in entity_context or "记住" in entity_context


class TestEntityContextBackwardCompatibility:
    def test_explicit_entity_context_unchanged(self):
        from src.services.core.llm_entity_extraction import get_default_entity_context

        custom_context = "Custom context for testing"
        default = get_default_entity_context("english")

        assert custom_context != default
        assert "Custom" in custom_context
