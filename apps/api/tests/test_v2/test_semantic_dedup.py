"""
Unit tests for semantic deduplication service.
Tests cosine similarity calculation and priority-based deduplication.
"""

import pytest
import asyncio
import math

from src.services.core.semantic_dedup_service import (
    semantic_dedup_service,
    DedupItem,
    SOURCE_PRIORITY,
)


class TestCosineSimilarity:
    def test_identical_vectors(self):
        a = [1.0, 0.0, 0.0]
        b = [1.0, 0.0, 0.0]
        result = semantic_dedup_service.compute_cosine_similarity(a, b)
        assert abs(result - 1.0) < 0.001

    def test_orthogonal_vectors(self):
        a = [1.0, 0.0, 0.0]
        b = [0.0, 1.0, 0.0]
        result = semantic_dedup_service.compute_cosine_similarity(a, b)
        assert abs(result - 0.0) < 0.001

    def test_opposite_vectors(self):
        a = [1.0, 0.0, 0.0]
        b = [-1.0, 0.0, 0.0]
        result = semantic_dedup_service.compute_cosine_similarity(a, b)
        assert abs(result - (-1.0)) < 0.001

    def test_similar_vectors(self):
        a = [1.0, 1.0, 1.0]
        b = [1.0, 1.0, 0.9]
        result = semantic_dedup_service.compute_cosine_similarity(a, b)
        assert result > 0.95

    def test_different_length_vectors(self):
        a = [1.0, 0.0]
        b = [1.0, 0.0, 0.0]
        result = semantic_dedup_service.compute_cosine_similarity(a, b)
        assert result == 0.0

    def test_empty_vectors(self):
        a = []
        b = []
        result = semantic_dedup_service.compute_cosine_similarity(a, b)
        assert result == 0.0

    def test_zero_vectors(self):
        a = [0.0, 0.0, 0.0]
        b = [1.0, 1.0, 1.0]
        result = semantic_dedup_service.compute_cosine_similarity(a, b)
        assert result == 0.0


class TestPriorityBasedDeduplication:
    @pytest.mark.asyncio
    async def test_higher_priority_kept(self):
        items = [
            DedupItem(content="A", source="chunk", priority=1, embedding=[1.0, 0.0]),
            DedupItem(content="B", source="profile", priority=4, embedding=[1.0, 0.0]),
        ]
        result = await semantic_dedup_service.deduplicate(items, threshold=0.85)
        assert len(result) == 1
        assert result[0].source == "profile"
        assert result[0].content == "B"

    @pytest.mark.asyncio
    async def test_different_content_kept(self):
        items = [
            DedupItem(
                content="在字节跳动工作",
                source="profile",
                priority=4,
                embedding=[1.0, 0.0],
            ),
            DedupItem(
                content="喜欢吃辣",
                source="userMemory",
                priority=2,
                embedding=[0.0, 1.0],
            ),
        ]
        result = await semantic_dedup_service.deduplicate(items, threshold=0.85)
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_similar_content_deduped(self):
        items = [
            DedupItem(
                content="我是素食主义者",
                source="profile",
                priority=4,
                embedding=[1.0] * 10,
            ),
            DedupItem(
                content="我吃素", source="userMemory", priority=2, embedding=[0.95] * 10
            ),
        ]
        result = await semantic_dedup_service.deduplicate(items, threshold=0.85)
        assert len(result) == 1
        assert result[0].source == "profile"

    @pytest.mark.asyncio
    async def test_threshold_strict(self):
        items = [
            DedupItem(content="A", source="profile", priority=4, embedding=[1.0, 0.0]),
            DedupItem(
                content="B", source="userMemory", priority=2, embedding=[0.5, 0.0]
            ),
        ]
        result = await semantic_dedup_service.deduplicate(items, threshold=0.99)
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_empty_list(self):
        result = await semantic_dedup_service.deduplicate([], threshold=0.85)
        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_single_item(self):
        items = [
            DedupItem(content="A", source="profile", priority=4, embedding=[1.0, 0.0]),
        ]
        result = await semantic_dedup_service.deduplicate(items, threshold=0.85)
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_threshold_strict(self):
        items = [
            DedupItem(content="A", source="profile", priority=4, embedding=[1.0, 0.0]),
            DedupItem(
                content="B", source="userMemory", priority=2, embedding=[0.0, 1.0]
            ),
        ]
        result = await semantic_dedup_service.deduplicate(items, threshold=0.99)
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_threshold_loose(self):
        items = [
            DedupItem(content="A", source="profile", priority=4, embedding=[1.0, 0.0]),
            DedupItem(
                content="B", source="userMemory", priority=2, embedding=[0.5, 0.5]
            ),
        ]
        result = await semantic_dedup_service.deduplicate(items, threshold=0.5)
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_multiple_sources_priority(self):
        items = [
            DedupItem(content="A", source="chunk", priority=1, embedding=[1.0, 0.0]),
            DedupItem(
                content="B", source="userMemory", priority=2, embedding=[1.0, 0.0]
            ),
            DedupItem(
                content="C", source="projectMemory", priority=3, embedding=[1.0, 0.0]
            ),
            DedupItem(content="D", source="profile", priority=4, embedding=[1.0, 0.0]),
        ]
        result = await semantic_dedup_service.deduplicate(items, threshold=0.85)
        assert len(result) == 1
        assert result[0].content == "D"

    @pytest.mark.asyncio
    async def test_deduplicate_with_stats(self):
        items = [
            DedupItem(content="A", source="profile", priority=4, embedding=[1.0, 0.0]),
            DedupItem(
                content="B", source="userMemory", priority=2, embedding=[1.0, 0.0]
            ),
            DedupItem(content="C", source="chunk", priority=1, embedding=[0.0, 1.0]),
        ]
        result = await semantic_dedup_service.deduplicate_with_stats(
            items, threshold=0.85
        )
        assert result["stats"]["total"] == 3
        assert result["stats"]["after_dedup"] == 2
        assert result["stats"]["removed"] == 1
        assert "by_source" in result["stats"]


class TestSourcePriority:
    def test_profile_highest(self):
        assert SOURCE_PRIORITY["profile"] == 4

    def test_project_memory_second(self):
        assert SOURCE_PRIORITY["projectMemory"] == 3

    def test_user_memory_third(self):
        assert SOURCE_PRIORITY["userMemory"] == 2

    def test_chunk_lowest(self):
        assert SOURCE_PRIORITY["chunk"] == 1


class TestSimilarityMatrix:
    def test_compute_matrix(self):
        items = [
            DedupItem(content="A", source="profile", priority=4, embedding=[1.0, 0.0]),
            DedupItem(
                content="B", source="userMemory", priority=2, embedding=[0.0, 1.0]
            ),
        ]
        matrix = semantic_dedup_service.compute_similarity_matrix(items)
        assert matrix.shape == (2, 2)
        assert abs(matrix[0, 0] - 1.0) < 0.001
        assert abs(matrix[1, 1] - 1.0) < 0.001
        assert abs(matrix[0, 1] - 0.0) < 0.001

    def test_empty_matrix(self):
        matrix = semantic_dedup_service.compute_similarity_matrix([])
        assert len(matrix) == 0

    def test_matrix_with_missing_embedding(self):
        items = [
            DedupItem(
                content="A", source="profile", priority=4, embedding=[1.0] * 1024
            ),
            DedupItem(content="B", source="userMemory", priority=2, embedding=None),
        ]
        matrix = semantic_dedup_service.compute_similarity_matrix(items)
        assert matrix.shape == (2, 2)
        assert abs(matrix[0, 0] - 1.0) < 0.001
        assert abs(matrix[1, 1] - 0.0) < 0.001
