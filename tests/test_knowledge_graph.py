"""Tests for knowledge graph endpoints."""

from collections.abc import AsyncIterator
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.dependencies import get_kg_service
from app.main import create_app
from app.models.knowledge_graph import SourceNodeInfo, SubgraphEdge, SubgraphNode


@pytest.fixture
def mock_kg_service() -> AsyncMock:
    """Create a mock KnowledgeGraphService."""
    service = AsyncMock()
    service.ingest.return_value = ("test-doc-id", 5)
    service.query.return_value = (
        "Test response about the topic.",
        [SourceNodeInfo(text="source text", score=0.9, metadata={"source": "test"})],
    )
    service.get_subgraph.return_value = (
        [SubgraphNode(id="Alice"), SubgraphNode(id="Acme Corp", label="Organization")],
        [SubgraphEdge(source="Alice", target="Acme Corp", relation="WORKS_AT")],
    )
    service.check_health.return_value = {"status": "ok", "backend": "in_memory"}
    return service


@pytest.fixture
async def kg_client(mock_kg_service: AsyncMock) -> AsyncIterator[AsyncClient]:
    """Provide an async HTTP client with a mocked KG service."""
    app = create_app()
    app.dependency_overrides[get_kg_service] = lambda: mock_kg_service
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
    assert data["documentId"] == "test-doc-id"
    assert data["tripletCount"] == 5
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
    response = await kg_client.get(
        "/api/v1/kg/query",
        params={"query": "Where does Alice work?"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["response"] == "Test response about the topic."
    assert len(data["sourceNodes"]) == 1
    assert data["sourceNodes"][0]["text"] == "source text"
    assert data["sourceNodes"][0]["score"] == 0.9
    mock_kg_service.query.assert_called_once()


@pytest.mark.asyncio
async def test_query_with_retrieval_mode(
    kg_client: AsyncClient, mock_kg_service: AsyncMock
) -> None:
    """Verify retrieval_mode parameter is passed through."""
    response = await kg_client.get(
        "/api/v1/kg/query",
        params={"query": "test", "retrieval_mode": "vector_only"},
    )
    assert response.status_code == 200
    mock_kg_service.query.assert_called_once()
    call_kwargs = mock_kg_service.query.call_args
    assert str(call_kwargs.kwargs["retrieval_mode"]) == "vector_only"


@pytest.mark.asyncio
async def test_subgraph(kg_client: AsyncClient, mock_kg_service: AsyncMock) -> None:
    """Verify subgraph endpoint returns nodes and edges."""
    response = await kg_client.get(
        "/api/v1/kg/subgraph",
        params={"entity": "Alice", "depth": 2},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["entity"] == "Alice"
    assert data["depth"] == 2
    assert len(data["nodes"]) == 2
    assert len(data["edges"]) == 1
    assert data["edges"][0]["relation"] == "WORKS_AT"
    mock_kg_service.get_subgraph.assert_called_once_with(entity="Alice", depth=2)


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
    response = await kg_client.get(
        "/api/v1/kg/query",
        params={"query": ""},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_subgraph_missing_entity(kg_client: AsyncClient) -> None:
    """Verify validation rejects missing entity parameter."""
    response = await kg_client.get("/api/v1/kg/subgraph")
    assert response.status_code == 422
