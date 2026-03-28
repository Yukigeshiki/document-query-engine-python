"""Dual retriever combining KG traversal and vector similarity."""

from llama_index.core.retrievers import BaseRetriever
from llama_index.core.schema import NodeWithScore, QueryBundle

from app.models.knowledge_graph import RetrievalMode, SourceRetrievalType

# LlamaIndex KG retriever returns this synthetic node when it finds nothing
_KG_MISS_SENTINEL = "No relationships found."


class DualRetriever(BaseRetriever):
    """
    Merges results from a KG retriever and a vector retriever.

    Deduplicates by node_id, keeping the higher score when
    the same node appears in both result sets.
    """

    def __init__(
        self,
        kg_retriever: BaseRetriever,
        vector_retriever: BaseRetriever,
        mode: RetrievalMode = RetrievalMode.DUAL,
    ) -> None:
        self._kg_retriever = kg_retriever
        self._vector_retriever = vector_retriever
        self._mode = mode
        super().__init__()

    def _retrieve(self, query_bundle: QueryBundle) -> list[NodeWithScore]:
        """
        Run applicable retrievers based on mode and merge results.

        Nodes appearing in both KG and vector results are deduplicated
        by node_id, keeping whichever has the higher relevance score.
        The KG miss sentinel ("No relationships found.") is filtered out
        to prevent it from contaminating vector results in dual mode.
        Results are returned sorted by score descending.
        """
        results: dict[str, NodeWithScore] = {}

        if self._mode in (RetrievalMode.KG_ONLY, RetrievalMode.DUAL):
            for node in self._kg_retriever.retrieve(query_bundle):
                if node.node.get_content() == _KG_MISS_SENTINEL:
                    continue
                node.node.metadata["_source_type"] = SourceRetrievalType.KG
                results[node.node.node_id] = node

        if self._mode in (RetrievalMode.VECTOR_ONLY, RetrievalMode.DUAL):
            for node in self._vector_retriever.retrieve(query_bundle):
                existing = results.get(node.node.node_id)
                if existing is None or (node.score or 0) > (existing.score or 0):
                    node.node.metadata["_source_type"] = SourceRetrievalType.VECTOR
                    results[node.node.node_id] = node

        return sorted(
            results.values(),
            key=lambda n: n.score or 0,
            reverse=True,
        )
