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
