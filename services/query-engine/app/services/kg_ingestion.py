"""Document ingestion into the knowledge graph and vector store."""

import asyncio
import hashlib
import time
from datetime import UTC, datetime
from typing import Any

import structlog
from llama_index.core import Document, Settings, StorageContext, VectorStoreIndex
from llama_index.core.node_parser import SentenceSplitter
from llama_index.core.schema import MetadataMode
from llama_index.graph_stores.neo4j import Neo4jGraphStore

from app.core.errors import IngestionError
from app.core.metrics import (
    kg_ingest_duration_seconds,
    kg_ingest_total,
    kg_ingest_triplets_total,
)
from app.services.query_cache import QueryCache
from app.services.triplet_extractor import extract_triplets

logger = structlog.stdlib.get_logger(__name__)


class KGIngestionService:
    """Handles document ingestion into Neo4j and pgvector."""

    def __init__(
        self,
        graph_store: Neo4jGraphStore,
        vector_index: VectorStoreIndex,
        storage_context: StorageContext,
        cache: QueryCache | None,
        max_triplets: int,
    ) -> None:
        self._graph_store = graph_store
        self._vector_index = vector_index
        self._storage_context = storage_context
        self._cache = cache
        self._max_triplets = max_triplets

    def _count_triplets(self) -> int:
        """Count the number of triplets in Neo4j."""
        try:
            result = self._graph_store.query(
                "MATCH ()-[r]->() RETURN count(r) AS cnt"
            )
            return int(result[0]["cnt"]) if result else 0
        except Exception as exc:
            logger.warning("triplet_count_failed", error=str(exc))
            return -1

    def _upsert_triplet_with_source(
        self, subj: str, rel: str, obj: str, source_node_id: str
    ) -> None:
        """
        Upsert a triplet and track which node produced it.

        Stores a `source_node_ids` list property on the Neo4j
        relationship so deletion can precisely target the right edges.

        Neo4j schema conventions this query depends on:
        - Entity nodes use the label from `graph_store.node_label` (default: "Entity")
        - Entity nodes are identified by an `id` string property
        - Relationship types are derived from the predicate (uppercased, spaces → underscores)
        - Relationships carry a `source_node_ids` list property for provenance tracking
        """
        rel_type = rel.replace(" ", "_").upper()
        label = self._graph_store.node_label
        cypher = (
            f"MERGE (n1:`{label}` {{id: $subj}}) "
            f"MERGE (n2:`{label}` {{id: $obj}}) "
            f"MERGE (n1)-[r:`{rel_type}`]->(n2) "
            "ON CREATE SET r.source_node_ids = [$source_node_id] "
            "ON MATCH SET r.source_node_ids = CASE "
            "  WHEN $source_node_id IN r.source_node_ids "
            "    THEN r.source_node_ids "
            "  ELSE r.source_node_ids + $source_node_id "
            "END"
        )
        self._graph_store.query(
            cypher,
            {"subj": subj, "obj": obj, "source_node_id": source_node_id},
        )

    async def ingest(
        self,
        text: str,
        source_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> tuple[str, int]:
        """
        Ingest a document into both KG and vector indexes.

        `source_id` must be a stable identifier for this document (e.g.
        derived from the source path and content hash). The resulting
        `doc_id` is `sha256(source_id)`, which makes the call idempotent —
        re-running with the same source_id replaces any prior vector-store
        state for that document instead of creating duplicates. This makes
        the ingest path safe to retry after a Celery worker crash.

        Returns a tuple of (document_id, triplet_count).
        """
        doc_id = hashlib.sha256(source_id.encode()).hexdigest()
        doc_metadata = metadata or {}
        doc_metadata["ingested_at"] = datetime.now(tz=UTC).isoformat()
        doc = Document(
            text=text,
            doc_id=doc_id,
            metadata=doc_metadata,
            excluded_llm_metadata_keys=list(doc_metadata.keys()),
        )

        start = time.perf_counter()
        loop = asyncio.get_running_loop()
        try:

            def _ingest_sync() -> int:
                def _stable_id(i: int, doc: Document) -> str:
                    content = doc.get_content()
                    return hashlib.sha256(
                        f"{doc.doc_id}:{i}:{content}".encode()
                    ).hexdigest()

                parser = SentenceSplitter(
                    chunk_size=Settings.chunk_size,
                    id_func=_stable_id,
                )
                nodes = parser.get_nodes_from_documents([doc])

                for node in nodes:
                    node.excluded_llm_metadata_keys = list(node.metadata.keys())

                # Idempotency guard: PGVectorStore.add() does NOT enforce
                # uniqueness on node_id, so a Celery retry of an ingest
                # would otherwise accumulate duplicate vector rows.
                try:
                    self._vector_index.vector_store.delete(ref_doc_id=doc_id)
                except Exception as exc:
                    logger.warning(
                        "vector_store_predelete_failed",
                        doc_id=doc_id,
                        error=str(exc),
                    )

                self._vector_index.insert_nodes(nodes)

                self._storage_context.docstore.add_documents(
                    nodes, allow_update=True
                )

                triplets_before = self._count_triplets()

                for node in nodes:
                    triplets = extract_triplets(
                        node.get_content(metadata_mode=MetadataMode.LLM),
                        max_triplets=self._max_triplets,
                    )
                    for subj, rel, obj in triplets:
                        self._upsert_triplet_with_source(
                            subj, rel, obj, node.node_id
                        )

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
