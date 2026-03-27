"""API v1 router aggregating all v1 endpoint routers."""

from fastapi import APIRouter

from app.api.v1.health import router as health_router
from app.api.v1.knowledge_graph import router as kg_router
from app.api.v1.tasks import router as tasks_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health_router)
api_router.include_router(kg_router)
api_router.include_router(tasks_router)
