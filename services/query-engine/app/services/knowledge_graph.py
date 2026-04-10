"""
Knowledge graph service facade.

Coordinates Neo4j, pgvector, and the docstore through focused sub-services
for ingestion, deletion, and querying. This class is the public interface
used by API endpoints, Celery tasks, and the ingestion pipeline.
"""

import asyncio
from functools import partial
from typing import Any
from urllib.parse import urlparse

import structlog
from llama_index.core import (
    Settings,
    StorageContext,
    VectorStoreIndex,
    load_index_from_storage,
)
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.graph_stores.neo4j import Neo4jGraphStore
from llama_index.llms.openai import OpenAI
from llama_index.storage.docstore.postgres import PostgresDocumentStore
from llama_index.storage.index_store.postgres import PostgresIndexStore
from llama_index.storage.kvstore.postgres.base import PostgresKVStore
from llama_index.vector_stores.postgres import PGVectorStore
from sqlalchemy import Engine

from app.core.config import Settings as AppSettings
from app.core.metrics import kg_cache_up, kg_graph_store_up, kg_vector_store_up
from app.models.knowledge_graph import (
    ResponseMode,
    RetrievalMode,
    SourceNodeInfo,
    SubgraphEdge,
    SubgraphNode,
)
from app.services.kg_deletion import KGDeletionService
from app.services.kg_ingestion import KGIngestionService
from app.services.kg_query import KGQueryService
from app.services.query_cache import QueryCache

logger = structlog.stdlib.get_logger(__name__)

VECTOR_INDEX_ID = "vector_index"


class KnowledgeGraphService:
    """Manages KG and vector indexes with Neo4j and PostgreSQL."""

    def __init__(
        self,
        config: AppSettings,
        cache: QueryCache | None = None,
        engine: Engine | None = None,
    ) -> None:
        """Initialize LlamaIndex settings, stores, and sub-services."""
        if config.postgres_enabled and config.postgres_uri and engine is None:
            raise ValueError(
                "A shared SQLAlchemy engine is required when PostgreSQL "
                "is enabled. Create one with get_pg_engine() and pass "
                "it to KnowledgeGraphService."
            )
        self._cache = cache
        self._engine = engine
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

        self._postgres_enabled = config.postgres_enabled
        self._graph_store = self._create_graph_store(config)
        self._storage_context = self._create_storage_context(config)
        self._vector_index = self._load_or_create_vector_index()

        self._ingestion = KGIngestionService(
            graph_store=self._graph_store,
            vector_index=self._vector_index,
            storage_context=self._storage_context,
            cache=cache,
            max_triplets=config.max_triplets_per_chunk,
        )
        self._deletion = KGDeletionService(
            graph_store=self._graph_store,
            vector_index=self._vector_index,
            storage_context=self._storage_context,
            cache=cache,
        )
        self._query = KGQueryService(
            graph_store=self._graph_store,
            vector_index=self._vector_index,
            storage_context=self._storage_context,
            cache=cache,
            vector_top_k=config.vector_top_k,
            postgres_enabled=self._postgres_enabled,
        )

        logger.info(
            "knowledge_graph_service_initialized",
            graph_backend="neo4j",
            vector_backend=(
                "pgvector" if self._postgres_enabled else "in_memory"
            ),
        )

    # ------------------------------------------------------------------
    # Infrastructure
    # ------------------------------------------------------------------

    @staticmethod
    def _create_graph_store(config: AppSettings) -> Neo4jGraphStore:
        """
        Create the Neo4j graph store.

        Raises on connection failure — Neo4j is required.
        """
        store = Neo4jGraphStore(
            username=config.neo4j_username,
            password=config.neo4j_password,
            url=config.neo4j_uri,
            database=config.neo4j_database,
        )
        logger.info("neo4j_connected", uri=config.neo4j_uri)
        return store

    def _create_storage_context(
        self, config: AppSettings
    ) -> StorageContext:
        """
        Create a StorageContext with PostgreSQL persistence.

        Raises on connection failure — the service should not start with
        degraded (in-memory) storage in production.
        """
        if not config.postgres_enabled or not config.postgres_uri:
            self._postgres_enabled = False
            return StorageContext.from_defaults(
                graph_store=self._graph_store
            )

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
            create_engine_kwargs={"pool_pre_ping": True},
        )

        sync_parsed = urlparse(config.postgres_uri)
        async_uri = sync_parsed._replace(
            scheme="postgresql+asyncpg"
        ).geturl()
        pg_engine = self._engine
        doc_kvstore = PostgresKVStore(
            table_name="docstore",
            engine=pg_engine,
            async_connection_string=async_uri,
            perform_setup=True,
        )
        index_kvstore = PostgresKVStore(
            table_name="indexstore",
            engine=pg_engine,
            async_connection_string=async_uri,
            perform_setup=True,
        )
        docstore = PostgresDocumentStore(postgres_kvstore=doc_kvstore)
        index_store = PostgresIndexStore(postgres_kvstore=index_kvstore)

        logger.info("postgres_connected", uri=parsed.hostname)
        return StorageContext.from_defaults(
            graph_store=self._graph_store,
            vector_store=vector_store,
            docstore=docstore,
            index_store=index_store,
        )

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

    def close(self) -> None:
        """Close Neo4j connection."""
        self._graph_store.close()
        logger.info("neo4j_connection_closed")

    # ------------------------------------------------------------------
    # Health checks
    # ------------------------------------------------------------------

    async def check_graph_store_health(self) -> dict[str, str]:
        """Check graph store connectivity."""
        loop = asyncio.get_running_loop()
        try:
            await loop.run_in_executor(
                None,
                partial(self._graph_store.query, "RETURN 1"),
            )
            kg_graph_store_up.set(1)
            return {"status": "ok", "backend": "neo4j"}
        except Exception as exc:
            kg_graph_store_up.set(0)
            return {
                "status": "degraded",
                "backend": "neo4j",
                "error": str(exc),
            }

    async def check_vector_store_health(self) -> dict[str, str] | None:
        """Check PostgreSQL/pgvector connectivity."""
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
            return {
                "status": "degraded",
                "backend": "pgvector",
                "error": str(exc),
            }

    async def check_cache_health(self) -> dict[str, str] | None:
        """Check query cache connectivity."""
        if self._cache is None:
            kg_cache_up.set(1)
            return None
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None, self._cache.check_health
        )
        kg_cache_up.set(1 if result.get("status") == "ok" else 0)
        return result

    # ------------------------------------------------------------------
    # Delegation to sub-services
    # ------------------------------------------------------------------

    async def ingest(
        self,
        text: str,
        source_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> tuple[str, int]:
        """Ingest a document into both KG and vector indexes."""
        return await self._ingestion.ingest(text, source_id, metadata)

    async def delete_document(self, doc_id: str) -> list[str]:
        """Delete a document from all storage layers."""
        return await self._deletion.delete_document(doc_id)

    async def document_exists(self, doc_id: str) -> bool:
        """Return True if a document with this doc_id exists."""
        return await self._deletion.document_exists(doc_id)

    async def list_documents(
        self,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        """List ingested documents with pagination."""
        return await self._deletion.list_documents(limit, offset)

    async def query(
        self,
        query_text: str,
        include_text: bool = True,
        response_mode: ResponseMode = ResponseMode.TREE_SUMMARIZE,
        retrieval_mode: RetrievalMode = RetrievalMode.DUAL,
    ) -> tuple[str, list[SourceNodeInfo]]:
        """Query using KG, vector, or dual retrieval."""
        return await self._query.query(
            query_text, include_text, response_mode, retrieval_mode
        )

    async def get_subgraph(
        self,
        entity: str,
        depth: int = 2,
    ) -> tuple[list[SubgraphNode], list[SubgraphEdge]]:
        """Retrieve a subgraph around an entity."""
        return await self._query.get_subgraph(entity, depth)

    async def get_document_graph(
        self,
        doc_ids: list[str],
    ) -> tuple[list[SubgraphNode], list[SubgraphEdge]]:
        """Retrieve the graph for a specific document."""
        return await self._query.get_document_graph(doc_ids)
