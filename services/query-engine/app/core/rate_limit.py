"""Rate limiting configuration using slowapi."""

from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.core.config import settings

limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=settings.celery_broker_url or None,
    default_limits=[settings.rate_limit_default],
    swallow_errors=True,
)


async def rate_limit_exceeded_handler(
    request: Request, exc: RateLimitExceeded
) -> JSONResponse:
    """Return a consistent JSON 429 response when rate limit is exceeded."""
    return JSONResponse(
        status_code=429,
        content={
            "error": "rate_limit_exceeded",
            "code": "rate_limit_exceeded",
            "detail": str(exc.detail),
        },
    )
