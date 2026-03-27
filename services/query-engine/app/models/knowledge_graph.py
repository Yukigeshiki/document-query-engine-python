"""Knowledge graph request and response models."""

from enum import StrEnum
from typing import Any

from pydantic import Field

from app.models import CamelModel


class SourceType(StrEnum):
    """Supported document source connector types."""

    FILESYSTEM = "filesystem"
    GCS = "gcs"


class RetrievalMode(StrEnum):
    """Controls which retrieval strategies are used for queries."""

    KG_ONLY = "kg_only"
    VECTOR_ONLY = "vector_only"
    DUAL = "dual"


class IngestRequest(CamelModel):
    """Request body for document ingestion."""

    text: str = Field(..., min_length=1, description="Document text to ingest")
    metadata: dict[str, Any] | None = Field(
        default=None, description="Optional metadata key-value pairs"
    )


class IngestResponse(CamelModel):
    """Response after successful document ingestion."""

    document_id: str
    triplet_count: int


class SourceIngestRequest(CamelModel):
    """Request body for bulk document ingestion from a source."""

    source_type: SourceType
    config: dict[str, Any] = Field(..., description="Source-specific configuration")


class SourceNodeInfo(CamelModel):
    """Information about a source node returned from a query."""

    text: str
    score: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class QueryResponse(CamelModel):
    """Response from a knowledge graph query."""

    response: str
    source_nodes: list[SourceNodeInfo] = Field(default_factory=list)


class DocumentInfo(CamelModel):
    """Information about an ingested document (grouped by file name)."""

    doc_id: str
    doc_ids: list[str] = Field(default_factory=list)
    file_name: str | None = None
    node_count: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)


class DocumentListResponse(CamelModel):
    """Paginated response for document listing."""

    documents: list[DocumentInfo]
    total: int
    limit: int
    offset: int


class SubgraphNode(CamelModel):
    """A node in a subgraph result."""

    id: str
    label: str | None = None
    properties: dict[str, str] = Field(default_factory=dict)


class SubgraphEdge(CamelModel):
    """An edge in a subgraph result."""

    source: str
    target: str
    relation: str


class SubgraphResponse(CamelModel):
    """Response from a subgraph retrieval query."""

    entity: str
    depth: int
    nodes: list[SubgraphNode] = Field(default_factory=list)
    edges: list[SubgraphEdge] = Field(default_factory=list)
