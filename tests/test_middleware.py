"""Tests for request context middleware."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_request_id_generated(client: AsyncClient):
    """Verify a request ID is generated and returned when none is provided."""
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    request_id = response.headers.get("x-request-id")
    assert request_id is not None
    assert len(request_id) > 0


@pytest.mark.asyncio
async def test_request_id_propagated(client: AsyncClient):
    """Verify a provided X-Request-ID is echoed back in the response."""
    custom_id = "test-request-123"
    response = await client.get(
        "/api/v1/health", headers={"x-request-id": custom_id}
    )
    assert response.status_code == 200
    assert response.headers.get("x-request-id") == custom_id
