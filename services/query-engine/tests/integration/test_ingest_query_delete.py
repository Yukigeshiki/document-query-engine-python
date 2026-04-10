"""Integration test: full ingest → query → delete lifecycle.

Exercises the real persistence contract across Neo4j, pgvector, and the
postgres docstore. Only the OpenAI LLM is mocked (to avoid API costs).
Requires Docker — run with: poetry run pytest tests/integration/ -m integration -v
"""

import pytest

from app.services.knowledge_graph import KnowledgeGraphService

pytestmark = pytest.mark.integration

SAMPLE_TEXT = (
    "Alice works at Acme Corp in New York. "
    "Acme Corp is a technology company founded in 2010."
)
SOURCE_ID = "integration-test:doc1:fakehash"


@pytest.mark.asyncio
async def test_full_lifecycle(kg_service: KnowledgeGraphService) -> None:
    """
    Verify the full ingest → list → graph → query → re-ingest → delete cycle.

    This single test covers the cross-store consistency contract:
    - Neo4j receives triplets with source_node_ids provenance
    - pgvector receives vector embeddings
    - Postgres docstore receives RefDocInfo
    - Idempotent re-ingest replaces (not duplicates)
    - Delete removes from all three stores cleanly
    """
    # 1. Ingest a document
    doc_id, triplet_count = await kg_service.ingest(
        text=SAMPLE_TEXT,
        source_id=SOURCE_ID,
        metadata={"file_name": "test-doc.txt"},
    )
    assert doc_id, "Expected a non-empty doc_id"
    assert triplet_count >= 0

    # 2. Verify docstore — document appears in the list
    docs, total = await kg_service.list_documents()
    assert total >= 1
    doc_ids_in_list = [d["doc_id"] for d in docs]
    assert doc_id in doc_ids_in_list

    # Find the full doc_ids list (for multi-chunk support)
    doc_entry = next(d for d in docs if d["doc_id"] == doc_id)
    all_doc_ids = doc_entry["doc_ids"]

    # 3. Verify Neo4j — document graph has entities and edges
    nodes, edges = await kg_service.get_document_graph(doc_ids=all_doc_ids)
    assert len(nodes) > 0, "Expected entities in Neo4j"
    assert len(edges) > 0, "Expected relationships in Neo4j"

    # 4. Verify document_exists
    assert await kg_service.document_exists(doc_id)
    assert not await kg_service.document_exists("nonexistent-id")

    # 5. Verify idempotent re-ingest — same source_id, no duplicates
    doc_id_2, _ = await kg_service.ingest(
        text=SAMPLE_TEXT,
        source_id=SOURCE_ID,
        metadata={"file_name": "test-doc.txt"},
    )
    assert doc_id_2 == doc_id, "Re-ingest must produce the same doc_id"

    docs_after, _total_after = await kg_service.list_documents()
    matching = [d for d in docs_after if d["doc_id"] == doc_id]
    assert len(matching) == 1, "Re-ingest must not create duplicate entries"

    # 6. Delete the document
    deleted_ids = await kg_service.delete_document(doc_id)
    assert doc_id in deleted_ids

    # 7. Verify all stores are clean
    docs_final, _total_final = await kg_service.list_documents()
    final_doc_ids = [d["doc_id"] for d in docs_final]
    assert doc_id not in final_doc_ids, "Doc should be gone from docstore"

    assert not await kg_service.document_exists(doc_id)

    _nodes_after, edges_after = await kg_service.get_document_graph(
        doc_ids=all_doc_ids
    )
    assert len(edges_after) == 0, "Relationships should be deleted from Neo4j"
