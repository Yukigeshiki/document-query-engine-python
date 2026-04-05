"""Knowledge graph request and response models."""

from enum import StrEnum
from typing import Any

from pydantic import Field

from app.models import CamelModel


class SourceType(StrEnum):
    """Supported document source connector types."""

    GCS = "gcs"


class RetrievalMode(StrEnum):
    """Controls which retrieval strategies are used for queries."""

    KG_ONLY = "kg_only"
    VECTOR_ONLY = "vector_only"
    DUAL = "dual"


class ResponseMode(StrEnum):
    """Supported LlamaIndex response synthesizer modes."""

    TREE_SUMMARIZE = "tree_summarize"
    COMPACT = "compact"
    REFINE = "refine"
    SIMPLE_SUMMARIZE = "simple_summarize"
    NO_TEXT = "no_text"
    ACCUMULATE = "accumulate"


class QueryRequest(CamelModel):
    """Request body for knowledge graph queries."""

    query: str = Field(..., min_length=1, description="Natural language query")
    include_text: bool = Field(default=True)
    response_mode: ResponseMode = Field(default=ResponseMode.TREE_SUMMARIZE)
    retrieval_mode: RetrievalMode = Field(default=RetrievalMode.DUAL)


class SourceIngestRequest(CamelModel):
    """Request body for bulk document ingestion from a source."""

    source_type: SourceType
    config: dict[str, Any] = Field(..., description="Source-specific configuration")


class SourceRetrievalType(StrEnum):
    """Indicates which retriever produced a source node."""

    KG = "kg"
    VECTOR = "vector"


class SourceNodeMetadata(CamelModel):
    """Typed metadata for a source node."""

    file_name: str | None = None


class SourceNodeInfo(CamelModel):
    """Information about a source node returned from a query."""

    source_type: SourceRetrievalType = SourceRetrievalType.VECTOR
    score: float | None = None
    metadata: SourceNodeMetadata = Field(default_factory=SourceNodeMetadata)


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
