import pytest
import sys
import os
from unittest.mock import AsyncMock, patch

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

from src.services.core.relation_service import (
    RelationService,
    RelationType,
)


class TestChineseRelationDetection:
    def setup_method(self):
        self.service = RelationService()

    @pytest.mark.asyncio
    async def test_detect_contradiction_chinese(self):
        is_contradiction, score = await self.service.detect_contradiction(
            new_content="我现在在北京工作",
            existing_content="我在上海工作",
        )
        assert isinstance(is_contradiction, bool)
        assert 0.0 <= score <= 1.0

    @pytest.mark.asyncio
    async def test_detect_contradiction_with_time_markers(self):
        is_contradiction, score = await self.service.detect_contradiction(
            new_content="我现在不喜欢喝咖啡了",
            existing_content="以前我喜欢喝咖啡",
        )
        assert isinstance(is_contradiction, bool)

    @pytest.mark.asyncio
    async def test_detect_topic_similarity(self):
        is_similar, score, topic = await self.service.detect_topic_similarity(
            content1="我喜欢喝咖啡",
            content2="我也喜欢喝茶",
        )
        assert isinstance(is_similar, bool)
        assert 0.0 <= score <= 1.0

    @pytest.mark.asyncio
    async def test_detect_topic_similarity_same_topic(self):
        is_similar, score, topic = await self.service.detect_topic_similarity(
            content1="我在北京工作",
            content2="我在上海工作",
        )
        assert is_similar is True
        assert topic == "工作"

    def test_relation_type_enum(self):
        assert RelationType.UPDATES.value == "updates"
        assert RelationType.EXTENDS.value == "extends"
        assert RelationType.DERIVES.value == "derives"
