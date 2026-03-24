"""Tests for knowledge graph endpoints."""

from collections.abc import AsyncIterator
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import create_app


@pytest.fixture
def mock_kg_service() -> AsyncMock:
    """Create a mock KnowledgeGraphService."""
    service = AsyncMock()
    service.ingest.return_value = ("test-doc-id", 5)
    service.query.return_value = (
        "Test response about the topic.",
        [{"text": "source text", "score": 0.9, "metadata": {"source": "test"}}],
    )
    return service


@pytest.fixture
async def kg_client(mock_kg_service: AsyncMock) -> AsyncIterator[AsyncClient]:
    """Provide an async HTTP client with a mocked KG service."""
    app = create_app()
    app.state.kg_service = mock_kg_service
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac


@pytest.mark.asyncio
async def test_ingest_document(kg_client: AsyncClient, mock_kg_service: AsyncMock) -> None:
    """Verify ingest endpoint returns document ID and triplet count."""
    response = await kg_client.post(
        "/api/v1/kg/ingest",
        json={"text": "Alice works at Acme Corp in New York."},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["document_id"] == "test-doc-id"
    assert data["triplet_count"] == 5
    mock_kg_service.ingest.assert_called_once()


@pytest.mark.asyncio
async def test_ingest_with_metadata(kg_client: AsyncClient, mock_kg_service: AsyncMock) -> None:
    """Verify ingest accepts optional metadata."""
    response = await kg_client.post(
        "/api/v1/kg/ingest",
        json={"text": "Some document.", "metadata": {"source": "test"}},
    )
    assert response.status_code == 200
    mock_kg_service.ingest.assert_called_once_with(
        text="Some document.",
        metadata={"source": "test"},
    )


@pytest.mark.asyncio
async def test_query_knowledge_graph(
    kg_client: AsyncClient, mock_kg_service: AsyncMock
) -> None:
    """Verify query endpoint returns response and source nodes."""
    response = await kg_client.post(
        "/api/v1/kg/query",
        json={"query": "Where does Alice work?"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["response"] == "Test response about the topic."
    assert len(data["source_nodes"]) == 1
    assert data["source_nodes"][0]["text"] == "source text"
    assert data["source_nodes"][0]["score"] == 0.9
    mock_kg_service.query.assert_called_once()


@pytest.mark.asyncio
async def test_ingest_empty_text(kg_client: AsyncClient) -> None:
    """Verify validation rejects empty text."""
    response = await kg_client.post(
        "/api/v1/kg/ingest",
        json={"text": ""},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_query_empty_query(kg_client: AsyncClient) -> None:
    """Verify validation rejects empty query."""
    response = await kg_client.post(
        "/api/v1/kg/query",
        json={"query": ""},
    )
    assert response.status_code == 422
