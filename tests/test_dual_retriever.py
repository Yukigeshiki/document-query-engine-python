"""Tests for the dual retriever."""

from unittest.mock import MagicMock

from llama_index.core.schema import NodeWithScore, TextNode

from app.models.knowledge_graph import RetrievalMode
from app.services.dual_retriever import DualRetriever


def _make_node(node_id: str, score: float) -> NodeWithScore:
    """Create a NodeWithScore for testing."""
    node = TextNode(id_=node_id, text=f"Text for {node_id}")
    return NodeWithScore(node=node, score=score)


def _mock_retriever(nodes: list[NodeWithScore]) -> MagicMock:
    """Create a mock retriever that returns the given nodes."""
    retriever = MagicMock()
    retriever.retrieve.return_value = nodes
    return retriever


class TestDualRetriever:
    """Tests for DualRetriever merge and dedup logic."""

    def test_dual_merges_results(self) -> None:
        """Verify dual mode returns nodes from both retrievers."""
        kg_nodes = [_make_node("a", 0.8), _make_node("b", 0.6)]
        vector_nodes = [_make_node("c", 0.9), _make_node("d", 0.5)]

        retriever = DualRetriever(
            kg_retriever=_mock_retriever(kg_nodes),
            vector_retriever=_mock_retriever(vector_nodes),
            mode=RetrievalMode.DUAL,
        )
        results = retriever.retrieve("test query")

        assert len(results) == 4
        assert results[0].node.node_id == "c"  # highest score

    def test_dual_deduplicates_keeps_higher_score(self) -> None:
        """Verify same node_id from both retrievers keeps higher score."""
        kg_nodes = [_make_node("shared", 0.6)]
        vector_nodes = [_make_node("shared", 0.9)]

        retriever = DualRetriever(
            kg_retriever=_mock_retriever(kg_nodes),
            vector_retriever=_mock_retriever(vector_nodes),
            mode=RetrievalMode.DUAL,
        )
        results = retriever.retrieve("test query")

        assert len(results) == 1
        assert results[0].score == 0.9

    def test_kg_only_mode(self) -> None:
        """Verify kg_only mode only uses KG retriever."""
        kg_nodes = [_make_node("a", 0.8)]
        vector_nodes = [_make_node("b", 0.9)]

        kg_retriever = _mock_retriever(kg_nodes)
        vector_retriever = _mock_retriever(vector_nodes)

        retriever = DualRetriever(
            kg_retriever=kg_retriever,
            vector_retriever=vector_retriever,
            mode=RetrievalMode.KG_ONLY,
        )
        results = retriever.retrieve("test query")

        assert len(results) == 1
        assert results[0].node.node_id == "a"
        vector_retriever.retrieve.assert_not_called()

    def test_vector_only_mode(self) -> None:
        """Verify vector_only mode only uses vector retriever."""
        kg_nodes = [_make_node("a", 0.8)]
        vector_nodes = [_make_node("b", 0.9)]

        kg_retriever = _mock_retriever(kg_nodes)
        vector_retriever = _mock_retriever(vector_nodes)

        retriever = DualRetriever(
            kg_retriever=kg_retriever,
            vector_retriever=vector_retriever,
            mode=RetrievalMode.VECTOR_ONLY,
        )
        results = retriever.retrieve("test query")

        assert len(results) == 1
        assert results[0].node.node_id == "b"
        kg_retriever.retrieve.assert_not_called()

    def test_empty_results(self) -> None:
        """Verify empty results handled gracefully."""
        retriever = DualRetriever(
            kg_retriever=_mock_retriever([]),
            vector_retriever=_mock_retriever([]),
            mode=RetrievalMode.DUAL,
        )
        results = retriever.retrieve("test query")
        assert results == []

    def test_kg_miss_sentinel_filtered(self) -> None:
        """Verify the KG 'No relationships found.' sentinel is dropped."""
        sentinel = NodeWithScore(
            node=TextNode(id_="sentinel", text="No relationships found."),
            score=1.0,
        )
        vector_nodes = [_make_node("real", 0.8)]

        retriever = DualRetriever(
            kg_retriever=_mock_retriever([sentinel]),
            vector_retriever=_mock_retriever(vector_nodes),
            mode=RetrievalMode.DUAL,
        )
        results = retriever.retrieve("test query")

        assert len(results) == 1
        assert results[0].node.node_id == "real"

    def test_kg_miss_sentinel_in_kg_only_mode(self) -> None:
        """Verify sentinel is also filtered in kg_only mode."""
        sentinel = NodeWithScore(
            node=TextNode(id_="sentinel", text="No relationships found."),
            score=1.0,
        )

        retriever = DualRetriever(
            kg_retriever=_mock_retriever([sentinel]),
            vector_retriever=_mock_retriever([]),
            mode=RetrievalMode.KG_ONLY,
        )
        results = retriever.retrieve("test query")

        assert results == []
