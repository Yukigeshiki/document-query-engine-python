"""Upload service for saving files to local storage or GCS."""

import asyncio
import uuid
from pathlib import Path
from typing import Any

import structlog
from fastapi import UploadFile
from google.cloud import storage as gcs_storage  # type: ignore[import-untyped]

from app.connectors import SUPPORTED_EXTENSIONS
from app.core.config import Settings
from app.core.errors import BadRequestError, ConnectorError
from app.models.knowledge_graph import SourceType

logger = structlog.stdlib.get_logger(__name__)
UPLOADS_SUBDIR = "uploads"
CHUNK_SIZE = 64 * 1024  # 64KB chunks for streaming
MAX_UPLOAD_SIZE = 20 * 1024 * 1024  # 20MB
VALID_STORAGE_TYPES = {"local", "gcs"}


class UploadService:
    """Saves uploaded files to local disk or GCS and returns connector config."""

    def __init__(self, config: Settings) -> None:
        if config.upload_storage not in VALID_STORAGE_TYPES:
            raise ValueError(
                f"Invalid upload_storage '{config.upload_storage}'. "
                f"Must be one of: {', '.join(sorted(VALID_STORAGE_TYPES))}"
            )
        self._storage = config.upload_storage
        self._gcs_bucket = config.gcs_bucket
        self._gcs_credentials_path = config.gcs_credentials_path
        self._local_upload_dir = Path(config.data_dir) / UPLOADS_SUBDIR

    async def save(self, file: UploadFile) -> tuple[SourceType, dict[str, Any]]:
        """
        Save an uploaded file and return the connector config for ingestion.

        Streams the file to disk or GCS in chunks to avoid loading
        the entire file into memory. Enforces a 20MB size limit.

        Returns (source_type, config) suitable for ingest_source_task.
        """
        raw_filename = file.filename or "document"
        filename = Path(raw_filename).name
        ext = Path(filename).suffix.lower()

        if ext not in SUPPORTED_EXTENSIONS:
            supported = ", ".join(sorted(SUPPORTED_EXTENSIONS))
            raise BadRequestError(
                detail=f"Unsupported file type '{ext}'. Supported: {supported}"
            )

        upload_id = str(uuid.uuid4())

        if self._storage == "gcs":
            return await self._save_to_gcs(upload_id, filename, file)
        return await self._save_to_local(upload_id, filename, file)

    async def _save_to_local(
        self, upload_id: str, filename: str, file: UploadFile
    ) -> tuple[SourceType, dict[str, Any]]:
        """Stream file to local disk in chunks."""
        subdir = self._local_upload_dir / upload_id
        subdir.mkdir(parents=True, exist_ok=True)
        file_path = subdir / filename

        total_size = 0
        with file_path.open("wb") as f:
            while chunk := await file.read(CHUNK_SIZE):
                total_size += len(chunk)
                if total_size > MAX_UPLOAD_SIZE:
                    file_path.unlink(missing_ok=True)
                    raise BadRequestError(
                        detail=f"File exceeds maximum size of {MAX_UPLOAD_SIZE // (1024 * 1024)}MB"
                    )
                f.write(chunk)

        logger.info(
            "file_saved_locally",
            upload_id=upload_id,
            path=str(file_path),
            size=total_size,
        )
        # Return relative path so the worker resolves against its own DATA_DIR
        return SourceType.FILESYSTEM, {"path": f"{UPLOADS_SUBDIR}/{upload_id}"}

    async def _save_to_gcs(
        self, upload_id: str, filename: str, file: UploadFile
    ) -> tuple[SourceType, dict[str, Any]]:
        """Stream file to GCS."""
        if not self._gcs_bucket:
            raise ConnectorError(detail="GCS bucket not configured for uploads")

        gcs_path = f"{UPLOADS_SUBDIR}/{upload_id}/{filename}"

        # Read with size check, then upload in executor
        chunks: list[bytes] = []
        total_size = 0
        while chunk := await file.read(CHUNK_SIZE):
            total_size += len(chunk)
            if total_size > MAX_UPLOAD_SIZE:
                raise BadRequestError(
                    detail=f"File exceeds maximum size of {MAX_UPLOAD_SIZE // (1024 * 1024)}MB"
                )
            chunks.append(chunk)

        content = b"".join(chunks)
        loop = asyncio.get_running_loop()

        def _upload() -> None:
            if self._gcs_credentials_path:
                client = gcs_storage.Client.from_service_account_json(
                    self._gcs_credentials_path
                )
            else:
                client = gcs_storage.Client()
            bucket = client.bucket(self._gcs_bucket)
            blob = bucket.blob(gcs_path)
            blob.upload_from_string(content)

        try:
            await loop.run_in_executor(None, _upload)
        except (BadRequestError, ConnectorError):
            raise
        except Exception as exc:
            raise ConnectorError(
                detail=f"Failed to upload to GCS: {exc}"
            ) from exc

        logger.info(
            "file_saved_to_gcs",
            upload_id=upload_id,
            bucket=self._gcs_bucket,
            path=gcs_path,
            size=total_size,
        )
        return SourceType.GCS, {
            "bucket": self._gcs_bucket,
            "prefix": f"{UPLOADS_SUBDIR}/{upload_id}/",
        }
