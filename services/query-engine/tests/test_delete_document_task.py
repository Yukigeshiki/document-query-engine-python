"""Tests for the Celery delete document task."""

from unittest.mock import AsyncMock, MagicMock, patch

from app.core.errors import NotFoundError
from app.worker.tasks import delete_document_task


@patch("app.worker.tasks._get_kg_service")
def test_delete_document_task_returns_deleted_ids(
    mock_get_service: MagicMock,
) -> None:
    """Verify task calls service and returns the deleted doc_ids."""
    mock_service = AsyncMock()
    mock_service.delete_document.return_value = ["doc-1", "doc-1-chunk-2"]
    mock_get_service.return_value = mock_service

    result = delete_document_task(doc_id="doc-1")

    assert result["task_type"] == "delete_document"
    assert result["doc_id"] == "doc-1"
    assert result["deleted_doc_ids"] == ["doc-1", "doc-1-chunk-2"]
    mock_service.delete_document.assert_called_once_with(doc_id="doc-1")


@patch("app.worker.tasks._get_kg_service")
def test_delete_document_task_treats_not_found_as_idempotent_success(
    mock_get_service: MagicMock,
) -> None:
    """A NotFoundError must be reported as success with empty deleted_doc_ids.

    This is the regression test for the P2 fix: with task_acks_late enabled,
    a worker crash after the delete completes but before the ACK causes the
    broker to redeliver the task. On the second run the document is already
    gone and the service raises NotFoundError. We treat this as idempotent
    success so the user-visible task state is SUCCESS, not FAILURE.
    """
    mock_service = AsyncMock()
    mock_service.delete_document.side_effect = NotFoundError(
        detail="Document doc-1 not found"
    )
    mock_get_service.return_value = mock_service

    result = delete_document_task(doc_id="doc-1")

    assert result["task_type"] == "delete_document"
    assert result["doc_id"] == "doc-1"
    assert result["deleted_doc_ids"] == []


@patch("app.worker.tasks._get_kg_service")
def test_delete_document_task_propagates_other_errors(
    mock_get_service: MagicMock,
) -> None:
    """Non-NotFoundError exceptions must propagate so Celery autoretry kicks in."""
    mock_service = AsyncMock()
    mock_service.delete_document.side_effect = RuntimeError("transient db error")
    mock_get_service.return_value = mock_service

    try:
        delete_document_task(doc_id="doc-1")
    except RuntimeError as exc:
        assert "transient db error" in str(exc)
    else:
        raise AssertionError("expected RuntimeError to propagate")
