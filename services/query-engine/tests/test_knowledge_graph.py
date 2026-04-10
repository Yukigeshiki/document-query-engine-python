"""Tests for knowledge graph endpoints."""

from collections.abc import AsyncIterator
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.dependencies import get_kg_service
from app.main import create_app
from app.models.knowledge_graph import (
    RetrievalMode,
    SourceNodeInfo,
    SourceNodeMetadata,
    SourceRetrievalType,
    SubgraphEdge,
    SubgraphNode,
)


@pytest.fixture
def mock_kg_service() -> AsyncMock:
    """Create a mock KnowledgeGraphService."""
    service = AsyncMock()
    service.query.return_value = (
        "Test response about the topic.",
        [SourceNodeInfo(
            source_type=SourceRetrievalType.VECTOR,
            score=0.9,
            metadata=SourceNodeMetadata(file_name="test.txt"),
        )],
    )
    service.get_subgraph.return_value = (
        [SubgraphNode(id="Alice"), SubgraphNode(id="Acme Corp", label="Organization")],
        [SubgraphEdge(source="Alice", target="Acme Corp", relation="WORKS_AT")],
    )
    service.get_document_graph.return_value = (
        [SubgraphNode(id="Bob"), SubgraphNode(id="Widget Inc", label="Organization")],
        [SubgraphEdge(source="Bob", target="Widget Inc", relation="WORKS_AT")],
    )
    service.list_documents.return_value = (
        [
            {
                "doc_id": "doc-1",
                "doc_ids": ["doc-1"],
                "file_name": "test.pdf",
                "node_count": 3,
                "metadata": {},
            },
            {
                "doc_id": "doc-2",
                "doc_ids": ["doc-2a", "doc-2b"],
                "file_name": "report.txt",
                "node_count": 5,
                "metadata": {},
            },
        ],
        2,
    )
    service.check_graph_store_health.return_value = {"status": "ok", "backend": "neo4j"}
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
    assert len(data["sourceNodes"]) == 1
    assert data["sourceNodes"][0]["score"] == 0.9
    assert data["sourceNodes"][0]["sourceType"] == SourceRetrievalType.VECTOR
    mock_kg_service.query.assert_called_once()


@pytest.mark.asyncio
async def test_query_with_retrieval_mode(
    kg_client: AsyncClient, mock_kg_service: AsyncMock
) -> None:
    """Verify retrieval_mode parameter is passed through."""
    response = await kg_client.post(
        "/api/v1/kg/query",
        json={"query": "test", "retrievalMode": RetrievalMode.VECTOR_ONLY},
    )
    assert response.status_code == 200
    mock_kg_service.query.assert_called_once()
    call_kwargs = mock_kg_service.query.call_args
    assert call_kwargs.kwargs["retrieval_mode"] == RetrievalMode.VECTOR_ONLY


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
async def test_list_documents(kg_client: AsyncClient, mock_kg_service: AsyncMock) -> None:
    """Verify list documents endpoint returns paginated results."""
    response = await kg_client.get("/api/v1/kg/documents")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2
    assert data["limit"] == 20
    assert data["offset"] == 0
    assert len(data["documents"]) == 2
    assert data["documents"][0]["fileName"] == "test.pdf"
    assert data["documents"][1]["docIds"] == ["doc-2a", "doc-2b"]
    mock_kg_service.list_documents.assert_called_once_with(limit=20, offset=0)


@pytest.mark.asyncio
async def test_list_documents_pagination(
    kg_client: AsyncClient, mock_kg_service: AsyncMock
) -> None:
    """Verify list documents accepts limit and offset params."""
    response = await kg_client.get(
        "/api/v1/kg/documents",
        params={"limit": 5, "offset": 10},
    )
    assert response.status_code == 200
    mock_kg_service.list_documents.assert_called_once_with(limit=5, offset=10)


@pytest.mark.asyncio
async def test_document_graph(kg_client: AsyncClient, mock_kg_service: AsyncMock) -> None:
    """Verify document graph endpoint returns nodes and edges."""
    response = await kg_client.get(
        "/api/v1/kg/documents/graph",
        params={"doc_ids": ["doc-1", "doc-2"]},
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["nodes"]) == 2
    assert len(data["edges"]) == 1
    assert data["edges"][0]["relation"] == "WORKS_AT"
    mock_kg_service.get_document_graph.assert_called_once_with(doc_ids=["doc-1", "doc-2"])


@pytest.mark.asyncio
async def test_document_graph_missing_doc_ids(kg_client: AsyncClient) -> None:
    """Verify document graph rejects missing doc_ids."""
    response = await kg_client.get("/api/v1/kg/documents/graph")
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_query_empty_query(kg_client: AsyncClient) -> None:
    """Verify validation rejects empty query."""
    response = await kg_client.post(
        "/api/v1/kg/query",
        json={"query": ""},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_subgraph_missing_entity(kg_client: AsyncClient) -> None:
    """Verify validation rejects missing entity parameter."""
    response = await kg_client.get("/api/v1/kg/subgraph")
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_delete_document_accepted(kg_client: AsyncClient, mock_kg_service: AsyncMock) -> None:
    """Verify delete endpoint returns 202 with a task ID when the doc exists."""
    from unittest.mock import MagicMock, patch

    mock_kg_service.document_exists.return_value = True

    mock_result = MagicMock()
    mock_result.id = "task-delete-1"
    with patch("app.api.v1.knowledge_graph.delete_document_task") as mock_task:
        mock_task.delay.return_value = mock_result
        response = await kg_client.delete("/api/v1/kg/documents/doc-1")

    assert response.status_code == 202
    data = response.json()
    assert data["taskId"] == "task-delete-1"
    mock_task.delay.assert_called_once_with(doc_id="doc-1")
    mock_kg_service.document_exists.assert_called_once_with("doc-1")


@pytest.mark.asyncio
async def test_delete_document_returns_404_for_unknown_id(
    kg_client: AsyncClient, mock_kg_service: AsyncMock
) -> None:
    """Verify a typoed doc_id returns 404 synchronously without dispatching a task.

    Without this synchronous validation, the user would have to poll the task
    status endpoint to learn that the doc didn't exist, and the worker-side
    NotFoundError catch (P2 idempotency fix) would silently report success.
    """
    from unittest.mock import patch

    mock_kg_service.document_exists.return_value = False

    with patch("app.api.v1.knowledge_graph.delete_document_task") as mock_task:
        response = await kg_client.delete("/api/v1/kg/documents/bogus-id")

    assert response.status_code == 404
    mock_kg_service.document_exists.assert_called_once_with("bogus-id")
    mock_task.delay.assert_not_called()
