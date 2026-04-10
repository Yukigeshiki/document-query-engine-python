"""Query, subgraph, and document graph retrieval from Neo4j and pgvector."""

import asyncio
import time
from functools import partial
from typing import Any

import structlog
from llama_index.core import StorageContext, VectorStoreIndex
from llama_index.core.query_engine import RetrieverQueryEngine
from llama_index.core.response_synthesizers import get_response_synthesizer
from llama_index.graph_stores.neo4j import Neo4jGraphStore

from app.core.errors import QueryError, ServiceUnavailableError
from app.core.metrics import (
    kg_query_cache_hits_total,
    kg_query_cache_misses_total,
    kg_query_duration_seconds,
    kg_query_total,
    kg_subgraph_duration_seconds,
    kg_subgraph_total,
)
from app.models.knowledge_graph import (
    ResponseMode,
    RetrievalMode,
    SourceNodeInfo,
    SourceNodeMetadata,
    SourceRetrievalType,
    SubgraphEdge,
    SubgraphNode,
)
from app.services.dual_retriever import DualRetriever
from app.services.neo4j_kg_retriever import Neo4jKGRetriever
from app.services.query_cache import QueryCache

logger = structlog.stdlib.get_logger(__name__)


class KGQueryService:
    """Handles querying, subgraph retrieval, and document graph reads."""

    def __init__(
        self,
        graph_store: Neo4jGraphStore,
        vector_index: VectorStoreIndex,
        storage_context: StorageContext,
        cache: QueryCache | None,
        vector_top_k: int,
        postgres_enabled: bool,
    ) -> None:
        self._graph_store = graph_store
        self._vector_index = vector_index
        self._storage_context = storage_context
        self._cache = cache
        self._vector_top_k = vector_top_k
        self._postgres_enabled = postgres_enabled

    async def query(
        self,
        query_text: str,
        include_text: bool = True,
        response_mode: ResponseMode = ResponseMode.TREE_SUMMARIZE,
        retrieval_mode: RetrievalMode = RetrievalMode.DUAL,
    ) -> tuple[str, list[SourceNodeInfo]]:
        """
        Query using KG, vector, or dual retrieval.

        Returns a tuple of (response_text, source_nodes).
        """
        start = time.perf_counter()
        loop = asyncio.get_running_loop()
        try:
            mode = RetrievalMode(retrieval_mode)

            if not self._postgres_enabled and mode != RetrievalMode.KG_ONLY:
                logger.warning(
                    "vector_store_not_available_falling_back_to_kg_only",
                    requested_mode=retrieval_mode,
                )
                mode = RetrievalMode.KG_ONLY

            def _query_sync() -> tuple[str, list[SourceNodeInfo]]:
                query_embedding: list[float] | None = None
                if self._cache is not None:
                    query_embedding = self._cache.embed_query(query_text)
                    cached = self._cache.get(
                        query_text, include_text,
                        response_mode, retrieval_mode,
                        embedding=query_embedding,
                    )
                    if cached is not None:
                        kg_query_cache_hits_total.inc()
                        response_text, source_nodes, _ = cached
                        return response_text, source_nodes
                    kg_query_cache_misses_total.inc()

                kg_retriever = Neo4jKGRetriever(
                    graph_store=self._graph_store,
                    docstore=self._storage_context.docstore,
                    include_text=include_text,
                )
                vector_retriever = self._vector_index.as_retriever(
                    similarity_top_k=self._vector_top_k
                )
                retriever = DualRetriever(
                    kg_retriever=kg_retriever,
                    vector_retriever=vector_retriever,
                    mode=mode,
                )
                synthesizer = get_response_synthesizer(
                    response_mode=response_mode  # type: ignore[arg-type]
                )
                query_engine = RetrieverQueryEngine(
                    retriever=retriever,
                    response_synthesizer=synthesizer,
                )
                response = query_engine.query(query_text)

                source_nodes = [
                    SourceNodeInfo(
                        source_type=node.node.metadata.get(
                            "_source_type",
                            SourceRetrievalType.VECTOR,
                        ),
                        score=node.score,
                        metadata=SourceNodeMetadata(
                            file_name=node.node.metadata.get("file_name"),
                        ),
                    )
                    for node in response.source_nodes
                ]

                if self._cache is not None:
                    self._cache.set(
                        query_text, include_text,
                        response_mode, retrieval_mode,
                        str(response), source_nodes,
                        embedding=query_embedding,
                    )

                return str(response), source_nodes

            response_text, source_nodes = await loop.run_in_executor(
                None, _query_sync
            )

            kg_query_duration_seconds.labels(
                retrieval_mode=mode.value
            ).observe(time.perf_counter() - start)
            kg_query_total.labels(
                retrieval_mode=mode.value, status="success"
            ).inc()

            logger.info(
                "query_completed",
                query=query_text,
                retrieval_mode=mode.value,
                num_sources=len(source_nodes),
            )
            return response_text, source_nodes
        except QueryError:
            kg_query_total.labels(
                retrieval_mode=retrieval_mode, status="error"
            ).inc()
            raise
        except Exception as exc:
            kg_query_total.labels(
                retrieval_mode=retrieval_mode, status="error"
            ).inc()
            logger.error(
                "query_failed", query=query_text, error=str(exc)
            )
            raise QueryError(detail=f"Query failed: {exc}") from exc

    @staticmethod
    def _records_to_graph(
        records: list[dict[str, Any]],
    ) -> tuple[list[SubgraphNode], list[SubgraphEdge]]:
        """Convert Neo4j query records to SubgraphNode/SubgraphEdge lists."""
        node_map: dict[str, SubgraphNode] = {}
        edges: list[SubgraphEdge] = []

        for record in records:
            src_id = str(record["source_id"])
            tgt_id = str(record["target_id"])

            if src_id not in node_map:
                labels = record.get("source_labels", [])
                node_map[src_id] = SubgraphNode(
                    id=src_id,
                    label=labels[0] if labels else None,
                    properties={},
                )
            if tgt_id not in node_map:
                labels = record.get("target_labels", [])
                node_map[tgt_id] = SubgraphNode(
                    id=tgt_id,
                    label=labels[0] if labels else None,
                    properties={},
                )

            edges.append(SubgraphEdge(
                source=src_id,
                target=tgt_id,
                relation=str(record["relation"]),
            ))

        return list(node_map.values()), edges

    async def get_subgraph(
        self,
        entity: str,
        depth: int = 2,
    ) -> tuple[list[SubgraphNode], list[SubgraphEdge]]:
        """
        Retrieve a subgraph around an entity using Cypher.

        Returns a tuple of (nodes, edges).

        Neo4j schema conventions this query depends on:
        - Entity nodes are identified by an `id` string property
        - Entity matching is case-insensitive (`toLower`)
        - Traversal follows all relationship types up to `depth` hops
        """
        cypher = (
            f"MATCH path = (start)-[*1..{depth}]-(connected) "
            "WHERE toLower(start.id) = toLower($entity) "
            "UNWIND relationships(path) AS rel "
            "WITH DISTINCT startNode(rel) AS src, rel, endNode(rel) AS tgt "
            "RETURN src.id AS source_id, labels(src) AS source_labels, "
            "type(rel) AS relation, "
            "tgt.id AS target_id, labels(tgt) AS target_labels"
        )

        start = time.perf_counter()
        loop = asyncio.get_running_loop()
        try:
            records: list[dict[str, Any]] = await loop.run_in_executor(
                None,
                partial(
                    self._graph_store.query,
                    cypher,
                    {"entity": entity},
                ),
            )

            nodes, edges = self._records_to_graph(records)

            kg_subgraph_duration_seconds.observe(time.perf_counter() - start)
            kg_subgraph_total.inc()

            logger.info(
                "subgraph_retrieved",
                entity=entity,
                depth=depth,
                nodes=len(nodes),
                edges=len(edges),
            )
            return nodes, edges
        except ServiceUnavailableError:
            raise
        except Exception as exc:
            logger.error(
                "subgraph_query_failed", entity=entity, error=str(exc)
            )
            raise QueryError(
                detail=f"Subgraph query failed: {exc}"
            ) from exc

    async def get_document_graph(
        self,
        doc_ids: list[str],
    ) -> tuple[list[SubgraphNode], list[SubgraphEdge]]:
        """
        Retrieve the graph for a specific document.

        Accepts multiple doc_ids to handle multi-chunk documents.
        Finds all entities associated with the documents' nodes
        and fetches their relationships from Neo4j.

        Neo4j schema conventions these queries depend on:
        - Relationships carry a `source_node_ids` list property
        - Entity nodes are identified by an `id` string property
        """
        loop = asyncio.get_running_loop()

        def _get_doc_graph_sync() -> (
            tuple[list[SubgraphNode], list[SubgraphEdge]]
        ):
            ref_info = (
                self._storage_context.docstore.get_all_ref_doc_info()
            )
            if not ref_info:
                return [], []

            doc_node_ids: set[str] = set()
            for did in doc_ids:
                if did in ref_info:
                    doc_node_ids.update(ref_info[did].node_ids)

            if not doc_node_ids:
                return [], []

            node_id_list = list(doc_node_ids)
            entity_records = self._graph_store.query(
                "MATCH (src)-[r]->(tgt) "
                "WHERE ANY(nid IN r.source_node_ids "
                "WHERE nid IN $node_ids) "
                "RETURN DISTINCT src.id AS entity_id "
                "UNION "
                "MATCH (src)-[r]->(tgt) "
                "WHERE ANY(nid IN r.source_node_ids "
                "WHERE nid IN $node_ids) "
                "RETURN DISTINCT tgt.id AS entity_id",
                {"node_ids": node_id_list},
            )
            if not entity_records:
                return [], []

            entity_list = [r["entity_id"] for r in entity_records]
            cypher = (
                "MATCH (src)-[rel]->(tgt) "
                "WHERE src.id IN $entities OR tgt.id IN $entities "
                "RETURN src.id AS source_id, "
                "labels(src) AS source_labels, "
                "type(rel) AS relation, "
                "tgt.id AS target_id, "
                "labels(tgt) AS target_labels"
            )
            records = self._graph_store.query(
                cypher, {"entities": entity_list}
            )

            return self._records_to_graph(records)

        try:
            return await loop.run_in_executor(None, _get_doc_graph_sync)
        except ServiceUnavailableError:
            raise
        except Exception as exc:
            logger.error(
                "document_graph_query_failed",
                doc_ids=doc_ids,
                error=str(exc),
            )
            raise QueryError(
                detail=f"Document graph query failed: {exc}"
            ) from exc
