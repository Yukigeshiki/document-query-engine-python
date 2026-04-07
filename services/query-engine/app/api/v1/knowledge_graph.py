"""Knowledge graph query, ingestion, and subgraph endpoints."""

import structlog
from fastapi import APIRouter, Depends, Query, Request, UploadFile

from app.core.config import settings
from app.core.errors import NotFoundError, ServiceUnavailableError
from app.core.rate_limit import limiter
from app.dependencies import get_kg_service, get_upload_service
from app.models.knowledge_graph import (
    DocumentInfo,
    DocumentListResponse,
    QueryRequest,
    QueryResponse,
    SourceIngestRequest,
    SubgraphResponse,
)
from app.models.tasks import TaskAcceptedResponse
from app.services.knowledge_graph import KnowledgeGraphService
from app.services.upload import UploadService
from app.worker.tasks import delete_document_task, ingest_source_task

logger = structlog.stdlib.get_logger(__name__)

router = APIRouter(prefix="/kg", tags=["knowledge-graph"])


@router.get("/documents", response_model=DocumentListResponse)
@limiter.limit(settings.rate_limit_default)
async def list_documents(
    request: Request,
    limit: int = Query(default=20, ge=1, le=100, description="Max documents to return"),
    offset: int = Query(default=0, ge=0, description="Number of documents to skip"),
    service: KnowledgeGraphService = Depends(get_kg_service),
) -> DocumentListResponse:
    """List ingested documents with pagination (newest first)."""
    docs, total = await service.list_documents(limit=limit, offset=offset)
    return DocumentListResponse(
        documents=[DocumentInfo(**doc) for doc in docs],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.delete(
    "/documents/{doc_id}",
    response_model=TaskAcceptedResponse,
    status_code=202,
)
@limiter.limit(settings.rate_limit_default)
async def delete_document(
    request: Request,
    doc_id: str,
    service: KnowledgeGraphService = Depends(get_kg_service),
) -> TaskAcceptedResponse:
    """
    Submit a document deletion job for background processing.

    Validates that the document exists synchronously so a typoed doc_id
    returns 404 immediately. The actual deletion runs as a Celery task
    that deletes from all storage layers (Neo4j, pgvector, docstore).
    Returns a task ID for polling.
    """
    if not await service.document_exists(doc_id):
        raise NotFoundError(detail=f"Document {doc_id} not found")

    try:
        result = delete_document_task.delay(doc_id=doc_id)
    except Exception as exc:
        raise ServiceUnavailableError(
            detail=f"Failed to submit deletion task: {exc}"
        ) from exc
    return TaskAcceptedResponse(task_id=result.id)


@router.post(
    "/ingest/source",
    response_model=TaskAcceptedResponse,
    status_code=202,
)
@limiter.limit(settings.rate_limit_ingest)
async def ingest_from_source(
    request: Request,
    body: SourceIngestRequest,
) -> TaskAcceptedResponse:
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
    return TaskAcceptedResponse(task_id=result.id)


@router.post(
    "/ingest/upload",
    response_model=TaskAcceptedResponse,
    status_code=202,
)
@limiter.limit(settings.rate_limit_ingest)
async def ingest_upload(
    request: Request,
    file: UploadFile,
    upload_service: UploadService = Depends(get_upload_service),
) -> TaskAcceptedResponse:
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
    return TaskAcceptedResponse(task_id=result.id)


@router.post("/query", response_model=QueryResponse)
@limiter.limit(settings.rate_limit_query)
async def query_knowledge_graph(
    request: Request,
    body: QueryRequest,
    service: KnowledgeGraphService = Depends(get_kg_service),
) -> QueryResponse:
    """Query the knowledge graph with a natural language question."""
    response_text, source_nodes = await service.query(
        query_text=body.query,
        include_text=body.include_text,
        response_mode=body.response_mode,
        retrieval_mode=body.retrieval_mode,
    )
    return QueryResponse(response=response_text, source_nodes=source_nodes)


@router.get("/subgraph", response_model=SubgraphResponse)
@limiter.limit(settings.rate_limit_default)
async def get_subgraph(
    request: Request,
    entity: str = Query(..., min_length=1, description="Entity to center the subgraph on"),
    depth: int = Query(default=2, ge=1, le=5, description="Traversal depth"),
    service: KnowledgeGraphService = Depends(get_kg_service),
) -> SubgraphResponse:
    """Retrieve a subgraph around a specific entity from Neo4j."""
    nodes, edges = await service.get_subgraph(entity=entity, depth=depth)
    return SubgraphResponse(entity=entity, depth=depth, nodes=nodes, edges=edges)


@router.get("/documents/graph", response_model=SubgraphResponse)
@limiter.limit(settings.rate_limit_default)
async def get_document_graph(
    request: Request,
    doc_ids: list[str] = Query(..., max_length=50, description="Document IDs (supports multi-chunk docs, max 50)"),
    service: KnowledgeGraphService = Depends(get_kg_service),
) -> SubgraphResponse:
    """Retrieve the graph for a specific ingested document."""
    nodes, edges = await service.get_document_graph(doc_ids=doc_ids)
    return SubgraphResponse(entity=doc_ids[0], depth=0, nodes=nodes, edges=edges)
