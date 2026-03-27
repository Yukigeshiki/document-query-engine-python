"""Task status models for background processing."""

from enum import StrEnum
from typing import Any

from pydantic import Field

from app.models import CamelModel


class TaskStatus(StrEnum):
    """Possible states of a background task."""

    PENDING = "pending"
    STARTED = "started"
    SUCCESS = "success"
    FAILURE = "failure"
    REVOKED = "revoked"


class TaskStatusResponse(CamelModel):
    """Response for a task status poll."""

    task_id: str
    status: TaskStatus
    result: dict[str, Any] | None = Field(default=None)
    error: str | None = Field(default=None)


class TaskCancelledResponse(CamelModel):
    """Response when a task is cancelled."""

    task_id: str
    status: TaskStatus = TaskStatus.REVOKED


class SourceIngestAcceptedResponse(CamelModel):
    """Response when a bulk ingestion task is accepted."""

    task_id: str
