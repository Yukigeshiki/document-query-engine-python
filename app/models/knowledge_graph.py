"""Knowledge graph request and response models."""

from typing import Any

from pydantic import Field

from app.models import CamelModel


class IngestRequest(CamelModel):
    """Request body for document ingestion."""

    text: str = Field(..., min_length=1, description="Document text to ingest")
    metadata: dict[str, str] | None = Field(
        default=None, description="Optional metadata key-value pairs"
    )


class IngestResponse(CamelModel):
    """Response after successful document ingestion."""

    document_id: str
    triplet_count: int


class SourceNodeInfo(CamelModel):
    """Information about a source node returned from a query."""

    text: str
    score: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class QueryResponse(CamelModel):
    """Response from a knowledge graph query."""

    response: str
    source_nodes: list[SourceNodeInfo] = Field(default_factory=list)


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
