"""Knowledge graph query and ingestion endpoints."""

import structlog
from fastapi import APIRouter, Request

from app.models.knowledge_graph import (
    IngestRequest,
    IngestResponse,
    QueryRequest,
    QueryResponse,
)
from app.services.knowledge_graph import KnowledgeGraphService

logger = structlog.stdlib.get_logger(__name__)

router = APIRouter(prefix="/kg", tags=["knowledge-graph"])


def _get_service(request: Request) -> KnowledgeGraphService:
    """Retrieve the KnowledgeGraphService from app state."""
    return request.app.state.kg_service  # type: ignore[no-any-return]


@router.post("/ingest", response_model=IngestResponse)
async def ingest_document(body: IngestRequest, request: Request) -> IngestResponse:
    """Ingest a text document into the knowledge graph."""
    service = _get_service(request)
    doc_id, triplet_count = await service.ingest(
        text=body.text,
        metadata=body.metadata,
    )
    return IngestResponse(document_id=doc_id, triplet_count=triplet_count)


@router.post("/query", response_model=QueryResponse)
async def query_knowledge_graph(body: QueryRequest, request: Request) -> QueryResponse:
    """Query the knowledge graph with a natural language question."""
    service = _get_service(request)
    response_text, source_nodes = await service.query(
        query_text=body.query,
        include_text=body.include_text,
        response_mode=body.response_mode,
    )
    return QueryResponse(response=response_text, source_nodes=source_nodes)
