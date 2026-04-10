"""Shared test fixtures for the test suite."""

import os
from collections.abc import AsyncIterator

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

# Force in-memory rate limiter storage regardless of the developer's .env.
# This must run before any app modules are imported, since Settings() and
# the Limiter() are constructed at module level.
os.environ["CELERY_BROKER_URL"] = ""

from app.main import create_app


@pytest.fixture
def app() -> FastAPI:
    """Create a fresh FastAPI application instance."""
    return create_app()


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    """Provide an async HTTP client wired to the test application."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac
