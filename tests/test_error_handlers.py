"""Tests for global error handling."""

import pytest
from fastapi import APIRouter
from httpx import ASGITransport, AsyncClient

from app.core.exceptions import BadRequestException, NotFoundException
from app.main import create_app


def _make_client_with_error_routes() -> AsyncClient:
    """Create a test client with routes that raise known exceptions."""
    app = create_app()

    error_router = APIRouter(prefix="/api/v1/test-errors")

    @error_router.get("/not-found")
    async def raise_not_found() -> None:
        raise NotFoundException("thing not found")

    @error_router.get("/bad-request")
    async def raise_bad_request() -> None:
        raise BadRequestException("invalid input")

    @error_router.get("/unhandled")
    async def raise_unhandled() -> None:
        raise RuntimeError("something broke")

    app.include_router(error_router)

    return AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    )


@pytest.mark.asyncio
async def test_not_found_exception():
    """Verify NotFoundException returns 404 with structured error body."""
    async with _make_client_with_error_routes() as client:
        response = await client.get("/api/v1/test-errors/not-found")
        assert response.status_code == 404
        data = response.json()
        assert data["error"] == "not_found"
        assert data["code"] == "not_found"
        assert data["detail"] == "thing not found"


@pytest.mark.asyncio
async def test_bad_request_exception():
    """Verify BadRequestException returns 400 with structured error body."""
    async with _make_client_with_error_routes() as client:
        response = await client.get("/api/v1/test-errors/bad-request")
        assert response.status_code == 400
        data = response.json()
        assert data["error"] == "bad_request"
        assert data["detail"] == "invalid input"


@pytest.mark.asyncio
async def test_unhandled_exception_returns_safe_500():
    """Verify unhandled exceptions return 500 without leaking internals."""
    async with _make_client_with_error_routes() as client:
        response = await client.get("/api/v1/test-errors/unhandled")
        assert response.status_code == 500
        data = response.json()
        assert data["error"] == "internal_error"
        assert data["code"] == "internal_error"
        assert "detail" not in data
