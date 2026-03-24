"""Application-specific exceptions with structured error codes."""


class AppException(Exception):
    """Base exception for all application errors.

    Subclass this for domain-specific errors. Each carries an HTTP status
    code, a machine-readable error code, and a human-readable message.
    """

    status_code: int = 500
    error: str = "internal_error"

    def __init__(self, detail: str | None = None) -> None:
        self.detail = detail
        super().__init__(detail or self.error)


class NotFoundException(AppException):
    """Raised when a requested resource does not exist."""

    status_code: int = 404
    error: str = "not_found"


class BadRequestException(AppException):
    """Raised when the request is malformed or invalid."""

    status_code: int = 400
    error: str = "bad_request"


class ConflictException(AppException):
    """Raised when the request conflicts with current state."""

    status_code: int = 409
    error: str = "conflict"


class ServiceUnavailableException(AppException):
    """Raised when a downstream dependency is unreachable."""

    status_code: int = 503
    error: str = "service_unavailable"
