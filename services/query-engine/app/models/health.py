"""Health check response models."""

from pydantic import Field

from app.models import CamelModel


class ComponentHealth(CamelModel):
    """Health status for an individual service component."""

    status: str
    backend: str
    error: str | None = None


class HealthResponse(CamelModel):
    """Response model for the health check endpoint."""

    status: str = "ok"
    version: str
    components: dict[str, ComponentHealth] | None = Field(default=None)
