"""Error response models."""

from app.models import CamelModel


class ErrorResponse(CamelModel):
    """Consistent error response returned by all exception handlers."""

    error: str
    code: str
    detail: str | None = None
