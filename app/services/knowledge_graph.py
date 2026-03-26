"""Knowledge graph service backed by LlamaIndex KnowledgeGraphIndex."""

import asyncio
import uuid
from functools import partial
from typing import Any

import structlog
from llama_index.core import (
    Document,
    KnowledgeGraphIndex,
    Settings,
    StorageContext,
)
from llama_index.core.graph_stores.simple import SimpleGraphStore
from llama_index.core.graph_stores.types import GraphStore
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.graph_stores.neo4j import Neo4jGraphStore
from llama_index.llms.openai import OpenAI

from app.core.config import Settings as AppSettings
from app.core.errors import IngestionError, QueryError, ServiceUnavailableError
from app.models.knowledge_graph import SourceNodeInfo, SubgraphEdge, SubgraphNode

logger = structlog.stdlib.get_logger(__name__)


class KnowledgeGraphService:
    """Manages a LlamaIndex KnowledgeGraphIndex with Neo4j or in-memory graph store."""

    def __init__(self, config: AppSettings) -> None:
        """Initialize LlamaIndex settings, graph store, and index."""
        logger.info(
            "initializing_knowledge_graph_service",
            llm_model=config.llm_model,
            embedding_model=config.embedding_model,
        )

        Settings.llm = OpenAI(
            model=config.llm_model,
            temperature=config.llm_temperature,
            api_key=config.openai_api_key,
        )
        Settings.embed_model = OpenAIEmbedding(
            model_name=config.embedding_model,
            api_key=config.openai_api_key,
        )
        Settings.chunk_size = config.chunk_size

        self._neo4j_enabled = config.neo4j_enabled
        self._graph_store: GraphStore = self._create_graph_store(config)

        self._storage_context = StorageContext.from_defaults(
            graph_store=self._graph_store,
        )
        self._max_triplets = config.max_triplets_per_chunk

        self._index = KnowledgeGraphIndex(
            nodes=[],
            storage_context=self._storage_context,
            max_triplets_per_chunk=self._max_triplets,
        )

        logger.info(
            "knowledge_graph_service_initialized",
            backend="neo4j" if self._neo4j_enabled else "in_memory",
        )

    def _create_graph_store(self, config: AppSettings) -> GraphStore:
        """Create the appropriate graph store based on configuration."""
        if not config.neo4j_enabled:
            return SimpleGraphStore()

        try:
            store = Neo4jGraphStore(
                username=config.neo4j_username,
                password=config.neo4j_password,
                url=config.neo4j_uri,
                database=config.neo4j_database,
            )
            logger.info("neo4j_connected", uri=config.neo4j_uri)
            return store  # type: ignore[no-any-return]
        except Exception as exc:
            logger.warning(
                "neo4j_connection_failed_falling_back_to_in_memory",
                error=str(exc),
            )
            self._neo4j_enabled = False
            return SimpleGraphStore()

    def _count_triplets(self) -> int:
        """Count the number of triplets in the graph store."""
        if self._neo4j_enabled:
            try:
                result = self._neo4j_store.query(
                    "MATCH ()-[r]->() RETURN count(r) AS cnt"
                )
                return int(result[0]["cnt"]) if result else 0
            except Exception as exc:
                logger.warning("triplet_count_failed", error=str(exc))
                return -1
        return len(self._simple_store._data.graph_dict)

    @property
    def _neo4j_store(self) -> Neo4jGraphStore:
        """Access the graph store as Neo4jGraphStore."""
        if not isinstance(self._graph_store, Neo4jGraphStore):
            raise TypeError("Graph store is not Neo4jGraphStore")
        return self._graph_store

    @property
    def _simple_store(self) -> SimpleGraphStore:
        """Access the graph store as SimpleGraphStore."""
        if not isinstance(self._graph_store, SimpleGraphStore):
            raise TypeError("Graph store is not SimpleGraphStore")
        return self._graph_store

    def close(self) -> None:
        """Close the Neo4j connection if active."""
        if self._neo4j_enabled:
            self._neo4j_store.close()
            logger.info("neo4j_connection_closed")

    async def check_health(self) -> dict[str, str]:
        """
        Check graph store connectivity.

        Returns a dict with status, backend, and optional error.
        """
        if not self._neo4j_enabled:
            return {"status": "ok", "backend": "in_memory"}

        loop = asyncio.get_running_loop()
        try:
            await loop.run_in_executor(
                None,
                partial(self._neo4j_store.query, "RETURN 1"),
            )
            return {"status": "ok", "backend": "neo4j"}
        except Exception as exc:
            return {"status": "degraded", "backend": "neo4j", "error": str(exc)}

    async def ingest(
        self,
        text: str,
        metadata: dict[str, Any] | None = None,
    ) -> tuple[str, int]:
        """
        Ingest a document into the knowledge graph.

        Returns a tuple of (document_id, triplet_count).
        """
        doc_id = str(uuid.uuid4())
        doc = Document(text=text, doc_id=doc_id, metadata=metadata or {})

        loop = asyncio.get_running_loop()
        try:

            def _ingest_sync() -> int:
                triplets_before = self._count_triplets()
                self._index.insert(doc)
                triplets_after = self._count_triplets()
                return max(triplets_after - triplets_before, 0)

            triplet_count = await loop.run_in_executor(None, _ingest_sync)

            logger.info(
                "document_ingested",
                document_id=doc_id,
                triplet_count=triplet_count,
            )
            return doc_id, triplet_count
        except IngestionError:
            raise
        except Exception as exc:
            logger.error("ingestion_failed", document_id=doc_id, error=str(exc))
            raise IngestionError(detail=f"Failed to ingest document: {exc}") from exc

    async def query(
        self,
        query_text: str,
        include_text: bool = True,
        response_mode: str = "tree_summarize",
    ) -> tuple[str, list[SourceNodeInfo]]:
        """
        Query the knowledge graph.

        Returns a tuple of (response_text, source_nodes).
        """
        loop = asyncio.get_running_loop()
        try:
            query_engine = self._index.as_query_engine(
                include_text=include_text,
                response_mode=response_mode,
            )
            response = await loop.run_in_executor(
                None, partial(query_engine.query, query_text)
            )

            source_nodes = [
                SourceNodeInfo(
                    text=node.node.get_content(),
                    score=node.score,
                    metadata=node.node.metadata,
                )
                for node in response.source_nodes
            ]

            logger.info(
                "query_completed",
                query=query_text,
                num_sources=len(source_nodes),
            )
            return str(response), source_nodes
        except QueryError:
            raise
        except Exception as exc:
            logger.error("query_failed", query=query_text, error=str(exc))
            raise QueryError(detail=f"Query failed: {exc}") from exc

    async def get_subgraph(
        self,
        entity: str,
        depth: int = 2,
    ) -> tuple[list[SubgraphNode], list[SubgraphEdge]]:
        """
        Retrieve a subgraph around an entity using Cypher.

        Returns a tuple of (nodes, edges).
        Raises ServiceUnavailableError if Neo4j is not enabled.
        """
        if not self._neo4j_enabled:
            raise ServiceUnavailableError(
                detail="Subgraph queries require Neo4j backend"
            )

        cypher = (
            f"MATCH path = (start)-[*1..{depth}]-(connected) "
            "WHERE start.id = $entity "
            "UNWIND relationships(path) AS rel "
            "WITH DISTINCT startNode(rel) AS src, rel, endNode(rel) AS tgt "
            "RETURN src.id AS source_id, labels(src) AS source_labels, "
            "type(rel) AS relation, "
            "tgt.id AS target_id, labels(tgt) AS target_labels"
        )

        loop = asyncio.get_running_loop()
        try:
            records: list[dict[str, Any]] = await loop.run_in_executor(
                None,
                partial(
                    self._neo4j_store.query,
                    cypher,
                    {"entity": entity},
                ),
            )

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

            logger.info(
                "subgraph_retrieved",
                entity=entity,
                depth=depth,
                nodes=len(node_map),
                edges=len(edges),
            )
            return list(node_map.values()), edges
        except ServiceUnavailableError:
            raise
        except Exception as exc:
            logger.error("subgraph_query_failed", entity=entity, error=str(exc))
            raise QueryError(detail=f"Subgraph query failed: {exc}") from exc
