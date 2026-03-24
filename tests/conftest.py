"""Shared test fixtures for the test suite."""

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import create_app


@pytest.fixture
def app():
    """Create a fresh FastAPI application instance."""
    return create_app()


@pytest.fixture
async def client(app):
    """Provide an async HTTP client wired to the test application."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac
