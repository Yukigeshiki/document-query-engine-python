"""Celery tasks for background processing."""

import asyncio
from typing import Any

import structlog

from app.connectors.setup import register_default_connectors
from app.core.config import settings
from app.core.logging import setup_logging
from app.models.knowledge_graph import SourceType
from app.services.ingestion_pipeline import IngestionPipeline
from app.services.knowledge_graph import KnowledgeGraphService
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
        _kg_service = KnowledgeGraphService(settings)
        register_default_connectors(settings)
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
