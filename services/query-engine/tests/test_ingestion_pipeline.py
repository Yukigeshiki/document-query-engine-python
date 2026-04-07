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


@pytest.mark.asyncio
@patch("app.services.ingestion_pipeline.default_registry")
async def test_pipeline_passes_stable_source_id_on_retry(
    mock_registry: MagicMock,
    mock_kg_service: AsyncMock,
) -> None:
    """Verify pipeline derives a deterministic source_id from each document.

    Running the pipeline twice over the same set of documents must produce
    the same source_id values both times — this is what makes the underlying
    Celery task safe to retry. The doc_id derived from this source_id is the
    sole guard against duplicates in the storage layers.
    """
    def make_connector() -> MagicMock:
        connector = MagicMock()
        connector.load_documents.return_value = iter([
            Document(
                text="content of doc one",
                metadata={"source_path": "gs://bucket/uploads/abc/doc1.txt"},
            ),
            Document(
                text="content of doc two",
                metadata={"source_path": "gs://bucket/uploads/abc/doc2.txt"},
            ),
        ])
        return connector

    mock_registry.get.side_effect = lambda _source_type: make_connector()

    pipeline = IngestionPipeline(kg_service=mock_kg_service)

    # First run
    await pipeline.run(SourceType.GCS, {"bucket": "bucket", "prefix": "uploads/abc/"})
    first_source_ids = [
        call.kwargs["source_id"]
        for call in mock_kg_service.ingest.call_args_list
    ]

    # Reset call history for the second run
    mock_kg_service.ingest.reset_mock()

    # Second run (simulates Celery retry)
    await pipeline.run(SourceType.GCS, {"bucket": "bucket", "prefix": "uploads/abc/"})
    second_source_ids = [
        call.kwargs["source_id"]
        for call in mock_kg_service.ingest.call_args_list
    ]

    # The source_ids must be identical across runs
    assert first_source_ids == second_source_ids
    assert len(first_source_ids) == 2

    # Each source_id has the expected shape: {source_type}:{source_path}:{content_hash}
    for source_id in first_source_ids:
        assert source_id.startswith(f"{SourceType.GCS.value}:gs://bucket/uploads/abc/")
        # The trailing 64 chars are the sha256 content hash hex digest
        assert len(source_id.rsplit(":", 1)[-1]) == 64


@pytest.mark.asyncio
@patch("app.services.ingestion_pipeline.default_registry")
async def test_pipeline_source_id_falls_back_to_file_name(
    mock_registry: MagicMock,
    mock_kg_service: AsyncMock,
) -> None:
    """Verify pipeline falls back to file_name when source_path is missing."""
    connector = MagicMock()
    connector.load_documents.return_value = iter([
        Document(text="content", metadata={"file_name": "report.pdf"}),
    ])
    mock_registry.get.return_value = connector

    pipeline = IngestionPipeline(kg_service=mock_kg_service)
    await pipeline.run(SourceType.GCS, {})

    source_id = mock_kg_service.ingest.call_args.kwargs["source_id"]
    assert "report.pdf" in source_id
