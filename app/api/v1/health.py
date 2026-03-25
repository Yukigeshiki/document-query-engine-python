"""Health check endpoint."""

from fastapi import APIRouter, Depends
from starlette.responses import JSONResponse

from app.core.config import settings
from app.dependencies import get_optional_kg_service
from app.models.health import ComponentHealth, HealthResponse
from app.services.knowledge_graph import KnowledgeGraphService

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health_check(
    kg_service: KnowledgeGraphService | None = Depends(get_optional_kg_service),
) -> JSONResponse:
    """Return application health status, version, and component health."""
    components: dict[str, ComponentHealth] = {}

    if kg_service is not None:
        graph_health = await kg_service.check_health()
        components["graph_store"] = ComponentHealth(**graph_health)

    overall = "ok"
    status_code = 200
    if any(c.status != "ok" for c in components.values()):
        overall = "degraded"
        status_code = 503

    body = HealthResponse(
        status=overall,
        version=settings.app_version,
        components=components if components else None,
    )
    return JSONResponse(
        content=body.model_dump(by_alias=True, exclude_none=True),
        status_code=status_code,
    )
