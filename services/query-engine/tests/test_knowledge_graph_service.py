"""Service-level tests for KnowledgeGraphService.

Constructs the service with __new__() to bypass the heavy LlamaIndex/Neo4j
initialization, then directly assigns mocked internals. This isolates the
ingest() logic (deterministic doc_id, predelete-then-insert) from the
storage backends.
"""

import hashlib
from unittest.mock import MagicMock, patch

import pytest

from app.services.knowledge_graph import KnowledgeGraphService


def _make_service_with_mocks() -> tuple[KnowledgeGraphService, MagicMock, MagicMock]:
    """Build a KnowledgeGraphService with mocked internals (no real init)."""
    service = KnowledgeGraphService.__new__(KnowledgeGraphService)
    service._cache = None  # type: ignore[attr-defined]
    service._engine = None  # type: ignore[attr-defined]
    service._postgres_enabled = True  # type: ignore[attr-defined]
    service._max_triplets = 10  # type: ignore[attr-defined]

    mock_vector_index = MagicMock()
    mock_vector_store = MagicMock()
    mock_vector_index.vector_store = mock_vector_store
    service._vector_index = mock_vector_index  # type: ignore[attr-defined]

    mock_index = MagicMock()
    mock_index._extract_triplets.return_value = []  # no triplets => fast path
    mock_index.index_struct = MagicMock()
    service._index = mock_index  # type: ignore[attr-defined]

    mock_storage_context = MagicMock()
    service._storage_context = mock_storage_context  # type: ignore[attr-defined]

    mock_graph_store = MagicMock()
    service._graph_store = mock_graph_store  # type: ignore[attr-defined]

    return service, mock_vector_index, mock_vector_store


@pytest.mark.asyncio
@patch("app.services.knowledge_graph.SentenceSplitter")
@patch.object(KnowledgeGraphService, "_count_triplets", return_value=0)
async def test_ingest_with_source_id_is_deterministic(
    _mock_count: MagicMock,
    mock_splitter_cls: MagicMock,
) -> None:
    """Same source_id must produce the same doc_id across calls."""
    service, _vector_index, _vector_store = _make_service_with_mocks()

    # Splitter returns one fake node so we exercise the insert path
    mock_node = MagicMock()
    mock_node.metadata = {}
    mock_node.node_id = "node-1"
    mock_node.get_content.return_value = "chunk content"
    mock_splitter_cls.return_value.get_nodes_from_documents.return_value = [mock_node]

    source_id = "gcs:gs://bucket/uploads/abc/doc.txt:sha256-stub"
    expected_doc_id = hashlib.sha256(source_id.encode()).hexdigest()

    doc_id_1, _ = await service.ingest(text="hello", source_id=source_id)
    doc_id_2, _ = await service.ingest(text="hello", source_id=source_id)

    assert doc_id_1 == expected_doc_id
    assert doc_id_2 == expected_doc_id


@pytest.mark.asyncio
@patch("app.services.knowledge_graph.SentenceSplitter")
@patch.object(KnowledgeGraphService, "_count_triplets", return_value=0)
async def test_ingest_with_source_id_predeletes_vector_rows(
    _mock_count: MagicMock,
    mock_splitter_cls: MagicMock,
) -> None:
    """Predelete is called before insert when source_id is provided.

    This is the key idempotency guard: PGVectorStore.add() does not enforce
    uniqueness on node_id, so a Celery retry would otherwise create duplicate
    vector rows. The predelete keyed on doc_id wipes any prior state.
    """
    service, vector_index, vector_store = _make_service_with_mocks()

    mock_node = MagicMock()
    mock_node.metadata = {}
    mock_node.node_id = "node-1"
    mock_node.get_content.return_value = "chunk content"
    mock_splitter_cls.return_value.get_nodes_from_documents.return_value = [mock_node]

    source_id = "gcs:gs://bucket/uploads/abc/doc.txt:sha256-stub"
    expected_doc_id = hashlib.sha256(source_id.encode()).hexdigest()

    await service.ingest(text="hello", source_id=source_id)

    vector_store.delete.assert_called_once_with(ref_doc_id=expected_doc_id)
    vector_index.insert_nodes.assert_called_once()


@pytest.mark.asyncio
@patch("app.services.knowledge_graph.SentenceSplitter")
@patch.object(KnowledgeGraphService, "_count_triplets", return_value=0)
async def test_ingest_predelete_failure_does_not_abort(
    _mock_count: MagicMock,
    mock_splitter_cls: MagicMock,
) -> None:
    """A predelete failure must be logged but not abort the ingestion.

    Vector store delete on a non-existent ref_doc_id should be a no-op,
    but if the underlying call raises (e.g. transient connection issue),
    we still proceed with the insert — fail-open behavior.
    """
    service, vector_index, vector_store = _make_service_with_mocks()
    vector_store.delete.side_effect = RuntimeError("transient pg error")

    mock_node = MagicMock()
    mock_node.metadata = {}
    mock_node.node_id = "node-1"
    mock_node.get_content.return_value = "chunk content"
    mock_splitter_cls.return_value.get_nodes_from_documents.return_value = [mock_node]

    # Should NOT raise
    await service.ingest(text="hello", source_id="gcs:test:hash")

    vector_store.delete.assert_called_once()
    vector_index.insert_nodes.assert_called_once()
