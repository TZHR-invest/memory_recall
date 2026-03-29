import pytest
import sys
import os
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

from src.api.graph import get_graph, GraphNode, GraphEdge, GraphResponse


class TestGraphAPI:
    @pytest.mark.asyncio
    async def test_get_graph_basic(self):
        mock_memories = [
            type(
                "Memory",
                (),
                {
                    "id": "mem_test1",
                    "content": "Test content 1",
                    "is_static": True,
                    "is_latest": True,
                    "is_inference": False,
                    "created_at": datetime.now(),
                    "metadata": {
                        "relations": {"updates": [], "extends": [], "derives": []}
                    },
                    "confidence": 0.8,
                },
            )()
        ]

        mock_user = {"user_id": "user_001", "permissions": ["read"]}

        with patch("src.api.graph.memory_store") as mock_store:
            mock_store.get_by_container = AsyncMock(return_value=mock_memories)

            response = await get_graph(
                container_tag="user_001",
                limit=100,
                offset=0,
                entity_types=None,
                is_static=None,
                date_from=None,
                date_to=None,
                current_user=mock_user,
                _={},
            )

            assert response.total_count == 1
            assert len(response.nodes) == 1
            assert response.has_more is False

    @pytest.mark.asyncio
    async def test_get_graph_with_pagination(self):
        mock_memories = [
            type(
                "Memory",
                (),
                {
                    "id": f"mem_test{i}",
                    "content": f"Test content {i}",
                    "is_static": True,
                    "is_latest": True,
                    "is_inference": False,
                    "created_at": datetime.now(),
                    "metadata": {
                        "relations": {"updates": [], "extends": [], "derives": []}
                    },
                    "confidence": 0.8,
                },
            )()
            for i in range(105)
        ]

        mock_user = {"user_id": "user_001", "permissions": ["read"]}

        with patch("src.api.graph.memory_store") as mock_store:
            mock_store.get_by_container = AsyncMock(return_value=mock_memories)

            response = await get_graph(
                container_tag="user_001",
                limit=100,
                offset=0,
                entity_types=None,
                is_static=None,
                date_from=None,
                date_to=None,
                current_user=mock_user,
                _={},
            )

            assert response.has_more is True
            assert len(response.nodes) == 100

    @pytest.mark.asyncio
    async def test_get_graph_with_static_filter(self):
        mock_memories = [
            type(
                "Memory",
                (),
                {
                    "id": "mem_test1",
                    "content": "Test content",
                    "is_static": True,
                    "is_latest": True,
                    "is_inference": False,
                    "created_at": datetime.now(),
                    "metadata": {
                        "relations": {"updates": [], "extends": [], "derives": []}
                    },
                    "confidence": 0.8,
                },
            )(),
            type(
                "Memory",
                (),
                {
                    "id": "mem_test2",
                    "content": "Dynamic content",
                    "is_static": False,
                    "is_latest": True,
                    "is_inference": False,
                    "created_at": datetime.now(),
                    "metadata": {
                        "relations": {"updates": [], "extends": [], "derives": []}
                    },
                    "confidence": 0.8,
                },
            )(),
        ]

        mock_user = {"user_id": "user_001", "permissions": ["read"]}

        with patch("src.api.graph.memory_store") as mock_store:
            mock_store.get_by_container = AsyncMock(return_value=mock_memories)

            response = await get_graph(
                container_tag="user_001",
                limit=100,
                offset=0,
                entity_types=None,
                is_static=True,
                date_from=None,
                date_to=None,
                current_user=mock_user,
                _={},
            )

            assert len(response.nodes) == 1
            assert response.nodes[0].is_static is True

    @pytest.mark.asyncio
    async def test_get_graph_with_edges(self):
        mock_memories = [
            type(
                "Memory",
                (),
                {
                    "id": "mem_test1",
                    "content": "Old content",
                    "is_static": True,
                    "is_latest": False,
                    "is_inference": False,
                    "created_at": datetime.now(),
                    "metadata": {
                        "relations": {"updates": [], "extends": [], "derives": []}
                    },
                    "confidence": 0.8,
                },
            )(),
            type(
                "Memory",
                (),
                {
                    "id": "mem_test2",
                    "content": "New content",
                    "is_static": True,
                    "is_latest": True,
                    "is_inference": False,
                    "created_at": datetime.now(),
                    "metadata": {
                        "relations": {
                            "updates": ["mem_test1"],
                            "extends": [],
                            "derives": [],
                        }
                    },
                    "confidence": 0.9,
                },
            )(),
        ]

        mock_user = {"user_id": "user_001", "permissions": ["read"]}

        with patch("src.api.graph.memory_store") as mock_store:
            mock_store.get_by_container = AsyncMock(return_value=mock_memories)

            response = await get_graph(
                container_tag="user_001",
                limit=100,
                offset=0,
                entity_types=None,
                is_static=None,
                date_from=None,
                date_to=None,
                current_user=mock_user,
                _={},
            )

            assert len(response.nodes) == 2
            assert len(response.edges) == 1
            assert response.edges[0].source == "mem_test2"
            assert response.edges[0].target == "mem_test1"
            assert response.edges[0].type == "updates"

    @pytest.mark.asyncio
    async def test_get_graph_container_ownership_mismatch(self):
        mock_user = {"user_id": "user_other", "permissions": ["read"]}

        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await get_graph(
                container_tag="user_001",
                limit=100,
                offset=0,
                entity_types=None,
                is_static=None,
                date_from=None,
                date_to=None,
                current_user=mock_user,
                _={},
            )

        assert exc_info.value.status_code == 403


class TestGraphModels:
    def test_graph_node_model(self):
        node = GraphNode(
            id="mem_test",
            type="memory",
            content="Test content",
            is_static=True,
            is_latest=True,
            is_inference=False,
            created_at="2024-01-15T10:30:00",
            entities={"preference": ["coffee"]},
        )
        assert node.id == "mem_test"
        assert node.type == "memory"
        assert node.is_static is True

    def test_graph_edge_model(self):
        edge = GraphEdge(
            source="mem_1",
            target="mem_2",
            type="updates",
            confidence=0.9,
        )
        assert edge.source == "mem_1"
        assert edge.target == "mem_2"
        assert edge.type == "updates"
        assert edge.confidence == 0.9

    def test_graph_response_model(self):
        response = GraphResponse(
            nodes=[
                GraphNode(
                    id="mem_1",
                    type="memory",
                    content="Test",
                    is_static=True,
                    is_latest=True,
                    is_inference=False,
                )
            ],
            edges=[
                GraphEdge(
                    source="mem_1",
                    target="mem_2",
                    type="updates",
                    confidence=0.9,
                )
            ],
            total_count=1,
            has_more=False,
        )
        assert response.total_count == 1
        assert response.has_more is False
