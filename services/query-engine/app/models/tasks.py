"""Task status models for background processing."""

from enum import StrEnum

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

    task_type: str = "ingest_source"
    source_type: str
    total_documents: int
    total_triplets: int
    errors: list[str] = Field(default_factory=list)


class DeleteDocumentResult(CamelModel):
    """Result payload from a completed document deletion task."""

    task_type: str = "delete_document"
    doc_id: str
    deleted_doc_ids: list[str] = Field(default_factory=list)


class TaskStatusResponse(CamelModel):
    """Response for a task status poll."""

    task_id: str
    status: TaskStatus
    result: SourceIngestResult | DeleteDocumentResult | None = Field(default=None)
    error: str | None = Field(default=None)


class TaskCancelledResponse(CamelModel):
    """Response when a task is cancelled."""

    task_id: str
    status: TaskStatus = TaskStatus.REVOKED


class TaskAcceptedResponse(CamelModel):
    """Response when a background task is accepted."""

    task_id: str
