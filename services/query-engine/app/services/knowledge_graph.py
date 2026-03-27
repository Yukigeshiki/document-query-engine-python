"""Knowledge graph service backed by LlamaIndex KnowledgeGraphIndex."""

import asyncio
import hashlib
import time
import uuid
from functools import partial
from typing import Any
from urllib.parse import urlparse

import structlog
from llama_index.core import (
    Document,
    KnowledgeGraphIndex,
    Settings,
    StorageContext,
    VectorStoreIndex,
    load_index_from_storage,
)
from llama_index.core.graph_stores.simple import SimpleGraphStore
from llama_index.core.graph_stores.types import GraphStore
from llama_index.core.node_parser import SentenceSplitter
from llama_index.core.query_engine import RetrieverQueryEngine
from llama_index.core.response_synthesizers import get_response_synthesizer
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.graph_stores.neo4j import Neo4jGraphStore
from llama_index.llms.openai import OpenAI
from llama_index.storage.docstore.postgres import PostgresDocumentStore
from llama_index.storage.index_store.postgres import PostgresIndexStore
from llama_index.vector_stores.postgres import PGVectorStore

from app.core.config import Settings as AppSettings
from app.core.errors import IngestionError, QueryError, ServiceUnavailableError
from app.core.metrics import (
    kg_cache_up,
    kg_graph_store_up,
    kg_ingest_duration_seconds,
    kg_ingest_total,
    kg_ingest_triplets_total,
    kg_query_cache_hits_total,
    kg_query_cache_misses_total,
    kg_query_duration_seconds,
    kg_query_total,
    kg_subgraph_duration_seconds,
    kg_subgraph_total,
    kg_vector_store_up,
)
from app.models.knowledge_graph import RetrievalMode, SourceNodeInfo, SubgraphEdge, SubgraphNode
from app.services.dual_retriever import DualRetriever
from app.services.query_cache import QueryCache

logger = structlog.stdlib.get_logger(__name__)

KG_INDEX_ID = "kg_index"
VECTOR_INDEX_ID = "vector_index"


class KnowledgeGraphService:
    """Manages KG and vector indexes with Neo4j, PostgreSQL, or in-memory stores."""

    def __init__(self, config: AppSettings, cache: QueryCache | None = None) -> None:
        """Initialize LlamaIndex settings, stores, and indexes."""
        self._cache = cache
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
        self._postgres_enabled = config.postgres_enabled
        self._graph_store: GraphStore = self._create_graph_store(config)
        self._storage_context = self._create_storage_context(config)
        self._max_triplets = config.max_triplets_per_chunk
        self._vector_top_k = config.vector_top_k

        self._index = self._load_or_create_kg_index()
        self._vector_index = self._load_or_create_vector_index()

        logger.info(
            "knowledge_graph_service_initialized",
            graph_backend="neo4j" if self._neo4j_enabled else "in_memory",
            vector_backend="pgvector" if self._postgres_enabled else "in_memory",
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
            return store
        except Exception as exc:
            logger.warning(
                "neo4j_connection_failed_falling_back_to_in_memory",
                error=str(exc),
            )
            self._neo4j_enabled = False
            return SimpleGraphStore()

    def _create_storage_context(self, config: AppSettings) -> StorageContext:
        """Create a StorageContext with optional PostgreSQL persistence."""
        if not config.postgres_enabled or not config.postgres_uri:
            self._postgres_enabled = False
            return StorageContext.from_defaults(graph_store=self._graph_store)

        try:
            parsed = urlparse(config.postgres_uri)
            vector_store = PGVectorStore.from_params(
                host=parsed.hostname or "localhost",
                port=str(parsed.port or 5432),
                database=(parsed.path or "/query_engine").lstrip("/"),
                user=parsed.username or "postgres",
                password=parsed.password or "",
                embed_dim=config.embed_dim,
                hybrid_search=True,
                text_search_config="english",
            )
            docstore = PostgresDocumentStore.from_uri(config.postgres_uri)
            index_store = PostgresIndexStore.from_uri(config.postgres_uri)

            logger.info("postgres_connected", uri=parsed.hostname)
            return StorageContext.from_defaults(
                graph_store=self._graph_store,
                vector_store=vector_store,
                docstore=docstore,
                index_store=index_store,
            )
        except Exception as exc:
            logger.warning(
                "postgres_connection_failed_falling_back_to_in_memory",
                error=str(exc),
            )
            self._postgres_enabled = False
            return StorageContext.from_defaults(graph_store=self._graph_store)

    def _load_or_create_kg_index(self) -> KnowledgeGraphIndex:
        """Load existing KG index from storage or create a new one."""
        if self._postgres_enabled:
            try:
                index = load_index_from_storage(
                    storage_context=self._storage_context,
                    index_id=KG_INDEX_ID,
                )
                logger.info("kg_index_loaded_from_storage")
                return index  # type: ignore[return-value]
            except (ValueError, KeyError):
                pass

        index = KnowledgeGraphIndex(
            nodes=[],
            storage_context=self._storage_context,
            max_triplets_per_chunk=self._max_triplets,
        )
        index.set_index_id(KG_INDEX_ID)
        logger.info("kg_index_created_new")
        return index

    def _load_or_create_vector_index(self) -> VectorStoreIndex:
        """Load existing vector index from storage or create a new one."""
        if self._postgres_enabled:
            try:
                index = load_index_from_storage(
                    storage_context=self._storage_context,
                    index_id=VECTOR_INDEX_ID,
                )
                logger.info("vector_index_loaded_from_storage")
                return index  # type: ignore[return-value]
            except (ValueError, KeyError):
                pass

        index = VectorStoreIndex(
            nodes=[],
            storage_context=self._storage_context,
        )
        index.set_index_id(VECTOR_INDEX_ID)
        logger.info("vector_index_created_new")
        return index

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
        """Close Neo4j connection if active."""
        if self._neo4j_enabled:
            self._neo4j_store.close()
            logger.info("neo4j_connection_closed")

    async def check_graph_store_health(self) -> dict[str, str]:
        """
        Check graph store connectivity.

        Returns a dict with status, backend, and optional error.
        """
        if not self._neo4j_enabled:
            kg_graph_store_up.set(1)
            return {"status": "ok", "backend": "in_memory"}

        loop = asyncio.get_running_loop()
        try:
            await loop.run_in_executor(
                None,
                partial(self._neo4j_store.query, "RETURN 1"),
            )
            kg_graph_store_up.set(1)
            return {"status": "ok", "backend": "neo4j"}
        except Exception as exc:
            kg_graph_store_up.set(0)
            return {"status": "degraded", "backend": "neo4j", "error": str(exc)}

    async def check_vector_store_health(self) -> dict[str, str] | None:
        """
        Check PostgreSQL/pgvector connectivity.

        Returns None if PostgreSQL is not enabled.
        """
        if not self._postgres_enabled:
            kg_vector_store_up.set(1)
            return None

        loop = asyncio.get_running_loop()
        try:
            await loop.run_in_executor(
                None,
                self._storage_context.docstore.get_all_document_hashes,
            )
            kg_vector_store_up.set(1)
            return {"status": "ok", "backend": "pgvector"}
        except Exception as exc:
            kg_vector_store_up.set(0)
            return {"status": "degraded", "backend": "pgvector", "error": str(exc)}

    async def check_cache_health(self) -> dict[str, str] | None:
        """Check query cache connectivity. Returns None if cache is not enabled."""
        if self._cache is None:
            kg_cache_up.set(1)
            return None
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(None, self._cache.check_health)
        kg_cache_up.set(1 if result.get("status") == "ok" else 0)
        return result

    async def ingest(
        self,
        text: str,
        metadata: dict[str, Any] | None = None,
    ) -> tuple[str, int]:
        """
        Ingest a document into both KG and vector indexes.

        Returns a tuple of (document_id, triplet_count).
        """
        doc_id = str(uuid.uuid4())
        doc = Document(text=text, doc_id=doc_id, metadata=metadata or {})

        start = time.perf_counter()
        loop = asyncio.get_running_loop()
        try:

            def _ingest_sync() -> int:
                # Stable node IDs based on doc_id + chunk position + content
                # so retries don't create duplicate nodes/triplets
                def _stable_id(i: int, doc: Document) -> str:
                    content = doc.get_content()
                    return hashlib.sha256(
                        f"{doc.doc_id}:{i}:{content}".encode()
                    ).hexdigest()

                parser = SentenceSplitter(
                    chunk_size=Settings.chunk_size, id_func=_stable_id
                )
                nodes = parser.get_nodes_from_documents([doc])

                # Vector-first: embedding/pgvector write is more likely to fail
                # (external API call). If it fails, Neo4j is untouched.
                # If it succeeds and KG insert fails, we have embeddings without
                # triplets (queryable via vector_only mode) — safer partial state.
                self._vector_index.insert_nodes(nodes)

                triplets_before = self._count_triplets()
                self._index.insert_nodes(nodes)
                triplets_after = self._count_triplets()
                return max(triplets_after - triplets_before, 0)

            triplet_count = await loop.run_in_executor(None, _ingest_sync)

            kg_ingest_duration_seconds.observe(time.perf_counter() - start)
            kg_ingest_total.labels(status="success").inc()
            kg_ingest_triplets_total.inc(triplet_count)

            logger.info(
                "document_ingested",
                document_id=doc_id,
                triplet_count=triplet_count,
            )
            return doc_id, triplet_count
        except IngestionError:
            kg_ingest_total.labels(status="error").inc()
            raise
        except Exception as exc:
            kg_ingest_total.labels(status="error").inc()
            logger.error("ingestion_failed", document_id=doc_id, error=str(exc))
            raise IngestionError(detail=f"Failed to ingest document: {exc}") from exc
        finally:
            if self._cache is not None:
                await self._cache.invalidate()

    async def query(
        self,
        query_text: str,
        include_text: bool = True,
        response_mode: str = "tree_summarize",
        retrieval_mode: str = "dual",
    ) -> tuple[str, list[SourceNodeInfo]]:
        """
        Query using KG, vector, or dual retrieval.

        Returns a tuple of (response_text, source_nodes).
        """
        start = time.perf_counter()
        loop = asyncio.get_running_loop()
        try:
            mode = RetrievalMode(retrieval_mode)

            # Fallback to kg_only if vector store not available
            if not self._postgres_enabled and mode != RetrievalMode.KG_ONLY:
                logger.warning(
                    "vector_store_not_available_falling_back_to_kg_only",
                    requested_mode=retrieval_mode,
                )
                mode = RetrievalMode.KG_ONLY

            def _query_sync() -> tuple[str, list[SourceNodeInfo]]:
                # Check semantic cache (blocking I/O — runs in executor)
                # Embed once and reuse for both get() and set()
                query_embedding: list[float] | None = None
                if self._cache is not None:
                    query_embedding = self._cache.embed_query(query_text)
                    cached = self._cache.get(
                        query_text, include_text, response_mode, retrieval_mode,
                        embedding=query_embedding,
                    )
                    if cached is not None:
                        kg_query_cache_hits_total.inc()
                        response_text, source_nodes, _ = cached
                        return response_text, source_nodes
                    kg_query_cache_misses_total.inc()

                kg_retriever = self._index.as_retriever(include_text=include_text)
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
                        text=node.node.get_content(),
                        score=node.score,
                        metadata=node.node.metadata,
                    )
                    for node in response.source_nodes
                ]

                # Store in cache, reusing pre-computed embedding
                if self._cache is not None:
                    self._cache.set(
                        query_text, include_text, response_mode, retrieval_mode,
                        str(response), source_nodes,
                        embedding=query_embedding,
                    )

                return str(response), source_nodes

            response_text, source_nodes = await loop.run_in_executor(
                None, _query_sync
            )

            kg_query_duration_seconds.labels(retrieval_mode=mode.value).observe(
                time.perf_counter() - start
            )
            kg_query_total.labels(retrieval_mode=mode.value, status="success").inc()

            logger.info(
                "query_completed",
                query=query_text,
                retrieval_mode=mode.value,
                num_sources=len(source_nodes),
            )
            return response_text, source_nodes
        except QueryError:
            kg_query_total.labels(retrieval_mode=retrieval_mode, status="error").inc()
            raise
        except Exception as exc:
            kg_query_total.labels(retrieval_mode=retrieval_mode, status="error").inc()
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

        start = time.perf_counter()
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

            kg_subgraph_duration_seconds.observe(time.perf_counter() - start)
            kg_subgraph_total.inc()

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
