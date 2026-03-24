"""Knowledge graph request and response models."""

from pydantic import BaseModel, Field


class IngestRequest(BaseModel):
    """Request body for document ingestion."""

    text: str = Field(..., min_length=1, description="Document text to ingest")
    metadata: dict[str, str] | None = Field(
        default=None, description="Optional metadata key-value pairs"
    )


class IngestResponse(BaseModel):
    """Response after successful document ingestion."""

    document_id: str
    triplet_count: int


class SourceNodeInfo(BaseModel):
    """Information about a source node returned from a query."""

    text: str
    score: float | None = None
    metadata: dict[str, str] = Field(default_factory=dict)


class QueryRequest(BaseModel):
    """Request body for querying the knowledge graph."""

    query: str = Field(..., min_length=1, description="Natural language query")
    include_text: bool = True
    response_mode: str = "tree_summarize"


class QueryResponse(BaseModel):
    """Response from a knowledge graph query."""

    response: str
    source_nodes: list[SourceNodeInfo] = Field(default_factory=list)
