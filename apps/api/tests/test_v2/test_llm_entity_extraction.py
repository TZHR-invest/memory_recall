"""
Tests for LLM Entity Extraction Service.
"""

import pytest
import sys
import os
from unittest.mock import MagicMock, patch, AsyncMock

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

from src.services.core.llm_entity_extraction import (
    LLMEntityExtractor,
    ExtractedFact,
    llm_entity_extractor,
)


class TestLLMEntityExtractor:
    def test_initialization_without_llm(self):
        with patch(
            "src.services.core.llm_entity_extraction.get_llm_client",
            side_effect=Exception("No LLM"),
        ):
            extractor = LLMEntityExtractor()
            assert extractor.llm_client is None

    def test_initialization_with_llm(self):
        mock_client = MagicMock()
        with patch(
            "src.services.core.llm_entity_extraction.get_llm_client",
            return_value=mock_client,
        ):
            extractor = LLMEntityExtractor()
            assert extractor.llm_client is not None

    @pytest.mark.asyncio
    async def test_extract_without_llm(self):
        with patch(
            "src.services.core.llm_entity_extraction.get_llm_client",
            side_effect=Exception("No LLM"),
        ):
            extractor = LLMEntityExtractor()
            result = await extractor.extract("我在北京工作")

            assert result.content == "我在北京工作"
            assert result.entities == {}
            assert result.confidence == 0.5

    @pytest.mark.asyncio
    async def test_extract_with_llm(self):
        mock_client = MagicMock()
        mock_client.extract_json = MagicMock(
            return_value={
                "entities": {"location": ["北京"]},
                "is_static": True,
                "confidence": 0.9,
            }
        )

        with patch(
            "src.services.core.llm_entity_extraction.get_llm_client",
            return_value=mock_client,
        ):
            extractor = LLMEntityExtractor()
            result = await extractor.extract("我在北京工作")

            assert result.entities == {"location": ["北京"]}
            assert result.is_static is True
            assert result.confidence == 0.9

    @pytest.mark.asyncio
    async def test_extract_with_llm_failure(self):
        mock_client = MagicMock()
        mock_client.extract_json = MagicMock(side_effect=Exception("API Error"))

        with patch(
            "src.services.core.llm_entity_extraction.get_llm_client",
            return_value=mock_client,
        ):
            extractor = LLMEntityExtractor()
            result = await extractor.extract("我在北京工作")

            assert result.entities == {}
            assert result.confidence == 0.5

    @pytest.mark.asyncio
    async def test_extract_entities_only(self):
        mock_client = MagicMock()
        mock_client.extract_json = MagicMock(
            return_value={
                "entities": {"location": ["北京"], "organization": ["Google"]},
                "is_static": True,
                "confidence": 0.9,
            }
        )

        with patch(
            "src.services.core.llm_entity_extraction.get_llm_client",
            return_value=mock_client,
        ):
            extractor = LLMEntityExtractor()
            entities = await extractor.extract_entities_only("我在北京Google工作")

            assert "location" in entities
            assert "organization" in entities

    @pytest.mark.asyncio
    async def test_detect_contradiction_true(self):
        mock_client = MagicMock()
        mock_client.extract_json = MagicMock(
            return_value={
                "is_contradiction": True,
                "confidence": 0.9,
                "reason": "Location changed from Beijing to Shanghai",
            }
        )

        with patch(
            "src.services.core.llm_entity_extraction.get_llm_client",
            return_value=mock_client,
        ):
            extractor = LLMEntityExtractor()
            is_contra, conf, reason = await extractor.detect_contradiction(
                "我现在在上海工作",
                "我在北京工作",
            )

            assert is_contra is True
            assert conf == 0.9
            assert "Location" in reason

    @pytest.mark.asyncio
    async def test_detect_contradiction_false(self):
        mock_client = MagicMock()
        mock_client.extract_json = MagicMock(
            return_value={
                "is_contradiction": False,
                "confidence": 0.1,
                "reason": "No contradiction",
            }
        )

        with patch(
            "src.services.core.llm_entity_extraction.get_llm_client",
            return_value=mock_client,
        ):
            extractor = LLMEntityExtractor()
            is_contra, conf, reason = await extractor.detect_contradiction(
                "我喜欢喝咖啡",
                "我喜欢运动",
            )

            assert is_contra is False

    @pytest.mark.asyncio
    async def test_detect_topic_similarity_true(self):
        mock_client = MagicMock()
        mock_client.extract_json = MagicMock(
            return_value={
                "is_same_topic": True,
                "similarity": 0.8,
                "topic": "dietary preferences",
            }
        )

        with patch(
            "src.services.core.llm_entity_extraction.get_llm_client",
            return_value=mock_client,
        ):
            extractor = LLMEntityExtractor()
            is_same, sim, topic = await extractor.detect_topic_similarity(
                "我喜欢喝咖啡",
                "我每天喝美式咖啡",
            )

            assert is_same is True
            assert sim == 0.8
            assert topic is not None

    @pytest.mark.asyncio
    async def test_detect_topic_similarity_false(self):
        mock_client = MagicMock()
        mock_client.extract_json = MagicMock(
            return_value={
                "is_same_topic": False,
                "similarity": 0.2,
                "topic": None,
            }
        )

        with patch(
            "src.services.core.llm_entity_extraction.get_llm_client",
            return_value=mock_client,
        ):
            extractor = LLMEntityExtractor()
            is_same, sim, topic = await extractor.detect_topic_similarity(
                "我喜欢喝咖啡",
                "我在北京工作",
            )

            assert is_same is False
            assert sim == 0.2

    @pytest.mark.asyncio
    async def test_batch_extract(self):
        mock_client = MagicMock()
        mock_client.extract_json = MagicMock(
            side_effect=[
                {
                    "entities": {"location": ["北京"]},
                    "is_static": True,
                    "confidence": 0.9,
                },
                {
                    "entities": {"preference": ["咖啡"]},
                    "is_static": True,
                    "confidence": 0.8,
                },
            ]
        )

        with patch(
            "src.services.core.llm_entity_extraction.get_llm_client",
            return_value=mock_client,
        ):
            extractor = LLMEntityExtractor()
            results = await extractor.batch_extract(
                [
                    "我在北京工作",
                    "我喜欢喝咖啡",
                ]
            )

            assert len(results) == 2
            assert results[0].entities == {"location": ["北京"]}
            assert results[1].entities == {"preference": ["咖啡"]}


class TestExtractedFact:
    def test_extracted_fact_creation(self):
        fact = ExtractedFact(
            content="Test content",
            entities={"location": ["Beijing"]},
            is_static=True,
            confidence=0.9,
        )

        assert fact.content == "Test content"
        assert fact.entities == {"location": ["Beijing"]}
        assert fact.is_static is True
        assert fact.confidence == 0.9

    def test_extracted_fact_defaults(self):
        fact = ExtractedFact(
            content="Test",
            entities={},
            is_static=False,
            confidence=0.5,
        )

        assert fact.entities == {}
        assert fact.confidence == 0.5


class TestExtractWithRelations:
    """测试 extract_with_relations() 方法"""

    @pytest.mark.asyncio
    async def test_extract_with_relations_chinese(self):
        """测试中文实体和关系提取"""
        mock_client = MagicMock()
        mock_client.extract_json = MagicMock(
            return_value={
                "entities": [
                    {"name": "字节跳动", "type": "organization"},
                    {"name": "张三", "type": "person"},
                ],
                "relations": [
                    {
                        "from": "我",
                        "to": "字节跳动",
                        "type": "works_at",
                        "confidence": 0.9,
                    },
                    {
                        "from": "张三",
                        "to": "字节跳动",
                        "type": "works_at",
                        "confidence": 0.85,
                    },
                ],
                "confidence": 0.8,
            }
        )

        with patch(
            "src.services.core.llm_entity_extraction.get_llm_client",
            return_value=mock_client,
        ):
            extractor = LLMEntityExtractor()
            result = await extractor.extract_with_relations(
                "我在字节跳动工作，同事张三也在那"
            )

            assert len(result["entities"]) == 2
            assert len(result["relations"]) == 2
            assert result["confidence"] == 0.8

            entity_names = [e["name"] for e in result["entities"]]
            assert "字节跳动" in entity_names
            assert "张三" in entity_names

    @pytest.mark.asyncio
    async def test_extract_with_relations_english(self):
        """测试英文实体和关系提取"""
        mock_client = MagicMock()
        mock_client.extract_json = MagicMock(
            return_value={
                "entities": [
                    {"name": "Google", "type": "organization"},
                    {"name": "John", "type": "person"},
                ],
                "relations": [
                    {
                        "from": "I",
                        "to": "Google",
                        "type": "works_at",
                        "confidence": 0.9,
                    },
                    {
                        "from": "John",
                        "to": "Google",
                        "type": "works_at",
                        "confidence": 0.85,
                    },
                ],
                "confidence": 0.9,
            }
        )

        with patch(
            "src.services.core.llm_entity_extraction.get_llm_client",
            return_value=mock_client,
        ):
            extractor = LLMEntityExtractor()
            result = await extractor.extract_with_relations(
                "I work at Google with my colleague John"
            )

            assert len(result["entities"]) == 2
            assert len(result["relations"]) == 2
            assert result["confidence"] == 0.9

    @pytest.mark.asyncio
    async def test_extract_with_relations_fallback(self):
        """测试降级逻辑（LLM 不可用时）"""
        with patch(
            "src.services.core.llm_entity_extraction.get_llm_client",
            side_effect=Exception("No LLM"),
        ):
            extractor = LLMEntityExtractor()
            result = await extractor.extract_with_relations("我在北京工作")

            assert "entities" in result
            assert "relations" in result
            assert result["relations"] == []
            assert result["confidence"] == 0.3

    @pytest.mark.asyncio
    async def test_extract_with_relations_filters_meaningless_entities(self):
        """测试过滤无意义实体"""
        mock_client = MagicMock()
        mock_client.extract_json = MagicMock(
            return_value={
                "entities": [
                    {"name": "我", "type": "person"},
                    {"name": "北京", "type": "location"},
                    {"name": "目前", "type": "time"},
                ],
                "relations": [],
                "confidence": 0.8,
            }
        )

        with patch(
            "src.services.core.llm_entity_extraction.get_llm_client",
            return_value=mock_client,
        ):
            extractor = LLMEntityExtractor()
            result = await extractor.extract_with_relations("我目前在北京")

            entity_names = [e["name"] for e in result["entities"]]
            assert "我" not in entity_names
            assert "目前" not in entity_names
            assert "北京" in entity_names

    @pytest.mark.asyncio
    async def test_extract_with_relations_filters_low_confidence(self):
        """测试过滤低置信度关系"""
        mock_client = MagicMock()
        mock_client.extract_json = MagicMock(
            return_value={
                "entities": [
                    {"name": "北京", "type": "location"},
                ],
                "relations": [
                    {"from": "我", "to": "北京", "type": "lives_at", "confidence": 0.9},
                    {"from": "我", "to": "上海", "type": "visited", "confidence": 0.1},
                ],
                "confidence": 0.8,
            }
        )

        with patch(
            "src.services.core.llm_entity_extraction.get_llm_client",
            return_value=mock_client,
        ):
            extractor = LLMEntityExtractor()
            result = await extractor.extract_with_relations("我在北京，去过上海")

            assert len(result["relations"]) == 1
            assert result["relations"][0]["confidence"] >= 0.3

    @pytest.mark.asyncio
    async def test_extract_with_relations_with_entity_context(self):
        """测试带 entity_context 的提取"""
        mock_client = MagicMock()
        mock_client.extract_json = MagicMock(
            return_value={
                "entities": [
                    {"name": "项目A", "type": "event"},
                ],
                "relations": [],
                "confidence": 0.8,
            }
        )

        with patch(
            "src.services.core.llm_entity_extraction.get_llm_client",
            return_value=mock_client,
        ):
            extractor = LLMEntityExtractor()
            result = await extractor.extract_with_relations(
                "我在做项目A", entity_context="只关注项目相关的信息"
            )

            assert len(result["entities"]) >= 1

    @pytest.mark.asyncio
    async def test_extract_with_relations_timeout(self):
        """测试超时降级"""
        mock_client = MagicMock()
        mock_client.extract_json = MagicMock(side_effect=TimeoutError("Timeout"))

        with patch(
            "src.services.core.llm_entity_extraction.get_llm_client",
            return_value=mock_client,
        ):
            extractor = LLMEntityExtractor(timeout=1.0)
            result = await extractor.extract_with_relations("我在北京工作")

            assert result["relations"] == []
            assert result["confidence"] == 0.3

    @pytest.mark.asyncio
    async def test_extract_with_relations_invalid_json(self):
        """测试无效 JSON 响应降级"""
        mock_client = MagicMock()
        mock_client.extract_json = MagicMock(return_value=None)

        with patch(
            "src.services.core.llm_entity_extraction.get_llm_client",
            return_value=mock_client,
        ):
            extractor = LLMEntityExtractor()
            result = await extractor.extract_with_relations("我在北京工作")

            assert "entities" in result
            assert "relations" in result
