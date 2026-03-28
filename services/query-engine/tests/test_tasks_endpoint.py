"""Tests for the task status and cancellation endpoints."""

from unittest.mock import MagicMock, patch

import pytest

from app.models.knowledge_graph import SourceType
from httpx import AsyncClient


@pytest.mark.asyncio
@patch("app.api.v1.tasks.AsyncResult")
async def test_get_task_status_pending(
    mock_async_result: MagicMock, client: AsyncClient
) -> None:
    """Verify pending task returns correct status."""
    instance = MagicMock()
    instance.status = "PENDING"
    instance.successful.return_value = False
    instance.failed.return_value = False
    mock_async_result.return_value = instance

    response = await client.get("/api/v1/tasks/some-id")
    assert response.status_code == 200
    data = response.json()
    assert data["taskId"] == "some-id"
    assert data["status"] == "pending"
    assert data["result"] is None
    assert data["error"] is None


@pytest.mark.asyncio
@patch("app.api.v1.tasks.AsyncResult")
async def test_get_task_status_started(
    mock_async_result: MagicMock, client: AsyncClient
) -> None:
    """Verify started task returns correct status."""
    instance = MagicMock()
    instance.status = "STARTED"
    instance.successful.return_value = False
    instance.failed.return_value = False
    mock_async_result.return_value = instance

    response = await client.get("/api/v1/tasks/some-id")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "started"


@pytest.mark.asyncio
@patch("app.api.v1.tasks.AsyncResult")
async def test_get_task_status_success(
    mock_async_result: MagicMock, client: AsyncClient
) -> None:
    """Verify successful task returns result."""
    instance = MagicMock()
    instance.status = "SUCCESS"
    instance.successful.return_value = True
    instance.failed.return_value = False
    instance.result = {
        "source_type": SourceType.GCS,
        "total_documents": 5,
        "total_triplets": 20,
        "errors": [],
    }
    mock_async_result.return_value = instance

    response = await client.get("/api/v1/tasks/some-id")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["result"]["totalDocuments"] == 5
    assert data["result"]["totalTriplets"] == 20


@pytest.mark.asyncio
@patch("app.api.v1.tasks.AsyncResult")
async def test_get_task_status_failure(
    mock_async_result: MagicMock, client: AsyncClient
) -> None:
    """Verify failed task returns error message."""
    instance = MagicMock()
    instance.status = "FAILURE"
    instance.successful.return_value = False
    instance.failed.return_value = True
    instance.result = Exception("Something went wrong")
    mock_async_result.return_value = instance

    response = await client.get("/api/v1/tasks/some-id")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "failure"
    assert "Something went wrong" in data["error"]


@pytest.mark.asyncio
@patch("app.api.v1.tasks.AsyncResult")
async def test_get_task_status_revoked(
    mock_async_result: MagicMock, client: AsyncClient
) -> None:
    """Verify revoked task returns correct status."""
    instance = MagicMock()
    instance.status = "REVOKED"
    instance.successful.return_value = False
    instance.failed.return_value = False
    mock_async_result.return_value = instance

    response = await client.get("/api/v1/tasks/some-id")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "revoked"


@pytest.mark.asyncio
@patch("app.api.v1.tasks.celery_app")
async def test_cancel_task(mock_celery: MagicMock, client: AsyncClient) -> None:
    """Verify task cancellation calls revoke and returns revoked status."""
    response = await client.delete("/api/v1/tasks/task-to-cancel")
    assert response.status_code == 200
    data = response.json()
    assert data["taskId"] == "task-to-cancel"
    assert data["status"] == "revoked"
    mock_celery.control.revoke.assert_called_once_with(
        "task-to-cancel", terminate=True
    )
