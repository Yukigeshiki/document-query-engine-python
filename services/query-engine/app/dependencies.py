"""FastAPI dependency providers."""

from fastapi import Request

from app.core.errors import ServiceUnavailableError
from app.services.knowledge_graph import KnowledgeGraphService
from app.services.upload import UploadService


def get_kg_service(request: Request) -> KnowledgeGraphService:
    """
    Return the KnowledgeGraphService singleton.

    Raises ServiceUnavailableError if the service has not been initialized.
    """
    service: KnowledgeGraphService | None = getattr(
        request.app.state, "kg_service", None
    )
    if service is None:
        raise ServiceUnavailableError(
            detail="Knowledge graph service is not available"
        )
    return service


def get_optional_kg_service(request: Request) -> KnowledgeGraphService | None:
    """
    Return the KnowledgeGraphService if available, otherwise None.

    Used by the health endpoint which must respond even when the service
    has not been initialized.
    """
    return getattr(request.app.state, "kg_service", None)


def get_upload_service(request: Request) -> UploadService:
    """Return the UploadService singleton."""
    service: UploadService | None = getattr(
        request.app.state, "upload_service", None
    )
    if service is None:
        raise ServiceUnavailableError(
            detail="Upload service is not available"
        )
    return service
