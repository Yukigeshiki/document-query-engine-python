"""Tests for KGIngestionService.

Constructs the service with mocked backends to isolate the ingest()
logic (deterministic doc_id, predelete-then-insert) from the storage layers.
"""

import hashlib
from unittest.mock import MagicMock, patch

import pytest

from app.services.kg_ingestion import KGIngestionService


def _make_ingestion_service() -> tuple[
    KGIngestionService, MagicMock, MagicMock
]:
    """Build a KGIngestionService with mocked backends."""
    mock_graph_store = MagicMock()
    mock_graph_store.node_label = "Entity"

    mock_vector_index = MagicMock()
    mock_vector_store = MagicMock()
    mock_vector_index.vector_store = mock_vector_store

    mock_storage_context = MagicMock()

    service = KGIngestionService(
        graph_store=mock_graph_store,
        vector_index=mock_vector_index,
        storage_context=mock_storage_context,
        cache=None,
        max_triplets=10,
    )
    return service, mock_vector_index, mock_vector_store


@pytest.mark.asyncio
@patch("app.services.kg_ingestion.extract_triplets", return_value=[])
@patch("app.services.kg_ingestion.SentenceSplitter")
@patch.object(KGIngestionService, "_count_triplets", return_value=0)
async def test_ingest_with_source_id_is_deterministic(
    _mock_count: MagicMock,
    mock_splitter_cls: MagicMock,
    _mock_extract: MagicMock,
) -> None:
    """Same source_id must produce the same doc_id across calls."""
    service, _vector_index, _vector_store = _make_ingestion_service()

    mock_node = MagicMock()
    mock_node.metadata = {}
    mock_node.node_id = "node-1"
    mock_node.get_content.return_value = "chunk content"
    mock_splitter_cls.return_value.get_nodes_from_documents.return_value = (
        [mock_node]
    )

    source_id = "gcs:gs://bucket/uploads/abc/doc.txt:sha256-stub"
    expected_doc_id = hashlib.sha256(source_id.encode()).hexdigest()

    doc_id_1, _ = await service.ingest(text="hello", source_id=source_id)
    doc_id_2, _ = await service.ingest(text="hello", source_id=source_id)

    assert doc_id_1 == expected_doc_id
    assert doc_id_2 == expected_doc_id


@pytest.mark.asyncio
@patch("app.services.kg_ingestion.extract_triplets", return_value=[])
@patch("app.services.kg_ingestion.SentenceSplitter")
@patch.object(KGIngestionService, "_count_triplets", return_value=0)
async def test_ingest_with_source_id_predeletes_vector_rows(
    _mock_count: MagicMock,
    mock_splitter_cls: MagicMock,
    _mock_extract: MagicMock,
) -> None:
    """
    Predelete is called before insert.

    PGVectorStore.add() does not enforce uniqueness on node_id, so a
    Celery retry would otherwise create duplicate vector rows.
    """
    service, vector_index, vector_store = _make_ingestion_service()

    mock_node = MagicMock()
    mock_node.metadata = {}
    mock_node.node_id = "node-1"
    mock_node.get_content.return_value = "chunk content"
    mock_splitter_cls.return_value.get_nodes_from_documents.return_value = (
        [mock_node]
    )

    source_id = "gcs:gs://bucket/uploads/abc/doc.txt:sha256-stub"
    expected_doc_id = hashlib.sha256(source_id.encode()).hexdigest()

    await service.ingest(text="hello", source_id=source_id)

    vector_store.delete.assert_called_once_with(ref_doc_id=expected_doc_id)
    vector_index.insert_nodes.assert_called_once()


@pytest.mark.asyncio
@patch("app.services.kg_ingestion.extract_triplets", return_value=[])
@patch("app.services.kg_ingestion.SentenceSplitter")
@patch.object(KGIngestionService, "_count_triplets", return_value=0)
async def test_ingest_predelete_failure_does_not_abort(
    _mock_count: MagicMock,
    mock_splitter_cls: MagicMock,
    _mock_extract: MagicMock,
) -> None:
    """
    A predelete failure must be logged but not abort the ingestion.

    Fail-open: transient connection issues during the predelete should
    not prevent the ingest from proceeding.
    """
    service, vector_index, vector_store = _make_ingestion_service()
    vector_store.delete.side_effect = RuntimeError("transient pg error")

    mock_node = MagicMock()
    mock_node.metadata = {}
    mock_node.node_id = "node-1"
    mock_node.get_content.return_value = "chunk content"
    mock_splitter_cls.return_value.get_nodes_from_documents.return_value = (
        [mock_node]
    )

    await service.ingest(text="hello", source_id="gcs:test:hash")

    vector_store.delete.assert_called_once()
    vector_index.insert_nodes.assert_called_once()
