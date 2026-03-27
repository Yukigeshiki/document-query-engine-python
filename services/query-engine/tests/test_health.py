"""Tests for the health check endpoint."""

from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.dependencies import get_optional_kg_service
from app.main import create_app


@pytest.mark.asyncio
async def test_health_check(client: AsyncClient) -> None:
    """Verify health endpoint returns 200 with status and version."""
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "version" in data


@pytest.mark.asyncio
async def test_health_check_with_graph_store() -> None:
    """Verify health endpoint includes graph store component health."""
    mock_service = AsyncMock()
    mock_service.check_graph_store_health.return_value = {"status": "ok", "backend": "in_memory"}
    mock_service.check_vector_store_health.return_value = None
    mock_service.check_cache_health.return_value = None

    app = create_app()
    app.dependency_overrides[get_optional_kg_service] = lambda: mock_service

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        response = await ac.get("/api/v1/health")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["components"]["graph_store"]["status"] == "ok"
    assert data["components"]["graph_store"]["backend"] == "in_memory"


@pytest.mark.asyncio
async def test_health_check_degraded() -> None:
    """Verify health reports degraded when graph store is unhealthy."""
    mock_service = AsyncMock()
    mock_service.check_graph_store_health.return_value = {
        "status": "degraded",
        "backend": "neo4j",
        "error": "connection refused",
    }
    mock_service.check_vector_store_health.return_value = None
    mock_service.check_cache_health.return_value = None

    app = create_app()
    app.dependency_overrides[get_optional_kg_service] = lambda: mock_service

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        response = await ac.get("/api/v1/health")

    assert response.status_code == 503
    data = response.json()
    assert data["status"] == "degraded"
    assert data["components"]["graph_store"]["error"] == "connection refused"
