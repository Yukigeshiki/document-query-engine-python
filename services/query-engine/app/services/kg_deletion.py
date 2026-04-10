"""Document deletion and listing from the knowledge graph and storage layers."""

import asyncio
from typing import Any

import structlog
from llama_index.core import StorageContext, VectorStoreIndex
from llama_index.graph_stores.neo4j import Neo4jGraphStore

from app.core.errors import DeletionError, NotFoundError
from app.services.query_cache import QueryCache

logger = structlog.stdlib.get_logger(__name__)


class KGDeletionService:
    """Handles document deletion, existence checks, and listing."""

    def __init__(
        self,
        graph_store: Neo4jGraphStore,
        vector_index: VectorStoreIndex,
        storage_context: StorageContext,
        cache: QueryCache | None,
    ) -> None:
        self._graph_store = graph_store
        self._vector_index = vector_index
        self._storage_context = storage_context
        self._cache = cache

    def _delete_neo4j_provenance(self, node_ids: set[str]) -> None:
        """
        Delete Neo4j relationships using source_node_ids provenance.

        Precisely removes only the node_ids belonging to the deleted
        document from each relationship's `source_node_ids` list.
        Relationships whose list becomes empty are deleted.
        Orphaned Entity nodes are cleaned up at the end.

        Neo4j schema conventions these queries depend on:
        - Entity nodes use the label from `graph_store.node_label`
        - Entity nodes are identified by an `id` string property
        - Relationships carry a `source_node_ids` list property
        - Orphan cleanup matches nodes with no remaining edges
        """
        node_id_list = list(node_ids)
        label = self._graph_store.node_label

        entity_records = self._graph_store.query(
            f"MATCH (n:`{label}`)-[r]->() "
            "WHERE ANY(nid IN r.source_node_ids WHERE nid IN $node_ids) "
            "RETURN DISTINCT n.id AS entity_id "
            "UNION "
            f"MATCH ()-[r]->(n:`{label}`) "
            "WHERE ANY(nid IN r.source_node_ids WHERE nid IN $node_ids) "
            "RETURN DISTINCT n.id AS entity_id",
            {"node_ids": node_id_list},
        )
        entity_list = (
            [r["entity_id"] for r in entity_records]
            if entity_records
            else []
        )

        self._graph_store.query(
            "MATCH ()-[r]->() "
            "WHERE ANY(nid IN r.source_node_ids WHERE nid IN $node_ids) "
            "SET r.source_node_ids = "
            "  [x IN r.source_node_ids WHERE NOT x IN $node_ids] "
            "WITH r WHERE size(r.source_node_ids) = 0 "
            "DELETE r",
            {"node_ids": node_id_list},
        )

        if entity_list:
            self._graph_store.query(
                f"MATCH (n:`{label}`) "
                "WHERE n.id IN $entities AND NOT (n)--() "
                "DELETE n",
                {"entities": entity_list},
            )

    async def delete_document(self, doc_id: str) -> list[str]:
        """
        Delete a document and all its data from every storage layer.

        Resolves all doc_ids for the grouped document (multi-chunk uploads
        share the same file_path) and removes them from the Neo4j graph
        store, vector index, and docstore.

        Deletion order is chosen for retry safety — the docstore (source of
        truth for node_ids) is deleted last so retries can still resolve
        what needs cleaning up. Each store's delete is idempotent.

        Returns the list of deleted doc_ids.
        """
        loop = asyncio.get_running_loop()

        def _delete_sync() -> list[str]:
            ref_doc_info = (
                self._storage_context.docstore.get_all_ref_doc_info()
            )
            if not ref_doc_info or doc_id not in ref_doc_info:
                raise NotFoundError(detail=f"Document {doc_id} not found")

            metadata = ref_doc_info[doc_id].metadata or {}
            group_key = (
                metadata.get("file_path")
                or metadata.get("file_name")
                or doc_id
            )
            all_doc_ids = [
                did
                for did, info in ref_doc_info.items()
                if (info.metadata or {}).get(
                    "file_path",
                    (info.metadata or {}).get("file_name", did),
                ) == group_key
            ]

            all_node_ids: set[str] = set()
            for did in all_doc_ids:
                info = ref_doc_info.get(did)
                if info:
                    all_node_ids.update(info.node_ids)

            # 1. Clean up Neo4j graph store using source_node_ids provenance.
            self._delete_neo4j_provenance(all_node_ids)

            # 2. Delete from vector index (pgvector) — idempotent
            for ref_doc_id in all_doc_ids:
                self._vector_index.delete_ref_doc(
                    ref_doc_id, delete_from_docstore=False
                )

            # 3. Delete from docstore last — it's the source of truth for
            #    node_ids, so keeping it until the end makes retries safe.
            for ref_doc_id in all_doc_ids:
                self._storage_context.docstore.delete_ref_doc(
                    ref_doc_id, raise_error=False
                )

            return all_doc_ids

        try:
            deleted_ids = await loop.run_in_executor(None, _delete_sync)
            logger.info(
                "document_deleted",
                doc_id=doc_id,
                deleted_doc_ids=deleted_ids,
            )
            return deleted_ids
        except NotFoundError:
            raise
        except Exception as exc:
            logger.error("deletion_failed", doc_id=doc_id, error=str(exc))
            raise DeletionError(
                detail=f"Failed to delete document: {exc}"
            ) from exc
        finally:
            if self._cache is not None:
                await self._cache.invalidate()

    async def document_exists(self, doc_id: str) -> bool:
        """
        Return True if a document with this doc_id exists in the docstore.

        Inexpensive key lookup used by the delete endpoint to validate input
        synchronously, so a typoed doc_id returns 404 immediately.
        """
        loop = asyncio.get_running_loop()

        def _check() -> bool:
            info = self._storage_context.docstore.get_ref_doc_info(doc_id)
            return info is not None

        return await loop.run_in_executor(None, _check)

    async def list_documents(
        self,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        """
        List ingested documents from the docstore.

        Returns a tuple of (documents, total_count) for pagination.
        Documents are sorted newest-first (by insertion order, reversed).
        """
        loop = asyncio.get_running_loop()

        def _list_sync() -> tuple[list[dict[str, Any]], int]:
            ref_doc_info = (
                self._storage_context.docstore.get_all_ref_doc_info()
            )
            if not ref_doc_info:
                return [], 0

            grouped: dict[str, dict[str, Any]] = {}
            for doc_id, info in ref_doc_info.items():
                metadata = info.metadata or {}
                group_key = (
                    metadata.get("file_path")
                    or metadata.get("file_name")
                    or doc_id
                )
                if group_key not in grouped:
                    grouped[group_key] = {
                        "doc_id": doc_id,
                        "file_name": metadata.get("file_name") or doc_id,
                        "node_count": 0,
                        "doc_ids": [],
                        "metadata": metadata,
                    }
                grouped[group_key]["node_count"] += len(info.node_ids)
                grouped[group_key]["doc_ids"].append(doc_id)

            all_docs = sorted(
                grouped.values(),
                key=lambda d: d["metadata"].get("ingested_at", ""),
                reverse=True,
            )
            total = len(all_docs)
            return all_docs[offset : offset + limit], total

        return await loop.run_in_executor(None, _list_sync)
