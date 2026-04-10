"""Tests for the Neo4j-backed KG retriever."""

from unittest.mock import MagicMock, patch

import pytest

from app.services.neo4j_kg_retriever import Neo4jKGRetriever


@pytest.fixture
def mock_graph_store() -> MagicMock:
    """Create a mock Neo4jGraphStore."""
    store = MagicMock()
    store.node_label = "Entity"
    return store


@pytest.fixture
def mock_docstore() -> MagicMock:
    """Create a mock docstore."""
    return MagicMock()


@pytest.fixture
def retriever(
    mock_graph_store: MagicMock, mock_docstore: MagicMock
) -> Neo4jKGRetriever:
    """Create a Neo4jKGRetriever with mocked backends."""
    return Neo4jKGRetriever(
        graph_store=mock_graph_store,
        docstore=mock_docstore,
        include_text=True,
    )


@patch("app.services.neo4j_kg_retriever.Settings")
def test_retrieves_relationship_text(
    mock_settings: MagicMock,
    retriever: Neo4jKGRetriever,
    mock_graph_store: MagicMock,
) -> None:
    """Verify retriever returns relationship context from Neo4j."""
    mock_settings.llm.predict.return_value = "KEYWORDS: Alice, Acme"

    mock_graph_store.query.return_value = [
        {
            "entity": "Alice",
            "relation": "WORKS_AT",
            "related": "Acme Corp",
            "source_node_ids": ["node-1"],
        },
    ]

    from llama_index.core.schema import QueryBundle
    results = retriever.retrieve(QueryBundle(query_str="Where does Alice work?"))

    assert len(results) >= 1
    # First result is the relationship text node
    assert "Alice" in results[0].node.get_content()
    assert "WORKS_AT" in results[0].node.get_content()
    assert "Acme Corp" in results[0].node.get_content()


@patch("app.services.neo4j_kg_retriever.Settings")
def test_returns_empty_when_no_entities_match(
    mock_settings: MagicMock,
    retriever: Neo4jKGRetriever,
    mock_graph_store: MagicMock,
) -> None:
    """Verify empty results when Neo4j finds no matching entities."""
    mock_settings.llm.predict.return_value = "KEYWORDS: nonexistent"
    mock_graph_store.query.return_value = []

    from llama_index.core.schema import QueryBundle
    results = retriever.retrieve(QueryBundle(query_str="Something unknown"))

    assert results == []


@patch("app.services.neo4j_kg_retriever.Settings")
def test_retrieves_source_text_nodes(
    mock_settings: MagicMock,
    retriever: Neo4jKGRetriever,
    mock_graph_store: MagicMock,
    mock_docstore: MagicMock,
) -> None:
    """Verify retriever fetches source text chunks from docstore."""
    mock_settings.llm.predict.return_value = "KEYWORDS: Alice"

    mock_graph_store.query.return_value = [
        {
            "entity": "Alice",
            "relation": "WORKS_AT",
            "related": "Acme",
            "source_node_ids": ["node-1", "node-2"],
        },
    ]

    from llama_index.core.schema import TextNode as LITextNode
    mock_doc = LITextNode(text="source chunk text", id_="source-node")
    # Access the actual docstore instance the retriever holds
    retriever._docstore.get_document.return_value = mock_doc

    from llama_index.core.schema import QueryBundle
    results = retriever.retrieve(QueryBundle(query_str="Alice"))

    # Should have relationship text + source nodes
    assert len(results) >= 2
    assert retriever._docstore.get_document.call_count == 2


@patch("app.services.neo4j_kg_retriever.Settings")
def test_keyword_extraction_fallback(
    mock_settings: MagicMock,
    retriever: Neo4jKGRetriever,
    mock_graph_store: MagicMock,
) -> None:
    """Verify fallback to full query when LLM doesn't return KEYWORDS format."""
    mock_settings.llm.predict.return_value = "I don't understand."
    mock_graph_store.query.return_value = []

    from llama_index.core.schema import QueryBundle
    retriever.retrieve(QueryBundle(query_str="test query"))

    # Should have used the full query as a keyword fallback
    call_args = mock_graph_store.query.call_args
    # query() is called as query(cypher, params_dict) — positional args
    params = call_args[0][1] if len(call_args[0]) > 1 else call_args[1]
    assert "test query" in params["keywords"]
