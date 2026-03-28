"""Celery tasks for background processing."""

import asyncio
from datetime import UTC, datetime
from typing import Any

import structlog

from app.connectors.setup import register_default_connectors
from app.core.config import settings
from app.core.gcs import get_gcs_client
from app.core.logging import setup_logging
from app.models.knowledge_graph import SourceType
from app.services.ingestion_pipeline import IngestionPipeline
from app.services.knowledge_graph import KnowledgeGraphService
from app.services.query_cache import create_query_cache
from app.worker.celery_app import celery_app

logger = structlog.stdlib.get_logger(__name__)

# NOTE: This lazy singleton is safe because worker_concurrency=1 in celery_app.py.
# If concurrency is ever increased, this must be replaced with thread-safe init.
_kg_service: KnowledgeGraphService | None = None


def _get_kg_service() -> KnowledgeGraphService:
    """
    Lazily initialize the KG service on first task execution.

    Creates an independent service instance for the worker process
    with its own Neo4j connections and LlamaIndex index.
    """
    global _kg_service
    if _kg_service is None:
        setup_logging()
        logger.info("initializing_kg_service_in_worker")
        _kg_service = KnowledgeGraphService(
            settings, cache=create_query_cache(settings)
        )
        if settings.gcs_bucket:
            gcs_client = get_gcs_client(settings)
            register_default_connectors(settings, gcs_client=gcs_client)
    return _kg_service


@celery_app.task(name="ingest_source")  # type: ignore[untyped-decorator]
def ingest_source_task(
    source_type: str,
    config: dict[str, Any],
) -> dict[str, Any]:
    """
    Background task: ingest documents from an external source.

    Uses asyncio.run() to bridge Celery's sync context with the async
    pipeline. A new event loop is created per invocation — this is correct
    because the Celery worker has no persistent loop, and the pipeline
    holds no async state across calls.
    """
    kg_service = _get_kg_service()
    pipeline = IngestionPipeline(kg_service=kg_service)

    total_documents, total_triplets, errors = asyncio.run(
        pipeline.run(source_type=SourceType(source_type), config=config)
    )

    return {
        "source_type": source_type,
        "total_documents": total_documents,
        "total_triplets": total_triplets,
        "errors": errors,
    }


UPLOADS_MAX_AGE_SECONDS = 24 * 60 * 60  # 24 hours
UPLOADS_PREFIX = "uploads/"


@celery_app.task(name="cleanup_uploads")  # type: ignore[untyped-decorator]
def cleanup_uploads_task() -> dict[str, Any]:
    """Remove uploaded files older than 24 hours from GCS."""
    deleted = _cleanup_gcs_uploads()
    logger.info("cleanup_completed", deleted=deleted)
    return {"deleted": deleted}


def _cleanup_gcs_uploads() -> int:
    """Remove GCS upload objects older than 24 hours."""
    if not settings.gcs_bucket:
        return 0

    try:
        client = get_gcs_client(settings)
        bucket = client.bucket(settings.gcs_bucket)
        cutoff = datetime.now(tz=UTC).timestamp() - UPLOADS_MAX_AGE_SECONDS
        deleted = 0

        for blob in bucket.list_blobs(prefix=UPLOADS_PREFIX):
            if blob.updated and blob.updated.timestamp() < cutoff:
                blob.delete()
                deleted += 1
                logger.info("gcs_upload_cleaned_up", path=blob.name)

        return deleted
    except Exception as exc:
        logger.warning("gcs_cleanup_failed", error=str(exc))
        return 0
