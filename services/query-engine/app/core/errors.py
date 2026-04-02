"""Application-specific exceptions with structured error codes."""


class AppError(Exception):
    """
    Base exception for all application errors.

    Subclass this for domain-specific errors. Each carries an HTTP status
    code, a machine-readable error code, and a human-readable message.
    """

    status_code: int = 500
    error: str = "internal_error"

    def __init__(self, detail: str | None = None) -> None:
        self.detail = detail
        super().__init__(detail or self.error)


class NotFoundError(AppError):
    """Raised when a requested resource does not exist."""

    status_code: int = 404
    error: str = "not_found"


class BadRequestError(AppError):
    """Raised when the request is malformed or invalid."""

    status_code: int = 400
    error: str = "bad_request"


class ConflictError(AppError):
    """Raised when the request conflicts with current state."""

    status_code: int = 409
    error: str = "conflict"


class ServiceUnavailableError(AppError):
    """Raised when a downstream dependency is unreachable."""

    status_code: int = 503
    error: str = "service_unavailable"


class IngestionError(AppError):
    """Raised when document ingestion into the knowledge graph fails."""

    status_code: int = 500
    error: str = "ingestion_error"


class QueryError(AppError):
    """Raised when a knowledge graph query fails."""

    status_code: int = 500
    error: str = "query_error"


class DeletionError(AppError):
    """Raised when document deletion from the knowledge graph fails."""

    status_code: int = 500
    error: str = "deletion_error"


class ConnectorError(AppError):
    """Raised when a document connector fails to load documents."""

    status_code: int = 502
    error: str = "connector_error"
