"""
Tests for batch relation detection and memory merge functionality.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime

from src.services.core.llm_entity_extraction import (
    LLMEntityExtractor,
    BatchRelationResult,
    get_batch_relation_prompt,
)
from src.services.core.memory_store import MemoryStore, Memory


class TestBatchRelationPrompt:
    def test_get_batch_relation_prompt_english(self):
        new_content = "I now work at Google"
        candidates = [
            {"id": "mem_1", "content": "I work at Meta"},
            {"id": "mem_2", "content": "I like basketball"},
        ]

        prompt = get_batch_relation_prompt(new_content, candidates, "english")

        assert "I now work at Google" in prompt
        assert "[ID: mem_1]" in prompt
        assert "[ID: mem_2]" in prompt
        assert "I work at Meta" in prompt

    def test_get_batch_relation_prompt_truncation(self):
        new_content = "Test content"
        long_content = "x" * 300
        candidates = [{"id": "mem_1", "content": long_content}]

        prompt = get_batch_relation_prompt(new_content, candidates, "english")

        assert len([line for line in prompt.split("\n") if "mem_1" in line][0]) < 300

    def test_get_batch_relation_prompt_chinese(self):
        new_content = "我现在在谷歌工作"
        candidates = [
            {"id": "mem_1", "content": "我在Meta工作"},
        ]

        prompt = get_batch_relation_prompt(new_content, candidates, "chinese")

        assert "我现在在谷歌工作" in prompt
        assert "[ID: mem_1]" in prompt


class TestBatchRelationResult:
    def test_batch_relation_result_creation(self):
        result = BatchRelationResult(
            memory_id="mem_123",
            relation_type="updates",
            confidence=0.9,
        )

        assert result.memory_id == "mem_123"
        assert result.relation_type == "updates"
        assert result.confidence == 0.9

    def test_batch_relation_result_null_type(self):
        result = BatchRelationResult(
            memory_id="mem_456",
            relation_type=None,
            confidence=0.5,
        )

        assert result.relation_type is None


class TestDetectRelationsBatch:
    @pytest.mark.asyncio
    async def test_detect_relations_batch_success(self):
        extractor = LLMEntityExtractor()
        extractor.llm_client = MagicMock()
        extractor.llm_client.extract_json = MagicMock(
            return_value={
                "relations": [
                    {"id": "mem_1", "type": "updates", "confidence": 0.9},
                    {"id": "mem_2", "type": "extends", "confidence": 0.8},
                    {"id": "mem_3", "type": None},
                ]
            }
        )

        new_content = "I now work at Google"
        candidates = [
            {"id": "mem_1", "content": "I work at Meta"},
            {"id": "mem_2", "content": "I like basketball"},
            {"id": "mem_3", "content": "Unrelated content"},
        ]

        results = await extractor.detect_relations_batch(new_content, candidates)

        assert len(results) == 2
        assert results[0].memory_id == "mem_1"
        assert results[0].relation_type == "updates"
        assert results[1].memory_id == "mem_2"
        assert results[1].relation_type == "extends"

    @pytest.mark.asyncio
    async def test_detect_relations_batch_no_llm_client(self):
        extractor = LLMEntityExtractor()
        extractor.llm_client = None

        results = await extractor.detect_relations_batch(
            "content", [{"id": "1", "content": "test"}]
        )

        assert results == []

    @pytest.mark.asyncio
    async def test_detect_relations_batch_empty_candidates(self):
        extractor = LLMEntityExtractor()
        extractor.llm_client = MagicMock()

        results = await extractor.detect_relations_batch("content", [])

        assert results == []

    @pytest.mark.asyncio
    async def test_detect_relations_batch_fallback(self):
        extractor = LLMEntityExtractor()
        extractor.llm_client = MagicMock()
        extractor.llm_client.extract_json = MagicMock(
            side_effect=Exception("API Error")
        )

        with patch(
            "src.services.core.chinese_entity_types.has_update_marker",
            return_value=True,
        ):
            new_content = "I now work at Google"
            candidates = [{"id": "mem_1", "content": "I work at Meta"}]

            results = await extractor.detect_relations_batch(new_content, candidates)

            assert len(results) == 1
            assert results[0].memory_id == "mem_1"
            assert results[0].relation_type == "updates"
            assert results[0].confidence == 0.7


class TestParseBatchRelations:
    def test_parse_batch_relations_valid(self):
        extractor = LLMEntityExtractor()
        relations_data = [
            {"id": "mem_1", "type": "updates", "confidence": 0.9},
            {"id": "mem_2", "type": "extends", "confidence": 0.8},
            {"id": "mem_3", "type": None, "confidence": 0.5},
        ]

        results = extractor._parse_batch_relations(relations_data)

        assert len(results) == 2
        assert results[0].relation_type == "updates"
        assert results[1].relation_type == "extends"

    def test_parse_batch_relations_invalid_type(self):
        extractor = LLMEntityExtractor()
        relations_data = [
            {"id": "mem_1", "type": "invalid_type", "confidence": 0.9},
        ]

        results = extractor._parse_batch_relations(relations_data)

        assert len(results) == 0


class TestFallbackBatchDetection:
    def test_fallback_updates_marker(self):
        extractor = LLMEntityExtractor()

        with patch(
            "src.services.core.chinese_entity_types.has_update_marker",
            return_value=True,
        ):
            results = extractor._fallback_batch_detection(
                "I now work at Google",
                [{"id": "mem_1", "content": "I work at Meta"}],
            )

            assert len(results) == 1
            assert results[0].relation_type == "updates"
            assert results[0].confidence == 0.7

    def test_fallback_extends_marker(self):
        extractor = LLMEntityExtractor()

        with patch(
            "src.services.core.chinese_entity_types.has_extend_marker",
            return_value=True,
        ):
            results = extractor._fallback_batch_detection(
                "I also like basketball",
                [{"id": "mem_1", "content": "I like sports"}],
            )

            assert len(results) == 1
            assert results[0].relation_type == "extends"

    def test_fallback_no_markers(self):
        extractor = LLMEntityExtractor()

        with (
            patch(
                "src.services.core.chinese_entity_types.has_update_marker",
                return_value=False,
            ),
            patch(
                "src.services.core.chinese_entity_types.has_extend_marker",
                return_value=False,
            ),
            patch(
                "src.services.core.chinese_entity_types.has_derive_marker",
                return_value=False,
            ),
        ):
            results = extractor._fallback_batch_detection(
                "Some random content",
                [{"id": "mem_1", "content": "Other content"}],
            )

            assert len(results) == 0


class TestCheckSimilarMemory:
    @pytest.mark.asyncio
    async def test_check_similar_memory_found(self):
        store = MemoryStore()

        with patch.object(
            store, "_generate_embedding", new_callable=AsyncMock
        ) as mock_embed:
            mock_embed.return_value = [0.1] * 1024

            with patch("src.services.core.memory_store.db") as mock_db:
                mock_db.fetchrow = AsyncMock(
                    return_value={
                        "id": "mem_123",
                        "content": "Similar content",
                        "similarity": 0.96,
                        "metadata": {},
                    }
                )

                result = await store._check_similar_memory(
                    "Test content", "container_1", threshold=0.95
                )

                assert result is not None
                assert result["id"] == "mem_123"
                assert result["similarity"] == 0.96

    @pytest.mark.asyncio
    async def test_check_similar_memory_not_found(self):
        store = MemoryStore()

        with patch.object(
            store, "_generate_embedding", new_callable=AsyncMock
        ) as mock_embed:
            mock_embed.return_value = [0.1] * 1024

            with patch("src.services.core.memory_store.db") as mock_db:
                mock_db.fetchrow = AsyncMock(return_value=None)

                result = await store._check_similar_memory(
                    "Test content", "container_1", threshold=0.95
                )

                assert result is None

    @pytest.mark.asyncio
    async def test_check_similar_memory_no_embedding(self):
        store = MemoryStore()

        with patch.object(
            store, "_generate_embedding", new_callable=AsyncMock
        ) as mock_embed:
            mock_embed.return_value = None

            result = await store._check_similar_memory("Test content", "container_1")

            assert result is None


class TestMergeSimilarMemory:
    @pytest.mark.asyncio
    async def test_merge_similar_memory_success(self):
        store = MemoryStore()

        with patch.object(store, "get_by_id", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = Memory(
                id="mem_123",
                container_tag="container_1",
                content="Original content",
                metadata={"merged_count": 2},
            )

            with patch.object(
                store, "update_metadata", new_callable=AsyncMock
            ) as mock_update:
                mock_update.return_value = True

                result = await store.merge_similar_memory("mem_123", "New content")

                assert result is True
                mock_update.assert_called_once()
                call_args = mock_update.call_args[0]
                assert call_args[0] == "mem_123"
                assert call_args[1]["merged_count"] == 3
                assert "last_merged_at" in call_args[1]

    @pytest.mark.asyncio
    async def test_merge_similar_memory_not_found(self):
        store = MemoryStore()

        with patch.object(store, "get_by_id", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = None

            result = await store.merge_similar_memory("nonexistent", "content")

            assert result is False


class TestContainerScopedMerge:
    @pytest.mark.asyncio
    async def test_merge_same_container_only(self):
        store = MemoryStore()

        with patch.object(
            store, "_generate_embedding", new_callable=AsyncMock
        ) as mock_embed:
            mock_embed.return_value = [0.1] * 1024

            with patch("src.services.core.memory_store.db") as mock_db:
                mock_db.fetchrow = AsyncMock(
                    return_value={
                        "id": "mem_123",
                        "content": "Similar in container A",
                        "similarity": 0.97,
                        "metadata": {},
                    }
                )

                result = await store._check_similar_memory(
                    "Test content", "container_A", threshold=0.95
                )

                assert result is not None
                call_args = mock_db.fetchrow.call_args
                assert "container_tag = $2" in mock_db.fetchrow.call_args[0][0]
