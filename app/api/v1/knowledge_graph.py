"""Knowledge graph query, ingestion, and subgraph endpoints."""

from typing import Literal

import structlog
from fastapi import APIRouter, Depends, Query, UploadFile

from app.core.errors import ServiceUnavailableError
from app.dependencies import get_kg_service, get_upload_service
from app.models.knowledge_graph import (
    IngestRequest,
    IngestResponse,
    QueryResponse,
    RetrievalMode,
    SourceIngestRequest,
    SubgraphResponse,
)
from app.models.tasks import SourceIngestAcceptedResponse
from app.services.knowledge_graph import KnowledgeGraphService
from app.services.upload import UploadService
from app.worker.tasks import ingest_source_task

logger = structlog.stdlib.get_logger(__name__)

router = APIRouter(prefix="/kg", tags=["knowledge-graph"])


@router.post("/ingest", response_model=IngestResponse)
async def ingest_document(
    body: IngestRequest,
    service: KnowledgeGraphService = Depends(get_kg_service),
) -> IngestResponse:
    """Ingest a text document into the knowledge graph."""
    doc_id, triplet_count = await service.ingest(
        text=body.text,
        metadata=body.metadata,
    )
    return IngestResponse(document_id=doc_id, triplet_count=triplet_count)


@router.post(
    "/ingest/source",
    response_model=SourceIngestAcceptedResponse,
    status_code=202,
)
async def ingest_from_source(
    body: SourceIngestRequest,
) -> SourceIngestAcceptedResponse:
    """
    Submit a bulk ingestion job for background processing.

    Returns immediately with a task ID. Poll GET /api/v1/tasks/{taskId}
    for status.
    """
    try:
        result = ingest_source_task.delay(
            source_type=body.source_type.value,
            config=body.config,
        )
    except Exception as exc:
        raise ServiceUnavailableError(
            detail=f"Failed to submit ingestion task: {exc}"
        ) from exc
    return SourceIngestAcceptedResponse(task_id=result.id)


@router.post(
    "/ingest/upload",
    response_model=SourceIngestAcceptedResponse,
    status_code=202,
)
async def ingest_upload(
    file: UploadFile,
    upload_service: UploadService = Depends(get_upload_service),
) -> SourceIngestAcceptedResponse:
    """
    Upload a document for async ingestion into the knowledge graph.

    Accepts PDF, DOCX, or TXT files. Returns a task ID for polling.
    """
    source_type, config = await upload_service.save(file)
    try:
        result = ingest_source_task.delay(
            source_type=source_type.value,
            config=config,
        )
    except Exception as exc:
        raise ServiceUnavailableError(
            detail=f"Failed to submit ingestion task: {exc}"
        ) from exc
    return SourceIngestAcceptedResponse(task_id=result.id)


@router.get("/query", response_model=QueryResponse)
async def query_knowledge_graph(
    query: str = Query(..., min_length=1, description="Natural language query"),
    include_text: bool = Query(default=True),
    response_mode: Literal[
        "tree_summarize", "compact", "refine", "simple_summarize", "no_text", "accumulate"
    ] = Query(default="tree_summarize"),
    retrieval_mode: RetrievalMode = Query(default=RetrievalMode.DUAL),
    service: KnowledgeGraphService = Depends(get_kg_service),
) -> QueryResponse:
    """Query the knowledge graph with a natural language question."""
    response_text, source_nodes = await service.query(
        query_text=query,
        include_text=include_text,
        response_mode=response_mode,
        retrieval_mode=retrieval_mode,
    )
    return QueryResponse(response=response_text, source_nodes=source_nodes)


@router.get("/subgraph", response_model=SubgraphResponse)
async def get_subgraph(
    entity: str = Query(..., min_length=1, description="Entity to center the subgraph on"),
    depth: int = Query(default=2, ge=1, le=5, description="Traversal depth"),
    service: KnowledgeGraphService = Depends(get_kg_service),
) -> SubgraphResponse:
    """Retrieve a subgraph around a specific entity from Neo4j."""
    nodes, edges = await service.get_subgraph(entity=entity, depth=depth)
    return SubgraphResponse(entity=entity, depth=depth, nodes=nodes, edges=edges)
