"""Tests for the Celery ingest source task."""

from unittest.mock import AsyncMock, MagicMock, patch

from app.models.knowledge_graph import SourceType
from app.worker.tasks import ingest_source_task


@patch("app.worker.tasks._get_kg_service")
@patch("app.services.ingestion_pipeline.default_registry")
def test_ingest_source_task_returns_result(
    mock_registry: MagicMock,
    mock_get_service: MagicMock,
) -> None:
    """Verify task calls pipeline and returns expected shape."""
    mock_service = AsyncMock()
    mock_service.ingest.return_value = ("doc-id", 5)
    mock_get_service.return_value = mock_service

    mock_doc = MagicMock()
    mock_doc.get_content.return_value = "Document text"
    mock_doc.metadata = {}

    connector = MagicMock()
    connector.load_documents.return_value = iter([mock_doc, mock_doc])
    mock_registry.get.return_value = connector

    result = ingest_source_task(SourceType.GCS, {"bucket": "test", "prefix": "docs/"})

    assert result["source_type"] == SourceType.GCS
    assert result["total_documents"] == 2
    assert result["total_triplets"] == 10
    assert result["errors"] == []


@patch("app.worker.tasks._get_kg_service")
@patch("app.services.ingestion_pipeline.default_registry")
def test_ingest_source_task_empty_source(
    mock_registry: MagicMock,
    mock_get_service: MagicMock,
) -> None:
    """Verify task handles empty source gracefully."""
    mock_service = AsyncMock()
    mock_get_service.return_value = mock_service

    connector = MagicMock()
    connector.load_documents.return_value = iter([])
    mock_registry.get.return_value = connector

    result = ingest_source_task(SourceType.GCS, {"bucket": "test", "prefix": "empty/"})

    assert result["total_documents"] == 0
    assert result["total_triplets"] == 0
    assert result["errors"] == []
