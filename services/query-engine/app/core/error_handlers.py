"""Global exception handlers registered on the FastAPI app."""

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from starlette.responses import JSONResponse

from app.core.errors import AppError
from app.models.errors import ErrorResponse

logger = structlog.stdlib.get_logger(__name__)


def register_error_handlers(app: FastAPI) -> None:
    """Register all global exception handlers on the application."""

    @app.exception_handler(AppError)
    async def handle_app_exception(
        request: Request, exc: AppError
    ) -> JSONResponse:
        """Handle known application exceptions with structured responses."""
        logger.warning(
            "app_exception",
            error=exc.error,
            detail=exc.detail,
            status_code=exc.status_code,
            path=request.url.path,
        )
        body = ErrorResponse(
            error=exc.error,
            code=exc.error,
            detail=exc.detail,
        )
        return JSONResponse(
            status_code=exc.status_code,
            content=body.model_dump(by_alias=True, exclude_none=True),
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        """Handle Pydantic validation errors with a consistent format."""
        logger.warning(
            "validation_error",
            errors=exc.errors(),
            path=request.url.path,
        )
        body = ErrorResponse(
            error="validation_error",
            code="validation_error",
            detail=str(exc.errors()),
        )
        return JSONResponse(
            status_code=422, content=body.model_dump(by_alias=True)
        )

    @app.exception_handler(Exception)
    async def handle_unhandled_exception(
        request: Request, exc: Exception
    ) -> JSONResponse:
        """Catch-all for unhandled exceptions. Logs the full error but returns a safe response."""
        logger.error(
            "unhandled_exception",
            error=str(exc),
            exc_type=type(exc).__name__,
            path=request.url.path,
        )
        body = ErrorResponse(
            error="internal_error",
            code="internal_error",
        )
        return JSONResponse(
            status_code=500,
            content=body.model_dump(by_alias=True, exclude_none=True),
        )

