"""Error response models."""

from pydantic import BaseModel


class ErrorResponse(BaseModel):
    """Consistent error response returned by all exception handlers."""

    error: str
    code: str
    detail: str | None = None
