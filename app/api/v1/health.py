"""Health check endpoint."""

from fastapi import APIRouter

from app.core.config import settings
from app.models.health import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Return application health status and version."""
    return HealthResponse(version=settings.app_version)
