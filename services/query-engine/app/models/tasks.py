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


class SourceIngestResult(CamelModel):
    """Result payload from a completed source ingestion task."""

    source_type: str
    total_documents: int
    total_triplets: int
    errors: list[str] = Field(default_factory=list)


class TaskStatusResponse(CamelModel):
    """Response for a task status poll."""

    task_id: str
    status: TaskStatus
    result: SourceIngestResult | None = Field(default=None)
    error: str | None = Field(default=None)


class TaskCancelledResponse(CamelModel):
    """Response when a task is cancelled."""

    task_id: str
    status: TaskStatus = TaskStatus.REVOKED


class SourceIngestAcceptedResponse(CamelModel):
    """Response when a bulk ingestion task is accepted."""

    task_id: str
