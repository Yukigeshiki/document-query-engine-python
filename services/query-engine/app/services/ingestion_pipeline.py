"""Ingestion pipeline: connects document connectors to the KG service."""

import asyncio
from typing import Any

import structlog

from app.connectors.registry import default_registry
from app.core.errors import IngestionError
from app.models.knowledge_graph import SourceType
from app.services.knowledge_graph import KnowledgeGraphService

logger = structlog.stdlib.get_logger(__name__)


class IngestionPipeline:
    """Orchestrates loading documents from a source and ingesting into the KG."""

    def __init__(self, kg_service: KnowledgeGraphService) -> None:
        self._kg_service = kg_service

    async def run(
        self,
        source_type: SourceType,
        config: dict[str, Any],
    ) -> tuple[int, int, list[str]]:
        """
        Run the pipeline: load docs from source, ingest each into KG.

        Documents are consumed from the connector iterator one at a time
        to avoid loading all documents into memory simultaneously.

        Returns a tuple of (total_documents, total_triplets, errors).
        """
        connector = default_registry.get(source_type)

        loop = asyncio.get_running_loop()
        documents = await loop.run_in_executor(
            None, lambda: list(connector.load_documents(config))
        )

        if not documents:
            logger.info("no_documents_found", source_type=source_type)
            return 0, 0, []

        total_triplets = 0
        errors: list[str] = []
        ingested_count = 0

        for doc in documents:
            try:
                _doc_id, triplets = await self._kg_service.ingest(
                    text=doc.get_content(),
                    metadata=doc.metadata,
                )
                total_triplets += triplets
                ingested_count += 1
            except IngestionError as exc:
                error_msg = f"Failed to ingest document: {exc.detail}"
                errors.append(error_msg)
                logger.warning("pipeline_document_failed", error=error_msg)

        logger.info(
            "pipeline_completed",
            source_type=source_type,
            total_documents=ingested_count,
            total_triplets=total_triplets,
            error_count=len(errors),
        )
        return ingested_count, total_triplets, errors
