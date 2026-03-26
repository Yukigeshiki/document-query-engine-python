"""FastAPI application factory and lifespan management."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.connectors.setup import register_default_connectors
from app.core.config import settings
from app.core.error_handlers import register_error_handlers
from app.core.logging import setup_logging
from app.core.middleware import RequestContextMiddleware
from app.services.knowledge_graph import KnowledgeGraphService
from app.services.upload import UploadService

logger = structlog.stdlib.get_logger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Handle application startup and shutdown events."""
    setup_logging()
    logger.info("starting", app_name=settings.app_name, version=settings.app_version)
    _app.state.kg_service = KnowledgeGraphService(settings)
    if settings.upload_storage:
        _app.state.upload_service = UploadService(settings)
    register_default_connectors(settings)
    yield
    _app.state.kg_service.close()
    logger.info("shutting_down", app_name=settings.app_name)


def create_app() -> FastAPI:
    """Create and configure the FastAPI application instance."""
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        debug=settings.debug,
        lifespan=lifespan,
        docs_url="/docs" if settings.debug else None,
        redoc_url="/redoc" if settings.debug else None,
    )

    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(api_router)
    register_error_handlers(app)

    return app


app = create_app()
