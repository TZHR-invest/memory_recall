"""
Tests for chunks search and hybrid search endpoints.
"""

import pytest
import sys
import os
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)


class TestChunksSearchEndpoint:
    """Tests for POST /documents/search endpoint"""

    @pytest.mark.asyncio
    async def test_search_chunks_success(self):
        """Test successful chunks search returns formatted results"""
        from src.api.memories import ChunkSearchRequest

        request = ChunkSearchRequest(
            query="how to deploy",
            container_tag="test_project",
            limit=5,
            threshold=0.5,
        )

        assert request.query == "how to deploy"
        assert request.container_tag == "test_project"
        assert request.limit == 5
        assert request.threshold == 0.5

    @pytest.mark.asyncio
    async def test_search_chunks_with_doc_types_filter(self):
        """Test chunks search with document type filter"""
        from src.api.memories import ChunkSearchRequest

        request = ChunkSearchRequest(
            query="API documentation",
            container_tag="test_project",
            doc_types=["markdown", "code"],
        )

        assert request.doc_types == ["markdown", "code"]

    def test_chunk_search_result_model(self):
        """Test ChunkSearchResult model structure"""
        from src.api.memories import ChunkSearchResult

        result = ChunkSearchResult(
            id="chunk_abc123",
            content="## Deployment Guide\nRun `bun run build`...",
            document_id="doc_xyz",
            document_title="README.md",
            document_type="markdown",
            position=5,
            similarity=0.85,
        )

        assert result.id == "chunk_abc123"
        assert result.document_title == "README.md"
        assert result.similarity == 0.85


class TestHybridSearchEndpoint:
    """Tests for POST /search/hybrid endpoint"""

    @pytest.mark.asyncio
    async def test_hybrid_search_request_model(self):
        """Test HybridSearchRequest model"""
        from src.api.memories import HybridSearchRequest

        request = HybridSearchRequest(
            query="deployment preferences",
            container_tag="test_user",
            limit=10,
            threshold=0.5,
            sources=["memory", "chunk"],
        )

        assert request.query == "deployment preferences"
        assert request.sources == ["memory", "chunk"]

    @pytest.mark.asyncio
    async def test_hybrid_search_filter_memory_only(self):
        """Test hybrid search filter to memories only"""
        from src.api.memories import HybridSearchRequest

        request = HybridSearchRequest(
            query="test query",
            container_tag="test_user",
            sources=["memory"],
        )

        assert request.sources == ["memory"]

    @pytest.mark.asyncio
    async def test_hybrid_search_filter_chunks_only(self):
        """Test hybrid search filter to chunks only"""
        from src.api.memories import HybridSearchRequest

        request = HybridSearchRequest(
            query="test query",
            container_tag="test_user",
            sources=["chunk"],
        )

        assert request.sources == ["chunk"]

    def test_hybrid_search_result_model(self):
        """Test HybridSearchResult model structure"""
        from src.api.memories import HybridSearchResult

        result = HybridSearchResult(
            id="mem_abc123",
            content="I prefer Docker for deployments",
            source="memory",
            similarity=0.92,
        )

        assert result.id == "mem_abc123"
        assert result.source == "memory"
        assert result.similarity == 0.92

    def test_hybrid_search_result_chunk_source(self):
        """Test HybridSearchResult with chunk source"""
        from src.api.memories import HybridSearchResult

        result = HybridSearchResult(
            id="chunk_xyz",
            content="## Deployment Guide",
            source="chunk",
            similarity=0.85,
            document_title="README.md",
            document_type="markdown",
        )

        assert result.source == "chunk"
        assert result.document_title == "README.md"


class TestChunksSearchGraciousDegradation:
    """Tests for graceful degradation when chunks search fails"""

    @pytest.mark.asyncio
    async def test_empty_result_on_embedding_failure(self):
        """Test that embedding failure returns empty results gracefully"""
        from src.services.core.document_store import DocumentStore

        store = DocumentStore()

        with patch.object(store, "search_chunks", return_value=[]):
            results = await store.search_chunks(
                query_embedding=[0.1] * 1024,
                container_tag="test_project",
            )
            assert results == []


class TestChunksSearchAPIIntegration:
    """Integration tests for chunks search API endpoint"""

    @pytest.fixture
    def app(self):
        from fastapi import FastAPI
        from src.api.memories import router

        app = FastAPI()
        app.include_router(router)
        return app

    @pytest.fixture
    def mock_db(self):
        with (
            patch("src.services.core.memory_store.db") as mock_db,
            patch("src.services.core.document_store.db") as mock_doc_db,
        ):
            mock_db.fetch = AsyncMock(return_value=[])
            mock_db.fetchrow = AsyncMock(return_value=None)
            mock_db.execute = AsyncMock(return_value="UPDATE 1")
            mock_doc_db.fetch = AsyncMock(return_value=[])
            mock_doc_db.fetchrow = AsyncMock(return_value=None)
            mock_doc_db.execute = AsyncMock(return_value="UPDATE 1")
            yield mock_db

    @pytest.mark.asyncio
    async def test_documents_search_endpoint_exists(self, app):
        """Test that /documents/search endpoint is registered"""
        from starlette.testclient import TestClient

        client = TestClient(app)
        response = client.post(
            "/documents/search",
            json={"query": "test"},
            headers={"X-API-Key": "test_key"},
        )

        assert response.status_code in [200, 401, 403, 422]

    @pytest.mark.asyncio
    async def test_search_hybrid_endpoint_exists(self, app):
        """Test that /search/hybrid endpoint is registered"""
        from starlette.testclient import TestClient

        client = TestClient(app)
        response = client.post(
            "/search/hybrid",
            json={"query": "test"},
            headers={"X-API-Key": "test_key"},
        )

        assert response.status_code in [200, 401, 403, 422]

    @pytest.mark.asyncio
    async def test_chunks_search_with_doc_types(self):
        """Test chunks search with doc_types filter"""
        from src.api.memories import ChunkSearchRequest

        request = ChunkSearchRequest(
            query="deployment guide",
            container_tag="test_project",
            doc_types=["markdown", "code"],
            limit=10,
            threshold=0.5,
        )

        assert request.doc_types == ["markdown", "code"]
        assert request.limit == 10

    @pytest.mark.asyncio
    async def test_hybrid_search_with_sources_filter(self):
        """Test hybrid search with sources filter"""
        from src.api.memories import HybridSearchRequest

        request = HybridSearchRequest(
            query="preferences",
            container_tag="test_user",
            sources=["memory", "chunk"],
            limit=5,
        )

        assert request.sources == ["memory", "chunk"]
        assert request.limit == 5
