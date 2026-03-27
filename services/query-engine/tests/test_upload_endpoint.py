"""Tests for the file upload ingestion endpoint."""

from collections.abc import AsyncIterator
from io import BytesIO
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.dependencies import get_kg_service, get_upload_service
from app.main import create_app
from app.models.knowledge_graph import SourceType


@pytest.fixture
def mock_upload_service() -> AsyncMock:
    """Create a mock UploadService."""
    service = AsyncMock()
    service.save.return_value = (SourceType.FILESYSTEM, {"path": "/tmp/uploads/abc"})
    return service


@pytest.fixture
async def upload_client(mock_upload_service: AsyncMock) -> AsyncIterator[AsyncClient]:
    """Provide an async HTTP client with mocked services."""
    app = create_app()
    app.dependency_overrides[get_kg_service] = lambda: AsyncMock()
    app.dependency_overrides[get_upload_service] = lambda: mock_upload_service
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac


@pytest.mark.asyncio
@patch("app.api.v1.knowledge_graph.ingest_source_task")
async def test_upload_txt_file(
    mock_task: MagicMock,
    upload_client: AsyncClient,
    mock_upload_service: AsyncMock,
) -> None:
    """Verify uploading a .txt file returns 202 with a task ID."""
    mock_result = MagicMock()
    mock_result.id = "upload-task-123"
    mock_task.delay.return_value = mock_result

    response = await upload_client.post(
        "/api/v1/kg/ingest/upload",
        files={"file": ("test.txt", BytesIO(b"Hello world"), "text/plain")},
    )
    assert response.status_code == 202
    data = response.json()
    assert data["taskId"] == "upload-task-123"
    mock_upload_service.save.assert_called_once()
    mock_task.delay.assert_called_once_with(
        source_type="filesystem",
        config={"path": "/tmp/uploads/abc"},
    )


@pytest.mark.asyncio
@patch("app.api.v1.knowledge_graph.ingest_source_task")
async def test_upload_pdf_accepted(
    mock_task: MagicMock,
    upload_client: AsyncClient,
) -> None:
    """Verify uploading a .pdf file is accepted."""
    mock_result = MagicMock()
    mock_result.id = "pdf-task-456"
    mock_task.delay.return_value = mock_result

    response = await upload_client.post(
        "/api/v1/kg/ingest/upload",
        files={"file": ("report.pdf", BytesIO(b"%PDF-1.4"), "application/pdf")},
    )
    assert response.status_code == 202


@pytest.mark.asyncio
async def test_upload_unsupported_extension() -> None:
    """Verify 400 for unsupported file types."""
    from app.core.errors import BadRequestError

    mock_svc = AsyncMock()
    mock_svc.save.side_effect = BadRequestError(detail="Unsupported file type '.jpg'")

    app = create_app()
    app.dependency_overrides[get_kg_service] = lambda: AsyncMock()
    app.dependency_overrides[get_upload_service] = lambda: mock_svc

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        response = await ac.post(
            "/api/v1/kg/ingest/upload",
            files={"file": ("photo.jpg", BytesIO(b"\xff\xd8"), "image/jpeg")},
        )
    assert response.status_code == 400
    assert "Unsupported" in response.json()["detail"]


@pytest.mark.asyncio
async def test_upload_no_file(upload_client: AsyncClient) -> None:
    """Verify 422 when no file is provided."""
    response = await upload_client.post("/api/v1/kg/ingest/upload")
    assert response.status_code == 422
