"""FastAPI application factory and lifespan management."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator
from slowapi.errors import RateLimitExceeded

from app.api.v1.router import api_router
from app.connectors.setup import register_default_connectors
from app.core.config import settings
from app.core.error_handlers import register_error_handlers
from app.core.gcs import get_gcs_client
from app.core.logging import setup_logging
from app.core.postgres import get_pg_engine
from app.core.middleware import RequestContextMiddleware
from app.core.rate_limit import limiter, rate_limit_exceeded_handler
from app.services.knowledge_graph import KnowledgeGraphService
from app.services.query_cache import create_query_cache
from app.services.upload import UploadService

logger = structlog.stdlib.get_logger(__name__)

HEALTH_POLL_INTERVAL_SECONDS = 30


async def _health_poller(kg_service: KnowledgeGraphService) -> None:
    """Periodically run health checks to keep Prometheus gauges fresh."""
    while True:
        try:
            await kg_service.check_graph_store_health()
            await kg_service.check_vector_store_health()
            await kg_service.check_cache_health()
        except Exception as exc:
            logger.warning("health_poll_failed", error=str(exc))
        await asyncio.sleep(HEALTH_POLL_INTERVAL_SECONDS)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Handle application startup and shutdown events."""
    setup_logging()
    logger.info("starting", app_name=settings.app_name, version=settings.app_version)
    pg_engine = get_pg_engine(settings.postgres_uri) if settings.postgres_enabled and settings.postgres_uri else None
    cache = create_query_cache(settings, engine=pg_engine)
    _app.state.kg_service = KnowledgeGraphService(
        settings, cache=cache, engine=pg_engine
    )
    if settings.gcs_bucket:
        gcs_client = get_gcs_client(settings)
        _app.state.upload_service = UploadService(
            gcs_bucket=settings.gcs_bucket, gcs_client=gcs_client
        )
        register_default_connectors(settings, gcs_client=gcs_client)
    else:
        logger.warning("gcs_not_configured", msg="Upload and GCS ingestion disabled")
    poller_task = asyncio.create_task(_health_poller(_app.state.kg_service))
    yield
    poller_task.cancel()
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

    app.state.limiter = limiter
    app.include_router(api_router)
    register_error_handlers(app)
    app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)  # type: ignore[arg-type]

    Instrumentator(
        excluded_handlers=[r".*health.*", r".*metrics.*"],
    ).instrument(app).expose(app, endpoint="/metrics")

    return app


app = create_app()
