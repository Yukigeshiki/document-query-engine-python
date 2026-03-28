"""Tests for the bulk source ingestion endpoint."""

from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.dependencies import get_kg_service
from app.main import create_app
from app.models.knowledge_graph import SourceType


@pytest.fixture
def mock_kg_service() -> AsyncMock:
    """Create a mock KnowledgeGraphService."""
    service = AsyncMock()
    return service


@pytest.fixture
async def source_client(mock_kg_service: AsyncMock) -> AsyncIterator[AsyncClient]:
    """Provide an async HTTP client with a mocked KG service."""
    app = create_app()
    app.dependency_overrides[get_kg_service] = lambda: mock_kg_service
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac


@pytest.mark.asyncio
@patch("app.api.v1.knowledge_graph.ingest_source_task")
async def test_ingest_from_source_returns_task_id(
    mock_task: MagicMock,
    source_client: AsyncClient,
) -> None:
    """Verify bulk ingest returns 202 with a task ID."""
    mock_result = MagicMock()
    mock_result.id = "abc-123"
    mock_task.delay.return_value = mock_result

    response = await source_client.post(
        "/api/v1/kg/ingest/source",
        json={"sourceType": SourceType.GCS, "config": {"bucket": "test", "prefix": "docs/"}},
    )
    assert response.status_code == 202
    data = response.json()
    assert data["taskId"] == "abc-123"
    mock_task.delay.assert_called_once_with(
        source_type=SourceType.GCS,
        config={"bucket": "test", "prefix": "docs/"},
    )


@pytest.mark.asyncio
async def test_ingest_from_unknown_source(source_client: AsyncClient) -> None:
    """Verify 422 for unknown source type."""
    response = await source_client.post(
        "/api/v1/kg/ingest/source",
        json={"sourceType": "nonexistent", "config": {}},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_ingest_source_missing_source_type(source_client: AsyncClient) -> None:
    """Verify 422 for missing sourceType."""
    response = await source_client.post(
        "/api/v1/kg/ingest/source",
        json={"config": {}},
    )
    assert response.status_code == 422
