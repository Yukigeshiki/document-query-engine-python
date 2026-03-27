"""Background task status and cancellation endpoints."""

import structlog
from celery.result import AsyncResult
from fastapi import APIRouter, Request

from app.core.config import settings
from app.core.rate_limit import limiter
from app.models.tasks import (
    SourceIngestResult,
    TaskCancelledResponse,
    TaskStatus,
    TaskStatusResponse,
)
from app.worker.celery_app import celery_app

logger = structlog.stdlib.get_logger(__name__)

router = APIRouter(prefix="/tasks", tags=["tasks"])

_STATUS_MAP: dict[str, TaskStatus] = {
    "PENDING": TaskStatus.PENDING,
    "STARTED": TaskStatus.STARTED,
    "SUCCESS": TaskStatus.SUCCESS,
    "FAILURE": TaskStatus.FAILURE,
    "RETRY": TaskStatus.STARTED,
    "REVOKED": TaskStatus.REVOKED,
}


@router.get("/{task_id}", response_model=TaskStatusResponse)
@limiter.limit(settings.rate_limit_default)
async def get_task_status(request: Request, task_id: str) -> TaskStatusResponse:
    """Poll the status of a background task."""
    result = AsyncResult(task_id, app=celery_app)

    status = _STATUS_MAP.get(result.status, TaskStatus.PENDING)

    task_result = None
    error = None

    if result.successful():
        task_result = SourceIngestResult(**result.result)
    elif result.failed():
        error = str(result.result)

    return TaskStatusResponse(
        task_id=task_id,
        status=status,
        result=task_result,
        error=error,
    )


@router.delete("/{task_id}", response_model=TaskCancelledResponse)
@limiter.limit(settings.rate_limit_default)
async def cancel_task(request: Request, task_id: str) -> TaskCancelledResponse:
    """Cancel a pending or running background task."""
    celery_app.control.revoke(task_id, terminate=True)
    logger.info("task_cancelled", task_id=task_id)
    return TaskCancelledResponse(task_id=task_id)
