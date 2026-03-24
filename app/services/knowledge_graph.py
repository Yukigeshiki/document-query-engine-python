"""Knowledge graph service backed by LlamaIndex KnowledgeGraphIndex."""

import asyncio
import uuid
from functools import partial

import structlog
from llama_index.core import (
    Document,
    KnowledgeGraphIndex,
    Settings,
    StorageContext,
)
from llama_index.core.graph_stores.simple import SimpleGraphStore
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.llms.openai import OpenAI

from app.core.config import Settings as AppSettings
from app.core.errors import IngestionError, QueryError
from app.models.knowledge_graph import SourceNodeInfo

logger = structlog.stdlib.get_logger(__name__)


class KnowledgeGraphService:
    """Manages a LlamaIndex KnowledgeGraphIndex with an in-memory graph store."""

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

        self._graph_store = SimpleGraphStore()
        self._storage_context = StorageContext.from_defaults(
            graph_store=self._graph_store,
        )
        self._max_triplets = config.max_triplets_per_chunk

        self._index = KnowledgeGraphIndex(
            nodes=[],
            storage_context=self._storage_context,
            max_triplets_per_chunk=self._max_triplets,
        )

        logger.info("knowledge_graph_service_initialized")

    async def ingest(
        self,
        text: str,
        metadata: dict[str, str] | None = None,
    ) -> tuple[str, int]:
        """Ingest a document into the knowledge graph.

        Returns a tuple of (document_id, triplet_count).
        """
        doc_id = str(uuid.uuid4())
        doc = Document(text=text, doc_id=doc_id, metadata=metadata or {})

        loop = asyncio.get_running_loop()
        try:
            triplets_before = len(self._graph_store._data.graph_dict)
            await loop.run_in_executor(None, partial(self._index.insert, doc))
            triplets_after = len(self._graph_store._data.graph_dict)
            triplet_count = triplets_after - triplets_before

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
        """Query the knowledge graph.

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
