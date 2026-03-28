"""Tests for the ingestion pipeline."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from llama_index.core import Document

from app.core.errors import BadRequestError, IngestionError
from app.models.knowledge_graph import SourceType
from app.services.ingestion_pipeline import IngestionPipeline


@pytest.fixture
def mock_kg_service() -> AsyncMock:
    """Create a mock KnowledgeGraphService."""
    service = AsyncMock()
    service.ingest.return_value = ("doc-id", 3)
    return service


@pytest.fixture
def mock_connector() -> MagicMock:
    """Create a mock connector that returns sample documents."""
    connector = MagicMock()
    connector.load_documents.return_value = iter([
        Document(text="Document one"),
        Document(text="Document two"),
        Document(text="Document three"),
    ])
    return connector


@pytest.mark.asyncio
@patch("app.services.ingestion_pipeline.default_registry")
async def test_pipeline_ingests_all_documents(
    mock_registry: MagicMock,
    mock_connector: MagicMock,
    mock_kg_service: AsyncMock,
) -> None:
    """Verify pipeline ingests all documents from the connector."""
    mock_registry.get.return_value = mock_connector

    pipeline = IngestionPipeline(kg_service=mock_kg_service)
    total_docs, total_triplets, errors = await pipeline.run(
        SourceType.GCS, {"bucket": "test", "prefix": "docs/"}
    )

    assert total_docs == 3
    assert total_triplets == 9
    assert errors == []
    assert mock_kg_service.ingest.call_count == 3


@pytest.mark.asyncio
@patch("app.services.ingestion_pipeline.default_registry")
async def test_pipeline_handles_partial_failures(
    mock_registry: MagicMock,
    mock_connector: MagicMock,
    mock_kg_service: AsyncMock,
) -> None:
    """Verify pipeline captures per-document failures without aborting."""
    mock_registry.get.return_value = mock_connector
    mock_kg_service.ingest.side_effect = [
        ("doc-1", 3),
        IngestionError(detail="LLM error"),
        ("doc-3", 2),
    ]

    pipeline = IngestionPipeline(kg_service=mock_kg_service)
    total_docs, total_triplets, errors = await pipeline.run(
        SourceType.GCS, {"bucket": "test", "prefix": "docs/"}
    )

    assert total_docs == 2
    assert total_triplets == 5
    assert len(errors) == 1
    assert "LLM error" in errors[0]


@pytest.mark.asyncio
@patch("app.services.ingestion_pipeline.default_registry")
async def test_pipeline_empty_source(
    mock_registry: MagicMock,
    mock_kg_service: AsyncMock,
) -> None:
    """Verify pipeline handles empty source gracefully."""
    connector = MagicMock()
    connector.load_documents.return_value = iter([])
    mock_registry.get.return_value = connector

    pipeline = IngestionPipeline(kg_service=mock_kg_service)
    total_docs, total_triplets, errors = await pipeline.run(
        SourceType.GCS, {"bucket": "test", "prefix": "empty/"}
    )

    assert total_docs == 0
    assert total_triplets == 0
    assert errors == []
    mock_kg_service.ingest.assert_not_called()


@pytest.mark.asyncio
@patch("app.services.ingestion_pipeline.default_registry")
async def test_pipeline_unknown_source_type(
    mock_registry: MagicMock,
    mock_kg_service: AsyncMock,
) -> None:
    """Verify pipeline raises BadRequestError for unknown source types."""
    mock_registry.get.side_effect = BadRequestError(detail="Unknown source type")

    pipeline = IngestionPipeline(kg_service=mock_kg_service)
    with pytest.raises(BadRequestError, match="Unknown source type"):
        await pipeline.run(SourceType.GCS, {})
