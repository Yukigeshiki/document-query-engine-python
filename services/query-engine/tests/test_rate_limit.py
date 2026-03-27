"""Tests for rate limiting."""

from collections.abc import AsyncIterator
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient
from slowapi.errors import RateLimitExceeded
from starlette.requests import Request

from app.core.rate_limit import rate_limit_exceeded_handler
from app.dependencies import get_kg_service
from app.main import create_app


@pytest.fixture
def mock_kg_service() -> AsyncMock:
    """Create a mock KnowledgeGraphService."""
    service = AsyncMock()
    service.query.return_value = ("response", [])
    service.check_graph_store_health.return_value = {"status": "ok", "backend": "in_memory"}
    service.check_vector_store_health.return_value = None
    return service


@pytest.fixture
async def rate_limited_client(
    mock_kg_service: AsyncMock,
) -> AsyncIterator[AsyncClient]:
    """Provide a client with rate limiting enabled."""
    app = create_app()
    app.dependency_overrides[get_kg_service] = lambda: mock_kg_service
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac


@pytest.mark.asyncio
async def test_rate_limit_handler_returns_429_json() -> None:
    """Verify the rate limit handler returns a 429 JSON response."""
    import json
    from unittest.mock import MagicMock

    scope = {"type": "http", "method": "GET", "path": "/test"}
    mock_request = Request(scope)

    mock_exc = MagicMock(spec=RateLimitExceeded)
    mock_exc.detail = "10 per 1 minute"

    response = await rate_limit_exceeded_handler(mock_request, mock_exc)

    assert response.status_code == 429
    body = json.loads(bytes(response.body))
    assert body["error"] == "rate_limit_exceeded"
    assert body["code"] == "rate_limit_exceeded"
    assert "10 per 1 minute" in body["detail"]


@pytest.mark.asyncio
async def test_health_endpoint_not_rate_limited(
    rate_limited_client: AsyncClient,
) -> None:
    """Verify health endpoint has no rate limit decorator."""
    for _ in range(20):
        response = await rate_limited_client.get("/api/v1/health")
        assert response.status_code == 200
