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
    CHINESE_UPDATE_MARKERS,
    CHINESE_EXTEND_MARKERS,
    CHINESE_DERIVE_MARKERS,
)


class TestChineseRelationDetection:
    def setup_method(self):
        self.service = RelationService()

    def test_chinese_update_markers_defined(self):
        assert "现在" in CHINESE_UPDATE_MARKERS
        assert "改" in CHINESE_UPDATE_MARKERS
        assert "换成" in CHINESE_UPDATE_MARKERS
        assert "不再" in CHINESE_UPDATE_MARKERS

    def test_chinese_extend_markers_defined(self):
        assert "而且" in CHINESE_EXTEND_MARKERS
        assert "另外" in CHINESE_EXTEND_MARKERS
        assert "还有" in CHINESE_EXTEND_MARKERS

    def test_chinese_derive_markers_defined(self):
        assert "所以" in CHINESE_DERIVE_MARKERS
        assert "因此" in CHINESE_DERIVE_MARKERS
        assert "可以推断" in CHINESE_DERIVE_MARKERS

    def test_detect_update_marker_now(self):
        rel_type, confidence = self.service.detect_relation_type_by_markers(
            new_content="我现在在Supermemory工作",
            existing_content="我在Google工作",
        )
        assert rel_type == RelationType.UPDATES.value
        assert confidence >= 0.7

    def test_detect_update_marker_change(self):
        rel_type, confidence = self.service.detect_relation_type_by_markers(
            new_content="我改用Python了",
            existing_content="我用Java",
        )
        assert rel_type == RelationType.UPDATES.value

    def test_detect_update_marker_no_longer(self):
        rel_type, confidence = self.service.detect_relation_type_by_markers(
            new_content="我不再喝咖啡了",
            existing_content="我喜欢喝咖啡",
        )
        assert rel_type == RelationType.UPDATES.value

    def test_detect_extend_marker_also(self):
        rel_type, confidence = self.service.detect_relation_type_by_markers(
            new_content="我喜欢喝咖啡，而且喜欢喝茶",
            existing_content="我喜欢喝咖啡",
        )
        assert rel_type == RelationType.EXTENDS.value

    def test_detect_extend_marker_additionally(self):
        rel_type, confidence = self.service.detect_relation_type_by_markers(
            new_content="另外我还喜欢看书",
            existing_content="我喜欢喝咖啡",
        )
        assert rel_type == RelationType.EXTENDS.value

    def test_detect_derive_marker_therefore(self):
        rel_type, confidence = self.service.detect_relation_type_by_markers(
            new_content="所以我可以推断他喜欢技术",
            existing_content="他是一个程序员",
        )
        assert rel_type == RelationType.DERIVES.value

    def test_detect_derive_marker_conclude(self):
        rel_type, confidence = self.service.detect_relation_type_by_markers(
            new_content="因此我们可以看出他的偏好",
            existing_content="他每天都喝咖啡",
        )
        assert rel_type == RelationType.DERIVES.value

    def test_calculate_relation_confidence_updates(self):
        confidence = self.service.calculate_relation_confidence(
            relation_type=RelationType.UPDATES.value,
            new_content="我现在在北京工作",
            existing_content="我在上海工作",
        )
        assert 0.5 <= confidence <= 1.0

    def test_calculate_relation_confidence_extends(self):
        confidence = self.service.calculate_relation_confidence(
            relation_type=RelationType.EXTENDS.value,
            new_content="而且我还喜欢喝茶",
            existing_content="我喜欢喝咖啡",
        )
        assert 0.5 <= confidence <= 1.0

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
        assert topic == "居住"

    def test_relation_type_enum(self):
        assert RelationType.UPDATES.value == "updates"
        assert RelationType.EXTENDS.value == "extends"
        assert RelationType.DERIVES.value == "derives"
